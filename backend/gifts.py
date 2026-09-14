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

# Mapa de ação interna -> nome exibido ao usuário (pt-BR)
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
    "points": "+10 pontos",
    "super_hint": "Super pista",
    "double_ability": "Dupla habilidade",
    "special_event": "Evento especial",
    "total_chaos": "Caos total",
    "legendary_event": "Evento lendário",
}

# Presentes padrão. Cada entrada: presente -> habilidade.
DEFAULT_GIFTS = {
    "Rose": {"action": "hint", "enabled": True},
    "Heart": {"action": "points", "quantity": 10, "enabled": True},
    "Finger Heart": {"action": "reveal_letter", "enabled": True},
    "Rosa": {"action": "eliminate", "enabled": True},
    "Perfume": {"action": "second_chance", "enabled": True},
    "Doughnut": {"action": "radar", "enabled": True},
    "Night Star": {"action": "second_chance", "enabled": True},
    "Money Gun": {"action": "chaos", "enabled": True},
    "Galaxy": {"action": "lightning", "enabled": True},
    "Fireworks": {"action": "super_hint", "enabled": True},
    "Party Laser": {"action": "double_ability", "enabled": True},
    "Meteor Shower": {"action": "total_chaos", "enabled": True},
    "Private Jet": {"action": "legendary_event", "enabled": True},
    # Compatibilidade com presentes já usados no projeto.
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
    await manager.ability_event("hint_result", player, "hint", msg, letra=letra.upper())


async def ability_reveal_letter(manager, player):
    r = manager.round
    if r is None:
        return
    secret = r.palavra
    candidatos = [i for i in range(len(secret)) if i not in manager.revealed_positions]
    pos = random.choice(candidatos) if candidatos else random.randrange(len(secret))
    manager.revealed_positions.add(pos)
    await manager.ability_event("letter_revealed", player, "reveal_letter",
                                f"{player.display_name()} revelou uma letra!",
                                pos=pos, letra=secret[pos].upper())


async def ability_eliminate(manager, player):
    r = manager.round
    if r is None:
        return
    secret = set(r.palavra)
    pool = [c for c in string.ascii_lowercase if c not in secret]
    letra = random.choice(pool)
    manager.eliminated_letters.add(letra)
    await manager.ability_event("letter_eliminated", player, "eliminate",
                                f"{player.display_name()} eliminou uma letra!",
                                letra=letra.upper(), mensagem=f"A letra {letra.upper()} não pertence à palavra.")


async def ability_second_chance(manager, player):
    r = manager.round
    if r is None:
        return
    if r.max_tentativas > manager.base_max_tentativas:
        return
    r.max_tentativas += 1
    await manager.ability_event("ability_completed", player, "second_chance",
                                f"{player.display_name()} deu uma segunda chance ao chat!",
                                max_tentativas=r.max_tentativas)


async def ability_shuffle(manager, player):
    await manager.ability_event("ability_completed", player, "shuffle", "Embaralhamento!")


async def ability_radar(manager, player):
    r = manager.round
    if r is None:
        return
    letra = random.choice(r.palavra)
    count = r.palavra.count(letra)
    await manager.ability_event("radar_result", player, "radar",
                                f"Radar: a letra {letra.upper()} aparece {count} vez(es).",
                                letra=letra.upper(), count=count)


async def ability_chaos(manager, player):
    opcoes = [ability_hint, ability_reveal_letter, ability_eliminate,
              ability_second_chance, ability_bonus, ability_points]
    escolhida = random.choice(opcoes)
    await manager.ability_event("chaos_started", player, "chaos", f"{player.display_name()} ativou CAOS!")
    await escolhida(manager, player)


async def ability_points(manager, player, quantity=10):
    manager.add_points(player, quantity)
    await manager.ability_event("ability_completed", player, "points",
                                f"+{quantity} pontos para {player.display_name()}.", quantidade=quantity)


async def ability_bonus(manager, player):
    await manager.start_bonus(2, 30, player)


async def ability_steal_points(manager, player):
    others = [p for p in manager.players.players.values()
              if p.unique_id != player.unique_id and p.pontos > 0]
    await manager.ability_event("ability_started", player, "steal_points",
                                f"{player.display_name()} ativou ROUBO DE PONTOS!")
    if not others:
        return
    target = random.choice(others)
    steal = min(10, target.pontos)
    manager.add_points(target, -steal)
    manager.add_points(player, steal)
    await manager.ability_event("ability_completed", player, "steal_points",
                                f"{target.display_name()} perdeu {steal} pontos.",
                                target=target.display_name(), pts=steal)


async def ability_super_hint(manager, player):
    r = manager.round
    if r is None:
        return
    vowels = sorted(set(r.palavra) & set("aeiou"))
    hints = [f"A palavra possui {vowels[0].upper()}." if vowels else "A palavra não possui vogais.",
             f"A palavra possui {len(vowels)} vogal(is).",
             "A última letra é uma vogal." if r.palavra[-1] in "aeiou" else "A última letra é uma consoante."]
    await manager.ability_event("ability_completed", player, "super_hint",
                                "SUPER PISTA\n" + "\n".join("✓ " + hint for hint in hints), pistas=hints)


async def ability_double_ability(manager, player):
    await manager.ability_event("ability_started", player, "double_ability",
                                f"{player.display_name()} ativou DUPLA HABILIDADE!")
    await ability_reveal_letter(manager, player)
    await ability_points(manager, player)


async def ability_special_event(manager, player):
    await manager.ability_event("event_started", player, "special_event",
                                "EVENTO ESPECIAL ativado!")
    await ability_bonus(manager, player)
    await ability_second_chance(manager, player)


async def ability_total_chaos(manager, player):
    await manager.ability_event("chaos_started", player, "total_chaos",
                                "CAOS TOTAL\n+1 tentativa\n×2 pontos\n1 letra revelada\n1 letra eliminada")
    await ability_second_chance(manager, player)
    await manager.start_bonus(2, 30, player)
    await ability_reveal_letter(manager, player)
    await ability_eliminate(manager, player)


async def ability_legendary_event(manager, player):
    await manager.ability_event("event_started", player, "legendary_event",
                                "EVENTO LENDÁRIO ativado!")
    await manager.start_bonus(3, 30, player)
    await ability_radar(manager, player)
    await ability_second_chance(manager, player)


async def ability_lightning(manager, player):
    await manager.ability_event("lightning_started", player, "lightning",
                                "PALAVRA RELÂMPAGO! Rodada de 30 segundos.")
    await manager.force_new_round(word=manager.round.palavra if manager.round else None, relampago=True)


# Registro de habilidades
HANDLERS = {
    "hint": ability_hint,
    "points": ability_points,
    "reveal_letter": ability_reveal_letter,
    "eliminate": ability_eliminate,
    "second_chance": ability_second_chance,
    "shuffle": ability_shuffle,
    "radar": ability_radar,
    "chaos": ability_chaos,
    "bonus": ability_bonus,
    "steal_points": ability_steal_points,
    "lightning": ability_lightning,
    "super_hint": ability_super_hint,
    "double_ability": ability_double_ability,
    "special_event": ability_special_event,
    "total_chaos": ability_total_chaos,
    "legendary_event": ability_legendary_event,
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

    def normalize_action(self, cfg):
        return cfg.get("action") or cfg.get("habilidade") or ""

    def actions(self):
        return list(HANDLERS.keys())

    def is_enabled(self, gift_name):
        cfg = self.gifts.get(gift_name)
        return bool(cfg and cfg.get("enabled"))

    def set_action_enabled(self, action, enabled):
        """Ativa/desativa uma habilidade para todos os presentes que a usam."""
        for cfg in self.gifts.values():
            if self.normalize_action(cfg) == action:
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
        action = self.normalize_action(cfg)
        handler = HANDLERS.get(action)
        if handler is None:
            return None, None
        if action == "points":
            await handler(manager, player, int(cfg.get("quantity", cfg.get("quantidade", 10))))
        else:
            await handler(manager, player)
        return gift_name, action

    def reload(self):
        self.gifts = self._load()
        return self.gifts