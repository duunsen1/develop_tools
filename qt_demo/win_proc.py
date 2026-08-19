"""Windows 子进程工具

本程序是 PyInstaller 打包的纯 GUI 程序(无控制台)。从 GUI 程序启动
adb/fastboot/7z/powershell 等控制台子进程时，如果不加 CREATE_NO_WINDOW，
Windows 会为子进程新建一个黑色控制台窗口。统一在这里定义该标志。
"""

import subprocess

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
