# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the DJ Clipper FastAPI backend.
#
# Build with:
#   pyinstaller dj_clipper_api.spec
#
# Output: dist/dj_clipper_api/ (--onedir for fast startup)

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# Packages whose full import trees must be discovered at build time.
# collect_all() handles submodules, data files, and binaries together —
# much more reliable than hiddenimports alone for complex packages.
for pkg in [
    # Audio processing
    'librosa', 'sklearn', 'scipy', 'soundfile', 'resampy',
    'numba', 'llvmlite', 'audioread',
    # API server — these use lazy importlib loading that static analysis misses
    'uvicorn', 'fastapi', 'starlette', 'pydantic',
    'aiofiles', 'sse_starlette', 'anyio', 'h11', 'httptools',
]:
    d, b, h = collect_all(pkg)
    datas    += d
    binaries += b
    hiddenimports += h

# Extra numpy internals that static analysis sometimes misses
hiddenimports += [
    'numpy.core._methods',
    'numpy.lib.format',
    'numpy.random',
    'numpy.random._common',
    'numpy.random.bounded_integers',
    'numpy.random.entropy',
]

a = Analysis(
    ['api/main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas + [
        # Bundle only the active dj_clipper packages (core + models)
        ('dj_clipper/core', 'dj_clipper/core'),
        ('dj_clipper/models', 'dj_clipper/models'),
        ('dj_clipper/config.py', 'dj_clipper'),
        ('dj_clipper/__init__.py', 'dj_clipper'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt6', 'PyQt5', 'tkinter', 'matplotlib', 'IPython',
        'jupyter', 'notebook', 'pytest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='dj_clipper_api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # console=True so stderr/stdout are piped correctly when spawned as a
    # background child process on Windows. No visible console appears because
    # Electron spawns it with stdio:'pipe', not attached to a terminal.
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='dj_clipper_api',
)
