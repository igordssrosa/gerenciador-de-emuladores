"""Testes offline do downloader (não usam a internet). Rodar: python -m unittest discover tests"""
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import py7zr

from app import catalog, downloader, paths


def fake_emulator(**kw):
    raw = {"emulators": [{"id": "emu", "name": "Emu", "executable": "emu.exe",
                          "args": ["{rom}"], "download": {"file_id": "x", "type": kw.get("type", "zip")},
                          "setup_files": {"portable.ini": ""}}]}
    return catalog.parse(raw).emulators[0]


class DownloaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = mock.patch.multiple(paths, EMULATORS_DIR=self.tmp / "emulators", GAMES_DIR=self.tmp / "games")
        p.start()
        self.addCleanup(p.stop)

    def _install(self, emu, builder):
        """Roda ensure_emulator com um download_file falso que cria o pacote com `builder`."""
        def fake_download(file_id, dest, on_progress=None, cancel=None):
            builder(dest)
            return dest
        with mock.patch.object(downloader, "download_file", fake_download):
            return downloader.ensure_emulator(emu)

    def test_zip_com_pasta_unica_e_setup_files(self):
        def build(dest):
            with zipfile.ZipFile(dest, "w") as z:
                z.writestr("pacote-1.0/emu.exe", "x")
        exe = self._install(fake_emulator(), build)
        self.assertTrue(exe.is_file())  # a pasta 'pacote-1.0' foi achatada
        self.assertTrue((exe.parent / "portable.ini").is_file())

    def test_7z(self):
        def build(dest):
            src = self.tmp / "src"; src.mkdir(exist_ok=True)
            (src / "emu.exe").write_text("x")
            with py7zr.SevenZipFile(dest, "w") as z:
                z.write(src / "emu.exe", "emu.exe")
        self.assertTrue(self._install(fake_emulator(type="7z"), build).is_file())

    def test_zip_slip_e_bloqueado(self):
        def build(dest):
            with zipfile.ZipFile(dest, "w") as z:
                z.writestr("../fora.txt", "x")
        with self.assertRaises(downloader.DownloadError):
            self._install(fake_emulator(), build)
        self.assertFalse((self.tmp / "fora.txt").exists())

    def test_pacote_sem_executavel_nao_instala(self):
        def build(dest):
            with zipfile.ZipFile(dest, "w") as z:
                z.writestr("outro.exe", "x")
        emu = fake_emulator()
        with self.assertRaises(downloader.DownloadError):
            self._install(emu, build)
        self.assertFalse(downloader.emulator_dir(emu).exists())

    def test_id_do_drive_vazio(self):
        with self.assertRaises(downloader.DownloadError):
            downloader.download_file("", self.tmp / "a.bin")

    def test_catalogo_rejeita_id_com_caminho(self):
        with self.assertRaises(catalog.CatalogError):
            catalog.parse({"emulators": [{"id": "../x", "name": "X", "executable": "x", "args": ["{rom}"]}]})


class ErrosSemLinkTest(unittest.TestCase):
    def test_erro_nao_mostra_link_nem_id_do_drive(self):
        msg = downloader.friendly_download_error(
            RuntimeError("falhou https://drive.google.com/uc?id=ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"))
        self.assertNotIn("drive.google.com", msg)
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZ123456", msg)


if __name__ == "__main__":
    unittest.main()


class FriendlyErrorTests(unittest.TestCase):
    def test_mensagens_amigaveis(self):
        f = downloader.friendly_download_error
        self.assertIn("espaço", f(OSError(28, "No space left on device")))
        self.assertIn("limitou", f(Exception("Too many users have viewed or downloaded this file recently")))
        self.assertIn("internet", f(Exception("Connection aborted")))
        self.assertIn("Não consegui baixar", f(Exception("algo estranho")))
