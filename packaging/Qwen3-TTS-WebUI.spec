# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: Qwen3-TTS WebUI single-file executable (web layer).

Usage: pyinstaller --clean packaging/Qwen3-TTS-WebUI.spec
Prereq: frontend built (backend/static/). Output: dist/Qwen3-TTS-WebUI(.exe).
"""
import os
import platform
import sys
import tomllib

repo_root = os.path.abspath(os.path.join(SPECPATH, ".."))
static_dir = os.path.join(repo_root, "backend", "static")

# Version from pyproject.toml is baked into the artifact name
with open(os.path.join(repo_root, "pyproject.toml"), "rb") as _f:
    app_version = tomllib.load(_f)["project"]["version"]

# Artifact name: {name}-v{version}-{os}-{arch}[-{libc}]
_os_tag = "win" if sys.platform == "win32" else "linux"
_arch = platform.machine().lower()
if _arch in ("amd64",):
    _arch = "x86_64"
elif _arch == "aarch64":
    _arch = "arm64"
_libc_tag = ""
if sys.platform.startswith("linux"):
    try:
        _libc_ver = os.confstr("CS_GNU_LIBC_VERSION")  # e.g. "glibc 2.39"
    except (ValueError, OSError):
        _libc_ver = ""
    _libc_tag = f"-{_libc_ver.replace(' ', '')}" if _libc_ver else "-musl"
artifact_name = f"Qwen3-TTS-WebUI-v{app_version}-{_os_tag}-{_arch}{_libc_tag}"

if not os.path.isdir(static_dir) or not os.path.isfile(os.path.join(static_dir, "index.html")):
    raise SystemExit("backend/static missing; run `cd frontend && pnpm build` first")

# conda Pythons link stdlib C extensions (_ssl/_ctypes/_decimal/pyexpat/_lzma/
# _bz2/zlib) against Library\bin runtime DLLs that PyInstaller does not collect.
# Derived from sys.base_prefix; skipped automatically on non-conda Pythons.
_conda_bin = os.path.join(sys.base_prefix, "Library", "bin")
_conda_dlls = []
if os.path.isdir(_conda_bin):
    for _name in (
        "libssl-3-x64.dll", "libcrypto-3-x64.dll", "libmpdec-4.dll",
        "ffi.dll", "ffi-8.dll", "libexpat.dll", "libbz2.dll", "liblzma.dll",
        "libzlib1.dll", "libzlib.dll",
    ):
        _path = os.path.join(_conda_bin, _name)
        if os.path.isfile(_path):
            _conda_dlls.append((_path, "."))
    if _conda_dlls:
        print(f"PyInstaller: collecting {len(_conda_dlls)} conda runtime DLLs from {_conda_bin}")

block_cipher = None

# The worker subprocess is launched with an external Python (env_dir), which
# loads backend modules via ordinary filesystem imports — PYZ-only modules are
# invisible to it. The whole backend package is therefore collected as a file
# tree (settings.json, __pycache__ and the separately-bundled static/ excluded).
from PyInstaller.building.datastruct import Tree  # noqa: E402

backend_tree = Tree(
    os.path.join(repo_root, "backend"),
    prefix="backend",
    excludes=["__pycache__", "*.pyc", "settings.json", "static"],
)

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[repo_root, os.path.join(SPECPATH)],
    binaries=_conda_dlls,
    datas=[(static_dir, "backend/static")],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "backend.branches.QwenLM_Qwen3-TTS",
        "backend.branches.dffdeeq_Qwen3-TTS-streaming",
        "backend.branches.andimarafioti_faster-qwen3-tts",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "qwen_tts",
        "faster_qwen3_tts",
        "transformers",
        "tiktoken",
        "numpy.testing",
        "matplotlib",
        "scipy",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

a.datas += backend_tree

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Windows embeds the icon (from frontend favicon.svg via make_icon.py);
# Linux ELF executables have no icon resource.
_icon_path = os.path.join(SPECPATH, "icon.ico")
_icon = _icon_path if sys.platform == "win32" and os.path.isfile(_icon_path) else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=artifact_name,
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
    icon=_icon,
)
