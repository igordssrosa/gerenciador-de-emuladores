"""Caminhos do app. Dados do usuário ficam em %LOCALAPPDATA%, nunca na pasta do projeto
(o projeto está no OneDrive e sincronizar um .sav em uso pode corromper o arquivo)."""
import os
import sys
from pathlib import Path

APP_NAME = "GerenciadorEmuladores"

DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
EMULATORS_DIR = DATA_DIR / "emulators"
GAMES_DIR = DATA_DIR / "games"
BACKUPS_DIR = DATA_DIR / "backups"
ICONS_DIR = DATA_DIR / "icons"
CATALOG_CACHE = DATA_DIR / "catalog.cache.json"
SETTINGS_FILE = DATA_DIR / "settings.json"


def resource_dir() -> Path:
    """Pasta com os arquivos que vêm junto do app (ui, catalog.json de exemplo).
    Dentro do .exe do PyInstaller eles ficam em sys._MEIPASS."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


# catalog.json (com os IDs reais) não vai para o git; num clone limpo cai no catalog.example.json.
BUNDLED_CATALOG = resource_dir() / "catalog.json"
if not BUNDLED_CATALOG.exists():
    BUNDLED_CATALOG = resource_dir() / "catalog.example.json"


def ensure_dirs() -> None:
    for d in (DATA_DIR, EMULATORS_DIR, GAMES_DIR, BACKUPS_DIR, ICONS_DIR):
        d.mkdir(parents=True, exist_ok=True)
