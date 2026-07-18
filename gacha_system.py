"""
Ядро вероятностной системы гачи.

Реализует:
- Soft pity для 5* (шанс резко растёт с 74-й попытки)
- Hard pity (гарантия на 90-й попытке)
- Систему 50/50 для limited-баннера
- Гарантию 4* минимум раз в 10 попыток
"""

import json
import random
from pathlib import Path

import config

DATA_DIR = Path(__file__).parent / "data"


def _load(filename: str) -> list[dict]:
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


CHARACTERS = _load("characters.json")
WEAPONS = _load("weapons.json")

# Быстрый доступ к полным данным предмета (стихия/тип оружия) по имени —
# нужен, чтобы по записи из инвентаря (в БД хранится только имя и редкость)
# восстановить информацию для отрисовки портрета.
ITEM_BY_NAME: dict[str, dict] = {i["name"]: i for i in CHARACTERS + WEAPONS}


def get_item_info(name: str, fallback_rarity: int) -> dict:
    """Возвращает полное описание предмета по имени, либо минимальную
    заглушку, если предмета почему-то нет в текущих data-файлах."""
    info = ITEM_BY_NAME.get(name)
    if info:
        return info
    return {"name": name, "rarity": fallback_rarity}


def _rate_5star(pity: int) -> float:
    """Возвращает текущий шанс выпадения 5* с учётом soft pity."""
    if pity >= config.HARD_PITY_5STAR - 1:
        return 1.0
    if pity + 1 >= config.SOFT_PITY_START_5STAR:
        steps_into_soft = pity + 1 - config.SOFT_PITY_START_5STAR + 1
        rate = config.BASE_RATE_5STAR + steps_into_soft * config.SOFT_PITY_STEP
        return min(rate, 1.0)
    return config.BASE_RATE_5STAR


def roll_rarity(pity_5star: int, pity_4star: int) -> int:
    """Определяет редкость одного тяня с учётом обоих pity-счётчиков."""
    rate5 = _rate_5star(pity_5star)

    if pity_4star >= config.HARD_PITY_4STAR - 1:
        # Гарантирован минимум 4* (либо выше, если повезёт на 5*)
        roll = random.random()
        return 5 if roll < rate5 else 4

    roll = random.random()
    if roll < rate5:
        return 5
    if roll < rate5 + config.BASE_RATE_4STAR:
        return 4
    return 3


def pick_item(rarity: int, pool: list[dict]) -> dict:
    candidates = [item for item in pool if item["rarity"] == rarity]
    if not candidates:
        # Фолбэк: например, персонажей 3* не существует (только оружие),
        # поэтому такой "тянь" на баннере персонажей превращается в 4*.
        for fallback_rarity in (4, 3, 5):
            candidates = [item for item in pool if item["rarity"] == fallback_rarity]
            if candidates:
                break
    return random.choice(candidates)


def _get_pool(pool_type: str) -> list[dict]:
    if pool_type == "weapon":
        return WEAPONS
    if pool_type == "standard":
        # Смешанный пул: только предметы со standard-баннера (без лимитных),
        # и персонажи, и оружие вместе — как Standard Wish в настоящей игре.
        return [i for i in CHARACTERS if i["banner"] == "standard"] + \
               [i for i in WEAPONS if i["banner"] == "standard"]
    return CHARACTERS


def single_pull(state: dict, pool_type: str = "character") -> dict:
    """
    Выполняет один тянь.

    pool_type:
        "character" — баннер персонажей (лимитный + стандартный, есть 50/50)
        "weapon"    — баннер оружия (лимитный + стандартный, есть 50/50)
        "standard"  — смешанный стандартный баннер: и персонажи, и оружие
                      вместе, без системы 50/50 (в игре у него её тоже нет)

    state — словарь с полями:
        pity_5star, pity_4star, guaranteed_limited (bool)
    Изменяет state на месте и возвращает результат тяня:
        {"item": {...}, "rarity": int, "is_limited_won": bool}
    """
    pool = _get_pool(pool_type)

    rarity = roll_rarity(state["pity_5star"], state["pity_4star"])

    if rarity == 5:
        state["pity_5star"] = 0
        state["pity_4star"] += 1

        if pool_type == "standard":
            # Нет рейт-апа — все 5* стандартного баннера равновероятны
            candidates = [i for i in pool if i["rarity"] == 5]
            item = random.choice(candidates)
            return {"item": item, "rarity": 5, "is_limited_won": False}

        limited_pool = [i for i in pool if i["rarity"] == 5 and i["banner"] == "limited"]
        standard_pool = [i for i in pool if i["rarity"] == 5 and i["banner"] == "standard"]

        won_limited = state.get("guaranteed_limited", False) or random.random() < config.FIFTY_FIFTY_CHANCE

        if won_limited and limited_pool:
            item = random.choice(limited_pool)
            state["guaranteed_limited"] = False
        else:
            item = random.choice(standard_pool) if standard_pool else random.choice(limited_pool)
            state["guaranteed_limited"] = True  # проиграли 50/50 — следующий 5* гарантирован

        return {"item": item, "rarity": 5, "is_limited_won": won_limited}

    elif rarity == 4:
        state["pity_5star"] += 1
        state["pity_4star"] = 0
        item = pick_item(4, pool)
        return {"item": item, "rarity": 4, "is_limited_won": False}

    else:
        state["pity_5star"] += 1
        state["pity_4star"] += 1
        if pool_type == "character":
            # В настоящей игре 3* на баннере персонажей — это всегда оружие
            # (заполнитель), персонажей 3* редкости не существует вовсе.
            filler_pool = [i for i in WEAPONS if i["rarity"] == 3]
            item = random.choice(filler_pool)
        else:
            item = pick_item(3, pool)
        return {"item": item, "rarity": item["rarity"], "is_limited_won": False}


def ten_pull(state: dict, pool_type: str = "character") -> list[dict]:
    return [single_pull(state, pool_type) for _ in range(10)]
