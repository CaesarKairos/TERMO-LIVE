# ============================================================
#  main.py
#  Entrada da aplicação FastAPI.
#  Serve o frontend, o WebSocket e a API de administração/teste.
# ============================================================

import os
import sys

# Garante que a raiz do projeto esteja em sys.path para poder
# importar o pacote `backend` (permite `python backend/main.py`).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import json
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import FRONTEND_DIR, LOGS_DIR, Config
from backend.live_manager import LiveManager
from backend.tiktok_client import TikTokClient

# ------------------------------------------------------------
#  Logging (logs/app.log)
# ------------------------------------------------------------
LOGS_DIR.mkdir(exist_ok=True)
_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_handler_file = RotatingFileHandler(
    LOGS_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
)
_handler_file.setFormatter(_formatter)
_handler_console = logging.StreamHandler()
_handler_console.setFormatter(_formatter)
logging.basicConfig(level=logging.INFO, handlers=[_handler_file, _handler_console])
log = logging.getLogger("termolive")

# ------------------------------------------------------------
#  Estado global da aplicação
# ------------------------------------------------------------
config = Config()
manager = LiveManager(config)
tiktok = TikTokClient(manager, config.tiktok_username)


async def _startup():
    await tiktok.start()
    await manager.start()
    log.info("TERMO LIVE pronto em http://127.0.0.1:%s/live", config.server_port)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _startup()
    yield
    manager.shutdown()
    log.info("TERMO LIVE encerrado.")


app = FastAPI(title="TERMO LIVE", version="1.0.0", lifespan=lifespan)


def is_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost")


def _local_only(request: Request):
    if not is_local(request):
        raise HTTPException(status_code=403, detail="Somente local")


def _test_only():
    if not config.test_mode:
        raise HTTPException(
            status_code=403,
            detail="Modo teste desativado. Defina TEST_MODE=true no .env e reinicie o servidor.",
        )


# ------------------------------------------------------------
#  Rotas de páginas
# ------------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/live")


@app.get("/live", response_class=HTMLResponse)
async def page_live():
    return FileResponse(FRONTEND_DIR / "live.html")


@app.get("/admin", response_class=HTMLResponse)
async def page_admin(request: Request):
    _local_only(request)
    return FileResponse(FRONTEND_DIR / "admin.html")


# ------------------------------------------------------------
#  WebSocket em tempo real
# ------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    manager.register(ws)
    try:
        await ws.send_text(json.dumps(
            {"type": "connection", "estado": manager.state()}, ensure_ascii=False
        ))
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        manager.unregister(ws)


# ------------------------------------------------------------
#  API de estado
# ------------------------------------------------------------
@app.get("/api/state")
async def api_state():
    return manager.state()


@app.get("/api/status")
async def api_status():
    return {
        "tiktok": {
            "conectado": tiktok.connected,
            "error": tiktok.error,
            "usuario": config.tiktok_username,
            "modo_test": config.test_mode,
            "carregado": bool(hasattr(tiktok, "client")),
        },
        "espectadores": manager.stats["espectadores"],
        "palavras_total": manager.words.total,
        "rodada_contador": manager.round_counter,
    }


# ------------------------------------------------------------
#  Modelos de entrada
# ------------------------------------------------------------
class WordBody(BaseModel):
    word: str = ""


class GuessBody(BaseModel):
    word: str = ""
    user: str = "test"
    nick: str = ""
    avatar: str = ""


class GiftBody(BaseModel):
    gift: str = ""
    user: str = "test"
    nick: str = ""
    avatar: str = ""


class UserBody(BaseModel):
    user: str = "test"
    nick: str = ""
    avatar: str = ""


class DurationBody(BaseModel):
    segundos: int = 120


class AbilityBody(BaseModel):
    action: str = ""
    enabled: bool = True


class GiftConfigBody(BaseModel):
    gift: str = ""
    action: str = ""
    enabled: bool = True
    cooldown: float | None = None


def _uinfo(b: BaseModel, default_id: str):
    return {
        "unique_id": (b.user or default_id),
        "nickname": b.nick or (b.user if b.user != "test" else ""),
        "avatar": b.avatar or "",
    }


# ------------------------------------------------------------
#  API de teste (modo TEST / sempre local)
# ------------------------------------------------------------
@app.post("/api/test/guess")
async def test_guess(body: GuessBody, request: Request):
    _local_only(request)
    _test_only()
    return await manager.handle_palpite(_uinfo(body, "test"), body.word)


@app.post("/api/test/gift")
async def test_gift(body: GiftBody, request: Request):
    _local_only(request)
    _test_only()
    return await manager.handle_gift(body.gift, _uinfo(body, "test"))


