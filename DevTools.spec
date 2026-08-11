# -*- mode: python ; coding: utf-8 -*-
"""DevTools 打包配置 - 文件夹模式"""

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # quick_cmds 的外部脚本：widget.py 用 __file__ 定位 scripts 目录
        ('qt_demo/tools/quick_cmds/scripts', 'qt_demo/tools/quick_cmds/scripts'),
        # 投屏 scrcpy 二进制：widget.py 用 __file__ 定位 scrcpy 子目录
        ('qt_demo/tools/scrcpy/scrcpy', 'qt_demo/tools/scrcpy/scrcpy'),
        # 程序图标：main.py 从 _internal/assets 加载
        ('assets/devtools.ico', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除用不到的大模块，减小体积、加速启动
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebChannel',
        'PySide6.QtQuick',
        'PySide6.QtQml',
        'PySide6.Qt3D*',
        'PySide6.QtMultimedia',
        'PySide6.QtLocation',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtGraphs',
        'PySide6.QtVirtualKeyboard',
    ],
    noarchive=False,
    optimize=1,
)

# PySide6 hook 会无条件收集所有 Qt DLL，这里按文件名过滤掉用不到的模块
EXCLUDE_DLL_PATTERNS = (
    'Qt6Quick',
    'Qt6Qml',
    'Qt6Pdf',
    'Qt6VirtualKeyboard',
    'Qt6Network',
    'Qt6OpenGL',
    'Qt6Svg',
    'opengl32sw',
)
a.binaries = [
    t for t in a.binaries
    if not any(t[0].endswith(p) or p in t[0] for p in EXCLUDE_DLL_PATTERNS)
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DevTools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI 程序，不显示控制台
    icon='assets/devtools.ico',   # exe 文件图标
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name='DevTools',
)
