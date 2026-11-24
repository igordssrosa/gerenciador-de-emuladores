"""Baixa emuladores, ROMs e capas do Google Drive (via gdown) e extrai .zip / .7z.

Tudo aqui é independente da interface: quem chama passa um `on_progress(stage, done, total)`
e, opcionalmente, um threading.Event (`cancel`) para interromper.
"""
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Callable

from . import paths
from .catalog import Emulator, Game

# stage: "emulador" | "extraindo" | "rom" | "capa"; total pode ser None se o Drive não informar.
ProgressCallback = Callable[[str, int, "int | None"], None]


class DownloadError(Exception):
    """Falha de download/extração (a mensagem pode ser mostrada ao usuário)."""


class DownloadCancelled(DownloadError):
    pass


# ---------- caminhos e estado ----------

def emulator_dir(emu: Emulator) -> Path:
    return paths.EMULATORS_DIR / emu.id


def emulator_exe(emu: Emulator) -> Path:
    return emulator_dir(emu) / emu.executable


def game_dir(game: Game) -> Path:
    return paths.GAMES_DIR / game.id


def rom_path(game: Game) -> Path:
    return game_dir(game) / game.rom_filename


def cover_path(game: Game) -> Path | None:
    """Capa já baixada (a extensão real é detectada no download), ou None."""
    for p in game_dir(game).glob("cover.*"):
        return p
    return None


def is_emulator_installed(emu: Emulator) -> bool:
    return emulator_exe(emu).is_file()


def is_game_ready(emu: Emulator, game: Game) -> bool:
    return is_emulator_installed(emu) and rom_path(game).is_file()


# ---------- download de um arquivo ----------

def download_file(file_id: str, dest: Path, on_progress: Callable[[int, "int | None"], None] | None = None,
                  cancel: threading.Event | None = None) -> Path:
    """Baixa um arquivo do Drive para `dest`. Só aparece em `dest` se terminar com sucesso."""
    if not file_id:
        raise DownloadError("Esse item ainda não tem ID do Drive no catálogo.")
    import gdown  # import tardio: abrir o app não depende da rede

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Baixa para uma pasta temporária na mesma unidade e só depois move: nunca sobra meio arquivo.
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix=".dl-") as tmp:
        tmp_file = Path(tmp) / "download.bin"
        try:
            result = gdown.download(
                id=file_id, output=str(tmp_file), quiet=True, retries=2, timeout=60,
                progress=(lambda done, total: on_progress(done, total)) if on_progress else None,
                cancel=cancel,
            )
        except Exception as exc:
            if cancel is not None and cancel.is_set():
                raise DownloadCancelled("Download cancelado.") from exc
            raise DownloadError(f"Falha ao baixar do Drive: {exc}") from exc
        if not result or not tmp_file.is_file() or tmp_file.stat().st_size == 0:
            raise DownloadError("O Drive não entregou o arquivo (link privado ou sem internet?).")
        shutil.move(str(tmp_file), str(dest))
    return dest


# ---------- extração ----------

def _check_members(names: list[str], target: Path) -> None:
    """Protege contra 'zip slip': nenhum arquivo pode sair da pasta de destino."""
    root = target.resolve()
    for name in names:
        if not (root / name).resolve().is_relative_to(root):
            raise DownloadError(f"Arquivo compactado suspeito (caminho fora da pasta): {name}")


def extract_archive(archive: Path, target: Path, kind: str) -> None:
    """Extrai .zip ou .7z em `target` (que deve estar vazia/nova)."""
    target.mkdir(parents=True, exist_ok=True)
    try:
        if kind == "zip":
            with zipfile.ZipFile(archive) as z:
                _check_members(z.namelist(), target)
                z.extractall(target)
        elif kind == "7z":
            import py7zr
            with py7zr.SevenZipFile(archive) as z:
                _check_members(z.getnames(), target)
                z.extractall(target)
        else:
            raise DownloadError(f"Tipo de arquivo não suportado no catálogo: '{kind}' (use zip ou 7z).")
    except DownloadError:
        raise
    except Exception as exc:  # arquivo corrompido, 7z inválido etc.
        if type(exc).__name__ == "UnsupportedCompressionMethodError":
            # Acontece com .7z feitos com filtro BCJ2 (como o oficial do mGBA).
            raise DownloadError("Este .7z usa uma compressão que o app não lê (BCJ2). "
                                "Recompacte o emulador como .zip e atualize o catálogo.") from exc
        raise DownloadError(f"Não consegui extrair o arquivo: {exc}") from exc


