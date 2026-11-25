"""Testes da atualização pelo GitHub (sem internet: o download é simulado)."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import updates
from app.version import GITHUB_REPO

NAME = "Instalar-GerenciadorEmuladores-9.9.9.exe"
URL = f"https://github.com/{GITHUB_REPO}/releases/download/v9.9.9/{NAME}"


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, final_url: str = "https://objects.githubusercontent.com/x"):
        super().__init__(data)
        self._url = final_url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class UpdatesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        p = mock.patch.object(tempfile, "gettempdir", return_value=tmp)
        p.start()
        self.addCleanup(p.stop)
        self.tmp = Path(tmp)

    def download(self, data: bytes, size: int | None = None, **fake):
        with mock.patch.object(updates.urllib.request, "urlopen", return_value=FakeResponse(data, **fake)):
            return updates.download_installer(URL, NAME, len(data) if size is None else size)

    def test_compara_versoes(self):
        self.assertTrue(updates.is_newer("v1.10.0", "1.9.9"))
        self.assertFalse(updates.is_newer("1.1.3", "1.1.3"))

    def test_baixa_e_guarda_o_instalador(self):
        path = self.download(b"MZ" + b"x" * 100)
        self.assertEqual(path.name, NAME)
        self.assertEqual(path.read_bytes()[:2], b"MZ")
        self.assertEqual([p.name for p in path.parent.iterdir()], [NAME])   # sem sobra do .part

    def test_recusa_download_incompleto(self):
        with self.assertRaises(updates.UpdateError):
            self.download(b"MZ" + b"x" * 10, size=500)
        self.assertEqual(list((self.tmp / "GerenciadorEmuladores-update").iterdir()), [])  # nada fica pela metade

    def test_recusa_arquivo_que_nao_e_exe(self):
        with self.assertRaises(updates.UpdateError):
            self.download(b"<html>erro</html>")

    def test_recusa_endereco_fora_da_release(self):
        with self.assertRaises(updates.UpdateError):
            updates.download_installer("https://exemplo.com/" + NAME, NAME, 10)
        with self.assertRaises(updates.UpdateError):
            updates.download_installer(URL, "malware.exe", 10)

    def test_recusa_redirecionamento_para_outro_dominio(self):
        with self.assertRaises(updates.UpdateError):
            self.download(b"MZ" + b"x" * 10, final_url="https://site-estranho.com/a.exe")

    def test_acha_o_instalador_na_release(self):
        assets = [{"name": "GerenciadorEmuladores.exe", "browser_download_url": URL, "size": 5},
                  {"name": NAME, "browser_download_url": URL, "size": 5}]
        self.assertEqual(updates._find_installer(assets)["name"], NAME)
        self.assertIsNone(updates._find_installer([{"name": NAME, "browser_download_url": "https://x.com/a", "size": 5}]))


if __name__ == "__main__":
    unittest.main()
