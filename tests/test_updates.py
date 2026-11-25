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
    def __init__(self, data: bytes, final_url: str = "https://objects.githubusercontent.com/x", length: int | None = None):
        super().__init__(data)
        self._url = final_url
        self.headers = {} if length == 0 else {"Content-Length": str(len(data) if length is None else length)}

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

    def download(self, data: bytes, **fake):
        with mock.patch.object(updates.urllib.request, "urlopen", return_value=FakeResponse(data, **fake)):
            return updates.download_installer(URL, NAME)

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
            self.download(b"MZ" + b"x" * 10, length=500)   # o GitHub prometeu 500 bytes e vieram 12
        self.assertEqual(list((self.tmp / "GerenciadorEmuladores-update").iterdir()), [])  # nada fica pela metade

    def test_recusa_arquivo_que_nao_e_exe(self):
        with self.assertRaises(updates.UpdateError):
            self.download(b"<html>erro</html>")

    def test_recusa_download_sem_tamanho_informado(self):
        with self.assertRaises(updates.UpdateError):
            self.download(b"MZ" + b"x" * 10, length=0)

    def test_recusa_endereco_fora_da_release(self):
        with self.assertRaises(updates.UpdateError):
            updates.download_installer("https://exemplo.com/" + NAME, NAME)
        with self.assertRaises(updates.UpdateError):
            updates.download_installer(URL, "malware.exe")

    def test_recusa_redirecionamento_para_outro_dominio(self):
        with self.assertRaises(updates.UpdateError):
            self.download(b"MZ" + b"x" * 10, final_url="https://site-estranho.com/a.exe")

    def check(self, final_url: str | None, local: str = "1.1.3"):
        """check() com o redirecionamento de /releases/latest simulado (sem internet)."""
        resp = FakeResponse(b"", final_url or "")
        with mock.patch.object(updates.urllib.request, "urlopen", return_value=resp),                 mock.patch.object(updates, "is_newer", lambda r: updates._as_tuple(r) > updates._as_tuple(local)):
            return updates.check()

    def test_check_acha_versao_nova_pelo_redirecionamento(self):
        info = self.check(f"https://github.com/{GITHUB_REPO}/releases/tag/v1.1.4")
        self.assertTrue(info["available"])
        self.assertEqual(info["version"], "1.1.4")
        self.assertEqual(info["asset_url"], f"{updates._RELEASE_PREFIX}v1.1.4/Instalar-GerenciadorEmuladores-1.1.4.exe")
        self.assertEqual(info["asset_name"], "Instalar-GerenciadorEmuladores-1.1.4.exe")

    def test_check_sem_novidade_ou_sem_release(self):
        self.assertFalse(self.check(f"https://github.com/{GITHUB_REPO}/releases/tag/v1.1.3")["available"])   # mesma versão
        self.assertFalse(self.check(f"https://github.com/{GITHUB_REPO}/releases")["available"])             # sem release ainda
        self.assertFalse(self.check("https://site-estranho.com/releases/tag/v9.9.9")["available"])          # outro endereço
        with mock.patch.object(updates.urllib.request, "urlopen", side_effect=OSError("sem internet")):
            self.assertFalse(updates.check()["available"])


if __name__ == "__main__":
    unittest.main()
