"""Testes offline da checagem de versão."""
import unittest

from app import updates


class UpdatesTests(unittest.TestCase):
    def test_comparacao_de_versoes(self):
        self.assertTrue(updates.is_newer("v1.2.0", "1.1.9"))
        self.assertTrue(updates.is_newer("2.0.0", "1.9.9"))
        self.assertFalse(updates.is_newer("v1.0.0", "1.0.0"))
        self.assertFalse(updates.is_newer("0.9.0", "1.0.0"))
