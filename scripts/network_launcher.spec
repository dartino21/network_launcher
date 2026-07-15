# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the portable Windows release."""

import os

block_cipher = None
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ngrok = os.path.join(ROOT, "bin", "ngrok.exe")
binaries = [(ngrok, "bin")] if os.path.isfile(ngrok) else []

a = Analysis(
    [os.path.join(ROOT, "scripts", "entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=[(os.path.join(ROOT, "assets"), "assets")],
    hiddenimports=[
        "PyQt5.QtWebEngineWidgets",
        "matplotlib.backends.backend_qt5agg",
        "aiohttp",
        "aiohttp.web",
        "multidict",
    ],
    excludes=["IPython", "ipykernel", "jupyter", "notebook", "pytest", "PyQt6", "PySide6", "PySide2", "tkinter"],
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="NetworkLauncher", console=False, upx=True,
    icon=os.path.join(ROOT, "assets", "network_launcher.ico"),
)
