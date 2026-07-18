"""
Генерация GIF-анимации "раскрытия" карточки — аналог момента,
когда в игре появляется свет и затем сам персонаж/оружие.

Важно: здесь НЕ используются оригинальные ассеты HoYoverse (портреты, CG,
звуки). Анимация полностью процедурная: цветной фон по стихии/редкости +
расширяющийся световой круг + текст с именем. Звёзды редкости рисуются
как векторные фигуры (не текстом), чтобы не зависеть от шрифтов,
установленных на конкретном компьютере (Windows/Linux/Mac).
"""

import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config

ASSETS_DIR = Path(__file__).parent / "assets"
WIDTH, HEIGHT = 480, 640

ELEMENT_COLORS = {
    "Pyro": (237, 91, 63),
    "Hydro": (55, 148, 214),
    "Electro": (177, 108, 217),
    "Cryo": (150, 214, 224),
    "Anemo": (128, 200, 176),
    "Geo": (252, 175, 62),
    "Dendro": (164, 199, 63),
    None: (120, 120, 130),
}

# Если в data/*.json стихии/типы оружия записаны по-русски (например, вы
# переименовали "Cryo" -> "Крио"), эти словари переводят их обратно на
# английские ключи — только для внутренней логики (выбор цвета/иконки).
# То, что отображается на карточке (имя, подпись) остаётся как в JSON.
_ELEMENT_RU_TO_EN = {
    "Пиро": "Pyro", "Гидро": "Hydro", "Электро": "Electro", "Крио": "Cryo",
    "Анемо": "Anemo", "Гео": "Geo", "Дендро": "Dendro",
}
_WEAPON_RU_TO_EN = {
    "Меч": "Sword", "Клэймор": "Claymore", "Клеймор": "Claymore",
    "Копье": "Polearm", "Копьё": "Polearm", "Лук": "Bow",
    "Каталист": "Catalyst", "Катализатор": "Catalyst",
}


def _normalize_element(element: str | None) -> str | None:
    return _ELEMENT_RU_TO_EN.get(element, element)


def _normalize_weapon_type(weapon_type: str | None) -> str | None:
    return _WEAPON_RU_TO_EN.get(weapon_type, weapon_type)

# Шрифты ищем по нескольким типичным путям для разных ОС, чтобы текст
# с именами персонажей нормально выглядел и на Windows, и на Linux/Mac.
# Шрифт ищем в первую очередь среди файлов, которые идут вместе с ботом —
# это гарантирует одинаковый результат на любом хостинге (Windows, Linux,
# Kerit Cloud и т.п.) и поддержку кириллицы, если системного шрифта с
# нужными символами может не оказаться на сервере.
_BUNDLED_FONT = ASSETS_DIR / "fonts" / "DejaVuSans-Bold.ttf"

_FONT_CANDIDATES = [
    str(_BUNDLED_FONT),
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]

_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int) -> ImageFont.FreeTypeFont:
    if size in _font_cache:
        return _font_cache[size]
    for path in _FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(path, size)
            _font_cache[size] = font
            return font
        except OSError:
            continue
    font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def _draw_star(draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float, fill, alpha: int = 255):
    """Рисует одну 5-конечную звезду как многоугольник — работает без шрифтов."""
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        r = radius if i % 2 == 0 else radius * 0.42
        x = cx + r * math.cos(angle)
        y = cy - r * math.sin(angle)
        points.append((x, y))
    color = (*fill, alpha) if len(fill) == 3 else fill
    draw.polygon(points, fill=color)


def _draw_stars_row(img: Image.Image, cx: int, cy: int, count: int, alpha: int, star_radius: int = 14):
    """Рисует ряд звёзд редкости по центру, поверх изображения img (RGBA-режим)."""
    draw = ImageDraw.Draw(img, "RGBA")
    spacing = star_radius * 2.4
    total_width = spacing * (count - 1)
    start_x = cx - total_width / 2
    for i in range(count):
        _draw_star(draw, start_x + i * spacing, cy, star_radius, (255, 235, 160), alpha)


