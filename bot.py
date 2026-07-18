import asyncio
import logging

import discord
from discord.ext import commands

import config
import database
import icons

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    # Загружаем список URL иконок персонажей/оружия через Ambr API.
    # Если API недоступен — бот молча откатится на процедурные портреты.
    asyncio.create_task(icons.preload())
    try:
        synced = await bot.tree.sync()
        logging.info(f"Синхронизировано {len(synced)} слэш-команд")
    except Exception as e:
        logging.error(f"Ошибка синхронизации команд: {e}")
    logging.info(f"Бот запущен как {bot.user}")


async def main():
    await database.init_db()
    async with bot:
        await bot.load_extension("cogs.gacha_cog")
        try:
            await bot.start(config.DISCORD_TOKEN)
        finally:
            await icons.close()
            await database.close()


if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        raise SystemExit(
            "Не задан DISCORD_TOKEN. Создайте файл .env и добавьте: DISCORD_TOKEN=ваш_токен"
        )
    asyncio.run(main())
