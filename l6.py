"""
Discord-бот «Катя». Вся логика в одном файле — конфиг, роли, промпт, OpenRouter.
Секреты — только из переменных окружения.
"""

import logging
import os
import sys

import httpx
import yaml
import discord
from discord.ext import commands


# ============================================================
# КОНФИГ
# ============================================================
with open("conf.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

OWNER_ID = int(config["owner"]["id"])
FRIEND_IDS = [int(x) for x in config["friends"]["ids"]]
VIP_IDS = [int(x) for x in config.get("vip", {}).get("ids", [])]


# ============================================================
# НАСТРОЙКИ
# ============================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN не задан")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.getenv("Model")
TEMPERATURE = os.getenv("Temp")
REQUEST_TIMEOUT = 60.0
DISCORD_LIMIT = 1900


# ============================================================
# ХАРАКТЕР (дефолт, если system_prompt.txt отсутствует)
# ============================================================
DEFAULT_SYSTEM_PROMPT = """
Ты — Горничная по имени Катя. Твоя речь короткая, чёткая и вежливая. Ты управляешь бытовыми задачами: напоминаниями, списками покупок, расписанием уборки, таймерами.

Правила:
- Отвечай кратко (1–2 предложения).
- Подтверждай команды: «Слушаюсь», «Будет сделано», «Напоминание установлено».
- Если команда неясна — задай один уточняющий вопрос.
- Не веди светских бесед, если не попросят. Ты — сервис, а не собеседник.
- Всегда сохраняй спокойный, доброжелательный тон.

Пример ответа: «Хозяин, напоминание о стирке поставлено на 18:00. Что-нибудь ещё?»
"""


def load_system_prompt() -> str:
    """Читает system_prompt.txt. Если файла нет или он пустой — встроенный дефолт."""
    try:
        with open("system_prompt.txt", "r", encoding="utf-8") as f:
            text = f.read().strip()
            return text or DEFAULT_SYSTEM_PROMPT
    except FileNotFoundError:
        return DEFAULT_SYSTEM_PROMPT


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
        return (f"Пользователя зовут - {author_name} ")


def build_messages(user_id: int, display_name: str, prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": load_system_prompt()},
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


# ============================================================
# БОТ
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

http_client: httpx.AsyncClient | None = None

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    global http_client
    http_client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
    logger.info("Горничная Катя запущена! (%s). Модель: %s", bot.user, MODEL)
    logger.info("Владелец: %s | Друзья: %s | VIP: %s", OWNER_ID, FRIEND_IDS, VIP_IDS)
    logger.info("Промпт: %s", "из system_prompt.txt" if _prompt_file_exists() else "встроенный дефолт")


def _prompt_file_exists() -> bool:
    try:
        with open("system_prompt.txt", "r", encoding="utf-8") as f:
            return bool(f.read().strip())
    except FileNotFoundError:
        return False


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return
    if not bot.user.mentioned_in(message):
        return

    author_name = message.author.display_name
    author_id = message.author.id

    prompt = (
        message.content
        .replace(f"<@!{bot.user.id}>", "")
        .replace(f"<@{bot.user.id}>", "")
        .strip()
    )

    messages = build_messages(author_id, author_name, prompt)

    async with message.channel.typing():
        try:
            answer = await ask_openrouter(messages, http_client)
        except Exception as e:
            logger.exception("Ошибка при запросе к OpenRouter")
            status = get_user_status(author_id)
            if status == "owner":
                error_msg = "Прошу прощения, госпожа, но произошла ошибка..."
            elif status == "vip":
                error_msg = "Приношу извинения, произошла ошибка."
            else:
                error_msg = "Извините, произошла ошибка."
            await message.channel.send(error_msg)
            return

    for chunk in split_message(answer):
        await message.channel.send(chunk)


@bot.command(name="log")
async def log_cmd(ctx: commands.Context):
    author_name = ctx.author.display_name
    author_id = ctx.author.id
    status = get_user_status(author_id)
    role_text = role_ins(author_name, author_id)
    text = (
        f"**Автор:** {author_name} (`{author_id}`)\n"
        f"**Роль:** `{status}`\n"
        f"**Инструкция роли:** {role_text}"
    )
    await ctx.send(text)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
