"""Avisa quando existe uma versão nova publicada no GitHub (aba Releases).
Só olha a versão: não baixa nem instala nada sozinho."""
import json
import re
import urllib.request

from .version import GITHUB_REPO, VERSION


def _as_tuple(version: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Só considera os números."""
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def is_newer(remote: str, local: str = VERSION) -> bool:
    return _as_tuple(remote) > _as_tuple(local)


def check() -> dict:
    """Devolve {'available': bool, 'version': str, 'url': str}. Sem internet = nenhuma novidade (sem erro)."""
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "GerenciadorEmuladores"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.load(resp)
        tag = str(data.get("tag_name", ""))
        if tag and is_newer(tag):
            return {"available": True, "version": tag.lstrip("v"), "url": data.get("html_url", "")}
    except Exception:  # offline, limite da API, repositório sem release ainda...
        pass
    return {"available": False, "version": VERSION, "url": ""}