def _safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in " -_").strip()


def _weapon_glyph(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, weapon_type: str, color, alpha: int = 255):
    """Рисует простую пиктограмму типа оружия (не копирует арты игры — это свой значок)."""
    c = (*color, alpha)
    if weapon_type == "Sword":
        draw.line([(cx, cy - size), (cx, cy + size)], fill=c, width=max(2, int(size * 0.14)))
        draw.line([(cx - size * 0.4, cy - size * 0.2), (cx + size * 0.4, cy - size * 0.2)], fill=c, width=max(2, int(size * 0.12)))
    elif weapon_type == "Claymore":
        draw.rectangle([cx - size * 0.25, cy - size, cx + size * 0.25, cy + size * 0.6], fill=c)
        draw.line([(cx - size * 0.45, cy - size * 0.3), (cx + size * 0.45, cy - size * 0.3)], fill=c, width=max(2, int(size * 0.14)))
    elif weapon_type == "Polearm":
        draw.line([(cx, cy - size), (cx, cy + size)], fill=c, width=max(2, int(size * 0.1)))
        draw.polygon([(cx, cy - size), (cx - size * 0.35, cy - size * 0.4), (cx + size * 0.35, cy - size * 0.4)], fill=c)
    elif weapon_type == "Bow":
        bbox = [cx - size * 0.6, cy - size, cx + size * 0.6, cy + size]
        draw.arc(bbox, start=250, end=110, fill=c, width=max(2, int(size * 0.12)))
        draw.line([(cx + size * 0.35, cy - size * 0.85), (cx + size * 0.35, cy + size * 0.85)], fill=c, width=max(1, int(size * 0.05)))
    elif weapon_type == "Catalyst":
        draw.ellipse([cx - size * 0.5, cy - size * 0.5, cx + size * 0.5, cy + size * 0.5], outline=c, width=max(2, int(size * 0.12)))
        draw.line([(cx - size * 0.5, cy), (cx + size * 0.5, cy)], fill=c, width=max(2, int(size * 0.1)))
        draw.line([(cx, cy - size * 0.5), (cx, cy + size * 0.5)], fill=c, width=max(2, int(size * 0.1)))
    else:
        draw.ellipse([cx - size * 0.4, cy - size * 0.4, cx + size * 0.4, cy + size * 0.4], fill=c)


def _draw_silhouette(img: Image.Image, cx: int, cy: int, scale: float, alpha: int = 255):
    """Простой процедурный силуэт фигуры (не портрет конкретного персонажа —
    абстрактная фигура, чтобы карточка не выглядела пустым цветным прямоугольником)."""
    draw = ImageDraw.Draw(img, "RGBA")
    fill = (255, 255, 255, min(int(alpha * 0.55), 255))
    head_r = 0.16 * scale
    # голова
    draw.ellipse([cx - head_r, cy - scale * 0.62 - head_r, cx + head_r, cy - scale * 0.62 + head_r], fill=fill)
    # плечи/торс (трапеция)
    draw.polygon(
        [
            (cx - 0.30 * scale, cy + 0.55 * scale),
            (cx + 0.30 * scale, cy + 0.55 * scale),
            (cx + 0.16 * scale, cy - 0.30 * scale),
            (cx - 0.16 * scale, cy - 0.30 * scale),
        ],
        fill=fill,
    )


