"""Testes do launcher com um emulador falso (.bat que grava os argumentos recebidos)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import catalog, launcher, paths


def make_catalog(args):
    raw = {"emulators": [{
        "id": "fake", "name": "Fake", "executable": "fake.bat", "args": args,
        "games": [{"id": "jogo", "title": "Jogo", "rom": {"file_id": "x", "filename": "jogo teste.gba"}}]}]}
    emu = catalog.parse(raw).emulators[0]
    return emu, emu.games[0]


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.multiple(paths, EMULATORS_DIR=self.tmp / "emulators", GAMES_DIR=self.tmp / "games")
        p.start()
        self.addCleanup(p.stop)

    def _install(self, emu, game):
        (paths.EMULATORS_DIR / emu.id).mkdir(parents=True)
        # %1 e %2 são os dois primeiros argumentos; "cd" grava a pasta de trabalho
        (paths.EMULATORS_DIR / emu.id / "fake.bat").write_text(
            '@echo off\r\n(echo ARG1=%~1& echo ARG2=%~2& cd) > "%~dp0saida.txt"\r\n', encoding="utf-8")
        (paths.GAMES_DIR / game.id).mkdir(parents=True)
        (paths.GAMES_DIR / game.id / game.rom_filename).write_bytes(b"rom")

    def test_rom_substituida_e_args_separados(self):
        emu, game = make_catalog(["-f", "{rom}"])
        cmd = launcher.build_command(emu, game)
        self.assertEqual(cmd[1], "-f")
        self.assertTrue(cmd[2].endswith("jogo teste.gba"))   # espaço no nome continua um argumento só
        self.assertEqual(len(cmd), 3)

    def test_com_state_usa_state_args(self):
        raw = {"emulators": [{"id": "fake", "name": "Fake", "executable": "fake.bat", "args": ["{rom}"],
                              "state_extensions": [".ss1"], "state_args": ["-t", "{state}", "{rom}"],
                              "games": [{"id": "jogo", "title": "Jogo", "rom": {"file_id": "x", "filename": "jogo.gba"}}]}]}
        emu = catalog.parse(raw).emulators[0]
        cmd = launcher.build_command(emu, emu.games[0], Path("C:/x y/jogo.ss1"))
        self.assertEqual(cmd[1], "-t")
        self.assertEqual(cmd[2], str(Path("C:/x y/jogo.ss1")))
        self.assertTrue(cmd[3].endswith("jogo.gba"))
        self.assertEqual(len(launcher.build_command(emu, emu.games[0])), 2)   # sem state: só a ROM

    def test_state_args_sem_marcador_e_rejeitado(self):
        raw = {"emulators": [{"id": "f", "name": "F", "executable": "f.bat", "args": ["{rom}"], "state_args": ["{rom}"],
                              "games": []}]}
        with self.assertRaises(catalog.CatalogError):
            catalog.parse(raw)

    def test_abre_com_argumentos_e_pasta_do_emulador(self):
        emu, game = make_catalog(["-f", "{rom}"])
        self._install(emu, game)
        self.assertEqual(launcher.launch(emu, game).wait(timeout=20), 0)
        out = (paths.EMULATORS_DIR / "fake" / "saida.txt").read_text().splitlines()
        self.assertEqual(out[0], "ARG1=-f")
        self.assertTrue(out[1].endswith("jogo teste.gba"))
        self.assertEqual(Path(out[2]).resolve(), (paths.EMULATORS_DIR / "fake").resolve())

    def test_erros_claros(self):
        emu, game = make_catalog(["{rom}"])
        with self.assertRaises(launcher.LaunchError):      # emulador não instalado
            launcher.launch(emu, game)
        self._install(emu, game)
        downloader_rom = paths.GAMES_DIR / game.id / game.rom_filename
        downloader_rom.unlink()
        with self.assertRaises(launcher.LaunchError):      # ROM sumiu
            launcher.launch(emu, game)


if __name__ == "__main__":
    unittest.main()
