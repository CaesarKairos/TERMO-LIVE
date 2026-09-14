# ============================================================
#  gifts.py
#  Sistema de presentes e habilidades.
#
#  A configuração de presentes está em config/gifts.json e
#  mapeia o nome do presente (TikTok) para uma habilidade (action).
#  Recomendação: não assumir nomes definitivos de presentes;
#  tudo é configurável por meio de gifts.json.
#
#  API pública recomendada:
#      gift_system.trigger(manager, "Rose", player, streak=1)
#
#  Toda a lógica de habilidades vive AQUI (funções independentes),
#  nunca dentro do handler do TikTok.
# ============================================================

import json
import random
import string
from pathlib import Path

from backend.game import normalize_word

# Mapa acción -> label exibido ao usuário (pt-BR)
ACTION_LABEL = {
    "hint": "Pista",
    "reveal_letter": "Revelar letra",
    "eliminate": "Eliminar",
    "second_chance": "Segunda chance",
    "shuffle": "Embaralhar",
    "radar": "Radar",
    "chaos": "Caos",
    "bonus": "Bônus",
    "steal_points": "Roubar pontos",
    "lightning": "Palavra relâmpago",
}

# Presentes por defecto. Cada entrada: presente -> habilidade.
DEFAULT_GIFTS = {
    "Rose": {"action": "hint", "enabled": True},
    "Heart": {"action": "reveal_letter", "enabled": True},
    "GG": {"action": "eliminate", "enabled": True},
    "Dice": {"action": "shuffle", "enabled": True},
    "Badge": {"action": "radar", "enabled": True},
    "Thor": {"action": "chaos", "enabled": True},
    "Crown": {"action": "bonus", "enabled": True},
    "Pandora": {"action": "steal_points", "enabled": True},
    "Silver": {"action": "second_chance", "enabled": True},
    "Zone": {"action": "lightning", "enabled": True},
}


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


# ------------------------------------------------------------
#  Implementação de cada habilidade.  Todas assíncronas e
#  independentes: só dependem do manager e do jogador.
# ------------------------------------------------------------

async def ability_hint(manager, player):
    r = manager.round
    if r is None:
        return
    letras = sorted(set(r.palavra))
    letra = random.choice(letras)
    msg = f"A palavra possui a letra {letra.upper()}."
    await manager.broadcast({"type": "hint", "user": player.display_name(),
                             "letra": letra.upper(), "mensagem": msg})


async def ability_reveal_letter(manager, player):
    r = manager.round
    if r is None:
        return
    secret = r.palavra
    candidatos = [i for i in range(len(secret)) if i not in manager.revealed_positions]
    pos = random.choice(candidatos) if candidatos else random.randrange(len(secret))
    manager.revealed_positions.add(pos)
    await manager.broadcast({"type": "reveal_letter", "pos": pos,
                             "letra": secret[pos].upper(), "user": player.display_name()})


async def ability_eliminate(manager, player):
    r = manager.round
    if r is None:
        return
    secret = set(r.palavra)
    pool = [c for c in string.ascii_lowercase if c not in secret]
    letra = random.choice(pool)
    manager.eliminated_letters.add(letra)
    await manager.broadcast({"type": "eliminate", "letra": letra.upper(),
                             "user": player.display_name(),
                             "mensagem": f"A letra {letra.upper()} NÃO pertence à palavra."})


async def ability_second_chance(manager, player):
    r = manager.round
    if r is None:
        return
    r.max_tentativas += 1
    await manager.broadcast({"type": "second_chance",
                             "max_tentativas": r.max_tentativas,
                             "user": player.display_name(),
                             "mensagem": "Segunda chance! +1 tentativa para todos."})


async def ability_shuffle(manager, player):
    await manager.broadcast({"type": "shuffle", "user": player.display_name(),
                             "mensagem": "Embaralhamento!"})


async def ability_radar(manager, player):
    r = manager.round
    if r is None:
        return
    letra = random.choice(r.palavra)
    count = r.palavra.count(letra)
    await manager.broadcast({"type": "radar", "letra": letra.upper(), "count": count,
                             "user": player.display_name(),
                             "mensagem": f"Radar: a letra {letra.upper()} aparece {count} vez(es)."})


