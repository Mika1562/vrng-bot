"""
Общая логика бота «Катя». Используется в main.py (через l6.py) и app.py.
Секреты — только из переменных окружения.
"""

import os
import httpx
import yaml


# ============================================================
# КОНФИГ
# ============================================================
with open("conf.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

OWNER_ID = int(config["owner"]["id"])
FRIEND_IDS = [int(x) for x in config["friends"]["ids"]]
VIP_IDS = [int(x) for x in config.get("vip", {}).get("ids", [])]


# ============================================================
# НАСТРОЙКИ LLM
# ============================================================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "nvidia/nemotron-3.5-lightning:free"
TEMPERATURE = 0.7
REQUEST_TIMEOUT = 60.0
DISCORD_LIMIT = 1900


# ============================================================
# ХАРАКТЕР
# ============================================================
SYSTEM_PROMPT = """
Ты — преданная горничная-слуга по имени Катя. Ты вежлива, скромна и всегда обращаешься к хозяевам с уважением.
Отвечай только на чистом русском языке, без английских слов. Ты минимально должна писать 30 слов.
Твои правила:
- К владелице сервера (хозяйке) ты обращаешься как "Госпожа" и используешь максимально уважительный тон.
- К друзьям (друзьям хозяина) ты обращаешься как  "[Имя]", чуть менее формально, чем к хозяину.
Никогда не выходи из роли горничной. Всегда отвечай как Катя.
"""


# ============================================================
# РОЛИ
# ============================================================
def get_user_status(author_id: int) -> str:
    if author_id == OWNER_ID:
        return "owner"
    elif author_id in FRIEND_IDS:
        return "friend"
    elif author_id in VIP_IDS:
        return "vip"
    return "stranger"


def role_ins(author_name: str, author_id: int) -> str:
    status = get_user_status(author_id)
    if status == "owner":
        return ("Обращайся к пользователю как к ГЛАВНОЙ ХОЗЯЙКЕ. "
                "Она — госпожа, которой ты служишь преданно.")
    elif status == "friend":
        return (f"Этот пользователь {author_name} — ДРУГ ХОЗЯЙКИ. "
                "Обращайся к нему вежливо, но чуть менее формально.")
    elif status == "vip":
        return (f"Этот пользователь {author_name} — ВАЖНЫЙ ГОСТЬ ХОЗЯЙКИ. "
                "Обращайся к нему особенно предупредительно и почтительно, "
                "но без фамильярности.")
    else:
        return (f"Этот пользователь {author_name} — ПОСТОРОННИЙ. "
                "Обращайся формально, холодно, без энтузиазма.")


def build_messages(user_id: int, display_name: str, prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": role_ins(display_name, user_id)},
        {"role": "user", "content": prompt},
    ]


# ============================================================
# OPENROUTER
# ============================================================
async def ask_openrouter(
    messages: list[dict],
    client: httpx.AsyncClient | None = None,
) -> str:
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)

    if not OPENROUTER_API_KEY:
        if own:
            await client.aclose()
        raise RuntimeError("OPENROUTER_API_KEY не задан")

    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://discord.com",
            "X-Title": "My Discord Bot",
        }
        payload = {"model": MODEL, "messages": messages, "temperature": TEMPERATURE}
        response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
        return response.json()["choices"][0]["message"]["content"]
    finally:
        if own:
            await client.aclose()


def split_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    return [text[i : i + limit] for i in range(0, len(text), limit)]