@app.post("/api/test/follow")
async def test_follow(body: UserBody, request: Request):
    _local_only(request)
    _test_only()
    return await manager.handle_follow(_uinfo(body, "test"))


@app.post("/api/test/like")
async def test_like(body: UserBody, request: Request):
    _local_only(request)
    _test_only()
    return await manager.handle_like(_uinfo(body, "test"))


@app.post("/api/test/comment")
async def test_comment(body: GuessBody, request: Request):
    _local_only(request)
    _test_only()
    return await manager.handle_comment(_uinfo(body, "test"), body.word)


# ------------------------------------------------------------
#  API administrativa (somente local)
# ------------------------------------------------------------
@app.post("/api/admin/nova-round")
async def admin_nova_round(body: WordBody, request: Request):
    _local_only(request)
    await manager.force_new_round(word=body.word or None)
    return {"ok": True}


@app.post("/api/admin/pausar")
async def admin_pausar(request: Request):
    _local_only(request)
    manager.pause()
    return {"pausada": True}


@app.post("/api/admin/continuar")
async def admin_continuar(request: Request):
    _local_only(request)
    manager.resume()
    return {"pausada": False}


@app.post("/api/admin/pular-palavra")
async def admin_saltar(request: Request):
    _local_only(request)
    manager.skip_word()
    return {"ok": True}


@app.post("/api/admin/trocar-palavra")
async def admin_trocar(body: WordBody, request: Request):
    _local_only(request)
    await manager.set_manual_word(body.word)
    return {"ok": True, "palavra": body.word}


@app.get("/api/admin/palavra")
async def admin_palavra(request: Request):
    _local_only(request)
    return {"palavra": manager.round.palavra if manager.round else None,
            "numero": manager.round.numero if manager.round else None}


@app.post("/api/admin/duracao")
async def admin_duracao(body: DurationBody, request: Request):
    _local_only(request)
    value = manager.set_round_ttl(body.segundos)
    return {"duracao": value}


@app.post("/api/admin/limpar-ranking")
async def admin_limpar(request: Request):
    _local_only(request)
    manager.clear_ranking()
    return {"ok": True}


@app.post("/api/admin/testar-presente")
async def admin_testar_presente(body: GiftBody, request: Request):
    _local_only(request)
    return await manager.handle_gift(body.gift, _uinfo(body, "admin"))


@app.get("/api/admin/gifts")
async def admin_gifts(request: Request):
    _local_only(request)
    return {
        "cooldown": config.data.get("gifts", {}).get("cooldown", 1),
        "streak_mode": config.data.get("gifts", {}).get("streak_mode", "final"),
        "acoes": manager.gifts.available_actions(),
        "gifts": [
            {"nome": name, "habilidade": manager.gifts.label_for(manager.gifts.normalize_action(cfg)),
             "action": manager.gifts.normalize_action(cfg), "ativo": bool(cfg.get("enabled", True))}
            for name, cfg in manager.gifts.gifts.items()
        ],
    }


@app.post("/api/admin/gifts/config")
async def admin_configurar_gift(body: GiftConfigBody, request: Request):
    _local_only(request)
    if body.cooldown is not None and not body.gift:
        config.data.setdefault("gifts", {})["cooldown"] = max(0, body.cooldown)
        return {"ok": True, "cooldown": config.data["gifts"]["cooldown"]}
    cfg = manager.gifts.gifts.get(body.gift)
    if cfg is None:
        return {"ok": False, "motivo": "presente-nao-configurado"}
    if body.action:
        cfg["action"] = body.action
    cfg["enabled"] = body.enabled
    return {"ok": True, "presente": body.gift, "action": manager.gifts.normalize_action(cfg), "ativo": cfg["enabled"]}


@app.post("/api/admin/habilidade")
async def admin_habilidade(body: AbilityBody, request: Request):
    _local_only(request)
    manager.gifts.set_action_enabled(body.action, body.enabled)
    return {"ok": True, "action": body.action, "enabled": body.enabled}


@app.get("/api/admin/tiktok")
async def admin_tiktok(request: Request):
    _local_only(request)
    return {
        "conectado": tiktok.connected,
        "error": tiktok.error,
        "usuario": config.tiktok_username,
        "modo_test": config.test_mode,
        "ultimos_comentarios": manager.round.guesses[-10:] if manager.round else [],
        "ultimos_presentes": [],
    }


# para testes manuais rápidos pela biblioteca (não expor a porta)
def run_app():
    import uvicorn

    uvicorn.run(app, host=config.server_host, port=config.server_port, log_level="info")


if __name__ == "__main__":
    run_app()