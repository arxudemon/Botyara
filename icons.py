"""
Получение официальных иконок персонажей и оружия через открытый API
Project Amber (gi.yatta.moe), с помощью пакета ambr-py:
https://github.com/seriaati/ambr

Эти иконки — не файлы, которые мы храним или распространяем вместе с
ботом: код запрашивает их у публичного API в реальном времени, каждый раз,
когда бот работает у вас. Это ваш выбор как владельца приватного бота —
аналогично тому, как любой Discord-бот может подтягивать картинки по
внешней ссылке (например, аватарки или обложки).

ВАЖНО: сами иконки — собственность HoYoverse, Project Amber лишь
предоставляет к ним открытый доступ. Используйте это для приватного или
некоммерческого сервера. Если API окажется недоступен (нет интернета,
сайт лёг, изменился) — бот автоматически откатится на процедурные
портреты из animator.py, ничего не сломается.
"""

import asyncio
import logging

import aiohttp

try:
    import ambr
    _AMBR_AVAILABLE = True
except ImportError:
    _AMBR_AVAILABLE = False

logger = logging.getLogger(__name__)

# Если вы переименовали персонажа/оружие в data/*.json на русский язык,
# поиск иконки по имени в Ambr API (там имена английские) перестанет
# находить совпадение. Здесь можно добавить соответствие "русское имя,
# как в вашем JSON" -> "английское имя в Ambr", чтобы иконка всё равно
# подтягивалась. Ключи должны совпадать с полем "name" в data/*.json.
NAME_ALIASES: dict[str, str] = {
    "Гань Юй": "Ganyu",
    "Ху Тао": "Hu Tao",
    "Райдэн Сёгун": "Raiden Shogun",
    "Чжун Ли": "Zhongli",
    "Дилюк": "Diluc",
}

_character_icons: dict[str, str] = {}
_weapon_icons: dict[str, str] = {}
# Дополнительный индекс "нормализованное имя" -> URL, на случай если
# точное имя в Ambr слегка отличается регистром/пробелами от вашего JSON.
_character_icons_normalized: dict[str, str] = {}
_weapon_icons_normalized: dict[str, str] = {}
_loaded = False
_load_lock = asyncio.Lock()

_download_session: aiohttp.ClientSession | None = None
_bytes_cache: dict[str, bytes] = {}


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().split())


async def preload():
    """Один раз при старте бота загружает список URL иконок всех персонажей
    и оружия. Если что-то пошло не так — просто оставляет кэш пустым, и
    бот работает дальше на процедурных портретах."""
    global _loaded
    if not _AMBR_AVAILABLE:
        logger.warning("Пакет ambr-py не установлен — иконки из Ambr API отключены (pip install ambr-py)")
        _loaded = True
        return

    async with _load_lock:
        if _loaded:
            return
        try:
            async with ambr.AmbrAPI(lang=ambr.Language.EN) as api:
                characters = await api.fetch_characters()
                for c in characters:
                    _character_icons[c.name] = c.icon
                    _character_icons_normalized[_normalize_name(c.name)] = c.icon

                weapons = await api.fetch_weapons()
                for w in weapons:
                    _weapon_icons[w.name] = w.icon
                    _weapon_icons_normalized[_normalize_name(w.name)] = w.icon

            logger.info(
                f"Ambr API: загружено {len(_character_icons)} иконок персонажей, "
                f"{len(_weapon_icons)} иконок оружия"
            )
        except Exception as e:
            logger.warning(f"Не удалось загрузить иконки из Ambr API, будут использованы процедурные портреты: {e}")
        _loaded = True


def get_icon_url(name: str, kind: str) -> str | None:
    cache = _character_icons if kind == "character" else _weapon_icons
    cache_normalized = _character_icons_normalized if kind == "character" else _weapon_icons_normalized

    url = cache.get(name)
    if url:
        return url

    alias = NAME_ALIASES.get(name)
    if alias:
        url = cache.get(alias)
        if url:
            return url
        url = cache_normalized.get(_normalize_name(alias))
        if url:
            return url

    # Последняя попытка: то же имя, но без учёта регистра/лишних пробелов
    return cache_normalized.get(_normalize_name(name))


async def get_icon_bytes(name: str, kind: str, retries: int = 2) -> bytes | None:
    """Скачивает (и кэширует в памяти на время работы бота) байты иконки
    предмета по его имени. Возвращает None, если иконка недоступна —
    вызывающий код в этом случае должен откатиться на процедурный портрет.
    При сетевой ошибке делает несколько попыток подряд, прежде чем сдаться —
    единичные обрывы соединения не должны надолго лишать предмет иконки."""
    global _download_session

    cache_key = f"{kind}:{name}"
    if cache_key in _bytes_cache:
        return _bytes_cache[cache_key]

    url = get_icon_url(name, kind)
    if not url:
        logger.info(f"Иконка для '{name}' не найдена в базе Ambr API (используется процедурный портрет)")
        return None

    if _download_session is None:
        _download_session = aiohttp.ClientSession()

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            async with _download_session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    _bytes_cache[cache_key] = data
                    return data
                last_error = f"HTTP {resp.status}"
        except Exception as e:
            last_error = str(e)
        if attempt < retries:
            await asyncio.sleep(0.5)

    logger.warning(f"Не удалось скачать иконку '{name}' за {retries} попытки: {last_error}")
    return None


async def close():
    global _download_session
    if _download_session is not None:
        await _download_session.close()
        _download_session = None
