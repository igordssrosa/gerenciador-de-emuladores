"""Funções expostas ao JavaScript pelo pywebview (window.pywebview.api.<nome>).

Regras desta camada:
- Todo método devolve dados simples (dict/list/str/bool), que viram JSON no JS.
- Erros esperados viram {"error": "mensagem"} em vez de exceção, para a interface mostrar.
- Métodos que começam com "_" ficam privados (o pywebview não os expõe).
"""
import base64
import mimetypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from pathlib import Path

from . import catalog, downloader, launcher, saves, updates

# Fatias da barra de progresso quando o emulador também precisa ser baixado.
_EMU_SHARE = 0.35      # baixar o emulador
_EXTRACT_SHARE = 0.05  # extrair
# o resto (0.60) é a ROM; se o emulador já existe, a ROM ocupa a barra toda.


def clean_pyinstaller_env(env) -> dict:
    """Cópia do ambiente sem as variáveis internas do PyInstaller.
    Sem isso o app novo, aberto pelo instalador, herda as do app antigo, acha que deve usar a pasta temporária
    dele (já apagada) e falha com "Failed to load Python DLL / não foi possível encontrar o módulo"."""
    clean = {k: v for k, v in env.items() if not (k.startswith("_PYI") or k.startswith("_MEIPASS"))}
    clean["PYINSTALLER_RESET_ENVIRONMENT"] = "1"   # o carregador do app novo trata a abertura como nova
    return clean


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
        self._update_info: dict = {}           # última release achada por check_update()
        self._update = {"state": "idle"}        # andamento da atualização: idle | downloading | installing | error
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

    def check_update(self) -> dict:
        """Pergunta ao GitHub se há versão nova (a interface mostra um aviso no topo).
        'can_install' diz se dá para atualizar de dentro do app (só no .exe instalado, não rodando pelo código)."""
        info = updates.check()
        self._update_info = info
        return {k: v for k, v in info.items() if not k.startswith("asset_")} | {
            "can_install": bool(info.get("asset_url")) and bool(getattr(sys, "frozen", False))}

    def install_update(self) -> dict:
        """Baixa o instalador da versão nova (numa thread), abre-o e fecha o app. Acompanhe com get_update_status().
        O endereço vem do que o próprio Python achou no GitHub, nunca de texto vindo da interface."""
        info = self._update_info
        if not (info.get("asset_url") and getattr(sys, "frozen", False)):
            return {"error": "Não dá para atualizar por aqui. Baixe a versão nova na página da release."}
        with self._lock:
            if self._running:   # o app fecha ao atualizar e não conseguiria fazer o backup do save depois de jogar
                return {"error": "Feche o jogo aberto no emulador antes de atualizar."}
            if self._update["state"] in ("downloading", "installing"):
                return {"ok": True}
            self._update = {"state": "downloading", "done": 0, "total": 0}
        threading.Thread(target=self._run_update, args=(dict(info),), daemon=True).start()
        return {"ok": True}

    def get_update_status(self) -> dict:
        with self._lock:
            return dict(self._update)

    def _run_update(self, info: dict) -> None:
        def progress(done: int, total: int) -> None:
            with self._lock:
                self._update.update(done=done, total=total)
        try:
            installer = updates.download_installer(info["asset_url"], info["asset_name"], progress)
            with self._lock:
                self._update = {"state": "installing"}
            self._start_installer_after_exit(installer)
        except (updates.UpdateError, OSError) as exc:
            with self._lock:
                self._update = {"state": "error", "error": str(exc) or "Não consegui instalar a atualização."}
            return
        time.sleep(1.5)   # dá tempo da interface mostrar "Instalando…" antes de o app fechar
        self._quit_app()

    @staticmethod
    def _start_installer_after_exit(installer: Path) -> None:
        """Deixa um PowerShell escondido esperando o app sair de vez e só então abre o instalador.
        O instalador precisa trocar o .exe; se rodasse já, ainda o encontraria em uso e desistiria.
        No .exe de arquivo único há dois processos (o carregador e o app): esperamos pelos dois."""
        pids = {os.getpid(), os.getppid()}
        quoted = str(installer).replace("'", "''")
        script = (f"Wait-Process -Id {','.join(map(str, sorted(pids)))} -Timeout 30 -ErrorAction SilentlyContinue; "
                  # /SILENT: sem perguntas, instala por cima e reabre o app no fim.
                  f"Start-Process -FilePath '{quoted}' -ArgumentList '/SILENT'")
        # sem DETACHED_PROCESS: com ele o PowerShell escondido sai na hora sem fazer nada
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         creationflags=flags, close_fds=True, env=clean_pyinstaller_env(os.environ))

    @staticmethod
    def _quit_app() -> None:
        """Fecha o app do jeito normal (fechar a janela). os._exit deixava o carregador do .exe vivo, segurando o arquivo."""
        try:
            import webview
            for window in list(webview.windows):
                window.destroy()
        except Exception:
            pass
        time.sleep(8)   # ainda aqui: algo travou o fechamento normal, então encerra à força
        if getattr(sys, "frozen", False):   # tira também o carregador (processo pai do .exe de arquivo único)
            subprocess.run(["taskkill", "/F", "/PID", str(os.getppid())], capture_output=True)
        os._exit(0)

    @staticmethod
    def open_url(url: str) -> dict:
        """Abre a página da versão nova no navegador. Só aceita links do GitHub do projeto."""
        import webbrowser

        from .version import GITHUB_REPO
        if not url.startswith(f"https://github.com/{GITHUB_REPO}/"):
            return {"error": "Link não permitido."}
        webbrowser.open(url)
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
        except Exception as exc:  # qualquer falha vira "sem capa", mas fica anotada no log
            downloader._log_image_error(game_id, exc)
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

    def play(self, game_id: str, state: str | None = None) -> dict:
        """Backup do save, abre o jogo no emulador e acompanha em uma thread até ele fechar.
        Com `state` (nome de um save state da lista), o emulador já abre carregando esse state."""
        try:
            emu, game = self._find(game_id)
            state_path = saves.find_state(emu, game, state).path if state else None
            if state_path and not emu.state_args:
                return {"error": f"O catálogo não diz como abrir um save state no {emu.name}."}
            if game_id in self._running:
                return {"error": f"{game.title} já está aberto."}
            warning = None
            try:
                saves.backup_now(emu, game, "antes-de-jogar")
            except saves.SaveError as exc:  # sem backup o jogo ainda abre, mas o usuário fica sabendo
                warning = f"Não consegui fazer o backup antes de jogar: {exc}"
            with self._lock:
                if game_id in self._running:
                    return {"error": f"{game.title} já está aberto."}
                proc = launcher.launch(emu, game, state_path)
                self._running.add(game_id)
        except (catalog.CatalogError, launcher.LaunchError, saves.SaveError) as exc:
            return {"error": str(exc)}
        threading.Thread(target=self._watch, args=(emu, game, proc), daemon=True).start()
        return {"ok": True, "warning": warning} if warning else {"ok": True}

    def _watch(self, emu, game, proc) -> None:
        started = time.monotonic()
        code = proc.wait()
        message = None
        try:  # o jogo ainda conta como "aberto" até o backup terminar: ninguém troca o save no meio
            saves.backup_now(emu, game, "depois-de-jogar")
        except saves.SaveError as exc:
            message = f"Não consegui fazer o backup depois de jogar: {exc}"
        with self._lock:
            self._running.discard(game.id)
            if code != 0 and time.monotonic() - started < 5:
                message = (f"O {emu.name} fechou logo ao abrir (código {code}). "
                           "Confira se a ROM não está corrompida.")
            if message:
                self._play_errors[game.id] = message

    def get_running(self) -> dict:
        """Jogos abertos agora e avisos/erros de abertura (entregues uma vez)."""
        with self._lock:
            errors, self._play_errors = self._play_errors, {}
            return {"running": sorted(self._running), "errors": errors}

    # ---------- saves ----------

    def _saves_action(self, game_id: str, action, needs_closed: bool = False) -> dict:
        """Roda action(emu, game) e converte erros esperados em {"error": ...}.
        needs_closed: ações que trocam/apagam o save não rodam com o jogo aberto, porque o emulador
        grava o save de novo ao fechar e desfaria a troca."""
        try:
            emu, game = self._find(game_id)
            if needs_closed and game_id in self._running:
                return {"error": "Feche o jogo no emulador antes de continuar."}
            return action(emu, game) or {"ok": True}
        except (catalog.CatalogError, saves.SaveError, downloader.DownloadError) as exc:
            return {"error": str(exc)}

    def get_saves(self, game_id: str) -> dict:
        """Tudo da tela de saves de um jogo: save atual, lista de backups e se o jogo está aberto."""
        def action(emu, game):
            return {
                "game": {"id": game.id, "title": game.title, "subtitle": game.subtitle,
                         "ready": downloader.is_game_ready(emu, game),
                         "has_rom": downloader.rom_path(game).is_file()},
                "emulator": {"id": emu.id, "name": emu.name},
                "save": saves.save_info(emu, game),
                "states": [{"name": s.name, "slot": s.slot, "modified": s.modified, "size": s.size}
                           for s in saves.list_states(emu, game)],
                "can_play_state": bool(emu.state_args),
                "running": game.id in self._running,
            }
        return self._saves_action(game_id, action)

    def delete_state(self, game_id: str, name: str) -> dict:
        """Apaga um save state (a interface confirma antes). Com o jogo aberto não, o emulador pode regravá-lo."""
        return self._saves_action(game_id, lambda emu, game: saves.delete_state(emu, game, name), needs_closed=True)

    def backup_save(self, game_id: str) -> dict:
        def action(emu, game):
            if saves.backup_now(emu, game, "manual"):
                return {"ok": True, "created": True}
            exists = saves.save_info(emu, game)["exists"]
            return {"ok": True, "created": False, "why": "igual" if exists else "sem-save"}
        return self._saves_action(game_id, action)

    def restore_backup(self, game_id: str, name: str, play: bool = False) -> dict:
        """Troca o save atual pelo backup (guardando o atual antes). Com play=True já abre o jogo."""
        def action(emu, game):
            saves.restore(emu, game, name)
            return {"ok": True}
        result = self._saves_action(game_id, action, needs_closed=True)
        if play and result.get("ok"):
            played = self.play(game_id)
            if "error" in played:
                result["play_error"] = played["error"]
            elif "warning" in played:
                result["play_error"] = played["warning"]
        return result

    def delete_backup(self, game_id: str, name: str) -> dict:
        return self._saves_action(game_id, lambda emu, game: saves.delete_backup(game, name))

    def delete_save(self, game_id: str) -> dict:
        return self._saves_action(game_id, lambda emu, game: saves.delete_save(emu, game), needs_closed=True)

    def delete_game(self, game_id: str) -> dict:
        """Exclui a ROM do PC. Saves e backups continuam guardados."""
        def action(emu, game):
            with self._lock:
                downloading = game_id in self._jobs
            if downloading:
                raise downloader.DownloadError("Espere o download terminar, ou cancele-o, antes de excluir.")
            downloader.delete_rom(game)
        return self._saves_action(game_id, action, needs_closed=True)

    @staticmethod
    def _file_dialog(kind, **options) -> Path | None:
        """Janela do Windows para escolher/salvar arquivo. None se o usuário cancelar."""
        import webview
        if not webview.windows:
            raise saves.SaveError("A janela do app não está disponível.")
        result = webview.windows[0].create_file_dialog(kind, **options)
        if isinstance(result, (list, tuple)):  # abrir devolve uma lista; salvar, um texto
            result = result[0] if result else None
        return Path(result) if result else None

    def pick_import_file(self) -> dict:
        """Passo 1 de importar: o usuário escolhe o .sav. A importação em si vem depois da confirmação."""
        import webview
        try:
            path = self._file_dialog(webview.FileDialog.OPEN,
                                     file_types=("Save de jogo (*.sav;*.srm)", "Todos os arquivos (*.*)"))
        except saves.SaveError as exc:
            return {"error": str(exc)}
        return {"path": str(path)} if path else {"cancelled": True}

    def import_save(self, game_id: str, path: str) -> dict:
        return self._saves_action(game_id, lambda emu, game: saves.import_save(emu, game, Path(path)),
                                  needs_closed=True)

    def export_save(self, game_id: str) -> dict:
        def action(emu, game):
            import webview
            if saves.current_save(emu, game) is None:
                raise saves.SaveError("Esse jogo ainda não tem save para exportar.")
            target = saves.save_path(emu, game)
            dest = self._file_dialog(webview.FileDialog.SAVE, save_filename=target.name,
                                     file_types=(f"Save de jogo (*{target.suffix})", "Todos os arquivos (*.*)"))
            if dest is None:
                return {"cancelled": True}
            saves.export_save(emu, game, dest)
            return {"ok": True, "path": str(dest)}
        return self._saves_action(game_id, action)
