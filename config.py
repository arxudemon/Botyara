"""
Конфигурация системы гачи (аналог механики Genshin Impact).

Все числа приближены к официальным значениям игры, но не являются
официальными данными HoYoverse — это независимая реализация вероятностной
модели по опубликованным игроками анализам (data mining сообщества).
"""

import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "gacha.db")

# --- Базовые шансы (до применения soft pity) ---
BASE_RATE_5STAR = 0.006   # 0.6%
BASE_RATE_4STAR = 0.051   # 5.1%
BASE_RATE_3STAR = 1 - BASE_RATE_5STAR - BASE_RATE_4STAR

# --- Pity (счётчик неудач) ---
HARD_PITY_5STAR = 90       # гарантия 5* на этой попытке
SOFT_PITY_START_5STAR = 74 # с этой попытки шанс 5* начинает резко расти
SOFT_PITY_STEP = 0.06      # прирост шанса за каждую попытку после soft pity

HARD_PITY_4STAR = 10       # гарантия 4* хотя бы раз в 10 попыток

# --- Система 50/50 ---
FIFTY_FIFTY_CHANCE = 0.5   # шанс выпадения баннерного 5* при первом 5* после гаранта

# Стоимость одной молитвы (в игровой валюте — "Переплетённая судьба")
COST_PER_PULL = 160  # примерно как Intertwined Fate / Fate Points

# Цвета для эмбедов и анимаций по редкости
RARITY_COLORS = {
    3: (74, 144, 217),    # синий
    4: (168, 85, 247),    # фиолетовый
    5: (250, 204, 21),    # золотой
}