def _generate_portrait(item: dict, rarity: int, size: int) -> Image.Image:
    """Процедурный 'портрет' предмета: градиент по стихии/редкости + силуэт +
    иконка типа оружия. Полностью сгенерирован кодом, без использования
    оригинальных ассетов игры."""
    element = _normalize_element(item.get("element"))
    base_color = ELEMENT_COLORS.get(element, config.RARITY_COLORS[rarity])

    img = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    top = tuple(min(255, c + 40) for c in base_color)
    bottom = tuple(max(0, c - 60) for c in base_color)
    for y in range(size):
        t = y / size
        r = int(top[0] * (1 - t) + bottom[0] * t)
        gg = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        ImageDraw.Draw(img).line([(0, y), (size, y)], fill=(r, gg, b, 255))

    weapon_type = _normalize_weapon_type(item.get("weapon_type"))

    if "weapon_type" in item and "element" not in item:
        # Это оружие — рисуем крупную пиктограмму по центру
        draw = ImageDraw.Draw(img, "RGBA")
        _weapon_glyph(draw, size / 2, size / 2, size * 0.32, weapon_type, (255, 255, 255), 235)
    else:
        # Это персонаж — рисуем силуэт + маленькую иконку оружия внизу справа
        _draw_silhouette(img, size / 2, size / 2, size * 0.8, 255)
        if "weapon_type" in item:
            draw = ImageDraw.Draw(img, "RGBA")
            badge_r = size * 0.13
            bx, by = size * 0.80, size * 0.80
            draw.ellipse([bx - badge_r, by - badge_r, bx + badge_r, by + badge_r], fill=(20, 20, 24, 220))
            _weapon_glyph(draw, bx, by, badge_r * 0.75, weapon_type, (255, 255, 255), 255)

    return img


