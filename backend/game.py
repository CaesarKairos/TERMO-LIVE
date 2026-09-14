# ============================================================
#  game.py
#  Lógica de uma rodada: estado, tentativas e avaliação das
#  letras de cada palpite (tratando letras repetidas).
# ============================================================

from backend.words import normalize_word

# Estados possíveis de cada letra
CORRECT = "correct"   # letra correta e posição correta
PRESENT = "present"   # letra existe em outra posição
ABSENT = "absent"     # letra inexistente


def evaluate_guess(secret: str, guess: str):
    """
    Compara um palpite com a palavra secreta.

    Devolve uma lista com o estado de cada letra, tratando
    corretamente letras repetidas (não duplica 'present'
    além da quantidade real na palavra).
    """
    secret_n = normalize_word(secret)
    guess_n = normalize_word(guess)
    length = len(secret_n)
    result = [ABSENT] * length
    used = [False] * length  # posições da palavra secreta já consumidas

    # 1) letras corretas na posição correta
    for i in range(length):
        if guess_n[i] == secret_n[i]:
            result[i] = CORRECT
            used[i] = True

    # 2) letras existentes em outra posição
    for i in range(length):
        if result[i] == CORRECT:
            continue
        for j in range(length):
            if not used[j] and secret_n[j] == guess_n[i]:
                result[i] = PRESENT
                used[j] = True
                break
    return result


class Round:
    """Representa uma rodada ativa do jogo."""

    def __init__(self, numero: int, palavra: str, max_tentativas: int):
        self.numero = numero
        self.palavra = normalize_word(palavra)
        self.max_tentativas = max_tentativas
        self.guesses = []          # palpites já processados
        self.vencedor = None       # dict do jogador que acertou (o primeiro)
        self.tentativas_count = 0
        self.iniciada_ts = 0
        self.relampago = False

    def add_guess(self, guess_info: dict):
        self.guesses.append(guess_info)
        self.tentativas_count += 1

    @property
    def terminada(self):
        return self.vencedor is not None or self.tentativas_count >= self.max_tentativas

    def to_dict(self):
        return {
            "numero": self.numero,
            "palavra": self.palavra,
            "max_tentativas": self.max_tentativas,
            "tentativas": self.tentativas_count,
            "vencedor": self.vencedor,
            "relampago": self.relampago,
        }