import logging
import os
import sys
import httpx
import discord
from discord.ext import commands

from bot_logic import (
    MODEL, OWNER_ID, FRIEND_IDS, VIP_IDS,
    get_user_status, role_ins, build_messages,
    ask_openrouter, split_message,
)


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN не задан")


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
    http_client = httpx.AsyncClient(timeout=60.0)
    logger.info("Горничная Катя запущена! (%s). Модель: %s", bot.user, MODEL)
    logger.info("Владелец: %s | Друзья: %s | VIP: %s", OWNER_ID, FRIEND_IDS, VIP_IDS)


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
            await message.channel.send(f"{error_msg} Техническая деталь: {e}")
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
