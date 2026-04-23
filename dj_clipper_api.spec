# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the DJ Clipper FastAPI backend.
#
# Build with:
#   pyinstaller dj_clipper_api.spec
#
# Output: dist/dj_clipper_api/ (--onedir for fast startup)
#
# Uses collect_all() for packages with complex dynamic imports (librosa, scipy,
# sklearn, numba) so PyInstaller finds everything without manual maintenance.

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas = []
binaries = []
hiddenimports = []

# Packages whose full import trees must be discovered at build time
for pkg in ['librosa', 'sklearn', 'scipy', 'soundfile', 'resampy', 'numba', 'llvmlite', 'audioread']:
    d, b, h = collect_all(pkg)
    datas    += d
    binaries += b
    hiddenimports += h

# Uvicorn + FastAPI — explicitly list the lazy-loaded modules uvicorn discovers
# at startup via importlib; PyInstaller misses these with static analysis.
hiddenimports += [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'starlette',
    'starlette.routing',
    'starlette.middleware',
    'starlette.middleware.cors',
    'starlette.responses',
    'starlette.background',
    'sse_starlette',
    'sse_starlette.sse',
    'fastapi',
    'pydantic',
    'pydantic.v1',
    'aiofiles',
    'aiofiles.os',
    'aiofiles.threadpool',
    'email_validator',
    'h11',
    'httptools',
    'httptools.parser',
    'anyio',
    'anyio._backends._asyncio',
    # numpy internals missed on some platforms
    'numpy.core._methods',
    'numpy.lib.format',
    'numpy.random',
    'numpy.random._common',
    'numpy.random.common',
    'numpy.random.bounded_integers',
    'numpy.random.entropy',
]

a = Analysis(
    ['api/main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas + [
        # Bundle the entire dj_clipper package (core, models, workers)
        ('dj_clipper', 'dj_clipper'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy packages we definitely don't use
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
    console=True,  # keep True for troubleshooting; set False once stable
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
