import os

IS_WINDOWS_HOST = os.name == "nt"
# 只需要绕开 macOS 分支、又要让真实文件路径在当前主机上可用的测试使用它。
NON_DARWIN_SYSTEM = "Windows" if IS_WINDOWS_HOST else "Linux"
# 更新清单里代表当前主机的平台标识。
HOST_PACKAGE_PLATFORM = "windows-x64" if IS_WINDOWS_HOST else "linux-x64"


def host_path(windows_path: str) -> str:
    """
    把 `D:/Game/Mods` 这类 Windows 风格的测试路径换成当前主机的绝对路径。

    Windows 下原样返回；POSIX 下盘符路径会被当成 Windows 路径规范化，
    与真实的 POSIX 路径永远不相等，所以映射成 `/mnt/d/Game/Mods`。
    """
    if IS_WINDOWS_HOST:
        return windows_path
    drive, rest = windows_path[0], windows_path[2:]
    return f"/mnt/{drive.lower()}{rest}"
