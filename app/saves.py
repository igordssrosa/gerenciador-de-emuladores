"""Saves e backups. Lógica pura, sem interface (a api.py chama estas funções).

O save fica ao lado da ROM (o mGBA grava <nome-da-rom>.sav na pasta do jogo).
Backups ficam em backups/<id-do-jogo>/ com data e hora no nome:
    2026-11-24_17-30-12__antes-de-jogar.sav

Regras (CLAUDE.md):
- Nunca perder progresso: antes de qualquer troca ou remoção do save atual, faz backup dele.
- Só guarda backup se o save mudou desde o backup mais recente.
- Mantém os 10 backups automáticos mais recentes por jogo. Os manuais ficam até você apagar.
"""
import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import downloader, paths
from .catalog import Emulator, Game

KEEP_AUTO = 10
MAX_SAVE_BYTES = 1024 * 1024  # saves de GBA têm no máximo 128 KB; 1 MB já é folga grande

# motivo -> texto mostrado na interface
REASONS = {
    "antes-de-jogar": "Antes de jogar",
    "depois-de-jogar": "Depois de jogar",
    "manual": "Backup manual",
    "antes-de-restaurar": "Antes de restaurar",
    "antes-de-importar": "Antes de importar",
    "antes-de-apagar": "Antes de apagar o save",
}
AUTO_REASONS = {"antes-de-jogar", "depois-de-jogar"}

# 2026-11-24_17-30-12[-2]__motivo.ext  (o -2 só existe se dois backups caírem no mesmo segundo)
_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})(?:-(\d+))?__([a-z-]+)\.[A-Za-z0-9]+$")


class SaveError(Exception):
    """Falha de save/backup (a mensagem pode ser mostrada ao usuário)."""


@dataclass
class Backup:
    name: str
    path: Path
    created: float   # segundos desde 1970, lido do nome do arquivo
    seq: int
    reason: str
    size: int

    @property
    def auto(self) -> bool:
        return self.reason in AUTO_REASONS


# ---------- save atual ----------

def save_path(emu: Emulator, game: Game) -> Path:
    """Onde o save do jogo está (ou ficaria): <pasta do jogo>/<nome da ROM sem extensão><ext do save>."""
    stem = Path(game.rom_filename).stem
    extensions = emu.save_extensions or [".sav"]
    for ext in extensions:
        candidate = downloader.game_dir(game) / (stem + ext)
        if candidate.is_file():
            return candidate
    return downloader.game_dir(game) / (stem + extensions[0])


def current_save(emu: Emulator, game: Game) -> Path | None:
    path = save_path(emu, game)
    return path if path.is_file() else None


def is_blank(path: Path) -> bool:
    """Save que o emulador criou vazio (tudo 0xFF ou tudo 0x00): o jogo ainda não salvou nada."""
    data = path.read_bytes()
    return not data or data == bytes([data[0]]) * len(data) and data[0] in (0x00, 0xFF)


def save_info(emu: Emulator, game: Game) -> dict:
    path = current_save(emu, game)
    if path is None:
        return {"exists": False, "blank": False, "size": 0, "modified": None}
    st = path.stat()
    return {"exists": True, "blank": is_blank(path), "size": st.st_size, "modified": st.st_mtime}


# ---------- backups ----------

def backups_dir(game: Game) -> Path:
    return paths.BACKUPS_DIR / game.id


def list_backups(game: Game) -> list[Backup]:
    """Backups do jogo, do mais novo para o mais antigo."""
    folder = backups_dir(game)
    found: list[Backup] = []
    if folder.is_dir():
        for f in folder.iterdir():
            m = _NAME.match(f.name)
            if not (m and f.is_file()):
                continue  # ignora temporários e arquivos estranhos
            created = datetime.strptime(f"{m[1]} {m[2]}", "%Y-%m-%d %H-%M-%S").timestamp()
            found.append(Backup(f.name, f, created, int(m[3] or 1), m[4], f.stat().st_size))
    return sorted(found, key=lambda b: (b.created, b.seq), reverse=True)


