# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['phone_backup_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icons/*.png', 'icons'),
        ('adb-tools/*', 'adb-tools')
    ],
    hiddenimports=[
        'PIL',
        'PIL.ExifTags',
        'hachoir',
        'hachoir.metadata',
        'hachoir.parser',
        'PyQt5.QtWidgets',
        'PyQt5.QtGui',
        'PyQt5.QtCore'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='DCIM_Backup_Utility',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',
)