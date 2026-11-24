"""Configurações do usuário (settings.json)."""
import json

from .paths import SETTINGS_FILE

# ID do catalog.json no Google Drive. Vazio = ainda não configurado:
# o app usa o cache local ou o catalog.json que vem junto do projeto.
# Depois de subir o catálogo no Drive, coloque o ID aqui ou no settings.json.
DEFAULT_CATALOG_FILE_ID = "1_9_pBB9bvQCam6y4kig7n2J3VNL6tKOk"

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
