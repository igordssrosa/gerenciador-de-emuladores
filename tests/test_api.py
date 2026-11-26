"""Testes da camada Api para excluir jogo (usam pastas temporárias; nada toca no AppData real)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import catalog, paths
from app.api import Api, clean_pyinstaller_env

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


class PyInstallerEnvTests(unittest.TestCase):
    def test_remove_variaveis_do_pyinstaller_e_mantem_o_resto(self):
        env = {"PATH": "x", "_PYI_APPLICATION_HOME_DIR": "C:/t/_MEI1", "_PYI_ARCHIVE_FILE": "a", "_MEIPASS2": "b", "TEMP": "t"}
        clean = clean_pyinstaller_env(env)
        self.assertEqual(clean["PATH"], "x")
        self.assertEqual(clean["TEMP"], "t")
        self.assertFalse(any(k.startswith(("_PYI", "_MEIPASS")) for k in clean))
        self.assertEqual(clean["PYINSTALLER_RESET_ENVIRONMENT"], "1")


class ControlsApiTests(unittest.TestCase):
    """Popup de controles: get_controls / save_controls (emulador e catálogo de mentira, em pasta temporária)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.multiple(paths, EMULATORS_DIR=self.tmp / "emulators", GAMES_DIR=self.tmp / "games",
                                BACKUPS_DIR=self.tmp / "backups", CATALOG_CACHE=self.tmp / "sem-cache.json")
        p.start()
        self.addCleanup(p.stop)
        self.emu_dir = paths.EMULATORS_DIR / "emu"
        self.config = self.emu_dir / "config.ini"
        self.api = Api()
        self.api._catalog = catalog.parse({"emulators": [
            {"id": "emu", "name": "Emu", "executable": "emu.exe", "args": ["{rom}"],
             "games": [{"id": "g", "title": "G", "rom": {"file_id": "x", "filename": "g.gba"}}],
             "controls": {"file": "config.ini", "format": "ini", "section": "s", "key_encoding": "qt",
                          "buttons": [{"id": "A", "label": "A", "group": "face", "key": "keyA", "default": "KeyK"},
                                      {"id": "B", "label": "B", "group": "face", "key": "keyB", "default": "KeyJ"}]}},
            {"id": "sem", "name": "Sem", "executable": "sem.exe", "args": ["{rom}"]}]})

    def install(self, text="[s]\nkeyA=75\n"):
        self.emu_dir.mkdir(parents=True)
        (self.emu_dir / "emu.exe").write_bytes(b"exe")
        self.config.write_text(text, encoding="utf-8")

    def test_indisponivel_sem_o_campo(self):
        self.assertFalse(self.api.get_controls("sem")["available"])

    def test_nao_instalado_nao_lista_botoes(self):
        res = self.api.get_controls("emu")
        self.assertEqual((res["available"], res["installed"], res["buttons"]), (True, False, []))

    def test_le_o_arquivo(self):
        self.install()
        res = self.api.get_controls("emu")
        self.assertEqual((res["installed"], res["running"]), (True, False))
        a, b = res["buttons"]
        self.assertEqual((a["id"], a["label"], a["group"], a["code"], a["display"], a["default_code"]),
                         ("A", "A", "face", "KeyK", "K", "KeyK"))
        self.assertEqual((b["code"], b["display"], b["default_code"]), (None, "", "KeyJ"))

    def test_salva_no_arquivo(self):
        self.install()
        self.assertEqual(self.api.save_controls("emu", {"A": "KeyL", "B": "KeyJ"}), {"ok": True})
        self.assertEqual(self.config.read_text(encoding="utf-8"), "[s]\nkeyA=76\nkeyB=74\n")

    def test_bloqueado_com_o_jogo_aberto(self):
        self.install()
        self.api._running.add("g")
        self.assertTrue(self.api.get_controls("emu")["running"])
        self.assertIn("error", self.api.save_controls("emu", {"A": "KeyL"}))
        self.assertEqual(self.config.read_text(encoding="utf-8"), "[s]\nkeyA=75\n")

    def test_mapeamento_invalido_da_erro_e_nao_grava(self):
        self.install()
        self.assertIn("error", self.api.save_controls("emu", {"A": "KeyL", "B": "KeyL"}))
        self.assertEqual(self.config.read_text(encoding="utf-8"), "[s]\nkeyA=75\n")

    def test_nao_instalado_nao_salva(self):
        self.assertIn("error", self.api.save_controls("emu", {"A": "KeyL"}))
        self.assertFalse(self.config.exists())

    def test_emulador_inexistente_ou_sem_controls_da_erro(self):
        self.assertIn("error", self.api.save_controls("nao-existe", {}))
        self.assertIn("error", self.api.save_controls("sem", {}))

    def test_biblioteca_informa_has_controls(self):
        flags = {e["id"]: e["has_controls"] for e in self.api.get_library()["emulators"]}
        self.assertEqual(flags, {"emu": True, "sem": False})
