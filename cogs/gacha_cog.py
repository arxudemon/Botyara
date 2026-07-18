import asyncio
import math

import discord
from discord import app_commands
from discord.ext import commands

import config
import database
import gacha_system
import icons
from animator import generate_reveal_gif, generate_multi_reveal_gif, generate_grid_static

_BANNER_CHOICES = [
    app_commands.Choice(name="Персонажи (событийный)", value="character"),
    app_commands.Choice(name="Оружие (событийный)", value="weapon"),
    app_commands.Choice(name="Стандартный (персонажи + оружие)", value="standard"),
]

_INVENTORY_PAGE_SIZE = 10

# Рендер Pillow — синхронный и CPU-bound, поэтому уезжает в отдельный поток:
# иначе он блокирует event loop целиком, и Discord успевает протухнуть
# интеракции другого юзера до defer() (ошибка 10062 Unknown interaction).
# Семафор держит рендеры по одному: параллелить их смысла нет (loop и так
# свободен), а animator._font_cache шарит объекты шрифтов между потоками.
_RENDER_SEMAPHORE = asyncio.Semaphore(1)


def _item_kind(item: dict) -> str:
    """Определяет, персонаж это или оружие, по структуре словаря."""
    return "character" if "element" in item else "weapon"


async def _attach_icon(item: dict) -> dict:
    """Пытается скачать реальную иконку через Ambr API и прикрепить её
    байты к item — тогда animator.py использует настоящую картинку вместо
    процедурного портрета. Если не вышло — item просто остаётся без иконки."""
    icon_bytes = await icons.get_icon_bytes(item["name"], _item_kind(item))
    if icon_bytes:
        item = {**item, "_icon_bytes": icon_bytes}
    return item


