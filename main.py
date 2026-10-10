"""
Главный файл на Render: веб-админка, self-ping, супервизор l6.py.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import aiohttp
from aiohttp import web


# ============================================================
# НАСТРОЙКИ
# ============================================================
PORT = int(os.getenv("PORT", 8080))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
SELF_URL = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("SELF_URL")
PING_INTERVAL = 600          # 10 минут
SUPERVISOR_DELAY = 3         # пауза перед рестартом l6
PROMPT_FILE = Path("system_prompt.txt")
STATS_FILE = Path("stats.json")
START_TIME = time.monotonic()

logging.basicConfig(
    format="%(asctime)s [main] %(levelname)s: %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger("main")


# ============================================================
# СУПЕРВИЗОР l6.py
# ============================================================
current_proc: asyncio.subprocess.Process | None = None
l6_starts = 0


async def supervise_l6():
    global current_proc, l6_starts
    while True:
        l6_starts += 1
        logger.info("Запускаю l6.py (попытка #%s)", l6_starts)
        try:
            current_proc = await asyncio.create_subprocess_exec(
                sys.executable, "l6.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for raw in current_proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    logger.info("[l6] %s", line)
            code = await current_proc.wait()
            logger.warning("l6.py завершился с кодом %s", code)
        except Exception as e:
            logger.exception("Ошибка супервизора: %s", e)
        current_proc = None
        await asyncio.sleep(SUPERVISOR_DELAY)


async def restart_l6():
    if current_proc and current_proc.returncode is None:
        logger.info("Убиваю l6.py по запросу из админки")
        current_proc.terminate()
        try:
            await asyncio.wait_for(current_proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            current_proc.kill()
    # супервизор сам поднимет новый


# ============================================================
# SELF-PING
# ============================================================
async def self_ping():
    if not SELF_URL:
        logger.warning("RENDER_EXTERNAL_URL не задан — self-ping отключён")
        return
    url = SELF_URL.rstrip("/") + "/health"
    logger.info("Self-ping стартовал: %s каждые %ss", url, PING_INTERVAL)
    async with aiohttp.ClientSession() as s:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                async with s.get(url, timeout=15) as r:
                    logger.info("self-ping → %s", r.status)
            except Exception as e:
                logger.warning("self-ping упал: %s", e)


# ============================================================
# РАБОТА С ФАЙЛАМИ
# ============================================================
def load_prompt() -> str:
    try:
        return PROMPT_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def save_prompt(text: str) -> None:
    PROMPT_FILE.write_text(text, encoding="utf-8")


def load_stats() -> dict:
    try:
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ============================================================
# АВТОРИЗАЦИЯ
# ============================================================
def check_token(request: web.Request) -> bool:
    if not ADMIN_TOKEN:
        return False
    if request.cookies.get("admin_token") == ADMIN_TOKEN:
        return True
    if request.query.get("token") == ADMIN_TOKEN:
        return True
    return False


# ============================================================
# HTML
# ============================================================
def page(body: str) -> str:
    return f"""<!DOCTYPE html><html lang="ru"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Катя — админка</title>
