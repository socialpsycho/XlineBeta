"""Authenticated Telegram Mini App API with persistent virtual-points games.

All game state and outcomes are server-side. This module never reads or changes
the legacy cash balance, deposits, withdrawals, or payment tables.
"""
import hashlib
import hmac
import json
import math
import os
import random
import time
import uuid
import secrets
from datetime import datetime, timezone

from aiohttp import web

from .config import BOT_TOKEN, DATABASE_PATH
from .db import connection

_rng = random.SystemRandom()
HOUSE_EDGE = 0.97
MIN_BET = 0.10
MAX_BET = 10000.0
INITIAL_DEMO_POINTS = 1000
DIFFICULTY = {
    "easy": (4, 1, 9),
    "medium": (3, 1, 9),
    "hard": (2, 1, 9),
    "expert": (3, 2, 5),
    "master": (4, 3, 4),
}
SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
SLOT_WEIGHTS = [40, 30, 15, 10, 5]
SUITS = ["♠", "♥", "♦", "♣"]
VALUES = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def init_demo_schema():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS miniapp_demo_wallet (
            user_id INTEGER PRIMARY KEY,
            points REAL NOT NULL DEFAULT 1000.0 CHECK(points >= 0),
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS miniapp_demo_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            state_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_demo_active_session
            ON miniapp_demo_sessions(user_id, status);
        CREATE TABLE IF NOT EXISTS miniapp_demo_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            result TEXT NOT NULL,
            bet REAL NOT NULL,
            payout REAL NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_demo_history_user
            ON miniapp_demo_history(user_id, id DESC);
        CREATE TABLE IF NOT EXISTS miniapp_launch_tokens (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            used_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS miniapp_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        );
        """)

        # Upgrade an early demo schema without discarding a saved active round.
        session_columns = db.execute("PRAGMA table_info(miniapp_demo_sessions)").fetchall()
        user_id_is_primary = any(row["name"] == "user_id" and row["pk"] == 1 for row in session_columns)
        if user_id_is_primary:
            db.execute("DROP INDEX IF EXISTS idx_demo_active_session")
            db.execute("ALTER TABLE miniapp_demo_sessions RENAME TO miniapp_demo_sessions_legacy")
            db.execute("""
                CREATE TABLE miniapp_demo_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    game TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            db.execute("""
                INSERT INTO miniapp_demo_sessions
                    (session_id, user_id, game, state_json, status, created_at, updated_at)
                SELECT session_id, user_id, game, state_json, status, created_at, updated_at
                FROM miniapp_demo_sessions_legacy
            """)
            db.execute("DROP TABLE miniapp_demo_sessions_legacy")
            db.execute("CREATE INDEX idx_demo_active_session ON miniapp_demo_sessions(user_id, status)")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def verify_init_data(init_data):
    if not init_data or not BOT_TOKEN:
        return None
    from urllib.parse import parse_qsl
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
        received_hash = pairs.pop("hash", "")
        auth_date = int(pairs.get("auth_date", "0"))
        if not received_hash or abs(time.time() - auth_date) > 86400:
            return None
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received_hash):
            return None
        user = json.loads(pairs.get("user", "{}"))
        user_id = int(user["id"])
        if user_id <= 0:
            return None
        return user
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def calculate_hand(hand):
    total = sum(card[1] for card in hand)
    aces = sum(1 for card in hand if card[0].startswith("A"))
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def new_deck():
    deck = [
        [f"{value}{suit}", 11 if value == "A" else 10 if value in ("J", "Q", "K") else int(value)]
        for value in VALUES for suit in SUITS
    ] * 4
    _rng.shuffle(deck)
    return deck


def multiplier_mines(opened_count, mines):
    safe_left = 25 - mines - opened_count
    total_left = 25 - opened_count
    if safe_left <= 0 or total_left <= 0:
        return 0.0
    survival = 1.0
    for i in range(opened_count):
        survival *= (25 - mines - i) / (25 - i)
    return (1.0 / survival) * HOUSE_EDGE


def crash_point():
    r = _rng.random()
    if r < 0.03:
        return 1.00
    return round(0.97 / (1 - r), 2)


def public_state(game, state):
    result = {k: v for k, v in state.items() if k not in ("mines", "bombs", "deck", "crash_at")}
    if game == "blackjack" and result.get("dealer_hand"):
        result["dealer_visible"] = [result["dealer_hand"][0]]
        result.pop("dealer_hand", None)
    return result


