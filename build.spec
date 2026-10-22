# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Preprod Telecom Operations Toolkit (windowed exe,
# config_ocs.json bundled as a read-only default; the app also looks for
# a config next to the exe at runtime).
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = [
    # paramiko's Ed25519/RSA backend is imported lazily; PyInstaller misses
    # it and the frozen exe fails at runtime with
    # "No module named cryptography.hazmat.primitives.kdf" (paramiko needs
    # it to load encrypted private keys / do kdf).
    'cryptography.hazmat.primitives.kdf',
    'ui',
    'ui.tabs',
    'ui.tabs.invoice_tab',
    'ui.tabs.contract_tab',
    'ui.tabs.msisdn_tab',
    'ui.tabs.sales_invoice_tab',
    'ui.tabs.sim_card_tab',
    'ui.tabs.roaming_tab',
    'services',
    'services.sim_card_service',
    'services.roaming_service',
    'connections',
    'connections.redis_client',
    'core',
    'core.crypto',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('config_ocs.json', '.')],
    hiddenimports=hiddenimports + collect_submodules('oracledb')
    + collect_submodules('cryptography'),
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
    name='PreprodTestTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # set True if you want a console for debugging
    disable_windowed_traceback=False,
    icon=None,              # e.g. 'assets/icon.ico'
)
