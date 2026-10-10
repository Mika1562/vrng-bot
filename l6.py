import os
import logging
import httpx
import yaml
import discord
from discord.ext import commands

# ============================================================
# КОНФИГ
# ============================================================
with open("conf.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "nvidia/nemotron-3.5-lightning:free"

OWNER_ID = int(config["owner"]["id"])
FRIEND_IDS = [int(x) for x in config["friends"]["ids"]]
VIP_IDS = [int(x) for x in config.get("vip", {}).get("ids", [])]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

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
        return (
            "Обращайся к пользователю как к ГЛАВНОЙ ХОЗЯЙКЕ. "
            "Она — госпожа, которой ты служишь преданно."
        )
    elif status == "friend":
        return (
            f"Этот пользователь {author_name} — ДРУГ ХОЗЯЙКИ. "
            "Обращайся к нему вежливо, но чуть менее формально."
        )
    elif status == "vip":
        return (
            f"Этот пользователь {author_name} — ВАЖНЫЙ ГОСТЬ ХОЗЯЙКИ. "
            "Обращайся к нему особенно предупредительно и почтительно, "
            "но без фамильярности."
        )
    else:
        return (
            f"Этот пользователь {author_name} — ПОСТОРОННИЙ. "
            "Обращайся формально, холодно, без энтузиазма."
        )


# ============================================================
# ЛОГИ
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ============================================================
# HTTP-КЛИЕНТ
# ============================================================
http_client: httpx.AsyncClient | None = None


async def ask_openrouter(messages: list[dict]) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://discord.com",
        "X-Title": "My Discord Bot",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
    }

    response = await http_client.post(
        OPENROUTER_URL, headers=headers, json=payload
    )

    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text}")

    return response.json()["choices"][0]["message"]["content"]


def split_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    return [text[i : i + limit] for i in range(0, len(text), limit)]


# ============================================================
# БОТ
# ============================================================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    global http_client
    http_client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
    logger.info("Горничная Катя запущена! (%s). Модель: %s", bot.user, MODEL)
    logger.info("Владелец: %s | Друзья: %s | VIP: %s", OWNER_ID, FRIEND_IDS, VIP_IDS)


@bot.event
async def on_message(message: discord.Message):

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

    role_instruction = role_ins(author_name, author_id)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": role_instruction},
        {"role": "user", "content": prompt},
    ]

    async with message.channel.typing():
        try:
            answer = await ask_openrouter(messages)
        except Exception as e:
            logger.exception("Ошибка при запросе к OpenRouter")

            status = get_user_status(author_id)
            if status == "owner":
                error_msg = "Прошу прощения, госпожа, но произошла ошибка..."
            elif status == "vip":
                error_msg = "Приношу извинения, произошла ошибка."
            else:
                error_msg = "Извините, произошла ошибка."

            await message.channel.send(f"{error_msg} Техническая деталь: {e}")
            return

    for chunk in split_message(answer):
        await message.channel.send(chunk)


# ============================================================
# КОМАНДА ДЛЯ ОТЛАДКИ
# ============================================================
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


# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