def _get_portrait(item: dict, rarity: int, size: int) -> Image.Image:
    """Определяет, какую картинку использовать для карточки, по приоритету:
    1) реальная иконка, скачанная через Ambr API (item['_icon_bytes']);
    2) локальный файл assets/icons/<name>.png, если вы положили его сами;
    3) процедурно сгенерированный портрет (силуэт + стихия/оружие)."""
    icon_bytes = item.get("_icon_bytes")
    if icon_bytes:
        try:
            icon = Image.open(io.BytesIO(icon_bytes)).convert("RGBA")
            # Иконки Ambr обычно квадратные с прозрачным фоном — просто вписываем
            icon.thumbnail((size, size), Image.LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            # Лёгкий цветной фон под иконкой, чтобы не было "дыр" на прозрачных местах
            bg_color = ELEMENT_COLORS.get(_normalize_element(item.get("element")), config.RARITY_COLORS[rarity])
            bg = Image.new("RGBA", (size, size), (*[max(0, c - 90) for c in bg_color], 255))
            canvas = Image.alpha_composite(bg, canvas)
            paste_x = (size - icon.width) // 2
            paste_y = (size - icon.height) // 2
            canvas.alpha_composite(icon, (paste_x, paste_y))
            return canvas
        except Exception:
            pass

    icon_path = ASSETS_DIR / "icons" / f"{_safe_filename(item['name'])}.png"
    if icon_path.exists():
        try:
            icon = Image.open(icon_path).convert("RGBA").resize((size, size))
            return icon
        except Exception:
            pass

    return _generate_portrait(item, rarity, size)


def _frame_background(rarity: int, progress: float, size=(WIDTH, HEIGHT)) -> Image.Image:
    """progress: 0..1 — доля прогресса анимации раскрытия."""
    w, h = size
    color = config.RARITY_COLORS[rarity]
    img = Image.new("RGB", (w, h), (18, 18, 24))
    draw = ImageDraw.Draw(img)

    max_radius = math.hypot(w, h)
    radius = max_radius * progress
    cx, cy = w // 2, h // 2
    glow = Image.new("L", (w, h), 0)
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius], fill=int(255 * min(progress * 1.5, 1))
    )
    glow = glow.filter(ImageFilter.GaussianBlur(max(20, w // 12)))

    color_layer = Image.new("RGB", (w, h), color)
    img = Image.composite(color_layer, img, glow)

    if rarity == 5 and progress > 0.4:
        ray_draw = ImageDraw.Draw(img, "RGBA")
        for i in range(16):
            angle = (i / 16) * 2 * math.pi + progress * 2
            length = max_radius * 0.9
            x2 = cx + length * math.cos(angle)
            y2 = cy + length * math.sin(angle)
            alpha = int(120 * progress)
            ray_draw.line([cx, cy, x2, y2], fill=(255, 235, 160, alpha), width=3)

    return img


def _draw_card_frame(item: dict, rarity: int, subtitle: str, progress: float) -> Image.Image:
    img = _frame_background(rarity, progress)
    item_name = item["name"]

    if progress > 0.55:
        card_alpha = int(255 * min((progress - 0.55) / 0.35, 1))
        card = Image.new("RGBA", (WIDTH - 60, HEIGHT - 220), (25, 25, 32, min(card_alpha, 230)))
        card_mask = card.split()[3]
        img.paste(card, (30, 140), card_mask)

        portrait_size = WIDTH - 60 - 40
        portrait = _get_portrait(item, rarity, portrait_size)
        portrait_alpha = portrait.split()[3].point(lambda a: int(a * card_alpha / 255))
        img.paste(portrait, (30 + 20, 140 + 15), portrait_alpha)

        _draw_stars_row(img, WIDTH // 2, HEIGHT - 170, rarity, card_alpha, star_radius=15)

        draw = ImageDraw.Draw(img, "RGBA")
        draw.text(
            (WIDTH // 2, HEIGHT - 120),
            item_name,
            font=_font(30),
            fill=(255, 255, 255, card_alpha),
            anchor="mm",
        )
        draw.text(
            (WIDTH // 2, HEIGHT - 85),
            subtitle,
            font=_font(18),
            fill=(210, 210, 220, card_alpha),
            anchor="mm",
        )

    return img


def _item_subtitle(item: dict) -> str:
    parts = []
    if "element" in item:
        parts.append(item["element"])
    if "weapon_type" in item:
        parts.append(item["weapon_type"])
    return " / ".join(parts)


def generate_reveal_gif(item: dict, rarity: int, n_frames: int = 24, duration_ms: int = 45) -> io.BytesIO:
    """Возвращает GIF в виде BytesIO, готовый к отправке в Discord (discord.File)."""
    subtitle = _item_subtitle(item)

    frames = []
    for i in range(n_frames):
        progress = i / (n_frames - 1)
        frame = _draw_card_frame(item, rarity, subtitle, progress)
        frames.append(frame.convert("P", palette=Image.ADAPTIVE))

    hold_frames = 12
    durations = [duration_ms] * n_frames + [duration_ms * 6] * hold_frames
    frames = frames + [frames[-1]] * hold_frames

    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=False,
    )
    buffer.seek(0)
    return buffer


# ---------------------------------------------------------------------------
# Анимация для 10-кратной молитвы: сетка 5x2, каждая карточка раскрывается
# по очереди, к концу анимации видно все 10 результатов одновременно.
# ---------------------------------------------------------------------------

_GRID_COLS, _GRID_ROWS = 5, 2
_CELL_W, _CELL_H = 220, 300
_GRID_PAD = 16
_GRID_W = _GRID_COLS * _CELL_W + _GRID_PAD * (_GRID_COLS + 1)
_GRID_H = _GRID_ROWS * _CELL_H + _GRID_PAD * (_GRID_ROWS + 1)


def _draw_cell(item: dict, rarity: int, subtitle: str, local_progress: float) -> Image.Image:
    """Одна карточка в сетке 10-кратной молитвы."""
    color = config.RARITY_COLORS[rarity]
    cell = Image.new("RGBA", (_CELL_W, _CELL_H), (25, 25, 32, 255))
    draw = ImageDraw.Draw(cell, "RGBA")

    portrait_top = 34
    portrait_size = _CELL_W - 20

    # Заливка цветом редкости нарастает снизу вверх
    fill_h = int(_CELL_H * min(local_progress * 1.3, 1))
    if fill_h > 0:
        overlay = Image.new("RGBA", (_CELL_W, _CELL_H), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rectangle([0, _CELL_H - fill_h, _CELL_W, _CELL_H], fill=(*color, 235))
        cell = Image.alpha_composite(cell, overlay)
        draw = ImageDraw.Draw(cell, "RGBA")

    border_color = (255, 235, 160) if rarity == 5 else ((255, 255, 255) if local_progress > 0 else (60, 60, 68))
    draw.rectangle([0, 0, _CELL_W - 1, _CELL_H - 1], outline=(*border_color, 255), width=3 if rarity == 5 else 2)

    if local_progress > 0.5:
        text_alpha = int(255 * min((local_progress - 0.5) / 0.4, 1))

        portrait = _get_portrait(item, rarity, portrait_size)
        portrait_alpha = portrait.split()[3].point(lambda a: int(a * text_alpha / 255))
        cell.paste(portrait, (10, portrait_top), portrait_alpha)

        _draw_stars_row(cell, _CELL_W // 2, 18, rarity, text_alpha, star_radius=8)
        draw = ImageDraw.Draw(cell, "RGBA")
        draw.text(
            (_CELL_W // 2, _CELL_H - 34),
            item["name"],
            font=_font(18),
            fill=(255, 255, 255, text_alpha),
            anchor="mm",
        )
        draw.text(
            (_CELL_W // 2, _CELL_H - 14),
            subtitle,
            font=_font(12),
            fill=(220, 220, 225, text_alpha),
            anchor="mm",
        )

    return cell


def generate_multi_reveal_gif(results: list[dict], n_frames: int = 40, duration_ms: int = 40) -> io.BytesIO:
    """
    Анимация для 10-кратной молитвы: карточки раскрываются по очереди
    (по одной, слева направо, сверху вниз), к финалу видно все 10 сразу.

    results — список словарей вида {"item": {...}, "rarity": int, ...}
    """
    n = len(results)
    frames = []

    for f in range(n_frames):
        overall_progress = f / (n_frames - 1)
        canvas = Image.new("RGBA", (_GRID_W, _GRID_H), (14, 14, 18, 255))

        for idx, res in enumerate(results):
            # Карточка idx начинает раскрываться в момент idx/n от общей анимации
            start = idx / n * 0.75
            end = start + 0.35
            if overall_progress <= start:
                local_progress = 0.0
            elif overall_progress >= end:
                local_progress = 1.0
            else:
                local_progress = (overall_progress - start) / (end - start)

            row = idx // _GRID_COLS
            col = idx % _GRID_COLS
            x = _GRID_PAD + col * (_CELL_W + _GRID_PAD)
            y = _GRID_PAD + row * (_CELL_H + _GRID_PAD)

            cell = _draw_cell(
                res["item"], res["rarity"], _item_subtitle(res["item"]), local_progress
            )
            canvas.alpha_composite(cell, (x, y))

        frames.append(canvas.convert("RGB").convert("P", palette=Image.ADAPTIVE))

    hold_frames = 15
    durations = [duration_ms] * n_frames + [duration_ms * 8] * hold_frames
    frames = frames + [frames[-1]] * hold_frames

    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=False,
    )
    buffer.seek(0)
    return buffer


def generate_grid_static(results: list[dict]) -> io.BytesIO:
    """
    Статичная (без анимации) сетка карточек — все ячейки отрисовываются
    сразу полностью раскрытыми. Используется для инвентаря: рамка + фото +
    имя, без анимации раскрытия, чтобы страницы открывались мгновенно.

    results — список словарей вида {"item": {...}, "rarity": int, ...}
    """
    canvas = Image.new("RGBA", (_GRID_W, _GRID_H), (14, 14, 18, 255))

    for idx, res in enumerate(results):
        row = idx // _GRID_COLS
        col = idx % _GRID_COLS
        x = _GRID_PAD + col * (_CELL_W + _GRID_PAD)
        y = _GRID_PAD + row * (_CELL_H + _GRID_PAD)

        cell = _draw_cell(res["item"], res["rarity"], _item_subtitle(res["item"]), 1.0)
        canvas.alpha_composite(cell, (x, y))

    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
