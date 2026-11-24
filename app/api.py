"""Funções expostas ao JavaScript pelo pywebview (window.pywebview.api.<nome>).

Regras desta camada:
- Todo método devolve dados simples (dict/list/str/bool), que viram JSON no JS.
- Erros esperados viram {"error": "mensagem"} em vez de exceção, para a interface mostrar.
- Métodos que começam com "_" ficam privados (o pywebview não os expõe).
"""
import base64
import mimetypes
import threading
import time
from pathlib import Path

from . import catalog, downloader, launcher

# Fatias da barra de progresso quando o emulador também precisa ser baixado.
_EMU_SHARE = 0.35      # baixar o emulador
_EXTRACT_SHARE = 0.05  # extrair
# o resto (0.60) é a ROM; se o emulador já existe, a ROM ocupa a barra toda.


class Api:
    def __init__(self) -> None:
        self._lock = threading.Lock()          # protege _jobs
        self._emu_lock = threading.Lock()      # só uma instalação de emulador por vez
        self._jobs: dict[str, dict] = {}       # game_id -> estado do download
        self._cancels: dict[str, threading.Event] = {}
        self._running: set[str] = set()        # jogos abertos agora (id do jogo)
        self._play_errors: dict[str, str] = {}  # jogos que fecharam logo ao abrir (entregue uma vez)
        self._catalog: catalog.Catalog | None = None
        self._catalog_error = ""
        self._reload_catalog()

    # ---------- catálogo ----------

    def _reload_catalog(self) -> None:
        try:
            self._catalog, self._catalog_error = catalog.load(), ""
        except catalog.CatalogError as exc:
            self._catalog, self._catalog_error = None, str(exc)

    def _find(self, game_id: str):
        """Acha (emulador, jogo) pelo ID do jogo, ou levanta CatalogError."""
        if self._catalog:
            for emu in self._catalog.emulators:
                for game in emu.games:
                    if game.id == game_id:
                        return emu, game
        raise catalog.CatalogError(f"Jogo '{game_id}' não existe no catálogo.")

    def get_library(self) -> dict:
        """Tudo que a interface precisa para desenhar as telas, com o estado atual em disco."""
        if self._catalog is None:
            return {"error": self._catalog_error}
        emulators = []
        for emu in self._catalog.emulators:
            games = [{
                "id": g.id,
                "title": g.title,
                "subtitle": g.subtitle,
                "has_rom": downloader.rom_path(g).is_file(),
            } for g in emu.games]
            emulators.append({
                "id": emu.id,
                "name": emu.name,
                "platform": emu.platform,
                "installed": downloader.is_emulator_installed(emu),
                "games": games,
            })
        return {"emulators": emulators}

    def refresh_catalog(self) -> dict:
        """Botão 'Atualizar catálogo': baixa o catalog.json do Drive de novo."""
        try:
            self._catalog, self._catalog_error = catalog.refresh(), ""
        except catalog.CatalogError as exc:
            return {"error": str(exc)}
        return {"ok": True}

    # ---------- imagens ----------

    @staticmethod
    def _data_url(path: Path | None) -> str | None:
        """A janela não lê arquivos do AppData direto, então mandamos a imagem embutida (base64)."""
        if path is None:
            return None
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

    def get_cover(self, game_id: str) -> str | None:
        try:
            _, game = self._find(game_id)
            return self._data_url(downloader.ensure_cover(game))
        except (catalog.CatalogError, OSError):
            return None

    def get_emulator_icon(self, emulator_id: str) -> str | None:
        try:
            emu = self._catalog.emulator(emulator_id) if self._catalog else None
            return self._data_url(downloader.ensure_emulator_icon(emu)) if emu else None
        except (catalog.CatalogError, OSError):
            return None

    # ---------- downloads ----------

    def start_download(self, game_id: str) -> dict:
        """Começa a baixar (emulador, se faltar, e depois a ROM) numa thread. Acompanhe com get_jobs()."""
        try:
            emu, game = self._find(game_id)
        except catalog.CatalogError as exc:
            return {"error": str(exc)}
        with self._lock:
            if game_id in self._jobs:
                return {"ok": True}  # já está baixando
            cancel = threading.Event()
            self._cancels[game_id] = cancel
            self._jobs[game_id] = {"stage": "preparando", "fraction": 0.0, "done": 0, "total": None,
                                   "finished": False, "cancelled": False, "error": None}
        threading.Thread(target=self._run_download, args=(emu, game, cancel), daemon=True).start()
        return {"ok": True}

    def _update_job(self, game_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs.get(game_id)
            if job is None:
                return
            if "fraction" in changes:  # a barra nunca anda para trás
                changes["fraction"] = max(job["fraction"], changes["fraction"])
            job.update(changes)

    def _run_download(self, emu, game, cancel: threading.Event) -> None:
        needs_emulator = not downloader.is_emulator_installed(emu)

        def on_progress(stage: str, done: int, total) -> None:
            share = (done / total) if total else 0.0
            if stage == "emulador":
                fraction = _EMU_SHARE * share
            elif stage == "extraindo":
                fraction = _EMU_SHARE + _EXTRACT_SHARE / 2
            else:  # rom
                base = _EMU_SHARE + _EXTRACT_SHARE if needs_emulator else 0.0
                fraction = base + (1.0 - base) * share
            self._update_job(game.id, stage=stage, fraction=fraction, done=done, total=total)

        try:
            if needs_emulator:
                self._update_job(game.id, stage="aguardando")
                with self._emu_lock:  # se outro jogo já está instalando o emulador, espera e reaproveita
                    downloader.ensure_emulator(emu, on_progress, cancel)
            downloader.ensure_rom(game, on_progress, cancel)
            downloader.ensure_cover(game)  # capa é opcional; nunca falha o download
            self._update_job(game.id, fraction=1.0, finished=True)
        except downloader.DownloadCancelled:
            self._update_job(game.id, finished=True, cancelled=True)
        except Exception as exc:  # qualquer falha vira mensagem na interface, nunca trava a thread
            self._update_job(game.id, finished=True, error=str(exc) or exc.__class__.__name__)

    def get_jobs(self) -> dict:
        """Estado de todos os downloads. Jobs terminados são entregues uma vez e depois esquecidos."""
        with self._lock:
            snapshot = {gid: dict(job) for gid, job in self._jobs.items()}
            for gid, job in snapshot.items():
                if job["finished"]:
                    self._jobs.pop(gid, None)
                    self._cancels.pop(gid, None)
        return snapshot

    def cancel_download(self, game_id: str) -> dict:
        cancel = self._cancels.get(game_id)
        if cancel:
            cancel.set()
        return {"ok": True}

    # ---------- jogar ----------

    def play(self, game_id: str) -> dict:
        """Abre o jogo no emulador e acompanha em uma thread até ele fechar."""
        try:
            emu, game = self._find(game_id)
            with self._lock:
                if game_id in self._running:
                    return {"error": f"{game.title} já está aberto."}
                # (etapa 5: aqui entra o backup automático do save, ANTES de abrir)
                proc = launcher.launch(emu, game)
                self._running.add(game_id)
        except (catalog.CatalogError, launcher.LaunchError) as exc:
            return {"error": str(exc)}
        threading.Thread(target=self._watch, args=(emu, game, proc), daemon=True).start()
        return {"ok": True}

    def _watch(self, emu, game, proc) -> None:
        started = time.monotonic()
        code = proc.wait()
        # (etapa 5: aqui entra o backup automático do save, DEPOIS de fechar)
        with self._lock:
            self._running.discard(game.id)
            if code != 0 and time.monotonic() - started < 5:
                self._play_errors[game.id] = (f"O {emu.name} fechou logo ao abrir (código {code}). "
                                              "Confira se a ROM não está corrompida.")

    def get_running(self) -> dict:
        """Jogos abertos agora e erros de abertura (entregues uma vez)."""
        with self._lock:
            errors, self._play_errors = self._play_errors, {}
            return {"running": sorted(self._running), "errors": errors}
