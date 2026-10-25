import io
import os
import signal
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.managers.mgr_steam import SteamManager
from backend.managers.mgr_steamcmd_core import SteamCMDController, prepare_steamcmd_env

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Linux 版 SteamCMD 的目录布局与进程组")


def _linux(monkeypatch):
    monkeypatch.setattr("backend.managers.mgr_steamcmd_core.sys.platform", "linux")


def test_prepare_env_points_private_home_steam_back_to_steamcmd_dir(monkeypatch, tmp_path):
    _linux(monkeypatch)

    env = prepare_steamcmd_env({"HOME": "/home/real", "PATH": "/usr/bin"}, str(tmp_path))

    # Linux 版 SteamCMD 把内容和日志写到 $HOME/Steam；链回自身目录后与 Windows 布局一致。
    private_home = Path(env["HOME"])
    assert private_home.parent == tmp_path
    assert (private_home / "Steam").is_symlink()
    assert (private_home / "Steam").resolve() == tmp_path.resolve()
    assert env["PATH"] == "/usr/bin"


def test_prepare_env_repairs_stale_steam_link(monkeypatch, tmp_path):
    _linux(monkeypatch)
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    steamcmd_dir = tmp_path / "steamcmd"
    steamcmd_dir.mkdir()
    prepare_steamcmd_env({}, str(old_dir))
    stale_home = old_dir / ".home"
    stale_home.rename(steamcmd_dir / ".home")

    env = prepare_steamcmd_env({}, str(steamcmd_dir))

    assert (Path(env["HOME"]) / "Steam").resolve() == steamcmd_dir.resolve()


def test_clean_corrupted_init_keeps_linux_bootstrap(monkeypatch, tmp_path):
    _linux(monkeypatch)
    for name in ("steamcmd.sh", "update_hosts_cached.vdf"):
        (tmp_path / name).write_text("", encoding="utf-8")
    for name in ("linux32", "linux64", "package", "public"):
        (tmp_path / name).mkdir()
    (tmp_path / "linux32" / "steamcmd").write_text("", encoding="utf-8")

    SteamCMDController(str(tmp_path / "steamcmd.sh"))._clean_corrupted_init()

    # steamcmd.sh 只是包装脚本，真正的引导程序在 linux32 里，删掉后只能重新下载。
    assert sorted(item.name for item in tmp_path.iterdir()) == ["linux32", "steamcmd.sh"]
    assert (tmp_path / "linux32" / "steamcmd").exists()


def test_run_and_monitor_starts_steamcmd_in_its_own_session(monkeypatch, tmp_path):
    _linux(monkeypatch)
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(pid=1234, stdout=io.StringIO(""), returncode=0, wait=lambda: 0)

    monkeypatch.setattr("backend.managers.mgr_steamcmd_core.subprocess.Popen", fake_popen)
    controller = SteamCMDController(str(tmp_path / "steamcmd.sh"))

    ok, _ = controller._run_and_monitor([str(tmp_path / "steamcmd.sh"), "+quit"], "初始化", timeout=1)

    assert ok is True
    # 超时或取消时按进程组终止；不新建会话的话，进程组就是 RimCrow 自己。
    assert captured["start_new_session"] is True
    assert captured["env"]["HOME"] == str(tmp_path / ".home")


def test_terminate_steamcmd_process_kills_whole_process_group(monkeypatch):
    monkeypatch.setattr("backend.managers.mgr_steam.platform.system", lambda: "Linux")
    killpg = Mock()
    monkeypatch.setattr("backend.managers.mgr_steam.os.killpg", killpg)
    monkeypatch.setattr("backend.managers.mgr_steam.os.getpgid", lambda pid: pid)
    manager = object.__new__(SteamManager)
    manager._steamcmd_lock = threading.Lock()
    process = Mock(spec=subprocess.Popen, pid=4321)

    manager._terminate_steamcmd_process("task-a", process)

    # steamcmd.sh 不 exec，只杀包装脚本会留下 linux32/steamcmd 继续下载。
    killpg.assert_called_once_with(4321, signal.SIGKILL)
    process.kill.assert_not_called()
