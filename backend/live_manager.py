# ============================================================
#  live_manager.py
#  Orquestrador do jogo: gerencia as rodadas infinitas, a fila de
#  palpites, o ranking, os presentes e a difusão por WebSocket.
#
#  A busca de rodadas é executada em uma asyncio.Task de fundo.
#  Nenhum evento externo (comentário, presente, desconexão)
#  pode travar o jogo completo.
# ============================================================

import asyncio
import json
import logging
import time

from backend.game import (
    CORRECT,
    evaluate_guess,
    Round,
)
from backend.gifts import GiftSystem
from backend.players import PlayerManager
from backend.words import WordBank, normalize_word

log = logging.getLogger("termolive")


class LiveManager:
    def __init__(self, config):
        self.config = config
        self.words = WordBank(
            config.game.get("arquivo_palavras", "data/words.txt"),
            config.game.get("comprimento_palavra", 5),
        )
        self.players = PlayerManager()
        self.gifts = GiftSystem()

        self.clients = set()           # Websockets conectados
        self.round = None              # rodada ativa
        self.round_counter = 0
        self.paused = False

        self.revealed_positions = set()
        self.eliminated_letters = set()
        self._bonus_multiplier = 1
        self._bonus_until = 0.0

        # Sinalizadores de controle da rodada
        self._end_event = asyncio.Event()
        self._running = True
        self._skip_wait = False
        self._lightning_pending = False
        self._manual_word = None
        self._gift_lock = asyncio.Lock()
        self._gift_cooldowns = {}
        self._bonus_multiplier = 1
        self._bonus_until = 0.0
        self._bonus_task = None
        self.base_max_tentativas = config.game.get("max_tentativas", 6)

        self.stats = {
            "total_comentarios": 0,
            "total_palpites": 0,
            "total_presentes": 0,
            "total_aciertos": 0,
            "total_likes": 0,
            "total_follows": 0,
            "espectadores": 0,
        }

        self._loop_task = None

    async def start(self):
        """Inicia o ciclo de rodadas (deve ser chamado dentro do event loop)."""
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._run())

    # --------------------------------------------------------
    #  WebSocket
    # --------------------------------------------------------
    def register(self, ws):
        self.clients.add(ws)
        self.stats["espectadores"] = len(self.clients)

    def unregister(self, ws):
        self.clients.discard(ws)
        self.stats["espectadores"] = len(self.clients)

    async def broadcast(self, data):
        """Envia um dicionário JSON a todos os WebSockets conectados."""
        payload = json.dumps(data, ensure_ascii=False)
        stale = []
        for ws in list(self.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.clients.discard(ws)
        self.stats["espectadores"] = len(self.clients)

    # --------------------------------------------------------
    #  Pontos
    # --------------------------------------------------------
    def add_points(self, player, delta):
        player.pontos = max(0, player.pontos + delta)

    def current_multiplier(self):
        return self._bonus_multiplier if self._bonus_until > time.time() else 1

    async def ability_event(self, event_type, player, ability, text, **extra):
        if self.round is None:
            return
        payload = {
            "type": event_type,
            "round_id": self.round.numero,
            "username": player.display_name() if player else "",
            "user": player.display_name() if player else "",
            "ability": ability,
            "habilidade": self.gifts.label_for(ability),
            "text": text,
            "mensagem": text,
        }
        payload.update(extra)
        await self.broadcast(payload)

    async def start_bonus(self, multiplier, seconds, player=None):
        self._bonus_multiplier = max(1, int(multiplier))
        self._bonus_until = time.time() + max(1, int(seconds))
        await self.broadcast({
            "type": "bonus_started",
            "round_id": self.round.numero if self.round else None,
            "username": player.display_name() if player else "",
            "ability": "bonus",
            "multiplicador": self._bonus_multiplier,
            "duracao": seconds,
            "mensagem": f"×{self._bonus_multiplier} pontos por {seconds} segundos!",
        })
        if self._bonus_task and not self._bonus_task.done():
            self._bonus_task.cancel()
        self._bonus_task = asyncio.create_task(self._finish_bonus(self._bonus_until))

    async def _finish_bonus(self, deadline):
        try:
            await asyncio.sleep(max(0, deadline - time.time()))
            if self._bonus_until <= deadline:
                self._bonus_multiplier = 1
                self._bonus_until = 0
                await self.broadcast({"type": "bonus_finished", "mensagem": "O multiplicador terminou."})
        except asyncio.CancelledError:
            pass

    # --------------------------------------------------------
    #  Estado
    # --------------------------------------------------------
    def state(self):
        bonus_ativo = self._bonus_until > time.time()
        return {
            "rodada": self.round.to_dict() if self.round else None,
            "contador": self.round_counter,
            "ranking": self.players.ranking(10),
            "total_jogadores": len(self.players.players),
            "palpites": self.round.guesses[-20:] if self.round else [],
            "reveladas": sorted(self.revealed_positions),
            "eliminadas": sorted(self.eliminated_letters),
            "pausada": self.paused,
            "modo_test": self.config.test_mode,
            "stats": self.stats,
            "habilidades": self.gifts.available_actions(),
            "bonus": {"ativo": bonus_ativo,
                       "multiplicador": self._bonus_multiplier if bonus_ativo else 1,
                       "restante": max(0, int(self._bonus_until - time.time())) if bonus_ativo else 0},
            "palavras": {"total": self.words.total},
        }

    # --------------------------------------------------------
    #  Ciclo de vida das rodadas (sistema infinito)
    # --------------------------------------------------------
    async def start_round(self, word=None, relampago=False):
        if word:
            w = normalize_word(word)
        else:
            w = self.words.next_word()
        if not w:
            log.error("O banco de palavras está vazio.")
            await self.broadcast({"type": "system", "mensagem": "Não há palavras carregadas."})
            w = "termo"
        self.round_counter += 1
        max_t = self.config.game.get("max_tentativas", 6)
        self.round = Round(self.round_counter, w, max_t)
        self.round.relampago = relampago
        self.round.iniciada_ts = time.time()
        self._round_ttl = (
            self.config.game.get("duracao_relampago", 30)
            if relampago
            else self.config.game.get("duracao_rodada", 120)
        )
        self.revealed_positions = set()
        self.eliminated_letters = set()
        for p in self.players.players.values():
            p.tentativas = 0
            p.em_rodada = False
        self._end_event = asyncio.Event()
        await self.broadcast({
            "type": "new_round",
            "round": self.round.to_dict(),
            "duracao": self._round_ttl,
            "mensagem": f"Nova rodada #{self.round.numero}",
        })

    async def _run(self):
        while self._running:
            try:
                while self.paused:
                    await asyncio.sleep(0.5)
                relampago = self._lightning_pending
                self._lightning_pending = False
                manual = self._manual_word
                self._manual_word = None
                await self.start_round(word=manual, relampago=relampago)
                try:
                    await asyncio.wait_for(self._end_event.wait(), timeout=self._round_ttl)
                except asyncio.TimeoutError:
                    pass
                if self.paused:
                    continue
                await self.finish_round()
                if self._skip_wait or self._lightning_pending:
                    self._skip_wait = False
                    continue
                await asyncio.sleep(self.config.game.get("intervalo_entre_rodadas", 8))
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Erro no ciclo de rodadas; recuperando...")
                await asyncio.sleep(1)

    async def finish_round(self):
        r = self.round
        if r is None:
            return
        winner = r.vencedor
        data = {"type": "victory", "round": r.to_dict(), "mensagem": ""}
        if winner and winner.get("nome"):
            data["mensagem"] = f"🏆 {winner['nome']} descobriu a palavra!"
        else:
            data["mensagem"] = f"A palavra era {r.palavra.upper()}."
        await self.broadcast(data)
        if r.relampago:
            await self.broadcast({"type": "lightning_finished", "round_id": r.numero,
                                  "mensagem": "A palavra relâmpago terminou."})
        await self.broadcast({"type": "leaderboard", "ranking": self.players.ranking(10)})

    # --------------------------------------------------------
    #  Palpites (comentários convertidos em tentativas)
    # --------------------------------------------------------
    async def handle_palpite(self, user_info, raw_word):
        """Valida e processa um palpite. Devolve um dicionário com resultado."""
        w = normalize_word(raw_word)
        length = self.config.game.get("comprimento_palavra", 5)
        if len(w) != length:
            return {"ok": False, "motivo": "tamanho"}
        if not self.words.words:
            return {"ok": False, "motivo": "sem-palavras"}
        if self.round is None or self.round.terminada:
            return {"ok": False, "motivo": "rodada-inativa"}

        player = self.players.get_or_create(
            user_info.get("unique_id", "anônimo"),
            user_info.get("nickname", ""),
            user_info.get("avatar", ""),
        )
        if not self.players.can_palpite(player, self.config.cooldowns.get("palpite_segundos", 3)):
            return {"ok": False, "motivo": "cooldown"}

        self.stats["total_palpites"] += 1
        player.palpites += 1
        player.tentativas += 1
        player.em_rodada = True

        result = evaluate_guess(self.round.palavra, w)
        correct = all(s == CORRECT for s in result)
        info = {
            "usuario": player.unique_id,
            "nome": player.display_name(),
            "avatar": player.avatar,
            "palpite": w,
            "original": raw_word,
            "resultado": result,
            "correta": correct,
            "tentativa": player.tentativas,
        }
        self.round.add_guess(info)

        if correct:
            self.round.vencedor = {
                "id": player.unique_id,
                "nome": player.display_name(),
                "avatar": player.avatar,
                "tentativas": player.tentativas,
            }
            player.acertos += 1
            player.vitorias += 1
            base = self.config.game.get("pontos_acerto", 100)
            per = self.config.game.get("pontos_por_tentativa", 10)
            pts = max(10, base - (player.tentativas - 1) * per) * self.current_multiplier()
            self.add_points(player, pts)
            await self.broadcast({"type": "guess", "palpite": info})
            await self.broadcast({"type": "correct", "palpite": info, "pts": pts})
            self._end_event.set()
            return {"ok": True, "correta": True, "pts": pts, "info": info}

        await self.broadcast({"type": "guess", "palpite": info})
        await self.broadcast({"type": "wrong", "palpite": info})
        if self.round.terminada:
            self._end_event.set()
        return {"ok": True, "correta": False, "info": info}

    # --------------------------------------------------------
    #  Comentários genéricos + comandos reservados
    # --------------------------------------------------------
    async def handle_comment(self, user_info, text):
        self.stats["total_comentarios"] += 1
        stripped = (text or "").strip()
        if not stripped:
            return None
        if stripped.startswith("/"):
            if self.config.test_mode:
                return await self._handle_command(user_info, stripped)
            return None  # comando reservado ignorado em modo real
        return await self.handle_palpite(user_info, stripped)

    async def _handle_command(self, user_info, text):
        parts = text.lstrip("/").split()
        cmd = parts[0].lower() if parts else ""
        value = " ".join(parts[1:]) if len(parts) > 1 else ""
        if cmd in ("guess", "palpite"):
            return await self.handle_palpite(user_info, value)
        if cmd in ("gift", "presente"):
            return await self.handle_gift(value, user_info)
        if cmd == "follow":
            return await self.handle_follow(user_info)
        if cmd == "like":
            return await self.handle_like(user_info)
        return {"ok": False, "motivo": f"comando-desconhecido: {cmd}"}

    # --------------------------------------------------------
    #  Presentes / habilidades
    # --------------------------------------------------------
    async def handle_gift(self, gift_name, user_info, streak=1):
        gift_name = (gift_name or "").strip()
        self.stats["total_presentes"] += 1
        player = self.players.get_or_create(
            user_info.get("unique_id", "anônimo"),
            user_info.get("nickname", ""),
            user_info.get("avatar", ""),
        )
        player.presentes += 1
        if not gift_name:
            return {"ok": False, "motivo": "sem-presente"}
        cfg = self.gifts.config_for(gift_name)
        round_id = self.round.numero if self.round else None
        if not cfg:
            log.warning("Presente não configurado: %s | usuário=%s | sequência=%s",
                        gift_name, player.display_name(), streak)
            await self.broadcast({"type": "gift_received", "round_id": round_id,
                                  "username": player.display_name(), "gift_name": gift_name,
                                  "presente": gift_name, "configurado": False,
                                  "mensagem": f"Presente não configurado: {gift_name}"})
            return {"ok": False, "motivo": "nao-configurado"}
        cooldown = float(self.config.data.get("gifts", {}).get("cooldown", 1))
        cooldown_key = (player.unique_id, gift_name)
        now = time.monotonic()
        if now - self._gift_cooldowns.get(cooldown_key, 0) < cooldown:
            return {"ok": False, "motivo": "cooldown"}
        self._gift_cooldowns[cooldown_key] = now
        action = self.gifts.normalize_action(cfg)
        await self.broadcast({"type": "gift_received", "round_id": round_id,
                              "username": player.display_name(), "user": player.display_name(),
                              "gift_name": gift_name, "presente": gift_name,
                              "ability": action, "habilidade": self.gifts.label_for(action),
                              "streak": streak, "configurado": True})
        if not cfg.get("enabled", True):
            return {"ok": False, "motivo": "desativado"}
        async with self._gift_lock:
            if self.round is None or self.round.numero != round_id:
                return {"ok": False, "motivo": "rodada-inativa"}
            await self.broadcast({"type": "ability_started", "round_id": round_id,
                                  "username": player.display_name(), "ability": action,
                                  "habilidade": self.gifts.label_for(action)})
            await self.gifts.trigger(self, gift_name, player, streak=streak)
            player.habilidades += 1
        await self.broadcast({"type": "ability_completed", "round_id": round_id,
                              "username": player.display_name(), "ability": action,
                              "habilidade": self.gifts.label_for(action)})
        return {"ok": True, "habilidade": action}

    async def handle_follow(self, user_info):
        self.stats["total_follows"] += 1
        player = self.players.get_or_create(
            user_info.get("unique_id", "anônimo"),
            user_info.get("nickname", ""),
            user_info.get("avatar", ""),
        )
        self.add_points(player, 5)
        await self.broadcast({"type": "follow", "user": player.display_name()})
        return {"ok": True}

    async def handle_like(self, user_info):
        self.stats["total_likes"] += 1
        player = self.players.get_or_create(
            user_info.get("unique_id", "anônimo"),
            user_info.get("nickname", ""),
            user_info.get("avatar", ""),
        )
        self.add_points(player, 2)
        await self.broadcast({"type": "like", "user": player.display_name()})
        return {"ok": True}

    # --------------------------------------------------------
    #  Controles administrativos
    # --------------------------------------------------------
    async def force_new_round(self, word=None, relampago=False):
        """Termina a rodada atual e inicia outra (manual ou relâmpago)."""
        self._manual_word = word
        self._lightning_pending = relampago
        self._skip_wait = True
        self._end_event.set()

    def pause(self):
        self.paused = True
        self._end_event.set()

    def resume(self):
        self.paused = False

    def skip_word(self):
        """Pula a palavra atual sem vencedor."""
        if self.round and not self.round.vencedor:
            self.round.vencedor = {"id": None, "nome": None, "avatar": ""}
        if self.round:
            self._end_event.set()

    def set_round_ttl(self, segundos):
        self.config.data["game"]["duracao_rodada"] = max(5, int(segundos))
        return self.config.data["game"]["duracao_rodada"]

    def clear_ranking(self):
        for p in self.players.players.values():
            p.pontos = 0
            p.acertos = 0
            p.vitorias = 0
        return True

    async def set_manual_word(self, word):
        self._manual_word = normalize_word(word)
        self._end_event.set()

    def shutdown(self):
        self._running = False
        self._end_event.set()
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()