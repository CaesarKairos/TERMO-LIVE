# ============================================================
#  words.py
#  Carga, normalização e seleção de palavras.
#  - remove acentos para comparação
#  - filtra palavras inválidas e duplicadas
#  - evita repetir palavras até esgotar a lista
# ============================================================

import random
import unicodedata


def strip_accents(text: str) -> str:
    """Remove acentos de uma string (NFD -> remove marcas combinadas)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(char for char in nfkd if not unicodedata.combining(char))


def normalize_word(word: str) -> str:
    """Normaliza uma palavra: minúsculas, sem acentos, sem espaços extremos."""
    return strip_accents((word or "").strip().lower())


class WordBank:
    """Banco de palavras válidas para o jogo, sem repetições até esgotar."""

    def __init__(self, path, length: int = 5):
        self.length = length
        self.words = self._load(path)
        self._shuffled = []
        self._index = 0
        self.reseed()

    def _load(self, path):
        seen = set()
        out = []
        try:
            with open(path, encoding="utf-8") as fh:
                for raw in fh:
                    w = normalize_word(raw)
                    if len(w) == self.length and w not in seen:
                        seen.add(w)
                        out.append(w)
        except OSError:
            pass
        return out

    def reseed(self):
        """Embaralha a lista para voltar a usar todas as palavras."""
        self._shuffled = list(self.words)
        random.shuffle(self._shuffled)
        self._index = 0

    def next_word(self):
        """Devolve a próxima palavra evitando repetições até esgotar."""
        if not self.words:
            return None
        if self._index >= len(self._shuffled):
            self.reseed()
        word = self._shuffled[self._index]
        self._index += 1
        return word

    @property
    def total(self):
        return len(self.words)