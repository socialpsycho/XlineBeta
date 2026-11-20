import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .config import DATABASE_PATH

@contextmanager
def connection():
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL NOT NULL DEFAULT 0.10 CHECK(balance >= 0),
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            wagered REAL NOT NULL DEFAULT 0.0,
            last_bet REAL NOT NULL DEFAULT 0.10,
            last_tower_diff TEXT NOT NULL DEFAULT 'easy',
            status TEXT NOT NULL DEFAULT 'active',
            ban_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            is_withdraw_blocked INTEGER NOT NULL DEFAULT 0,
            username TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            result TEXT NOT NULL,
            bet REAL NOT NULL,
            payout REAL NOT NULL DEFAULT 0.0,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_history_user ON game_history(user_id, id DESC);
        
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            amount REAL NOT NULL,
            uses_left INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            method TEXT NOT NULL DEFAULT 'stars',
            destination TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS star_purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            product_title TEXT NOT NULL,
            stars INTEGER NOT NULL,
            telegram_charge_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_star_purchases_user
            ON star_purchases(user_id, id DESC);
        """)
        
        for col, definition in [
            ("last_tower_diff", "TEXT NOT NULL DEFAULT 'easy'"),
            ("status", "TEXT NOT NULL DEFAULT 'active'"),
            ("ban_reason", "TEXT NOT NULL DEFAULT ''"),
            ("created_at", "TEXT NOT NULL DEFAULT ''"),
            ("is_withdraw_blocked", "INTEGER NOT NULL DEFAULT 0"),
            ("username", "TEXT NOT NULL DEFAULT ''")
        ]:
            try:
                db.execute(f"SELECT {col} FROM users LIMIT 1")
            except sqlite3.OperationalError:
                db.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")

        for col, definition in [
            ("method", "TEXT NOT NULL DEFAULT 'stars'"),
            ("destination", "TEXT NOT NULL DEFAULT ''")
        ]:
            try:
                db.execute(f"SELECT {col} FROM withdrawals LIMIT 1")
            except sqlite3.OperationalError:
                db.execute(f"ALTER TABLE withdrawals ADD COLUMN {col} {definition}")

def register_user(user_id: int, username: str = ""):
    with connection() as db:
        # Явно указываем 0.10 баланса при создании
        db.execute("INSERT OR IGNORE INTO users(user_id, balance) VALUES (?, 0.10)", (user_id,))
        db.execute("UPDATE users SET created_at = ? WHERE user_id = ? AND (created_at IS NULL OR created_at = '')", 
                   (datetime.now(timezone.utc).isoformat(), user_id))
        if username is not None:
            db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username or "", user_id))

def get_user(user_id: int):
    with connection() as db:
        db.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
        row = db.execute("SELECT balance,wins,losses,wagered,last_bet,last_tower_diff,status FROM users WHERE user_id=?", (user_id,)).fetchone()
        return tuple(row)

def get_ban_reason(user_id: int) -> str:
    with connection() as db:
        row = db.execute("SELECT ban_reason FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row[0] if row else ""

def set_user_status(user_id: int, status: str, reason: str = ""):
    with connection() as db:
        db.execute("UPDATE users SET status=?, ban_reason=? WHERE user_id=?", (status, reason, user_id))

def save_tower_diff(user_id: int, diff: str):
    with connection() as db:
        db.execute("UPDATE users SET last_tower_diff=? WHERE user_id=?", (diff, user_id))

def place_bet(user_id: int, bet: float):
    if bet < 0.10: raise ValueError("Минимальная ставка — 0.10 $.")
    with connection() as db:
        db.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
        cur = db.execute("UPDATE users SET balance=ROUND(balance-?, 2), wagered=ROUND(wagered+?, 2), last_bet=? WHERE user_id=? AND balance>=?", (bet, bet, bet, user_id, bet))
        if cur.rowcount != 1: raise ValueError("Недостаточно средств.")

def settle_game(user_id: int, game: str, result: str, bet: float, payout: float, details: dict):
    with connection() as db:
        db.execute("UPDATE users SET balance=ROUND(balance+?, 2), wins=wins+?, losses=losses+? WHERE user_id=?",
                   (payout, int(payout > 0), int(payout == 0), user_id))
        db.execute("INSERT INTO game_history(user_id,game,result,bet,payout,details_json,created_at) VALUES(?,?,?,?,?,?,?)",
                   (user_id, game, result, bet, payout, json.dumps(details, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))

def credit_win(user_id: int, game: str, bet: float, payout: float, details: dict):
    settle_game(user_id, game, "win", bet, payout, details)

def record_loss(user_id: int, game: str, bet: float, details: dict):
    settle_game(user_id, game, "loss", bet, 0.0, details)

def record_cashout(user_id: int, game: str, bet: float, payout: float, details: dict):
    settle_game(user_id, game, "cashout", bet, payout, details)

def add_balance(user_id: int, amount: float, description: str = "deposit"):
    with connection() as db:
        db.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
        db.execute("UPDATE users SET balance=ROUND(balance+?, 2) WHERE user_id=?", (amount, user_id))
        db.execute("INSERT INTO game_history(user_id,game,result,bet,payout,details_json,created_at) VALUES(?,?,?,?,?,?,?)",
                   (user_id, "wallet", description, 0.0, amount, json.dumps({"type": description}), datetime.now(timezone.utc).isoformat()))

def deduct_balance(user_id: int, amount: float, description: str = "withdraw") -> bool:
    with connection() as db:
        db.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))
        cur = db.execute("UPDATE users SET balance=ROUND(balance-?, 2) WHERE user_id=? AND balance>=?", (amount, user_id, amount))
        if cur.rowcount == 1:
            db.execute("INSERT INTO game_history(user_id,game,result,bet,payout,details_json,created_at) VALUES(?,?,?,?,?,?,?)",
                       (user_id, "wallet", description, 0.0, -amount, json.dumps({"type": description}), datetime.now(timezone.utc).isoformat()))
            return True
        return False

def get_max_win(user_id: int) -> float:
    with connection() as db:
        row = db.execute("SELECT MAX(payout) FROM game_history WHERE user_id=? AND payout > 0", (user_id,)).fetchone()
        return row[0] if row and row[0] else 0.0

def get_history(user_id: int, limit: int = 5) -> list:
    with connection() as db:
        rows = db.execute(
            "SELECT game, result, bet, payout FROM game_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [tuple(r) for r in rows]

def get_all_users() -> list:
    with connection() as db:
        rows = db.execute("SELECT user_id, balance, status, username FROM users ORDER BY user_id DESC").fetchall()
        return [tuple(r) for r in rows]

def create_promo(code: str, amount: float, uses: int):
    with connection() as db:
        db.execute(
            "INSERT INTO promocodes (code, amount, uses_left, created_at) VALUES (?, ?, ?, ?)",
            (code.upper(), amount, uses, datetime.now(timezone.utc).isoformat())
        )

def use_promo(user_id: int, code: str) -> float | None:
    code = code.upper().strip()
    with connection() as db:
        row = db.execute("SELECT amount, uses_left FROM promocodes WHERE code = ?", (code,)).fetchone()
        if not row or row["uses_left"] <= 0:
            return None
            
        amount = row["amount"]
        db.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
        db.execute("UPDATE users SET balance = ROUND(balance + ?, 2) WHERE user_id = ?", (amount, user_id))
        db.execute("INSERT INTO game_history(user_id, game, result, bet, payout, details_json, created_at) VALUES(?,?,?,?,?,?,?)",
                   (user_id, "wallet", "promo", 0.0, amount, json.dumps({"code": code}), datetime.now(timezone.utc).isoformat()))
        return amount

def create_withdrawal(user_id: int, amount: float, method: str = "stars", destination: str = "") -> int:
    with connection() as db:
        db.execute("UPDATE users SET balance = ROUND(balance - ?, 2) WHERE user_id = ?", (amount, user_id))
        cur = db.execute("INSERT INTO withdrawals (user_id, amount, status, method, destination, created_at) VALUES (?, ?, 'pending', ?, ?, ?)", 
                   (user_id, amount, method, destination, datetime.now(timezone.utc).isoformat()))
        return cur.lastrowid

def approve_withdrawal(withdrawal_id: int):
    with connection() as db:
        db.execute("UPDATE withdrawals SET status = 'paid' WHERE id = ?", (withdrawal_id,))

def reject_withdrawal(withdrawal_id: int) -> int | None:
    with connection() as db:
        row = db.execute("SELECT user_id, amount, status FROM withdrawals WHERE id = ?", (withdrawal_id,)).fetchone()
        if not row or row["status"] != "pending":
            return None
        db.execute("UPDATE users SET balance = ROUND(balance + ?, 2) WHERE user_id = ?", (row["amount"], row["user_id"]))
        db.execute("UPDATE withdrawals SET status = 'rejected' WHERE id = ?", (withdrawal_id,))
        return row["user_id"]

def create_ticket(user_id: int, message_id: int):
    with connection() as db:
        db.execute("INSERT INTO tickets (user_id, message_id, created_at) VALUES (?, ?, ?)",
                   (user_id, message_id, datetime.now(timezone.utc).isoformat()))

def get_ticket_user(message_id: int) -> int | None:
    with connection() as db:
        row = db.execute("SELECT user_id FROM tickets WHERE message_id = ?", (message_id,)).fetchone()
        return row[0] if row else None

def close_ticket_db(message_id: int):
    with connection() as db:
        db.execute("UPDATE tickets SET status = 'closed' WHERE message_id = ?", (message_id,))

def get_ticket_status(message_id: int) -> str | None:
    with connection() as db:
        row = db.execute("SELECT status FROM tickets WHERE message_id = ?", (message_id,)).fetchone()
        return row[0] if row else None

def get_active_ticket_by_user(user_id: int) -> int | None:
    with connection() as db:
        row = db.execute("SELECT message_id FROM tickets WHERE user_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
        return row[0] if row else None

# --- ТЕХ. РАБОТЫ ---
def set_maintenance(status: bool):
    with connection() as db:
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('maintenance', ?)", ("1" if status else "0",))

def is_maintenance() -> bool:
    with connection() as db:
        row = db.execute("SELECT value FROM settings WHERE key = 'maintenance'").fetchone()
        return row[0] == "1" if row else False

# --- ИСТОРИЯ КОШЕЛЬКА ---
def get_deposit_history(user_id: int, limit: int = 10) -> list:
    with connection() as db:
        rows = db.execute(
            "SELECT payout, result, created_at FROM game_history "
            "WHERE user_id=? AND game='wallet' AND payout > 0 "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [tuple(r) for r in rows]

def get_withdraw_history(user_id: int, limit: int = 10) -> list:
    with connection() as db:
        rows = db.execute(
            "SELECT amount, method, status, destination, created_at FROM withdrawals "
            "WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [tuple(r) for r in rows]

def get_promo_history(user_id: int, limit: int = 10) -> list:
    with connection() as db:
        rows = db.execute(
            "SELECT payout, details_json, created_at FROM game_history "
            "WHERE user_id=? AND game='wallet' AND result='promo' "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [tuple(r) for r in rows]

# --- ОЧИСТКА БД ---
def clear_history_and_promos():
    with connection() as db:
        db.execute("DELETE FROM withdrawals")
        db.execute("DELETE FROM sqlite_sequence WHERE name='withdrawals'")
        db.execute("DELETE FROM game_history WHERE game='wallet'")
        db.execute("DELETE FROM promocodes")

# --- АНТИФРОД ---
def set_withdraw_block(user_id: int, blocked: bool):
    with connection() as db:
        db.execute("UPDATE users SET is_withdraw_blocked = ? WHERE user_id = ?", (int(blocked), user_id))

def is_withdraw_blocked(user_id: int) -> bool:
    with connection() as db:
        row = db.execute("SELECT is_withdraw_blocked FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row[0]) if row else False

def has_real_deposit(user_id: int) -> bool:
    with connection() as db:
        row = db.execute(
            "SELECT COUNT(*) FROM game_history WHERE user_id=? AND game='wallet' AND (result LIKE 'Пополнение%' OR result='Пополнение криптой' OR result='Админ-пополнение')",
            (user_id,)
        ).fetchone()
        return row[0] > 0 if row else False

# --- УДАЛЕНИЕ ЮЗЕРА ---
def delete_user(user_id: int):
    with connection() as db:
        db.execute("DELETE FROM game_history WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM withdrawals WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM tickets WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

# --- ГЛОБАЛЬНАЯ ИСТОРИЯ ---
def get_all_deposits(limit: int = 10) -> list:
    with connection() as db:
        rows = db.execute(
            "SELECT user_id, payout, result, created_at FROM game_history "
            "WHERE game='wallet' AND payout > 0 AND (result LIKE 'Пополнение%' OR result='promo') "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [tuple(r) for r in rows]

def get_all_withdrawals(limit: int = 10) -> list:
    with connection() as db:
        rows = db.execute(
            "SELECT id, user_id, amount, method, status, created_at FROM withdrawals "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [tuple(r) for r in rows]


# --- TELEGRAM STARS: DIGITAL GOODS ONLY ---
def record_star_purchase(user_id: int, product_id: str, product_title: str,
                         stars: int, telegram_charge_id: str) -> bool:
    """Store a verified digital-goods purchase once; never credits a cash/XP balance."""
    with connection() as db:
        try:
            db.execute(
                "INSERT INTO star_purchases "
                "(user_id, product_id, product_title, stars, telegram_charge_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, product_id, product_title, stars, telegram_charge_id,
                 datetime.now(timezone.utc).isoformat())
            )
            return True
        except sqlite3.IntegrityError:
            return False


def get_star_purchases(user_id: int, limit: int = 10) -> list:
    with connection() as db:
        rows = db.execute(
            "SELECT product_title, stars, created_at FROM star_purchases "
            "WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [tuple(row) for row in rows]
