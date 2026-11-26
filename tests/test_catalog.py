"""Testes do catálogo. Rodar: python -m unittest discover tests"""
import unittest

from app import catalog


def emu(**extra):
    return {"emulators": [{"id": "e", "name": "E", "executable": "e.exe", "args": ["{rom}"], **extra}]}


class CatalogTests(unittest.TestCase):
    def test_window_mode_padrao_e_borderless(self):
        self.assertEqual(catalog.parse(emu()).emulators[0].window_mode, "default")
        self.assertEqual(catalog.parse(emu(window_mode="borderless")).emulators[0].window_mode, "borderless")

    def test_window_mode_invalido(self):
        with self.assertRaises(catalog.CatalogError):
            catalog.parse(emu(window_mode="tela-cheia"))

    def test_id_de_jogo_repetido_entre_emuladores(self):
        game = {"id": "g", "title": "G", "rom": {"file_id": "x", "filename": "g.gba"}}
        raw = {"emulators": [
            {"id": "a", "name": "A", "executable": "a", "args": ["{rom}"], "games": [game]},
            {"id": "b", "name": "B", "executable": "b", "args": ["{rom}"], "games": [game]}]}
        with self.assertRaises(catalog.CatalogError):
            catalog.parse(raw)

    # ---------- controls (teclas do emulador) ----------

    def controls(self, **changes):
        base = {"file": "config.ini", "format": "ini", "section": "gba.input.QT_K", "key_encoding": "qt",
                "buttons": [{"id": "A", "label": "A", "group": "face", "key": "keyA", "default": "KeyK"},
                            {"id": "Up", "label": "Cima", "group": "dpad", "key": "keyUp", "default": "KeyW"}]}
        base.update(changes)
        return base

    def test_controls_valido(self):
        c = catalog.parse(emu(controls=self.controls())).emulators[0].controls
        self.assertEqual((c.file, c.format, c.section, c.key_encoding), ("config.ini", "ini", "gba.input.QT_K", "qt"))
        self.assertEqual([(b.id, b.label, b.group, b.key, b.default) for b in c.buttons],
                         [("A", "A", "face", "keyA", "KeyK"), ("Up", "Cima", "dpad", "keyUp", "KeyW")])

    def test_sem_controls_fica_none(self):
        self.assertIsNone(catalog.parse(emu()).emulators[0].controls)

    def test_controls_invalidos(self):
        botao = {"id": "A", "label": "A", "group": "face", "key": "keyA", "default": "KeyK"}
        casos = {
            "formato desconhecido": self.controls(format="yaml"),
            "encoding desconhecido": self.controls(key_encoding="sdl"),
            "tecla padrão fora da tabela": self.controls(buttons=[{**botao, "default": "NumpadEnter"}]),
            "id repetido": self.controls(buttons=[botao, botao]),
            "grupo desconhecido": self.controls(buttons=[{**botao, "group": "meio"}]),
            "arquivo absoluto": self.controls(file="C:/config.ini"),
            "arquivo saindo da pasta": self.controls(file="../config.ini"),
            "sem botões": self.controls(buttons=[]),
            "botão sem key": self.controls(buttons=[{k: v for k, v in botao.items() if k != "key"}]),
        }
        for nome, valor in casos.items():
            with self.subTest(nome), self.assertRaises(catalog.CatalogError):
                catalog.parse(emu(controls=valor))


if __name__ == "__main__":
    unittest.main()
