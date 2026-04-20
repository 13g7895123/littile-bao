# build.spec — PyInstaller 打包設定
# 執行：pyinstaller build.spec
# 說明：此版本為獨立模擬版，不依賴 shioaji，可直接打包

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        'tkinter.messagebox',
        'tkinter.font',
        'json',
        'threading',
        'queue',
        'random',
        'collections',
        'dataclasses',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['shioaji', 'numpy', 'pandas', 'matplotlib'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='StockTrader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,           # DEBUG: show console for error messages
    icon=None,
)
