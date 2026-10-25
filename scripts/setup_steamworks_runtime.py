from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = ROOT_DIR / "tools" / "steamworks"
DEFAULT_SUBMODULE_DIR = ROOT_DIR / "submodules" / "SteamworksPy"

SDK_FILES = {
    "windows": {
        "sdk/redistributable_bin/win64/steam_api64.dll": "steam_api64.dll",
        "sdk/redistributable_bin/win64/steam_api64.lib": "steam_api64.lib",
    },
    "linux": {
        "sdk/redistributable_bin/linux64/libsteam_api.so": "libsteam_api.so",
    },
    "darwin": {
        "sdk/redistributable_bin/osx/libsteam_api.dylib": "libsteam_api.dylib",
    },
}

STEAMWORKSPY_FILES = {
    "windows": {
        "SteamworksPy64.dll": [
            DEFAULT_SUBMODULE_DIR / "redist" / "windows" / "SteamworksPy64.dll",
            DEFAULT_SUBMODULE_DIR / "library" / "SteamworksPy64.dll",
        ],
    },
    "linux": {
        "SteamworksPy.so": [
            DEFAULT_SUBMODULE_DIR / "library" / "SteamworksPy.so",
            DEFAULT_SUBMODULE_DIR / "library" / "SteamworksPy_x86_64.so",
        ],
    },
    "darwin": {
        "SteamworksPy.dylib": [
            DEFAULT_SUBMODULE_DIR / "library" / "SteamworksPy.dylib",
            DEFAULT_SUBMODULE_DIR / "library" / "SteamworksPy_x86_64.dylib",
            DEFAULT_SUBMODULE_DIR / "library" / "SteamworksPy_arm.dylib",
        ],
    },
}


SDK_HEADER_PREFIX = "sdk/public/steam/"
LINUX_SDK_LIBRARY = "sdk/redistributable_bin/linux64/libsteam_api.so"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_sdk_path(raw_path: str) -> Path:
    candidates = [
        Path(raw_path).expanduser() if raw_path else None,
        Path(os.environ.get("STEAMWORKS_SDK_ZIP", "")).expanduser() if os.environ.get("STEAMWORKS_SDK_ZIP") else None,
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("未找到 Steamworks SDK zip，请用 --sdk 指定路径，或设置 STEAMWORKS_SDK_ZIP")


def extract_sdk_files(sdk_path: Path, runtime_dir: Path) -> list[Path]:
    copied: list[Path] = []
    runtime_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(sdk_path) as archive:
        names = set(archive.namelist())
        for files in SDK_FILES.values():
            for source_name, target_name in files.items():
                if source_name not in names:
                    raise FileNotFoundError(f"SDK zip 缺少必要文件: {source_name}")
                target_path = runtime_dir / target_name
                with archive.open(source_name) as source, target_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
                copied.append(target_path)
    return copied


def copy_steamworkspy_files(runtime_dir: Path) -> tuple[list[Path], list[str]]:
    copied: list[Path] = []
    missing: list[str] = []
    runtime_dir.mkdir(parents=True, exist_ok=True)
    for platform_name, files in STEAMWORKSPY_FILES.items():
        for target_name, candidates in files.items():
            source_path = next((path for path in candidates if path.is_file()), None)
            if not source_path:
                missing.append(f"{platform_name}/{target_name}")
                continue
            target_path = runtime_dir / target_name
            shutil.copy2(source_path, target_path)
            copied.append(target_path)
    return copied, missing


def build_linux_steamworkspy(sdk_path: Path, runtime_dir: Path, source_dir: Path = DEFAULT_SUBMODULE_DIR / "library") -> Path:
    """上游只提供 Windows 预编译版；Linux 下用 SDK 头文件和 libsteam_api.so 现场编译 SteamworksPy.so。"""
    compiler = shutil.which("g++")
    if not compiler:
        raise FileNotFoundError("未找到 g++，无法编译 SteamworksPy.so")
    source_file = source_dir / "SteamworksPy.cpp"
    if not source_file.is_file():
        raise FileNotFoundError(f"未找到 {source_file}，请先执行 git submodule update --init")

    with tempfile.TemporaryDirectory(prefix="steamworkspy-build-") as temp_dir:
        build_dir = Path(temp_dir)
        shutil.copy2(source_file, build_dir / "SteamworksPy.cpp")
        header_dir = build_dir / "sdk" / "steam"
        with ZipFile(sdk_path) as archive:
            for name in archive.namelist():
                if not name.startswith(SDK_HEADER_PREFIX) or name.endswith("/"):
                    continue
                relative = PurePosixPath(name[len(SDK_HEADER_PREFIX):])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(f"SDK zip 包含非法路径: {name}")
                target = header_dir.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
            with archive.open(LINUX_SDK_LIBRARY) as source, (build_dir / "libsteam_api.so").open("wb") as output:
                shutil.copyfileobj(source, output)

        # SteamworksPy.cpp 以 "sdk/steam/steam_api.h" 引用头文件；rpath 让它在运行库目录里找到同目录的 libsteam_api.so。
        subprocess.run(
            [compiler, "-std=c++11", "-O2", "-shared", "-fPIC", "-o", "SteamworksPy.so", "SteamworksPy.cpp",
             "-L.", "-lsteam_api", "-Wl,-rpath,$ORIGIN"],
            cwd=build_dir,
            check=True,
        )
        runtime_dir.mkdir(parents=True, exist_ok=True)
        target_path = runtime_dir / "SteamworksPy.so"
        shutil.copy2(build_dir / "SteamworksPy.so", target_path)
    return target_path


def main() -> int:
    parser = argparse.ArgumentParser(description="准备 SteamworksPy 和 Steamworks SDK 运行库")
    parser.add_argument("--sdk", default="", help="steamworks_sdk_*.zip 路径；也可用 STEAMWORKS_SDK_ZIP 环境变量")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR), help="运行库输出目录")
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    sdk_path = resolve_sdk_path(args.sdk)
    sdk_outputs = extract_sdk_files(sdk_path, runtime_dir)
    steamworkspy_outputs, missing = copy_steamworkspy_files(runtime_dir)
    if sys.platform.startswith("linux"):
        steamworkspy_outputs.append(build_linux_steamworkspy(sdk_path, runtime_dir))
        missing = [item for item in missing if item != "linux/SteamworksPy.so"]

    print(f"Steamworks SDK: {sdk_path}")
    print(f"Runtime dir: {runtime_dir}")
    for path in sdk_outputs + steamworkspy_outputs:
        print(f"OK {path.relative_to(ROOT_DIR)} sha256={sha256(path)}")
    if missing:
        print("以下 SteamworksPy wrapper 未找到，需要在对应平台编译后再放入运行库目录：")
        for item in missing:
            print(f"- {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
