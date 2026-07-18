"""Асинхронный слой работы с БД (SQLite через aiosqlite)."""

import asyncio
import json
import aiosqlite

import config

_db: aiosqlite.Connection | None = None

_locks: dict[int, asyncio.Lock] = {}


def lock_for(user_id: int) -> asyncio.Lock:
    return _locks.setdefault(user_id, asyncio.Lock())


_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_state (
    user_id INTEGER PRIMARY KEY,
    pity_5star INTEGER NOT NULL DEFAULT 0,
    pity_4star INTEGER NOT NULL DEFAULT 0,
    guaranteed_limited INTEGER NOT NULL DEFAULT 0,
    primogems INTEGER NOT NULL DEFAULT 16000
);

CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    rarity INTEGER NOT NULL,
    pulled_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db():
    global _db
    _db = await aiosqlite.connect(config.DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(_SCHEMA)
    await _db.commit()


async def close():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def get_state(user_id: int) -> dict:
    async with _db.execute(
        "SELECT * FROM user_state WHERE user_id = ?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        await _db.execute(
            "INSERT OR IGNORE INTO user_state (user_id) VALUES (?)", (user_id,)
        )
        await _db.commit()
        return {
            "pity_5star": 0,
            "pity_4star": 0,
            "guaranteed_limited": False,
            "primogems": 16000,
        }
    return {
        "pity_5star": row["pity_5star"],
        "pity_4star": row["pity_4star"],
        "guaranteed_limited": bool(row["guaranteed_limited"]),
        "primogems": row["primogems"],
    }


async def save_state(user_id: int, state: dict):
    await _db.execute(
        """UPDATE user_state
           SET pity_5star = ?, pity_4star = ?, guaranteed_limited = ?, primogems = ?
           WHERE user_id = ?""",
        (
            state["pity_5star"],
            state["pity_4star"],
            int(state["guaranteed_limited"]),
            state["primogems"],
            user_id,
        ),
    )
    await _db.commit()


async def add_to_inventory(user_id: int, item_name: str, rarity: int):
    await _db.execute(
        "INSERT INTO inventory (user_id, item_name, rarity) VALUES (?, ?, ?)",
        (user_id, item_name, rarity),
    )
    await _db.commit()


async def get_inventory(user_id: int) -> list[dict]:
    async with _db.execute(
        "SELECT item_name, rarity, pulled_at FROM inventory WHERE user_id = ? ORDER BY pulled_at DESC",
        (user_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]
