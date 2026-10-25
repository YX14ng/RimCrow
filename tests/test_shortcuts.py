import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.managers.mgr_files import FileManager
from backend.utils.shortcuts import create_shortcut


class TestShortcutHelpers(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.desktop_dir = self.temp_dir / "Desktop"
        self.desktop_dir.mkdir(parents=True, exist_ok=True)
        self.target_path = self.temp_dir / "RimWorld"
        self.target_path.write_text("echo shortcut", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _profile(self):
        return SimpleNamespace(
            id="demo",
            name="Demo Profile",
            game_install_path=str(self.temp_dir),
        )

    @patch("backend.utils.shortcuts.platform.system", return_value="Linux")
    @patch("backend.managers.mgr_files.get_desktop_directory")
    @patch("backend.managers.mgr_files.GameManager.detect_executable")
    def test_build_profile_shortcut_spec_uses_linux_desktop_launcher(
        self,
        detect_executable,
        get_desktop_directory,
        _platform_system,
    ):
        detect_executable.return_value = str(self.target_path)
        get_desktop_directory.return_value = str(self.desktop_dir)

        spec = FileManager.build_profile_shortcut_spec(
            profile=self._profile(),
            extra_args=["--profile", "hello world"],
        )

        self.assertEqual(spec["shortcut_kind"], "desktop")
        self.assertTrue(spec["shortcut_path"].endswith(".desktop"))
        self.assertIn("'hello world'", spec["arguments"])

    @patch("backend.utils.shortcuts.platform.system", return_value="Darwin")
    @patch("backend.managers.mgr_files.get_desktop_directory")
    @patch("backend.managers.mgr_files.GameManager.detect_executable")
    def test_build_profile_shortcut_spec_uses_macos_command_launcher(
        self,
        detect_executable,
        get_desktop_directory,
        _platform_system,
    ):
        detect_executable.return_value = str(self.target_path)
        get_desktop_directory.return_value = str(self.desktop_dir)

        spec = FileManager.build_profile_shortcut_spec(profile=self._profile())

        self.assertEqual(spec["shortcut_kind"], "command")
        self.assertTrue(spec["shortcut_path"].endswith(".command"))

    @patch("backend.utils.shortcuts.platform.system", return_value="Linux")
    def test_create_shortcut_writes_linux_desktop_file(self, _platform_system):
        shortcut_path = self.desktop_dir / "Demo.desktop"
        result = create_shortcut(
            {
                "shortcut_path": str(shortcut_path),
                "target_path": str(self.target_path),
                "arguments": "--browser",
                "working_directory": str(self.temp_dir),
                "icon_location": str(self.target_path),
                "description": "Linux launcher",
                "shortcut_kind": "desktop",
            }
        )

        content = shortcut_path.read_text(encoding="utf-8")
        self.assertEqual(result["shortcut_kind"], "desktop")
        self.assertIn("Exec=", content)
        self.assertIn("Terminal=false", content)
        self.assertTrue(os.access(shortcut_path, os.X_OK))

    @patch("backend.utils.shortcuts.platform.system", return_value="Linux")
    def test_linux_desktop_exec_follows_desktop_entry_quoting(self, _platform_system):
        shortcut_path = self.desktop_dir / "Quoted.desktop"
        create_shortcut(
            {
                "shortcut_path": str(shortcut_path),
                "target_path": str(self.target_path),
                "arguments": "'-savedatafolder=/tmp/my profile' 100% '$HOME' 'a\\b'",
                "environment": {"LC_ALL": "C"},
                "shortcut_kind": "desktop",
            }
        )

        exec_line = next(line for line in shortcut_path.read_text(encoding="utf-8").splitlines() if line.startswith("Exec="))
        # Desktop Entry 规范：保留字符用双引号，% 写成 %%，引号内的反斜杠还要再按字符串规则转义一次。
        self.assertEqual(
            exec_line,
            f'Exec=env LC_ALL=C {self.target_path} "-savedatafolder=/tmp/my profile" 100%% "\\\\$HOME" "a\\\\\\\\b"',
        )

    @patch("backend.utils.shortcuts.platform.system", return_value="Linux")
    def test_linux_desktop_file_cannot_be_split_by_newlines(self, _platform_system):
        shortcut_path = self.desktop_dir / "Injected.desktop"
        create_shortcut(
            {
                "shortcut_path": str(shortcut_path),
                "target_path": str(self.target_path),
                # 导入的数据包里的启动参数和环境名都可能带换行，不能借此多写一行 Exec=。
                "arguments": "'-x\nExec=sh -c \"echo PWNED\" #'",
                "description": "环境\nExec=sh -c 'echo PWNED'",
                "shortcut_kind": "desktop",
            }
        )

        lines = shortcut_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sum(1 for line in lines if line.startswith("Exec=")), 1)
        self.assertIn("\\n", next(line for line in lines if line.startswith("Exec=")))
        self.assertEqual(next(line for line in lines if line.startswith("Comment=")), "Comment=环境 Exec=sh -c 'echo PWNED'")

    @patch("backend.utils.shortcuts.platform.system", return_value="Linux")
    def test_linux_desktop_env_prefix_handles_target_path_with_equals(self, _platform_system):
        target_dir = self.temp_dir / "a=b"
        target_dir.mkdir()
        target = target_dir / "RimWorldLinux"
        target.write_text("", encoding="utf-8")
        shortcut_path = self.desktop_dir / "Equals.desktop"
        create_shortcut(
            {
                "shortcut_path": str(shortcut_path),
                "target_path": str(target),
                "environment": {"LC_ALL": "C"},
                "shortcut_kind": "desktop",
            }
        )

        exec_line = next(line for line in shortcut_path.read_text(encoding="utf-8").splitlines() if line.startswith("Exec="))
        # env 会把带 = 的路径当成变量赋值；这时要经由 sh 再 exec 目标。
        self.assertIn("sh -c", exec_line)
        self.assertIn(str(target), exec_line)

    @patch("backend.utils.shortcuts.platform.system", return_value="Linux")
    @patch("backend.managers.mgr_files.platform.system", return_value="Linux")
    @patch("backend.managers.mgr_files.get_desktop_directory")
    @patch("backend.managers.mgr_files.GameManager.detect_executable")
    def test_linux_direct_profile_shortcut_uses_c_locale_and_game_icon(
        self,
        detect_executable,
        get_desktop_directory,
        _files_platform,
        _platform_system,
    ):
        game_exe = self.temp_dir / "RimWorldLinux"
        game_exe.write_text("", encoding="utf-8")
        icon = self.temp_dir / "RimWorldLinux_Data" / "Resources" / "UnityPlayer.png"
        icon.parent.mkdir(parents=True)
        icon.write_bytes(b"png")
        detect_executable.return_value = str(game_exe)
        get_desktop_directory.return_value = str(self.desktop_dir)

        spec = FileManager.build_profile_shortcut_spec(profile=self._profile())

        # 直接启动要和 start_RimWorld.sh 一样带 LC_ALL=C；图标用游戏自带的 PNG，而不是可执行文件。
        self.assertEqual(spec["environment"], {"LC_ALL": "C"})
        self.assertEqual(spec["icon_location"], str(icon))

    @patch("backend.utils.shortcuts.platform.system", return_value="Darwin")
    def test_create_shortcut_writes_macos_command_file(self, _platform_system):
        shortcut_path = self.desktop_dir / "Demo.command"
        result = create_shortcut(
            {
                "shortcut_path": str(shortcut_path),
                "target_path": str(self.target_path),
                "arguments": "--browser",
                "working_directory": str(self.temp_dir),
                "shortcut_kind": "command",
            }
        )

        content = shortcut_path.read_text(encoding="utf-8")
        self.assertEqual(result["shortcut_kind"], "command")
        self.assertIn("#!/bin/sh", content)
        self.assertIn("exec", content)
        self.assertTrue(os.access(shortcut_path, os.X_OK))

    def test_ensure_browser_mode_shortcut_only_creates_when_missing(self):
        shortcut_path = self.temp_dir / "Browser mode.lnk"
        spec = {
            "shortcut_path": str(shortcut_path),
            "target_path": str(self.target_path),
            "shortcut_kind": "lnk",
        }

        with (
            patch.object(FileManager, "build_browser_mode_shortcut_spec", return_value=spec),
            patch("backend.managers.mgr_files.create_shortcut", return_value={**spec, "arguments": "--browser"}) as create_shortcut_mock,
        ):
            missing_result = FileManager.ensure_browser_mode_shortcut(str(self.target_path))
            self.assertTrue(missing_result["changed"])
            create_shortcut_mock.assert_called_once_with(spec)

            shortcut_path.write_text("exists", encoding="utf-8")
            existing_result = FileManager.ensure_browser_mode_shortcut(str(self.target_path))
            self.assertFalse(existing_result["changed"])
            self.assertEqual(create_shortcut_mock.call_count, 1)

    def test_ensure_browser_mode_shortcut_removes_legacy_rimmodmanager_entries(self):
        current_exe = self.temp_dir / "RimCrow.exe"
        current_exe.write_text("current", encoding="utf-8")
        legacy_exe = self.temp_dir / "RimModManager.exe"
        legacy_exe.write_text("legacy", encoding="utf-8")
        legacy_shortcut = self.temp_dir / "RimModManager [Browser mode].lnk"
        legacy_shortcut.write_text("legacy shortcut", encoding="utf-8")
        shortcut_path = self.temp_dir / "RimCrow [Browser mode].lnk"
        spec = {
            "shortcut_path": str(shortcut_path),
            "target_path": str(current_exe),
            "shortcut_kind": "lnk",
        }

        with (
            patch.object(FileManager, "build_browser_mode_shortcut_spec", return_value=spec),
            patch("backend.managers.mgr_files.create_shortcut", return_value={**spec, "arguments": "--browser"}),
        ):
            FileManager.ensure_browser_mode_shortcut(str(current_exe))

        self.assertFalse(legacy_exe.exists())
        self.assertFalse(legacy_shortcut.exists())


if __name__ == "__main__":
    unittest.main()