def _flatten_single_folder(target: Path) -> None:
    """Se o pacote veio dentro de uma única pasta (ex.: mGBA-0.10.5-win64/), sobe o conteúdo um nível."""
    children = list(target.iterdir())
    if len(children) == 1 and children[0].is_dir():
        inner = children[0]
        for item in list(inner.iterdir()):
            shutil.move(str(item), str(target / item.name))
        inner.rmdir()


# ---------- emulador ----------

def ensure_emulator(emu: Emulator, on_progress: ProgressCallback | None = None,
                    cancel: threading.Event | None = None) -> Path:
    """Garante o emulador instalado (baixa e extrai se preciso). Devolve o caminho do executável."""
    if is_emulator_installed(emu):
        return emulator_exe(emu)

    final_dir = emulator_dir(emu)
    paths.EMULATORS_DIR.mkdir(parents=True, exist_ok=True)
    staging = paths.EMULATORS_DIR / f".{emu.id}.new"  # extrai aqui e só então renomeia
    shutil.rmtree(staging, ignore_errors=True)
    for stale in paths.EMULATORS_DIR.glob(".dl-*"):  # sobras de downloads que travaram antes
        shutil.rmtree(stale, ignore_errors=True)
    try:
        # ignore_cleanup_errors: no Windows um arquivo ainda aberto não deve esconder o erro real
        with tempfile.TemporaryDirectory(dir=paths.EMULATORS_DIR, prefix=".dl-",
                                         ignore_cleanup_errors=True) as tmp:
            archive = Path(tmp) / f"emulator.{emu.download_type}"
            download_file(emu.download_file_id, archive,
                          (lambda d, t: on_progress("emulador", d, t)) if on_progress else None, cancel)
            if on_progress:
                on_progress("extraindo", 0, None)
            extract_archive(archive, staging, emu.download_type)
        _flatten_single_folder(staging)
        if not (staging / emu.executable).is_file():
            raise DownloadError(f"O pacote do {emu.name} não contém '{emu.executable}'. Confira o catálogo.")
        for name, content in emu.setup_files.items():
            f = staging / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content, encoding="utf-8")
        shutil.rmtree(final_dir, ignore_errors=True)  # sobra de instalação quebrada
        staging.rename(final_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return emulator_exe(emu)


# ---------- jogo ----------

def ensure_rom(game: Game, on_progress: ProgressCallback | None = None,
               cancel: threading.Event | None = None) -> Path:
    dest = rom_path(game)
    if not dest.is_file():
        download_file(game.rom_file_id, dest,
                      (lambda d, t: on_progress("rom", d, t)) if on_progress else None, cancel)
    return dest


def _image_extension(path: Path) -> str:
    """Descobre o tipo da imagem pelos primeiros bytes (o Drive não garante a extensão)."""
    head = path.read_bytes()[:12]
    if head.startswith(b"\x89PNG"):
        return ".png"
    if head.startswith(b"\xff\xd8"):
        return ".jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head[:3] == b"GIF":
        return ".gif"
    raise DownloadError("O arquivo da capa não é uma imagem reconhecida.")


def _ensure_image(file_id: str, folder: Path, stem: str, cancel: threading.Event | None) -> Path | None:
    """Baixa uma imagem opcional (capa/ícone) para folder/<stem>.<ext>. Sem ID ou com erro: None."""
    for existing in folder.glob(f"{stem}.[!d]*"):  # [!d] ignora o temporário "<stem>.download"
        return existing
    if not file_id:
        return None
    tmp = folder / f"{stem}.download"
    try:
        download_file(file_id, tmp, None, cancel)
        final = tmp.with_name(stem + _image_extension(tmp))
        tmp.replace(final)
        return final
    except DownloadError:
        return None
    finally:
        tmp.unlink(missing_ok=True)


def ensure_cover(game: Game, cancel: threading.Event | None = None) -> Path | None:
    return _ensure_image(game.cover_file_id, game_dir(game), "cover", cancel)


def emulator_icon_path(emu: Emulator) -> Path | None:
    return next(paths.ICONS_DIR.glob(f"{emu.id}.[!d]*"), None)


def ensure_emulator_icon(emu: Emulator, cancel: threading.Event | None = None) -> Path | None:
    """O ícone fica fora da pasta do emulador, para existir antes de o emulador ser baixado."""
    return _ensure_image(emu.icon_file_id, paths.ICONS_DIR, emu.id, cancel)


def ensure_game(emu: Emulator, game: Game, on_progress: ProgressCallback | None = None,
                cancel: threading.Event | None = None) -> Path:
    """Fluxo completo do botão 'Baixar': emulador (se faltar) -> ROM. Devolve o caminho da ROM."""
    ensure_emulator(emu, on_progress, cancel)
    return ensure_rom(game, on_progress, cancel)
