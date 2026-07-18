"""Асинхронный слой работы с БД (SQLite через aiosqlite)."""

import json
import aiosqlite

import config

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
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def get_state(user_id: int) -> dict:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM user_state WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO user_state (user_id) VALUES (?)", (user_id,)
            )
            await db.commit()
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
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
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
        await db.commit()


async def add_to_inventory(user_id: int, item_name: str, rarity: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO inventory (user_id, item_name, rarity) VALUES (?, ?, ?)",
            (user_id, item_name, rarity),
        )
        await db.commit()


async def get_inventory(user_id: int) -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT item_name, rarity, pulled_at FROM inventory WHERE user_id = ? ORDER BY pulled_at DESC",
            (user_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
