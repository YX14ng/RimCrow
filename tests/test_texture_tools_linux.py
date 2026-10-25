import os
import stat
from unittest.mock import patch

import pytest

from backend.managers.mgr_files import PathChecker
from backend.managers.mgr_github import GithubInstallRequest
from backend.managers.mgr_texture_opt import TODDS_LINUX_ASSET_PREFIX, ToddsEncoder, TextureOptimizationManager

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Linux 版 todds 的可执行位")


def _linux(monkeypatch):
    monkeypatch.setattr("backend.managers.mgr_texture_opt.platform.system", lambda: "Linux")
    monkeypatch.setattr("backend.managers.mgr_texture_opt.platform.machine", lambda: "x86_64")


def test_resolve_executable_finds_linux_todds_and_restores_exec_bit(monkeypatch, tmp_path):
    _linux(monkeypatch)
    todds = tmp_path / "todds"
    todds.write_bytes(b"\x7fELF")
    todds.chmod(0o644)

    resolved = ToddsEncoder({"texture_tools_path": str(tmp_path)}).resolve_executable()

    assert resolved == todds
    # 解压 zip 不保留可执行位，否则 Popen 会报 PermissionError。
    assert todds.stat().st_mode & stat.S_IXUSR


def test_resolve_executable_accepts_todds_file_selected_directly(monkeypatch, tmp_path):
    _linux(monkeypatch)
    todds = tmp_path / "todds"
    todds.write_bytes(b"\x7fELF")
    todds.chmod(0o755)

    assert ToddsEncoder({"texture_tools_path": str(todds)}).resolve_executable() == todds


def test_prepare_tool_download_uses_linux_release_asset(monkeypatch, tmp_path):
    _linux(monkeypatch)
    captured: dict[str, GithubInstallRequest] = {}

    def fake_install(_self, _download_mgr, request):
        captured["request"] = request
        return "task-1"

    manager = TextureOptimizationManager()
    with patch.object(TextureOptimizationManager, "get_backend_status", return_value={"available": False}), \
         patch("backend.managers.mgr_github.GithubManager.install_from_github", new=fake_install):
        result = manager.prepare_tool_download(object(), {"texture_tools_path": str(tmp_path / "texture_tools")})

    artifact = captured["request"].artifact
    assert result == {"already_ready": False}
    assert artifact.asset_name_prefix == TODDS_LINUX_ASSET_PREFIX
    assert artifact.fallback_filename == "todds_Linux_x86_64_0.4.1.zip"


def test_check_texture_tools_path_accepts_linux_todds(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.managers.mgr_files.platform.system", lambda: "Linux")
    (tmp_path / "todds").write_bytes(b"\x7fELF")

    result = PathChecker.check_texture_tools_path(str(tmp_path))

    assert result["pass"] is True
