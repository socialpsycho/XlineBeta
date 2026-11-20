import random

def generate_mines(count: int = 3, width: int = 25) -> list[int]:
    # Теперь первым аргументом идет count, вторым - размер поля (5x5 = 25)
    if not 0 < count < width:
        raise ValueError("Mine count must be between zero and board size.")
    return sorted(random.sample(range(width), count))

def generate_tower_layout(cells: int, bombs_per_floor: int, floors: int) -> dict[int,list[int]]:
    if not 0 < bombs_per_floor < cells or floors < 1:
        raise ValueError("Invalid Tower dimensions.")
    return {floor: sorted(random.sample(range(cells),bombs_per_floor)) for floor in range(floors)}

# --- ГЕНЕРАТОР ДЛЯ СЛОТОВ ---
SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
# Веса подобраны так, чтобы RTP был ~97%
SLOT_WEIGHTS = [40, 30, 15, 10, 5] 

def spin_slots() -> list[str]:
    # random.choices выбирает 3 символа с учетом весов
    return random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)
