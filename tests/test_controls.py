"""Testes de controls.py: tabela de teclas e editor do arquivo de configuração dos emuladores.
Rodar: python -m unittest discover tests"""
import tempfile
import unittest
from pathlib import Path

from app import controls


class KeyTableTests(unittest.TestCase):
    def test_codigos_qt_conhecidos(self):
        esperado = {"KeyW": 87, "KeyK": 75, "Enter": 16777220, "Space": 32, "ArrowUp": 16777235,
                    "ArrowDown": 16777237, "ArrowLeft": 16777234, "ArrowRight": 16777236, "Tab": 16777217,
                    "Backspace": 16777219, "F1": 16777264, "F12": 16777275, "Digit1": 49}
        for code, qt in esperado.items():
            self.assertEqual(controls.DOM_TO_QT[code], qt, code)

    def test_ida_e_volta(self):
        for code, qt in controls.DOM_TO_QT.items():
            self.assertEqual(controls.qt_to_code(qt), code)

    def test_qt_desconhecido(self):
        self.assertIsNone(controls.qt_to_code(-1))
        self.assertIsNone(controls.qt_to_code(16777248))  # Shift

    def test_rotulos(self):
        esperado = {"KeyW": "W", "Digit1": "1", "Space": "Espaço", "ArrowUp": "↑", "ArrowDown": "↓",
                    "ArrowLeft": "←", "ArrowRight": "→", "Enter": "Enter", "F5": "F5"}
        for code, label in esperado.items():
            self.assertEqual(controls.code_label(code), label)


class FileEditorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.path = self.dir / "config.ini"

    def put(self, text: str) -> None:
        self.path.write_bytes(text.encode("utf-8"))

    def text(self) -> str:
        return self.path.read_bytes().decode("utf-8")

    def test_le_secao_e_chave(self):
        self.put("[a]\nkeyA=75\n[b]\nkeyA=1\n")
        self.assertEqual(controls.read_values(self.path, "a", ["keyA", "keyB"]), {"keyA": 75, "keyB": None})

    def test_arquivo_ausente_le_none(self):
        self.assertEqual(controls.read_values(self.path, "a", ["k"]), {"k": None})

    def test_troca_valor_mantendo_estilo(self):
        self.put("# nota\n[a]\nA = 1\nB = 2\n")
        controls.write_values(self.path, "a", {"A": 75}, " = ")
        self.assertEqual(self.text(), "# nota\n[a]\nA = 75\nB = 2\n")
        self.put("[a]\nkeyA=1\nkeyB=2\n")
        controls.write_values(self.path, "a", {"keyA": 75}, "=")
        self.assertEqual(self.text(), "[a]\nkeyA=75\nkeyB=2\n")

    def test_so_a_secao_pedida(self):
        # o melonDS tem "A" em Keyboard e em Joystick: só a seção pedida pode mudar
        self.put("[Instance0.Keyboard]\nA = -1\n[Instance0.Joystick]\nA = 1\n")
        controls.write_values(self.path, "Instance0.Keyboard", {"A": 75}, " = ")
        self.assertEqual(self.text(), "[Instance0.Keyboard]\nA = 75\n[Instance0.Joystick]\nA = 1\n")

    def test_ponto_no_nome_da_secao_e_literal(self):
        self.put("[InstanceX0Keyboard]\nA = 1\n[Instance0.Keyboard]\nA = 2\n")
        controls.write_values(self.path, "Instance0.Keyboard", {"A": 9}, " = ")
        self.assertEqual(self.text(), "[InstanceX0Keyboard]\nA = 1\n[Instance0.Keyboard]\nA = 9\n")

    def test_chave_ausente_entra_no_fim_da_secao(self):
        self.put("[a]\nA = 1\n\n[b]\nB = 2\n")
        controls.write_values(self.path, "a", {"X": 5}, " = ")
        self.assertEqual(self.text(), "[a]\nA = 1\nX = 5\n\n[b]\nB = 2\n")

    def test_secao_ausente_e_criada_no_fim(self):
        self.put("[a]\nA = 1\n")
        controls.write_values(self.path, "novo", {"K": 3}, "=")
        self.assertEqual(self.text(), "[a]\nA = 1\n\n[novo]\nK=3\n")

    def test_arquivo_ausente_e_criado(self):
        alvo = self.dir / "pasta" / "x.ini"
        controls.write_values(alvo, "s", {"k": 1}, "=")
        self.assertEqual(alvo.read_text(encoding="utf-8"), "[s]\nk=1\n")

    def test_preserva_crlf(self):
        self.put("[a]\r\nk=1\r\n")
        controls.write_values(self.path, "a", {"k": 2, "novo": 3}, "=")
        dados = self.path.read_bytes()
        self.assertEqual(dados, b"[a]\r\nk=2\r\nnovo=3\r\n")
        self.assertNotIn(b"\n", dados.replace(b"\r\n", b""))

    def test_bak_so_na_primeira_gravacao(self):
        self.put("[a]\nk=1\n")
        controls.write_values(self.path, "a", {"k": 2}, "=")
        controls.write_values(self.path, "a", {"k": 3}, "=")
        bak = self.dir / "config.ini.bak"
        self.assertEqual(bak.read_text(encoding="utf-8"), "[a]\nk=1\n")
        self.assertEqual(self.text(), "[a]\nk=3\n")

    def test_nao_deixa_temporario(self):
        self.put("[a]\nk=1\n")
        controls.write_values(self.path, "a", {"k": 2}, "=")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["config.ini", "config.ini.bak"])


if __name__ == "__main__":
    unittest.main()
