# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

STDLIB_FOR_EMBEDDED_PYTHON = [
    'argparse', 'base64', 'binascii', 'bisect', 'cmath', 'collections',
    'configparser', 'copy', 'csv', 'dataclasses', 'datetime', 'decimal',
    'difflib', 'enum', 'fractions', 'functools', 'getpass', 'glob', 'gzip',
    'hashlib', 'heapq', 'hmac', 'html', 'html.parser', 'http.client', 'io',
    'itertools', 'json', 'math', 'pathlib', 'pprint', 'random', 're', 'runpy',
    'shutil', 'sqlite3', 'statistics', 'string', 'struct', 'tarfile',
    'tempfile', 'textwrap', 'time', 'traceback', 'typing', 'unittest',
    'urllib.parse', 'xml.etree.ElementTree', 'zipfile', 'zlib',
]

hiddenimports = collect_submodules('alethic') + STDLIB_FOR_EMBEDDED_PYTHON


_tok_dir = 'data/tokenizer/alethic-tokenizer-v1'
if not os.path.isdir(_tok_dir):
    _tok_dir = 'src/alethic/_assets/data/tokenizer/alethic-tokenizer-v1'

a = Analysis(
    ['deploy/agent_entry.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        (_tok_dir, 'data/tokenizer/alethic-tokenizer-v1'),
        ('configs/model_gqa.yaml', 'configs'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'tkinter', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='alethic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    upx_exclude=[],
    name='alethic-agent',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Alethic Agent.app',
        bundle_identifier='com.alethic.agent',
    )
