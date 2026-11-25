"""Atualização do app pelo GitHub (aba Releases).

check() só olha a versão. download_installer() baixa o instalador da release para uma pasta temporária;
quem chama (api.py) abre o instalador e fecha o app. Só aceita arquivos da release deste repositório.
"""
import json
import re
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .version import GITHUB_REPO, VERSION

_RELEASE_PREFIX = f"https://github.com/{GITHUB_REPO}/releases/download/"
_ASSET_NAME = re.compile(r"^Instalar-GerenciadorEmuladores-[\d.]+\.exe$")
# o GitHub entrega o arquivo por um redirecionamento para um destes domínios
_ALLOWED_HOSTS = ("github.com", "githubusercontent.com")


class UpdateError(Exception):
    """Falha ao baixar a atualização (a mensagem pode ser mostrada ao usuário)."""


def _as_tuple(version: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Só considera os números."""
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def is_newer(remote: str, local: str = VERSION) -> bool:
    return _as_tuple(remote) > _as_tuple(local)


def _find_installer(assets: list) -> dict | None:
    """O instalador na lista de arquivos da release (nome e link precisam bater com o esperado)."""
    for a in assets:
        if (_ASSET_NAME.match(str(a.get("name", ""))) and str(a.get("browser_download_url", "")).startswith(_RELEASE_PREFIX)
                and int(a.get("size", 0)) > 0):
            return a
    return None


def check() -> dict:
    """Devolve {'available', 'version', 'url'} e, se a release tem o instalador, 'asset_url', 'asset_name', 'asset_size'.
    Sem internet = nenhuma novidade (sem erro)."""
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "GerenciadorEmuladores"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.load(resp)
        tag = str(data.get("tag_name", ""))
        if tag and is_newer(tag):
            info = {"available": True, "version": tag.lstrip("v"), "url": data.get("html_url", "")}
            asset = _find_installer(data.get("assets", []))
            if asset:
                info.update(asset_url=asset["browser_download_url"], asset_name=asset["name"], asset_size=int(asset["size"]))
            return info
    except Exception:  # offline, limite da API, repositório sem release ainda...
        pass
    return {"available": False, "version": VERSION, "url": ""}


def download_installer(url: str, name: str, size: int,
                       on_progress: Callable[[int, int], None] | None = None) -> Path:
    """Baixa o instalador para a pasta temporária e devolve o caminho. Só vira .exe se terminar e o tamanho bater."""
    if not url.startswith(_RELEASE_PREFIX) or not _ASSET_NAME.match(name):
        raise UpdateError("Endereço da atualização não permitido.")
    folder = Path(tempfile.gettempdir()) / "GerenciadorEmuladores-update"
    folder.mkdir(parents=True, exist_ok=True)
    final, part = folder / name, folder / (name + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GerenciadorEmuladores"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            host = urlparse(resp.geturl()).hostname or ""
            if not any(host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS):
                raise UpdateError("A atualização veio de um endereço inesperado.")
            done = 0
            with part.open("wb") as f:
                while chunk := resp.read(1 << 16):
                    f.write(chunk)
                    done += len(chunk)
                    if on_progress:
                        on_progress(done, size)
        if part.stat().st_size != size:
            raise UpdateError("O download veio incompleto. Tente de novo.")
        with part.open("rb") as f:
            if f.read(2) != b"MZ":   # todo .exe do Windows começa com "MZ"
                raise UpdateError("O arquivo baixado não é um instalador.")
        part.replace(final)
        return final
    except UpdateError:
        raise
    except OSError as exc:   # sem internet, queda no meio, disco cheio...
        raise UpdateError("Não consegui baixar a atualização (sem internet?).") from exc
    finally:
        part.unlink(missing_ok=True)
