# ============================================================
#  players.py
#  Gestão de jogadores. O TikTok é a identidade do participante:
#  unique_id, nickname, avatar e suas estatísticas.
# ============================================================

import time


class Player:
    def __init__(self, unique_id: str, nickname: str = "", avatar: str = ""):
        self.unique_id = unique_id
        self.nickname = nickname or f"@{unique_id}"
        self.avatar = avatar or ""            # URL do avatar (se disponível)
        self.palpites = 0                     # total de palpites enviados
        self.acertos = 0                      # rodadas acertadas
        self.pontos = 0                       # pontos totais
        self.presentes = 0                    # presentes enviados
        self.habilidades = 0                  # vezes que ativou habilidades
        self.vitorias = 0
        self.tentativas = 0                   # tentativas na rodada atual
        self.em_rodada = False
        self.ultimo_palpite_ts = 0.0          # para rate-limit

    def display_name(self):
        return self.nickname if self.nickname.startswith("@") else f"@{self.nickname}"


class PlayerManager:
    def __init__(self):
        self.players = {}

    def get_or_create(self, unique_id: str, nickname: str = "", avatar: str = ""):
        player = self.players.get(unique_id)
        if player is None:
            player = Player(unique_id, nickname, avatar)
            self.players[unique_id] = player
        else:
            if avatar and not player.avatar:
                player.avatar = avatar
            if nickname and not player.nickname.startswith("@"):
                player.nickname = nickname
        return player

    def can_palpite(self, player: Player, cooldown: float) -> bool:
        """Rate-limit: um palpite por usuário cada N segundos."""
        now = time.monotonic()
        if now - player.ultimo_palpite_ts < cooldown:
            return False
        player.ultimo_palpite_ts = now
        return True

    def ranking(self, limit: int = 10):
        ordered = sorted(self.players.values(), key=lambda p: p.pontos, reverse=True)
        return [
            {"posicao": i + 1, "nome": p.display_name(), "pontos": p.pontos, "avatar": p.avatar,
             "acertos": p.acertos, "palpites": p.palpites}
            for i, p in enumerate(ordered[:limit])
        ]