def _wallet(db, user_id):
    db.execute(
        "INSERT OR IGNORE INTO miniapp_demo_wallet(user_id, points, updated_at) VALUES (?, ?, ?)",
        (user_id, INITIAL_DEMO_POINTS, now_iso()),
    )
    row = db.execute("SELECT points FROM miniapp_demo_wallet WHERE user_id=?", (user_id,)).fetchone()
    return round(float(row["points"]), 2)


def _active(db, user_id):
    row = db.execute(
        "SELECT session_id, game, state_json FROM miniapp_demo_sessions WHERE user_id=? AND status='active'",
        (user_id,),
    ).fetchone()
    if not row:
        return None
    return {"session_id": row["session_id"], "game": row["game"], "state": json.loads(row["state_json"])}


def _save_session(db, user_id, session):
    db.execute(
        "UPDATE miniapp_demo_sessions SET state_json=?, updated_at=? WHERE user_id=? AND session_id=? AND status='active'",
        (json.dumps(session["state"], ensure_ascii=False), now_iso(), user_id, session["session_id"]),
    )


def _settle(db, user_id, session, result, payout, details):
    bet = round(float(session["state"]["bet"]), 2)
    payout = max(0.0, round(float(payout), 2))
    db.execute(
        "UPDATE miniapp_demo_wallet SET points=points+?, updated_at=? WHERE user_id=?",
        (payout, now_iso(), user_id),
    )
    db.execute(
        "INSERT INTO miniapp_demo_history(user_id,game,result,bet,payout,details_json,created_at) VALUES(?,?,?,?,?,?,?)",
        (user_id, session["game"], result, bet, payout,
         json.dumps(details, ensure_ascii=False), now_iso()),
    )
    db.execute(
        "UPDATE miniapp_demo_sessions SET status='finished', state_json=?, updated_at=? WHERE user_id=? AND session_id=? AND status='active'",
        (json.dumps({"result": result, "payout": payout, "details": details}, ensure_ascii=False),
         now_iso(), user_id, session["session_id"]),
    )
    return _wallet(db, user_id)


def _start_game(db, user_id, payload):
    game = str(payload.get("game", "")).lower()
    bet = payload.get("bet")
    if game not in {"mines", "tower", "rocket", "slots", "blackjack"}:
        raise web.HTTPBadRequest(text="Неизвестная игра.")
    if isinstance(bet, bool) or not isinstance(bet, (int, float)) or not math.isfinite(float(bet)) or not MIN_BET <= float(bet) <= MAX_BET:
        raise web.HTTPBadRequest(text=f"Ставка должна быть числом от {MIN_BET} до {MAX_BET} очков.")
    bet = round(float(bet), 2)
    if _active(db, user_id):
        raise web.HTTPConflict(text="Сначала заверши текущую игру.")
    balance = _wallet(db, user_id)
    if balance < bet:
        raise web.HTTPBadRequest(text="Недостаточно виртуальных очков.")
    db.execute(
        "UPDATE miniapp_demo_wallet SET points=points-?, updated_at=? WHERE user_id=? AND points>=?",
        (bet, now_iso(), user_id, bet),
    )
    state = {"bet": bet, "started_at": time.time()}
    if game == "mines":
        count = payload.get("mines", 5)
        if isinstance(count, bool) or not isinstance(count, int) or not 5 <= count <= 24:
            raise web.HTTPBadRequest(text="Количество мин должно быть от 5 до 24.")
        state.update({"mines_count": count, "mines": sorted(_rng.sample(range(25), count)),
                      "opened": [], "multiplier": 1.0})
    elif game == "tower":
        difficulty = payload.get("difficulty", "easy")
        if difficulty not in DIFFICULTY:
            raise web.HTTPBadRequest(text="Неизвестная сложность Tower.")
        cells, bombs, floors = DIFFICULTY[difficulty]
        prob = (cells - bombs) / cells
        base = (1 / prob) * HOUSE_EDGE
        state.update({"difficulty": difficulty, "cells": cells, "bombs_count": bombs,
                      "levels": floors, "opened": [],
                      "bombs": {str(i): sorted(_rng.sample(range(cells), bombs)) for i in range(floors)},
                      "base": base, "multiplier": base})
    elif game == "rocket":
        state.update({"multiplier": 1.0, "crash_at": crash_point()})
    elif game == "slots":
        state.update({"status": "ready"})
    elif game == "blackjack":
        deck = new_deck()
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]
        state.update({"deck": deck, "player_hand": player, "dealer_hand": dealer})
    session_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO miniapp_demo_sessions(user_id,session_id,game,state_json,status,created_at,updated_at) VALUES(?,?,?,?, 'active', ?, ?)",
        (user_id, session_id, game, json.dumps(state, ensure_ascii=False), now_iso(), now_iso()),
    )
    session = {"session_id": session_id, "game": game, "state": state}
    if game == "slots":
        return _slot_spin(db, user_id, session)
    if game == "blackjack" and calculate_hand(state["player_hand"]) == 21:
        payout = round(bet * 2.5, 2)
        balance = _settle(db, user_id, session, "win", payout,
                          {"player_total": 21, "dealer_total": calculate_hand(state["dealer_hand"]),
                           "player_hand": state["player_hand"], "dealer_hand": state["dealer_hand"]})
        return {"finished": True, "result": "blackjack", "payout": payout, "balance": balance,
                "state": {"player_hand": state["player_hand"], "dealer_hand": state["dealer_hand"],
                          "player_total": 21, "dealer_total": calculate_hand(state["dealer_hand"])}}
    return {"finished": False, "session_id": session_id, "game": game,
            "balance": _wallet(db, user_id), "state": public_state(game, state)}