def _find_backup(game: Game, name: str) -> Backup:
    # só aceita nomes que existem na listagem: impede caminhos como "..\\..\\algo"
    for b in list_backups(game):
        if b.name == name:
            return b
    raise SaveError("Esse backup não existe mais.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_atomic(src: Path, dest: Path) -> None:
    """Copia para um temporário na pasta de destino e só então troca: nunca deixa arquivo pela metade."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest)
    except OSError as exc:
        Path(tmp).unlink(missing_ok=True)
        raise SaveError(f"Não consegui gravar o arquivo: {exc.strerror or exc}") from exc


def backup_now(emu: Emulator, game: Game, reason: str) -> Backup | None:
    """Guarda um backup do save atual. Devolve None se não há save, se ele está vazio (o emulador cria
    um arquivo em branco ao abrir) ou se nada mudou desde o backup mais recente."""
    if reason not in REASONS:
        raise ValueError(f"motivo de backup desconhecido: {reason}")
    src = current_save(emu, game)
    if src is None or is_blank(src):
        return None
    existing = list_backups(game)
    if existing and _sha256(existing[0].path) == _sha256(src):
        return None

    now = datetime.now().replace(microsecond=0)
    stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    # Se já há backup neste mesmo segundo, o novo ganha o próximo número (maior que todos), para a
    # ordem nunca se misturar, mesmo depois de a limpeza apagar backups antigos.
    same_second = [b.seq for b in existing if b.created == now.timestamp()]
    seq = max(same_second) + 1 if same_second else 1
    suffix = src.suffix or ".sav"
    name_stamp = stamp if seq == 1 else f"{stamp}-{seq}"
    dest = backups_dir(game) / f"{name_stamp}__{reason}{suffix}"
    _copy_atomic(src, dest)
    prune(game)
    return next(b for b in list_backups(game) if b.name == dest.name)


def prune(game: Game) -> None:
    """Apaga os backups automáticos além dos 10 mais recentes. Manuais nunca são apagados aqui."""
    autos = [b for b in list_backups(game) if b.auto]
    for old in autos[KEEP_AUTO:]:
        old.path.unlink(missing_ok=True)


def delete_backup(game: Game, name: str) -> None:
    _find_backup(game, name).path.unlink(missing_ok=True)


# ---------- ações sobre o save atual ----------

def restore(emu: Emulator, game: Game, name: str) -> None:
    """Troca o save atual pelo backup. Antes, guarda o save atual."""
    backup = _find_backup(game, name)
    backup_now(emu, game, "antes-de-restaurar")
    _copy_atomic(backup.path, save_path(emu, game))


def import_save(emu: Emulator, game: Game, source: Path) -> None:
    """Usa um .sav de fora como save do jogo. Antes, guarda o save atual."""
    if not source.is_file():
        raise SaveError("Não encontrei o arquivo escolhido.")
    size = source.stat().st_size
    if size == 0:
        raise SaveError("O arquivo está vazio.")
    if size > MAX_SAVE_BYTES:
        raise SaveError("O arquivo é grande demais para ser um save (máximo 1 MB).")
    backup_now(emu, game, "antes-de-importar")
    _copy_atomic(source, save_path(emu, game))


def export_save(emu: Emulator, game: Game, dest: Path) -> None:
    src = current_save(emu, game)
    if src is None:
        raise SaveError("Esse jogo ainda não tem save para exportar.")
    _copy_atomic(src, dest)


def delete_save(emu: Emulator, game: Game) -> None:
    """Apaga o save atual, depois de guardar um backup (dá para desfazer pela lista)."""
    src = current_save(emu, game)
    if src is None:
        raise SaveError("Esse jogo não tem save para apagar.")
    backup_now(emu, game, "antes-de-apagar")  # se falhar, levanta erro e o save não é apagado
    try:
        src.unlink()
    except OSError as exc:
        raise SaveError(f"Não consegui apagar o save: {exc.strerror or exc}") from exc