class InventoryView(discord.ui.View):
    """Кнопки ◀ ▶ под сообщением инвентаря для листания страниц."""

    def __init__(self, owner_id: int, entries: list[dict]):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.entries = entries
        self.page = 0
        self.total_pages = max(1, math.ceil(len(entries) / _INVENTORY_PAGE_SIZE))
        self._sync_buttons()

    def _sync_buttons(self):
        self.previous_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.total_pages - 1

    async def _render_page(self) -> discord.File:
        start = self.page * _INVENTORY_PAGE_SIZE
        page_entries = self.entries[start:start + _INVENTORY_PAGE_SIZE]

        results = []
        for entry in page_entries:
            info = gacha_system.get_item_info(entry["item_name"], entry["rarity"])
            info = {**info, "name": entry["item_name"]}
            info = await _attach_icon(info)
            results.append({"item": info, "rarity": entry["rarity"]})

        async with _RENDER_SEMAPHORE:
            png_buffer = await asyncio.to_thread(generate_grid_static, results)
        return discord.File(png_buffer, filename="inventory.png")

    async def _update_message(self, interaction: discord.Interaction):
        # Discord даёт всего 3 секунды на первый отклик на нажатие кнопки.
        # Генерация гифки (скачивание иконок + отрисовка кадров) может занять
        # дольше, поэтому сразу "подтверждаем" нажатие через defer(), а уже
        # потом не спеша готовим картинку и редактируем сообщение.
        await interaction.response.defer()
        self._sync_buttons()
        file = await self._render_page()
        embed = discord.Embed()
        embed.set_image(url="attachment://inventory.png")
        embed.set_footer(text=f"Страница {self.page + 1}/{self.total_pages} · Всего предметов: {len(self.entries)}")
        await interaction.edit_original_response(embed=embed, attachments=[file], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Это не ваш инвентарь.", ephemeral=True)
            return
        self.page = max(0, self.page - 1)
        await self._update_message(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Это не ваш инвентарь.", ephemeral=True)
            return
        self.page = min(self.total_pages - 1, self.page + 1)
        await self._update_message(interaction)


class GachaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pull", description="Сделать одну молитву (гача-тянь)")
    @app_commands.describe(banner="Тип баннера")
    @app_commands.choices(banner=_BANNER_CHOICES)
    async def pull(self, interaction: discord.Interaction, banner: app_commands.Choice[str]):
        await interaction.response.defer(thinking=True)

        async with database.lock_for(interaction.user.id):
            state = await database.get_state(interaction.user.id)
            result = gacha_system.single_pull(state, pool_type=banner.value)
            await database.save_state(interaction.user.id, state)
            await database.add_to_inventory(
                interaction.user.id, result["item"]["name"], result["rarity"]
            )

        item_with_icon = await _attach_icon(result["item"])
        async with _RENDER_SEMAPHORE:
            gif_buffer = await asyncio.to_thread(
                generate_reveal_gif, item_with_icon, result["rarity"]
            )
        file = discord.File(gif_buffer, filename="pull.gif")

        embed = discord.Embed(
            color=discord.Color.from_rgb(*config.RARITY_COLORS[result["rarity"]]),
        )
        embed.set_image(url="attachment://pull.gif")
        embed.set_footer(
            text=f"Pity 5★: {state['pity_5star']}/90 · Pity 4★: {state['pity_4star']}/10"
        )

        await interaction.followup.send(embed=embed, file=file)

    @app_commands.command(name="pull10", description="Сделать 10 молитв подряд")
    @app_commands.describe(banner="Тип баннера")
    @app_commands.choices(banner=_BANNER_CHOICES)
    async def pull10(self, interaction: discord.Interaction, banner: app_commands.Choice[str]):
        await interaction.response.defer(thinking=True)

        async with database.lock_for(interaction.user.id):
            state = await database.get_state(interaction.user.id)
            results = gacha_system.ten_pull(state, pool_type=banner.value)
            await database.save_state(interaction.user.id, state)
            for r in results:
                await database.add_to_inventory(interaction.user.id, r["item"]["name"], r["rarity"])

        # Подтягиваем реальные иконки для всех 10 результатов параллельно
        items_with_icons = [await _attach_icon(r["item"]) for r in results]
        results_with_icons = [
            {**r, "item": item} for r, item in zip(results, items_with_icons)
        ]

        best = max(results, key=lambda r: r["rarity"])
        async with _RENDER_SEMAPHORE:
            gif_buffer = await asyncio.to_thread(
                generate_multi_reveal_gif, results_with_icons
            )
        file = discord.File(gif_buffer, filename="pull10.gif")

        embed = discord.Embed(
            color=discord.Color.from_rgb(*config.RARITY_COLORS[best["rarity"]]),
        )
        embed.set_image(url="attachment://pull10.gif")
        embed.set_footer(
            text=f"Pity 5★: {state['pity_5star']}/90 · Pity 4★: {state['pity_4star']}/10"
        )

        await interaction.followup.send(embed=embed, file=file)

    @app_commands.command(name="inventory", description="Показать полученных персонажей и оружие")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        entries = await database.get_inventory(interaction.user.id)
        if not entries:
            await interaction.followup.send("У вас пока нет полученных предметов.")
            return

        view = InventoryView(interaction.user.id, entries)
        file = await view._render_page()

        embed = discord.Embed()
        embed.set_image(url="attachment://inventory.png")
        embed.set_footer(text=f"Страница 1/{view.total_pages} · Всего предметов: {len(entries)}")

        await interaction.followup.send(embed=embed, file=file, view=view)

    @app_commands.command(name="pity", description="Показать текущий счётчик pity")
    async def pity(self, interaction: discord.Interaction):
        state = await database.get_state(interaction.user.id)
        embed = discord.Embed(title="Ваш прогресс pity")
        embed.add_field(name="Pity до 5★", value=f"{state['pity_5star']}/90", inline=True)
        embed.add_field(name="Pity до 4★", value=f"{state['pity_4star']}/10", inline=True)
        embed.add_field(
            name="Гарант лимитки",
            value="Да" if state["guaranteed_limited"] else "Нет",
            inline=True,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GachaCog(bot))
