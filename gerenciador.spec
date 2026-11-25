# -*- mode: python ; coding: utf-8 -*-
# Gera dist/GerenciadorEmuladores.exe (um arquivo só, sem console).  Uso: pyinstaller gerenciador.spec
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH)
UI = ROOT / "app" / "ui"

# Tudo de app/ui (HTML, CSS, JS, fonte) vai junto, mantendo as pastas.
# A pasta dev/ (simulador só para desenvolvimento) fica de fora.
ui_files = [
    (str(p), str(p.parent.relative_to(ROOT)))
    for p in UI.rglob("*")
    if p.is_file() and "dev" not in p.relative_to(UI).parts
]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    # catalog.json do projeto vai junto: é o catálogo de reserva quando não há cache nem internet
    # (se não existir, como num clone limpo do git, usa o catalog.example.json)
    datas=ui_files + [(str(next(f for f in (ROOT / "catalog.json", ROOT / "catalog.example.json") if f.exists())), ".")]
    # o gdown pergunta a própria versão em tempo de execução; sem os metadados ele falha no .exe
    + copy_metadata("gdown"),
    hiddenimports=[],
    excludes=["tkinter", "unittest", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GerenciadorEmuladores",
    console=False,          # app de janela: sem terminal preto atrás
    icon=str(ROOT / "assets" / "icon.ico"),
    upx=False,              # UPX costuma causar falso alarme de antivírus
)
