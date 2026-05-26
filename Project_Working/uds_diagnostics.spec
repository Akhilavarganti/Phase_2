# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

datas = [('/home/mobase/Single_Exe/GIT_Working/Project_2_25/venv/lib/python3.13/site-packages/board_imports.json', '.'), ('/home/mobase/Single_Exe/GIT_Working/Project_2_25/venv/lib/python3.13/site-packages/microcontroller_imports.json', '.')]
binaries = []
hiddenimports = ['board', 'RPi', 'RPi.GPIO', 'board', 'adafruit_blinka', 'adafruit_blinka.board', 'adafruit_platformdetect', 'adafruit_platformdetect.constants', 'busio', 'adafruit_ssd1306', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont', 'can', 'can.interfaces.socketcan', 'can.io.asc', 'isotp', 'udsoncan', 'udsoncan.client', 'udsoncan.connections', 'udsoncan.configs', 'udsoncan.services', 'drivers', 'drivers.config_loader', 'drivers.oled_display', 'drivers.button_input', 'drivers.uds_client', 'drivers.transfer_file', 'drivers.Parse_handler', 'drivers.can_logger', 'drivers.report_generator']
datas += collect_data_files('microcontroller')
tmp_ret = collect_all('adafruit_platformdetect')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('adafruit_blinka')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('digitalio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('busio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('microcontroller')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='uds_diagnostics',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
