import os
import subprocess
import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def supports_win32_ctypes() -> bool:
    return is_windows()


def monitoring_mode() -> str:
    if is_windows():
        return "windows"
    # 监控循环只依赖 psutil，Linux 上可以直接用。
    return "psutil" if is_linux() else "disabled"


def supports_process_monitoring() -> bool:
    return monitoring_mode() != "disabled"


def open_uri(uri: str) -> None:
    if is_windows():
        os.startfile(uri)  # type: ignore[attr-defined]
        return
    if is_macos():
        subprocess.Popen(["open", uri])
        return
    subprocess.Popen(["xdg-open", uri])


def get_restart_command(executable_path: str = "", *, main_script: str | Path | None = None) -> list[str]:
    if executable_path:
        return [os.path.abspath(executable_path)]
    # 命令行指定的浏览器模式在重启后也要保持。
    forwarded_args = [arg for arg in sys.argv[1:] if arg == "--browser"]
    if getattr(sys, "frozen", False):
        return [os.path.abspath(sys.executable), *forwarded_args]

    # 不解析符号链接：POSIX 虚拟环境里的 python 指向基础解释器，解析后新实例会跳出虚拟环境、导入不了依赖。
    python_executable = Path(os.path.abspath(sys.executable))
    target_script = str(main_script) if main_script is not None else ""
    if is_windows():
        pythonw_executable = python_executable.with_name("pythonw.exe")
        if pythonw_executable.exists():
            return [str(pythonw_executable), target_script, *forwarded_args]
    return [str(python_executable), target_script, *forwarded_args]