async def ability_chaos(manager, player):
    opcoes = [ability_hint, ability_reveal_letter, ability_eliminate]
    escolhida = random.choice(opcoes)
    await manager.broadcast({"type": "chaos", "user": player.display_name(),
                             "mensagem": "Caos! Um evento aleatório ocorreu."})
    await escolhida(manager, player)


async def ability_bonus(manager, player):
    pts = 50
    manager.add_points(player, pts)
    await manager.broadcast({"type": "bonus", "user": player.display_name(), "pts": pts,
                             "mensagem": f"Bônus! {player.display_name()} ganhou {pts} pontos."})


async def ability_steal_points(manager, player):
    others = [p for p in manager.players.players.values()
              if p.unique_id != player.unique_id and p.pontos > 0]
    await manager.broadcast({"type": "steal_points", "user": player.display_name(),
                             "mensagem": "Roubo de pontos ativado..."})
    if not others:
        return
    target = random.choice(others)
    steal = min(10, target.pontos)
    manager.add_points(target, -steal)
    manager.add_points(player, steal)
    await manager.broadcast({"type": "steal_points_result", "target": target.display_name(),
                             "pts": steal, "user": player.display_name()})


async def ability_lightning(manager, player):
    await manager.broadcast({"type": "lightning", "user": player.display_name(),
                             "mensagem": "Palavra relâmpago! Rodada curta."})
    await manager.force_new_round(relampago=True)


# Registro de habilidades
HANDLERS = {
    "hint": ability_hint,
    "reveal_letter": ability_reveal_letter,
    "eliminate": ability_eliminate,
    "second_chance": ability_second_chance,
    "shuffle": ability_shuffle,
    "radar": ability_radar,
    "chaos": ability_chaos,
    "bonus": ability_bonus,
    "steal_points": ability_steal_points,
    "lightning": ability_lightning,
}


class GiftSystem:
    """Coordena presentes do TikTok -> habilidades configuradas."""

    def __init__(self, gift_file=None):
        from backend.config import CONFIG_DIR
        self.gift_file = Path(gift_file) if gift_file else CONFIG_DIR / "gifts.json"
        self.gifts = self._load()

    def _load(self):
        data = _read_json(self.gift_file)
        merged = {name: dict(cfg) for name, cfg in DEFAULT_GIFTS.items()}
        for name, cfg in data.items():
            base = merged.get(name, {})
            merged[name] = {**base, **cfg}
        return merged

    def get_file(self):
        return self.gift_file

    def config_for(self, gift_name):
        return self.gifts.get(gift_name)

    def label_for(self, action):
        return ACTION_LABEL.get(action, action)

    def actions(self):
        return list(HANDLERS.keys())

    def is_enabled(self, gift_name):
        cfg = self.gifts.get(gift_name)
        return bool(cfg and cfg.get("enabled"))

    def set_action_enabled(self, action, enabled):
        """Ativa/desativa uma habilidade para todos os presentes que a usam."""
        for cfg in self.gifts.values():
            if cfg.get("action") == action:
                cfg["enabled"] = bool(enabled)

    def available_actions(self):
        return {a: self.label_for(a) for a in HANDLERS}

    async def trigger(self, manager, gift_name, player, streak=1):
        """
        Executa a habilidade correspondente a um presente.

        'streak' permite saber quantas vezes o TikTok reportou o mesmo
        evento (presentes em sequência). A habilidade só é executada uma
        vez por chamada; é responsabilidade do chamador (o handler do
        TikTok) executá-la quando a sequência terminar (streak final).
        """
        cfg = self.config_for(gift_name)
        if not cfg or not cfg.get("enabled"):
            return None, None
        action = cfg.get("action")
        handler = HANDLERS.get(action)
        if handler is None:
            return None, None
        await handler(manager, player)
        return gift_name, action

    def reload(self):
        self.gifts = self._load()
        return self.gifts