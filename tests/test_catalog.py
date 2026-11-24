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


if __name__ == "__main__":
    unittest.main()
