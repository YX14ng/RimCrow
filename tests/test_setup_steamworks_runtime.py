import importlib.util
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "setup_steamworks_runtime.py"
_spec = importlib.util.spec_from_file_location("setup_steamworks_runtime", _SCRIPT)
setup_steamworks_runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(setup_steamworks_runtime)


def _write_sdk_zip(path: Path, extra: dict[str, str] | None = None) -> Path:
    entries = {
        "sdk/public/steam/steam_api.h": "// api",
        "sdk/public/steam/isteamugc.h": "// ugc",
        "sdk/redistributable_bin/linux64/libsteam_api.so": "ELF",
        **(extra or {}),
    }
    with ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return path


def test_build_linux_steamworkspy_compiles_against_sdk_headers(tmp_path):
    sdk_zip = _write_sdk_zip(tmp_path / "steamworks_sdk.zip")
    source_dir = tmp_path / "library"
    source_dir.mkdir()
    (source_dir / "SteamworksPy.cpp").write_text("// wrapper", encoding="utf-8")
    runtime_dir = tmp_path / "runtime"
    seen = {}

    def fake_run(cmd, cwd, check):
        build_dir = Path(cwd)
        seen["cmd"] = cmd
        seen["headers"] = sorted(path.name for path in (build_dir / "sdk" / "steam").iterdir())
        seen["has_lib"] = (build_dir / "libsteam_api.so").is_file()
        (build_dir / "SteamworksPy.so").write_text("built", encoding="utf-8")

    with patch.object(setup_steamworks_runtime.shutil, "which", return_value="/usr/bin/g++"), \
         patch.object(setup_steamworks_runtime.subprocess, "run", side_effect=fake_run):
        output = setup_steamworks_runtime.build_linux_steamworkspy(sdk_zip, runtime_dir, source_dir=source_dir)

    assert output == runtime_dir / "SteamworksPy.so"
    assert output.read_text(encoding="utf-8") == "built"
    # SteamworksPy.cpp 用 "sdk/steam/steam_api.h" 引用头文件，链接时要能找到同目录的 libsteam_api.so。
    assert seen["headers"] == ["isteamugc.h", "steam_api.h"]
    assert seen["has_lib"] is True
    assert seen["cmd"][0] == "/usr/bin/g++"
    assert {"-shared", "-fPIC", "-lsteam_api", "-Wl,-rpath,$ORIGIN"} <= set(seen["cmd"])


def test_build_linux_steamworkspy_rejects_header_paths_outside_build_dir(tmp_path):
    sdk_zip = _write_sdk_zip(tmp_path / "steamworks_sdk.zip", {"sdk/public/steam/../../evil.h": "x"})
    source_dir = tmp_path / "library"
    source_dir.mkdir()
    (source_dir / "SteamworksPy.cpp").write_text("// wrapper", encoding="utf-8")

    with patch.object(setup_steamworks_runtime.shutil, "which", return_value="/usr/bin/g++"), \
         patch.object(setup_steamworks_runtime.subprocess, "run") as run, \
         pytest.raises(ValueError):
        setup_steamworks_runtime.build_linux_steamworkspy(sdk_zip, tmp_path / "runtime", source_dir=source_dir)

    run.assert_not_called()


def test_build_linux_steamworkspy_requires_compiler(tmp_path):
    with patch.object(setup_steamworks_runtime.shutil, "which", return_value=None), \
         pytest.raises(FileNotFoundError, match="g\\+\\+"):
        setup_steamworks_runtime.build_linux_steamworkspy(tmp_path / "sdk.zip", tmp_path / "runtime")
