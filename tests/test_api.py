"""Testes da camada Api para excluir jogo (usam pastas temporárias; nada toca no AppData real)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import paths
from app.api import Api

GAME = "pokemon-firered-ptbr"   # existe no catalog.json do projeto


class DeleteGameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.multiple(paths, EMULATORS_DIR=self.tmp / "emulators", GAMES_DIR=self.tmp / "games",
                                BACKUPS_DIR=self.tmp / "backups", CATALOG_CACHE=self.tmp / "sem-cache.json")
        p.start()
        self.addCleanup(p.stop)
        self.folder = paths.GAMES_DIR / GAME
        self.folder.mkdir(parents=True)
        self.rom = self.folder / "firered.gba"
        self.rom.write_bytes(b"rom")
        (self.folder / "firered.sav").write_bytes(b"progresso")
        (self.folder / "cover.jpg").write_bytes(b"capa")
        self.api = Api()

    def test_exclui_so_a_rom_e_mantem_save_e_capa(self):
        self.assertEqual(self.api.delete_game(GAME), {"ok": True})
        self.assertFalse(self.rom.exists())
        self.assertEqual((self.folder / "firered.sav").read_bytes(), b"progresso")
        self.assertTrue((self.folder / "cover.jpg").exists())

    def test_segunda_exclusao_da_erro_claro(self):
        self.api.delete_game(GAME)
        self.assertIn("error", self.api.delete_game(GAME))

    def test_bloqueado_com_o_jogo_aberto(self):
        self.api._running.add(GAME)
        self.assertIn("error", self.api.delete_game(GAME))
        self.assertTrue(self.rom.exists())

    def test_bloqueado_durante_download(self):
        self.api._jobs[GAME] = {"finished": False}
        self.assertIn("error", self.api.delete_game(GAME))
        self.assertTrue(self.rom.exists())

    def test_jogo_inexistente(self):
        self.assertIn("error", self.api.delete_game("nao-existe"))

    def test_tela_de_saves_informa_se_a_rom_existe(self):
        self.assertTrue(self.api.get_saves(GAME)["game"]["has_rom"])
        self.api.delete_game(GAME)
        self.assertFalse(self.api.get_saves(GAME)["game"]["has_rom"])


if __name__ == "__main__":
    unittest.main()
