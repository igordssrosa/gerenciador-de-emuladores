"""Testes de saves e backups (usam pastas temporárias; nada toca no AppData real)."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from app import catalog, paths, saves


class SavesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.multiple(paths, EMULATORS_DIR=self.tmp / "emulators", GAMES_DIR=self.tmp / "games",
                                BACKUPS_DIR=self.tmp / "backups")
        p.start()
        self.addCleanup(p.stop)
        raw = {"emulators": [{"id": "e", "name": "E", "executable": "e.exe", "args": ["{rom}"],
                              "save_extensions": [".sav"],
                              "games": [{"id": "g", "title": "G", "rom": {"file_id": "x", "filename": "jogo.gba"}}]}]}
        self.emu = catalog.parse(raw).emulators[0]
        self.game = self.emu.games[0]
        self.save = saves.save_path(self.emu, self.game)

    def write_save(self, data: bytes):
        self.save.parent.mkdir(parents=True, exist_ok=True)
        self.save.write_bytes(data)

    def test_save_fica_ao_lado_da_rom_com_o_nome_dela(self):
        self.assertEqual(self.save.name, "jogo.sav")

    def test_sem_save_nao_ha_backup(self):
        self.assertIsNone(saves.backup_now(self.emu, self.game, "manual"))
        self.assertFalse(saves.save_info(self.emu, self.game)["exists"])

    def test_backup_so_quando_mudou(self):
        self.write_save(b"A" * 100)
        self.assertIsNotNone(saves.backup_now(self.emu, self.game, "antes-de-jogar"))
        self.assertIsNone(saves.backup_now(self.emu, self.game, "depois-de-jogar"))   # igual: não duplica
        self.write_save(b"B" * 100)
        self.assertIsNotNone(saves.backup_now(self.emu, self.game, "depois-de-jogar"))
        self.assertEqual(len(saves.list_backups(self.game)), 2)

    def test_mantem_so_10_automaticos_e_nunca_apaga_manuais(self):
        self.write_save(b"manual")
        saves.backup_now(self.emu, self.game, "manual")
        for i in range(14):
            self.write_save(f"auto{i}".encode())
            saves.backup_now(self.emu, self.game, "depois-de-jogar")
        backups = saves.list_backups(self.game)
        self.assertEqual(sum(b.auto for b in backups), 10)
        self.assertEqual(sum(not b.auto for b in backups), 1)   # o manual sobreviveu
        self.assertTrue(backups[0].auto and backups[0].path.read_bytes() == b"auto13")  # mais novo primeiro

    def test_restaurar_guarda_o_save_atual_antes(self):
        self.write_save(b"VELHO")
        old = saves.backup_now(self.emu, self.game, "manual")
        self.write_save(b"NOVO-PROGRESSO")
        saves.restore(self.emu, self.game, old.name)
        self.assertEqual(self.save.read_bytes(), b"VELHO")
        reasons = [b.reason for b in saves.list_backups(self.game)]
        self.assertIn("antes-de-restaurar", reasons)
        safety = next(b for b in saves.list_backups(self.game) if b.reason == "antes-de-restaurar")
        self.assertEqual(safety.path.read_bytes(), b"NOVO-PROGRESSO")   # o progresso não se perdeu

    def test_importar_guarda_o_atual_e_valida_o_arquivo(self):
        self.write_save(b"ATUAL")
        outside = self.tmp / "de-fora.sav"
        outside.write_bytes(b"IMPORTADO")
        saves.import_save(self.emu, self.game, outside)
        self.assertEqual(self.save.read_bytes(), b"IMPORTADO")
        self.assertEqual(saves.list_backups(self.game)[0].path.read_bytes(), b"ATUAL")
        vazio = self.tmp / "vazio.sav"; vazio.write_bytes(b"")
        grande = self.tmp / "grande.sav"; grande.write_bytes(b"x" * (saves.MAX_SAVE_BYTES + 1))
        for ruim in (vazio, grande, self.tmp / "nao-existe.sav"):
            with self.assertRaises(saves.SaveError):
                saves.import_save(self.emu, self.game, ruim)
        self.assertEqual(self.save.read_bytes(), b"IMPORTADO")      # falhas não mexem no save

    def test_importar_sem_save_atual(self):
        outside = self.tmp / "novo.sav"; outside.write_bytes(b"NOVO")
        saves.import_save(self.emu, self.game, outside)
        self.assertEqual(self.save.read_bytes(), b"NOVO")
        self.assertEqual(saves.list_backups(self.game), [])

    def test_save_em_branco_nao_gera_backup(self):
        for blank in (b"\xff" * 131072, b"\x00" * 64):
            self.write_save(blank)
            self.assertTrue(saves.save_info(self.emu, self.game)["blank"])
            self.assertIsNone(saves.backup_now(self.emu, self.game, "antes-de-jogar"))
        self.write_save(b"\xff" * 100 + b"x")   # com um byte de progresso, já não é em branco
        self.assertFalse(saves.save_info(self.emu, self.game)["blank"])
        self.assertIsNotNone(saves.backup_now(self.emu, self.game, "manual"))

    def test_exportar(self):
        with self.assertRaises(saves.SaveError):
            saves.export_save(self.emu, self.game, self.tmp / "x.sav")
        self.write_save(b"DADOS")
        saves.export_save(self.emu, self.game, self.tmp / "saida.sav")
        self.assertEqual((self.tmp / "saida.sav").read_bytes(), b"DADOS")

    def test_apagar_save_faz_backup_e_da_para_desfazer(self):
        self.write_save(b"PRECIOSO")
        saves.delete_save(self.emu, self.game)
        self.assertFalse(self.save.exists())
        backup = saves.list_backups(self.game)[0]
        self.assertEqual(backup.reason, "antes-de-apagar")
        saves.restore(self.emu, self.game, backup.name)
        self.assertEqual(self.save.read_bytes(), b"PRECIOSO")

    def test_apagar_backup(self):
        self.write_save(b"A")
        b = saves.backup_now(self.emu, self.game, "manual")
        saves.delete_backup(self.game, b.name)
        self.assertEqual(saves.list_backups(self.game), [])

    def test_nomes_perigosos_sao_recusados(self):
        self.write_save(b"A")
        saves.backup_now(self.emu, self.game, "manual")
        (self.tmp / "segredo.sav").write_bytes(b"nao mexa")
        for nome in ("..\\..\\segredo.sav", "../../segredo.sav", "naoexiste.sav"):
            with self.assertRaises(saves.SaveError):
                saves.restore(self.emu, self.game, nome)
            with self.assertRaises(saves.SaveError):
                saves.delete_backup(self.game, nome)
        self.assertTrue((self.tmp / "segredo.sav").exists())

    def test_dois_backups_no_mesmo_segundo(self):
        for i in range(3):
            self.write_save(f"v{i}".encode())
            saves.backup_now(self.emu, self.game, "manual")
        names = [b.name for b in saves.list_backups(self.game)]
        self.assertEqual(len(set(names)), 3)
        newest = saves.list_backups(self.game)[0]
        self.assertEqual(newest.path.read_bytes(), b"v2")


if __name__ == "__main__":
    unittest.main()
