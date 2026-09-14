# ============================================================
#  tiktok_client.py
#  Camada de integração com o TikTok LIVE, totalmente ISOLADA.
#
#  Propósito: conectar-se à LIVE, capturar comentários, presentes,
#  follows e likes, e entregá-los ao LiveManager sem travar o jogo.
#  Se o TikTok desconectar, o cliente tentará se reconectar e
#  nunca deve derrubar a aplicação.
#
#  Esta camada pode ser substituída/futuramente por outra (ou por
#  um simulador) sem reescrever o jogo.
# ============================================================

import asyncio
import logging
import threading
import time

log = logging.getLogger("termolive")


class TikTokClient:
    def __init__(self, manager, username: str = ""):
        self.manager = manager
        self.username = (username or "").strip().lstrip("@")
        self.running = False
        self.connected = False
        self.error = ""
        # Supressores de sequência de presentes: (user_id, gift) -> ts
        self._gift_window = {}

    # ------------------------------------------------------------
    async def start(self):
        if self.manager.config.test_mode:
            log.info("Modo TEST ativo: não se conectará ao TikTok.")
            return
        if not self.username:
            self.error = "Sem username TikTok configurado."
            log.warning(self.error)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        try:
            from TikTokLive import TikTokLiveClient  # noqa: F401
        except Exception as exc:  # TikTokLive não instalado
            self.error = f"TikTokLive não instalado: {exc}"
            log.warning(self.error)
            return
        self.running = True
        thread = threading.Thread(target=self._run_sync, args=(loop,), daemon=True)
        thread.start()

    def _run_sync(self, loop):
        try:
            from TikTokLive import TikTokLiveClient
        except Exception as exc:
            self.error = str(exc)
            log.error("Erro ao carregar o TikTokLive: %s", exc)
            return
        try:
            client = TikTokLiveClient(unique_id=self.username)
        except TypeError:
            client = TikTokLiveClient(self.username)
        self.client = client
        self._setup_handlers(client)

        def on_connect(_ec):
            self.connected = True
            log.info("TikTok LIVE conectado: @%s", self.username)
        client.on("connect")(on_connect)

        log.info("TiktoK LIVE: escutando @%s", self.username)
        try:
            client.run()
        except Exception as exc:
            log.exception("Erro no loop do TikTok: %s", exc)
            self.error = str(exc)
            self.connected = False
        finally:
            self.running = False
            self.connected = False

    def _setup_handlers(self, client):
        # Registramos com decoradores do TikTokLive; cada evento
        # volta para o ciclo principal do asyncio.
        client.on("comment")(self._make_handler("comment"))
        client.on("gift")(self._make_handler("gift"))
        client.on("follow")(self._make_handler("follow"))
        client.on("like")(self._make_handler("like"))

    def _make_handler(self, kind):
        def handler(event):
            self._dispatch(kind, event)
        return handler

    def _dispatch(self, kind, event):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            return
        loop.call_soon_threadsafe(lambda: asyncio.create_task(self._handle_event(kind, event)))

    # ------------------------------------------------------------
    async def _handle_event(self, kind, event):
        """Converte um evento TikTok e chama o LiveManager."""
        try:
            info = self._user_info(event)
            if kind == "comment":
                text = getattr(event, "comment", getattr(event, "text", "")) or ""
                await self.manager.handle_comment(info, str(text))
            elif kind == "gift":
                await self._handle_gift(event, info)
            elif kind == "follow":
                await self.manager.handle_follow(info)
            elif kind == "like":
                await self.manager.handle_like(info)
        except Exception:
            log.exception("Erro ao tratar o evento %s", kind)

    @staticmethod
    def _user_info(event):
        user = getattr(event, "user", None)
        if user is None:
            user = getattr(event, "user_data", None)
        if user is not None:
            return {
                "unique_id": str(getattr(user, "unique_id", getattr(user, "id", "desconhecido"))),
                "nickname": getattr(user, "nickname", "") or "",
                "avatar": getattr(user, "avatar", "") or "",
            }
        return {"unique_id": "desconhecido", "nickname": "", "avatar": ""}

    async def _handle_gift(self, event, info):
        gift = getattr(event, "gift", None)
        name = ""
        streak = 1
        if gift is not None:
            name = getattr(gift, "name", "") or ""
            streak = int(getattr(gift, "repeats", getattr(gift, "streak", 1)) or 1)
        else:
            name = str(getattr(event, "gift_name", "") or "")
        if not name:
            return
        key = (info["unique_id"], name)
        now = time.monotonic()
        # Sequência: aplicamos a habilidade uma única vez por sequência.
        if self._gift_window.get(key) and now - self._gift_window.get(key, 0) < 1.0:
            return
        self._gift_window[key] = now
        await self.manager.handle_gift(name, info, streak=streak)