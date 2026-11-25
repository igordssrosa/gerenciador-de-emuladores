"""Configurações do usuário (settings.json)."""
import json

from .paths import SETTINGS_FILE

# ID do catalog.json no Google Drive. Ele fica em app/_private.py (fora do git, para o
# repositório público não revelar o Drive). Sem esse arquivo o ID fica vazio e o app usa
# o cache local ou o catálogo que vem junto do projeto; também dá para pôr no settings.json.
try:
    from ._private import CATALOG_FILE_ID as DEFAULT_CATALOG_FILE_ID
except ImportError:
    DEFAULT_CATALOG_FILE_ID = ""

DEFAULTS = {"catalog_file_id": DEFAULT_CATALOG_FILE_ID}


def load() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return {**DEFAULTS, **data}


def save(settings: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
