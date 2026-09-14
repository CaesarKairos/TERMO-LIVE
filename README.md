# TERMO LIVE

Jogo de palavras de 5 letras para TikTok LIVE + OBS.
Interface vertical 9:16 (1080x1920). Textos da interface em pt-BR.

## Instalação

```
pip install -r requirements.txt
```

## Executar

```
python backend/main.py      ou      start.bat
```

Abrir: http://127.0.0.1:8000/live

## Configuracion

| Arquivo           | Para que serve                      |
|-------------------|--------------------------------------|
| `.env`            | `TIKTOK_USERNAME`, `TEST_MODE=true`  |
| `config/config.json` | regras e duração                    |
| `config/gifts.json`  | presentes -> habilidade              |
| `data/words.txt`     | palavras (uma por linha, 5 letras)  |

## Modo TEST

Com `TEST_MODE=true` no `.env`, em `/admin`:

```
/palpite TERMO     /presente Rose     /seguir Cesar     /curtida Cesar
```

## Páginas

| Rota     | O que é             | Acesso |
|----------|--------------------|--------|
| `/live`  | tela OBS 9:16      | Pública|
| `/admin` | painel de controle  | Somente local |
| `/api/*` | API                | Somente local |

## Habilidades (pt-BR)

| action           | Habilidade          |
|------------------|---------------------|
| `hint`           | Pista               |
| `reveal_letter`  | Letra revelada      |
| `eliminate`      | Letra eliminada     |
| `second_chance`  | Segunda chance      |
| `shuffle`        | Embaralhamento      |
| `radar`          | Radar               |
| `chaos`          | Caos                |
| `bonus`          | Bônus               |
| `steal_points`   | Roubo de pontos     |
| `lightning`      | Palavra relámpago   |

## Arquitetura

```
backend/   main.py · config.py · words.py · game.py · players.py ·
           gifts.py · live_manager.py · tiktok_client.py
frontend/  live.html·live.js·style.css (9:16) · admin.html·admin.js
data/      words.txt
config/    config.json · gifts.json
logs/      app.log (gerado pelo aplicativo)
```