def _slot_spin(db, user_id, session):
    result = _rng.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)
    bet = session["state"]["bet"]
    if result[0] == result[1] == result[2]:
        multiplier = {"7️⃣": 50, "💎": 20, "🔔": 10, "🍋": 5, "🍒": 4}[result[0]]
        payout = round(bet * multiplier, 2)
        description = "Три одинаковых символа"
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        payout, description = bet, "Два одинаковых — возврат ставки"
    else:
        payout, description = 0, "Совпадений нет"
    balance = _settle(db, user_id, session, "win" if payout > bet else "push" if payout else "loss",
                      payout, {"symbols": result, "description": description})
    return {"finished": True, "game": "slots", "symbols": result, "description": description,
            "payout": payout, "balance": balance}


def _action(db, user_id, payload):
    session = _active(db, user_id)
    if not session:
        raise web.HTTPConflict(text="Активная игра не найдена.")
    if payload.get("session_id") != session["session_id"]:
        raise web.HTTPConflict(text="Сессия игры устарела.")
    game, state = session["game"], session["state"]
    action = payload.get("action")
    if game == "mines":
        if action == "open":
            idx = payload.get("cell")
            if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx < 25:
                raise web.HTTPBadRequest(text="Некорректная клетка.")
            if idx in state["opened"]:
                raise web.HTTPConflict(text="Клетка уже открыта.")
            if idx in state["mines"]:
                balance = _settle(db, user_id, session, "loss", 0,
                                  {"mines": state["mines"], "opened": state["opened"], "hit": idx})
                return {"finished": True, "result": "mine", "hit": idx, "mines": state["mines"],
                        "opened": state["opened"], "balance": balance, "payout": 0}
            state["opened"].append(idx)
            state["multiplier"] = multiplier_mines(len(state["opened"]), state["mines_count"])
            if len(state["opened"]) == 25 - state["mines_count"]:
                payout = round(state["bet"] * state["multiplier"], 2)
                balance = _settle(db, user_id, session, "win", payout,
                                  {"mines": state["mines"], "opened": state["opened"]})
                return {"finished": True, "result": "clear", "mines": state["mines"],
                        "opened": state["opened"], "payout": payout, "balance": balance}
            _save_session(db, user_id, session)
            return {"finished": False, "state": public_state(game, state), "balance": _wallet(db, user_id)}
        if action == "cashout":
            if not state["opened"]:
                raise web.HTTPBadRequest(text="Сначала открой безопасную клетку.")
            payout = round(state["bet"] * state["multiplier"], 2)
            balance = _settle(db, user_id, session, "cashout", payout,
                              {"mines": state["mines"], "opened": state["opened"]})
            return {"finished": True, "result": "cashout", "mines": state["mines"],
                    "opened": state["opened"], "payout": payout, "balance": balance}
    elif game == "tower":
        if action == "open":
            level, cell = payload.get("level"), payload.get("cell")
            if (isinstance(level, bool) or not isinstance(level, int) or level != len(state["opened"])
                    or isinstance(cell, bool) or not isinstance(cell, int) or not 0 <= cell < state["cells"]):
                raise web.HTTPBadRequest(text="Некорректный ход Tower.")
            bombs = state["bombs"][str(level)]
            if cell in bombs:
                balance = _settle(db, user_id, session, "loss", 0,
                                  {"bombs": state["bombs"], "opened": state["opened"], "hit": {"level": level, "cell": cell}})
                return {"finished": True, "result": "bomb", "bombs": state["bombs"],
                        "opened": state["opened"], "hit": {"level": level, "cell": cell}, "balance": balance}
            state["opened"].append(cell)
            state["multiplier"] *= state["base"]
            if len(state["opened"]) == state["levels"]:
                payout = round(state["bet"] * state["multiplier"], 2)
                balance = _settle(db, user_id, session, "win", payout,
                                  {"bombs": state["bombs"], "opened": state["opened"]})
                return {"finished": True, "result": "top", "bombs": state["bombs"],
                        "opened": state["opened"], "payout": payout, "balance": balance}
            _save_session(db, user_id, session)
            return {"finished": False, "state": public_state(game, state), "balance": _wallet(db, user_id)}
        if action == "cashout":
            if not state["opened"]:
                raise web.HTTPBadRequest(text="Пройди хотя бы один этаж.")
            payout = round(state["bet"] * state["multiplier"])
            balance = _settle(db, user_id, session, "cashout", payout,
                              {"bombs": state["bombs"], "opened": state["opened"]})
            return {"finished": True, "result": "cashout", "bombs": state["bombs"],
                    "opened": state["opened"], "payout": payout, "balance": balance}
    elif game == "rocket":
        if action == "status" or action == "cashout":
            elapsed_ticks = max(0, int(time.time() - state["started_at"]))
            current = round(1.0 + 0.12 * elapsed_ticks, 2)
            previous = round(1.0 + 0.12 * max(0, elapsed_ticks - 1), 2)
            if state["crash_at"] <= current:
                balance = _settle(db, user_id, session, "loss", 0, {"crash_at": state["crash_at"]})
                return {"finished": True, "result": "crash", "crash_at": state["crash_at"],
                        "balance": balance, "payout": 0}
            if action == "cashout":
                payout = round(state["bet"] * current, 2)
                balance = _settle(db, user_id, session, "cashout", payout, {"cashed_out_at": current})
                return {"finished": True, "result": "cashout", "multiplier": current,
                        "payout": payout, "balance": balance}
            state["multiplier"] = current
            _save_session(db, user_id, session)
            return {"finished": False, "multiplier": current, "potential_payout": round(state["bet"] * current)}
    elif game == "blackjack":
        if action == "hit":
            state["player_hand"].append(state["deck"].pop())
            total = calculate_hand(state["player_hand"])
            if total > 21:
                balance = _settle(db, user_id, session, "loss", 0,
                                  {"player_hand": state["player_hand"], "dealer_hand": state["dealer_hand"],
                                   "player_total": total, "dealer_total": calculate_hand(state["dealer_hand"])})
                return {"finished": True, "result": "bust", "state": {"player_hand": state["player_hand"], "dealer_hand": state["dealer_hand"], "player_total": total, "dealer_total": calculate_hand(state["dealer_hand"])}, "balance": balance, "payout": 0}
            _save_session(db, user_id, session)
            return {"finished": False, "state": public_state(game, state), "player_total": total}
        if action == "stand":
            while calculate_hand(state["dealer_hand"]) < 17:
                state["dealer_hand"].append(state["deck"].pop())
            player_total, dealer_total = calculate_hand(state["player_hand"]), calculate_hand(state["dealer_hand"])
            if dealer_total > 21 or player_total > dealer_total:
                payout, result = round(state["bet"] * 2, 2), "win"
            elif player_total < dealer_total:
                payout, result = 0, "loss"
            else:
                payout, result = state["bet"], "push"
            balance = _settle(db, user_id, session, result, payout,
                              {"player_hand": state["player_hand"], "dealer_hand": state["dealer_hand"],
                               "player_total": player_total, "dealer_total": dealer_total})
            return {"finished": True, "result": result, "state": {
                "player_hand": state["player_hand"], "dealer_hand": state["dealer_hand"],
                "player_total": player_total, "dealer_total": dealer_total},
                "payout": payout, "balance": balance}
    raise web.HTTPBadRequest(text="Действие недоступно для этой игры.")


