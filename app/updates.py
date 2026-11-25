"""Atualização do app pelo GitHub (aba Releases).

check() só olha a versão. download_installer() baixa o instalador da release para uma pasta temporária;
quem chama (api.py) abre o instalador e fecha o app. Só aceita arquivos da release deste repositório.
"""
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
# o redirecionamento de /releases/latest termina assim: .../releases/tag/v1.2.3
_TAG_URL = re.compile(rf"^https://github\.com/{re.escape(GITHUB_REPO)}/releases/tag/(?P<tag>v?\d+\.\d+\.\d+)$")


class UpdateError(Exception):
    """Falha ao baixar a atualização (a mensagem pode ser mostrada ao usuário)."""


def _as_tuple(version: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Só considera os números."""
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def is_newer(remote: str, local: str = VERSION) -> bool:
    return _as_tuple(remote) > _as_tuple(local)


def check() -> dict:
    """Devolve {'available', 'version', 'url'} e, se há versão nova, 'asset_url' e 'asset_name' do instalador.

    Não usa a API do GitHub (que só deixa 60 consultas por hora por endereço de internet e, ao estourar,
    faria o aviso sumir em silêncio). Em vez disso segue o redirecionamento de /releases/latest, que
    termina em /releases/tag/vX.Y.Z, e monta o endereço do instalador pelo padrão de nome.
    Sem internet ou sem release = nenhuma novidade (sem erro)."""
    try:
        req = urllib.request.Request(f"https://github.com/{GITHUB_REPO}/releases/latest", method="HEAD",
                                     headers={"User-Agent": "GerenciadorEmuladores"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            final = resp.geturl()
        m = _TAG_URL.match(final)
        if m and is_newer(m["tag"]):
            version, tag = m["tag"].lstrip("v"), m["tag"]
            name = f"Instalar-GerenciadorEmuladores-{version}.exe"
            return {"available": True, "version": version, "url": final,
                    "asset_url": f"{_RELEASE_PREFIX}{tag}/{name}", "asset_name": name}
    except Exception:  # offline, repositório sem release ainda...
        pass
    return {"available": False, "version": VERSION, "url": ""}


def download_installer(url: str, name: str, on_progress: Callable[[int, int], None] | None = None) -> Path:
    """Baixa o instalador para a pasta temporária e devolve o caminho.
    Só vira .exe se terminar, se o tamanho bater com o que o GitHub informou (Content-Length) e se parecer um .exe."""
    if not url.startswith(_RELEASE_PREFIX) or not _ASSET_NAME.match(name):
        raise UpdateError("Endereço da atualização não permitido.")
    folder = Path(tempfile.gettempdir()) / "GerenciadorEmuladores-update"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():   # instaladores de atualizações anteriores não precisam ficar
        try:
            old.unlink()
        except OSError:
            pass
    final, part = folder / name, folder / (name + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GerenciadorEmuladores"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            host = urlparse(resp.geturl()).hostname or ""
            if not any(host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS):
                raise UpdateError("A atualização veio de um endereço inesperado.")
            size = int(resp.headers.get("Content-Length") or 0)
            if size <= 0:
                raise UpdateError("O GitHub não informou o tamanho da atualização.")
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
