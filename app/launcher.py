"""Abre um jogo no emulador certo, usando só o que está no catálogo (executável + argumentos)."""
import subprocess
import threading
from pathlib import Path

from . import downloader, winmode
from .catalog import Emulator, Game


class LaunchError(Exception):
    """Não foi possível abrir o jogo (a mensagem é mostrada ao usuário)."""


def build_command(emu: Emulator, game: Game, state: Path | None = None) -> list[str]:
    """Monta a linha de comando: [executável, *args], trocando {rom} pelo caminho da ROM.
    Com `state` (e state_args no catálogo), usa os state_args e troca {state} pelo caminho do save state.
    Cada argumento é um item da lista, então espaços no caminho não precisam de aspas."""
    rom = str(downloader.rom_path(game))
    if state is not None and emu.state_args:
        args = [a.replace("{state}", str(state)) for a in emu.state_args]
    else:
        args = emu.args
    return [str(downloader.emulator_exe(emu))] + [arg.replace("{rom}", rom) for arg in args]


def launch(emu: Emulator, game: Game, state: Path | None = None) -> subprocess.Popen:
    """Abre o emulador com a ROM e devolve o processo (quem chamou pode esperar ele fechar)."""
    if not downloader.is_emulator_installed(emu):
        raise LaunchError(f"O {emu.name} não está instalado. Baixe o jogo primeiro.")
    if not downloader.rom_path(game).is_file():
        raise LaunchError(f"A ROM de {game.title} não foi encontrada. Baixe o jogo de novo.")
    try:
        # cwd = pasta do emulador: é lá que ficam portable.ini e a configuração dele.
        # Sem shell=True: a lista de argumentos vai direto ao programa.
        proc = subprocess.Popen(build_command(emu, game, state), cwd=downloader.emulator_dir(emu))
    except OSError as exc:
        raise LaunchError(f"Não consegui abrir o {emu.name}: {exc.strerror or exc}. "
                          "Se o antivírus ou o Windows bloqueou, libere o arquivo.") from exc
    if emu.window_mode == "borderless":
        # numa thread: espera a janela aparecer sem travar o app
        threading.Thread(target=winmode.make_borderless, args=(proc.pid,), daemon=True).start()
    return proc