@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = os.getenv("MINIAPP_CORS_ORIGIN", "*")
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Telegram-Init-Data, X-XLINE-Session"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Vary"] = "Origin"
    return response


@web.middleware
async def error_middleware(request, handler):
    try:
        return await handler(request)
    except web.HTTPException as exc:
        return web.json_response({"error": exc.text or exc.reason}, status=exc.status)
    except Exception:
        request.app.logger.exception("Mini App API error")
        return web.json_response({"error": "Внутренняя ошибка сервера."}, status=500)


def create_app():
    app = web.Application(middlewares=[cors_middleware, error_middleware], client_max_size=16 * 1024)
    init_demo_schema()

    def auth(request):
        # Prefer Telegram-signed initData. The short-lived session is a secure fallback
        # minted only after an authenticated Telegram bot callback click.
        user = verify_init_data(request.headers.get("X-Telegram-Init-Data", ""))
        if user:
            return int(user["id"]), user
        session_token = request.headers.get("X-XLINE-Session", "")
        if session_token:
            token_hash = hashlib.sha256(session_token.encode()).hexdigest()
            with connection() as db:
                row = db.execute(
                    "SELECT user_id FROM miniapp_sessions WHERE token_hash=? AND expires_at>?",
                    (token_hash, int(time.time())),
                ).fetchone()
            if row:
                return int(row["user_id"]), {"id": int(row["user_id"])}
        raise web.HTTPUnauthorized(text="Не удалось подтвердить вход. Запусти XLINE через кнопку в боте.")

    async def health(request):
        return web.json_response({"status": "ok", "service": "xline-miniapp-api"})

    async def exchange_launch_token(request):
        payload = await request.json()
        raw_token = str(payload.get("launch_token", ""))
        if len(raw_token) < 32 or len(raw_token) > 256:
            raise web.HTTPUnauthorized(text="Ссылка входа недействительна или устарела.")
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        now = int(time.time())
        session_token = secrets.token_urlsafe(48)
        session_hash = hashlib.sha256(session_token.encode()).hexdigest()
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT user_id FROM miniapp_launch_tokens WHERE token_hash=? AND expires_at>? AND used_at IS NULL",
                (token_hash, now),
            ).fetchone()
            if not row:
                raise web.HTTPUnauthorized(text="Ссылка входа уже использована или истекла. Нажми /start в боте.")
            db.execute("UPDATE miniapp_launch_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL", (now, token_hash))
            db.execute(
                "INSERT INTO miniapp_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                (session_hash, int(row["user_id"]), now + 43200),
            )
        return web.json_response({"session_token": session_token, "expires_in": 43200})

    async def me(request):
        user_id, user = auth(request)
        with connection() as db:
            balance = _wallet(db, user_id)
            session = _active(db, user_id)
        data = {"id": user_id, "name": user.get("first_name", "Игрок"),
                "username": user.get("username", ""), "points": balance,
                "currency": "виртуальные очки", "active_game": None}
        if session:
            data["active_game"] = {"session_id": session["session_id"], "game": session["game"],
                                   "state": public_state(session["game"], session["state"])}
        return web.json_response(data)

    async def history(request):
        user_id, _ = auth(request)
        with connection() as db:
            rows = db.execute(
                "SELECT game,result,bet,payout,created_at FROM miniapp_demo_history WHERE user_id=? ORDER BY id DESC LIMIT 30",
                (user_id,),
            ).fetchall()
        return web.json_response({"items": [dict(row) for row in rows]})

    async def start(request):
        user_id, _ = auth(request)
        payload = await request.json()
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            result = _start_game(db, user_id, payload)
        return web.json_response(result)

    async def action(request):
        user_id, _ = auth(request)
        payload = await request.json()
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            result = _action(db, user_id, payload)
        return web.json_response(result)

    async def cancel(request):
        user_id, _ = auth(request)
        payload = await request.json()
        with connection() as db:
            db.execute("BEGIN IMMEDIATE")
            session = _active(db, user_id)
            if not session or payload.get("session_id") != session["session_id"]:
                raise web.HTTPConflict(text="Активная игра не найдена.")
            balance = _settle(db, user_id, session, "cancelled", 0, {"cancelled": True})
        return web.json_response({"finished": True, "balance": balance, "payout": 0})

    # Friendly root endpoint: opening the service URL in a browser should not return 405.
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_post("/api/auth/exchange", exchange_launch_token)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/history", history)
    app.router.add_post("/api/game/start", start)
    app.router.add_post("/api/game/action", action)
    app.router.add_post("/api/game/cancel", cancel)
    async def options(request):
        return web.Response(status=204)

    app.router.add_route("OPTIONS", "/{tail:.*}", options)
    return app