<style>
 body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,sans-serif;
      max-width:1000px;margin:2rem auto;padding:0 1rem}}
 h1{{color:#4ade80}} h2{{color:#60a5fa;margin-top:2rem}}
 textarea{{width:100%;height:40vh;background:#1e293b;color:#e2e8f0;
          border:1px solid #334155;border-radius:8px;padding:1rem;
          font-family:monospace;font-size:.9rem}}
 button{{background:#2563eb;color:#fff;border:none;padding:.6rem 1.4rem;
        border-radius:6px;cursor:pointer;font-size:1rem;margin-right:.5rem}}
 button:hover{{background:#1d4ed8}}
 button.danger{{background:#b91c1c}} button.danger:hover{{background:#991b1b}}
 .msg{{padding:.6rem 1rem;border-radius:6px;margin:.8rem 0}}
 .ok{{background:#064e3b;color:#d1fae5}} .err{{background:#7f1d1d;color:#fee2e2}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.7rem}}
 .stat{{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:.8rem}}
 .stat .v{{font-size:1.4rem;color:#4ade80;font-weight:600}}
 .stat .k{{font-size:.75rem;color:#94a3b8;text-transform:uppercase}}
 .hint{{color:#94a3b8;font-size:.85rem;margin-top:.5rem}}
</style></head><body>{body}
<script>
async function refresh(){{
  try{{
    const r=await fetch('/stats');const d=await r.json();
    for(const [k,v] of Object.entries(d.stats||{{}})){{
      const el=document.getElementById('s-'+k);
      if(el)el.textContent=v;
    }}
    const u=document.getElementById('s-uptime');
    if(u&&d.uptime!=null){{
      const s=Math.floor(d.uptime);const h=Math.floor(s/3600);
      const m=Math.floor((s%3600)/60);u.textContent=h+'ч '+m+'м '+(s%60)+'с';
    }}
    const p=document.getElementById('s-proc');
    if(p)p.textContent=d.l6_alive?'жив':'мёртв';
  }}catch(e){{}}
}}
setInterval(refresh,5000);refresh();
async function post(url,body){{
  const r=await fetch(url,{{method:'POST',headers:{{'Content-Type':'application/json'}},
                            body:JSON.stringify(body||{{}})}});
  const j=await r.json(); alert(JSON.stringify(j)); refresh();
}}
</script></body></html>"""


def login_page(err: str = "") -> str:
    e = f'<div class="msg err">{err}</div>' if err else ""
    return page(f"""<h1>Вход в админку Кати</h1>{e}
<form method="POST" action="/login">
 <input type="password" name="token" placeholder="ADMIN_TOKEN"
  style="width:100%;padding:.7rem;background:#1e293b;color:#e2e8f0;
         border:1px solid #334155;border-radius:6px">
 <button type="submit" style="margin-top:.8rem">Войти</button>
</form>""")


def admin_page(msg: str = "") -> str:
    m = f'<div class="msg ok">{msg}</div>' if msg else ""
    stats = load_stats()
    return page(f"""
<h1>🧹 Катя — админка</h1>
{m}

<h2>Статистика</h2>
<div class="grid">
  <div class="stat"><div class="k">Uptime</div><div class="v" id="s-uptime">—</div></div>
  <div class="stat"><div class="k">l6.py</div><div class="v" id="s-proc">—</div></div>
  <div class="stat"><div class="k">Сообщений</div><div class="v" id="s-messages">{stats.get('messages', 0)}</div></div>
  <div class="stat"><div class="k">Успешных LLM</div><div class="v" id="s-llm_ok">{stats.get('llm_ok', 0)}</div></div>
  <div class="stat"><div class="k">Ошибок LLM</div><div class="v" id="s-llm_err">{stats.get('llm_err', 0)}</div></div>
  <div class="stat"><div class="k">Запусков l6</div><div class="v" id="s-l6_starts">{l6_starts}</div></div>
</div>

<h2>Управление</h2>
<button onclick="if(confirm('Перезапустить l6.py?'))post('/restart-bot')">Перезапустить бота</button>
<button class="danger" onclick="if(confirm('Жёсткий рестарт всего процесса? Render поднимет заново, ~10 сек даунтайма.'))post('/restart-all')">Жёсткий рестарт</button>

<h2>Системный промпт</h2>
<form method="POST" action="/prompt">
  <textarea name="prompt">{load_prompt() or '— пусто, бот использует встроенный дефолт —'}</textarea>
  <button type="submit" style="margin-top:.8rem">Сохранить</button>
</form>
<p class="hint">Файл: system_prompt.txt. Изменения применяются со следующего сообщения.</p>
""")


# ============================================================
# РОУТЫ
# ============================================================
async def h_health(_): return web.json_response({"status": "ok"})

async def h_stats(_):
    return web.json_response({
        "uptime": time.monotonic() - START_TIME,
        "l6_alive": current_proc is not None and current_proc.returncode is None,
        "l6_starts": l6_starts,
        "stats": load_stats(),
    })

async def h_login_post(req):
    data = await req.post()
    if data.get("token") == ADMIN_TOKEN:
        resp = web.HTTPFound("/")
        resp.set_cookie("admin_token", ADMIN_TOKEN, httponly=True, samesite="Strict")
        return resp
    return web.Response(text=login_page("Неверный токен"), content_type="text/html")

async def h_index(req):
    if not ADMIN_TOKEN:
        return web.Response(text=page("<h1>ADMIN_TOKEN не задан в env</h1>"), content_type="text/html")
    if not check_token(req):
        return web.Response(text=login_page(), content_type="text/html")
    return web.Response(text=admin_page(), content_type="text/html")

async def h_prompt(req):
    if not check_token(req):
        return web.Response(status=403, text="forbidden")
    data = await req.post()
    text = (data.get("prompt") or "").strip()
    if text and text != "— пусто, бот использует встроенный дефолт —":
        save_prompt(text)
        return web.HTTPFound("/")
    return web.HTTPFound("/")

async def h_restart_bot(req):
    if not check_token(req):
        return web.json_response({"error": "forbidden"}, status=403)
    asyncio.create_task(restart_l6())
    return web.json_response({"status": "restarting l6"})

async def h_restart_all(req):
    if not check_token(req):
        return web.json_response({"error": "forbidden"}, status=403)
    logger.warning("Жёсткий рестарт по запросу из админки")
    asyncio.get_event_loop().call_later(1, lambda: os._exit(0))
    return web.json_response({"status": "dying"})


# ============================================================
# ЗАПУСК
# ============================================================
async def main():
    app = web.Application()
    app.router.add_get("/", h_index)
    app.router.add_post("/login", h_login_post)
    app.router.add_post("/prompt", h_prompt)
    app.router.add_post("/restart-bot", h_restart_bot)
    app.router.add_post("/restart-all", h_restart_all)
    app.router.add_get("/stats", h_stats)
    app.router.add_get("/health", h_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Веб-сервер на порту %s", PORT)

    asyncio.create_task(supervise_l6())
    asyncio.create_task(self_ping())

    await asyncio.Event().wait()   # вечно


if __name__ == "__main__":
    asyncio.run(main())
