# ============================================================
#  config.py
#  Carregamento da configuração do TERMO-LIVE.
#  Prioridades:
#    1) valores padrão (DEFAULTS)
#    2) config/config.json   (se existir)
#    3) variáveis de ambiente / .env
# ============================================================

import json
import os
from pathlib import Path

# Diretórios-base do projeto
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"
FRONTEND_DIR = BASE_DIR / "frontend"
LOGS_DIR = BASE_DIR / "logs"

# Chaves técnicas internas em inglês; textos para o usuário em pt-BR.
DEFAULTS = {
    "server": {"host": "127.0.0.1", "port": 8000},
    "game": {
        "comprimento_palavra": 5,
        "max_tentativas": 6,
        "arquivo_palavras": "data/words.txt",
        "intervalo_entre_rodadas": 8,
        "duracao_rodada": 120,
        "duracao_relampago": 30,
        "pontos_acerto": 100,
        "pontos_por_tentativa": 10,
    },
    "cooldowns": {"palpite_segundos": 3},
    "test": {"enabled": False},
    "tiktok": {"username": ""},
    "gifts": {"arquivo": "config/gifts.json"},
}


def _deep_merge(base, override):
    """Une dois dicionários, mesclando dicionários aninhados."""
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            out[key] = _deep_merge(base[key], value)
        else:
            out[key] = value
    return out


def _read_json(path: Path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _parse_env_file(path: Path):
    """Le um arquivo .env simples sem adicionar dependências."""
    values = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip()
    except OSError:
        pass
    return values


class Config:
    """Objeto de configuração com atalhos para valores usados com frequência."""

    def __init__(self, config_path: Path | None = None, env_path: Path | None = None):
        self.config_path = Path(config_path) if config_path else CONFIG_DIR / "config.json"
        self.data = _deep_merge(DEFAULTS, _read_json(self.config_path))
        self.env = _parse_env_file(Path(env_path) if env_path else BASE_DIR / ".env")
        self._apply_env()

    def _apply_env(self):
        sel_env = {**self.env, **os.environ}
        self.tiktok_username = (sel_env.get("TIKTOK_USERNAME") or self.data["tiktok"].get("username", "")).strip()
        self.server_host = sel_env.get("HOST") or str(self.data["server"].get("host", "127.0.0.1"))
        self.server_port = int(sel_env.get("PORT") or self.data["server"].get("port", 8000))
        self.test_mode = (sel_env.get("TEST_MODE") or "").lower() in ("1", "true", "yes") or bool(
            self.data["test"].get("enabled")
        )
        self.dark = None  # reservado para futuros temas

    @property
    def game(self):
        return self.data["game"]

    @property
    def cooldowns(self):
        return self.data["cooldowns"]