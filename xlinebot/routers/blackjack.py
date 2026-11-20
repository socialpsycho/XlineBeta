import random
import asyncio
from aiogram import Router, types, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..db import get_user, place_bet, settle_game
from ..keyboards import play_menu, bet_menu
from ..states import GameStates

router = Router()

class BlackjackStates(StatesGroup):
    PLAYER_TURN = State()

CARD_EMOJIS = {
    '♠': '♠️', '♥': '♥️', '♦': '♦️', '♣': '♣️',
    'J': '🃏', 'Q': '👑', 'K': '🤴', 'A': '🅰️'
}

def get_card_emoji(card: tuple) -> str:
    value, suit = card[0][:-1], card[0][-1]
    emoji_value = CARD_EMOJIS.get(value, value)
    return f"{emoji_value}{CARD_EMOJIS[suit]}"

def calculate_hand(hand: list) -> int:
    total = sum(card[1] for card in hand)
    aces = sum(1 for card in hand if card[0].startswith('A'))
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def create_deck():
    deck = [
        (f"{value}{suit}", 11 if value == 'A' else 10 if value in ('J', 'Q', 'K') else int(value))
        for value in ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        for suit in ['♠', '♥', '♦', '♣']
    ] * 4
    random.shuffle(deck)
    return deck

def render_hand(hand: list, hide_second: bool = False) -> str:
    parts = []
    if len(hand) >= 1:
        parts.append(get_card_emoji(hand[0]))
    if len(hand) >= 2:
        parts.append('🂠' if hide_second else get_card_emoji(hand[1]))
    for card in hand[2:]:
        parts.append(get_card_emoji(card))
    return ' '.join(parts)

def game_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Взять карту", callback_data="bj_hit")
    kb.button(text="⛔ Остановиться", callback_data="bj_stand")
    kb.adjust(1, 1)
    return kb.as_markup()

# --- СТАРТ ИГРЫ ---
@router.callback_query(F.data == "game_blackjack")
async def start_blackjack(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    uid = call.from_user.id
    balance, _, _, _, last_bet, _, _ = get_user(uid)
    
    await state.set_state(GameStates.waiting_bj_bet)
    
    await call.message.edit_text(
        f"🃏 <b>Blackjack</b>\n\n💰 Твой баланс: <b>{balance:.2f} $</b>\nВыбери ставку или введи свою:", 
        parse_mode="HTML", 
        reply_markup=bet_menu("bj", last_bet, "play_menu")
    )
    await call.answer()

# --- ОБРАБОТКА КНОПОК СТАВКИ ---
@router.callback_query(F.data.startswith("bj_bet_"))
async def process_bet_btn(call: types.CallbackQuery, state: FSMContext):
    # Парсим дробное значение из callback_data
    bet = float(call.data.rsplit("_", 1)[1])
    await start_game(call.message, call.from_user.id, bet, state, edit=True)
    await call.answer()

# --- ОБРАБОТКА РУЧНОГО ВВОДА СТАВКИ ---
@router.message(GameStates.waiting_bj_bet)
async def process_custom_bet(message: types.Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", "."))
        if bet < 0.10:
            raise ValueError
    except (ValueError, AttributeError):
        return await message.answer("Введи число (например, 0.50 или 1.00). Минимум 0.10 $.")
        
    await start_game(message, message.from_user.id, bet, state, edit=False)

async def start_game(message: Message, uid: int, bet: float, state: FSMContext, edit: bool = False):
    try:
        place_bet(uid, bet) 
    except ValueError:
        return await message.answer("❌ Недостаточно средств!")

    deck = create_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]
    
    await state.update_data(bet=bet, player_hand=player_hand, dealer_hand=dealer_hand, deck=deck)

    player_total = calculate_hand(player_hand)
    
    if player_total == 21:
        await end_game(message, state, instant_blackjack=True, edit=edit)
        return

    text = (
        f"🃏 Твои карты:\n{render_hand(player_hand)}\n"
        f"➖ Сумма: {player_total}\n\n"
        f"💼 Карта дилера:\n{render_hand(dealer_hand, hide_second=True)}"
    )
    
    if edit:
        await message.edit_text(text, reply_markup=game_kb())
    else:
        await message.answer(text, reply_markup=game_kb())
        
    await state.set_state(BlackjackStates.PLAYER_TURN)

# --- ХОД ИГРОКА ---
@router.callback_query(BlackjackStates.PLAYER_TURN, F.data.in_(["bj_hit", "bj_stand"]))
async def player_action(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    player_hand = data["player_hand"]
    deck = data["deck"]

    if call.data == "bj_hit":
        player_hand.append(deck.pop())
        await state.update_data(player_hand=player_hand, deck=deck)
        player_total = calculate_hand(player_hand)
        
        if player_total > 21:
            await end_game(call.message, state, busted=True)
            await call.answer()
            return

        await call.message.edit_text(
            f"🃏 Твои карты:\n{render_hand(player_hand)}\n"
            f"➖ Сумма: {player_total}\n\n"
            f"💼 Карта дилера:\n{render_hand(data['dealer_hand'], hide_second=True)}",
            reply_markup=game_kb()
        )
        await call.answer()
    else:
        dealer_hand = data["dealer_hand"]
        dealer_total = calculate_hand(dealer_hand)
        while dealer_total < 17:
            dealer_hand.append(deck.pop())
            dealer_total = calculate_hand(dealer_hand)
        await state.update_data(dealer_hand=dealer_hand)
        await end_game(call.message, state)
        await call.answer()

# --- ЗАВЕРШЕНИЕ ИГРЫ ---
async def end_game(message: Message, state: FSMContext, busted: bool = False, instant_blackjack: bool = False, edit: bool = False):
    data = await state.get_data()
    player_hand = data["player_hand"]
    dealer_hand = data["dealer_hand"]
    bet = data["bet"]

    player_total = calculate_hand(player_hand)
    dealer_total = calculate_hand(dealer_hand)

    if instant_blackjack:
        result = "🎉 <b>BLACKJACK!</b> x2.5 выплата!"
        payout = round(bet * 2.5, 2)
        game_result = "win"
    elif busted:
        result = "💥 Перебор! Вы проиграли"
        payout = 0.0
        game_result = "loss"
    elif dealer_total > 21:
        result = "🎉 Дилер перебрал! Вы победили"
        payout = round(bet * 2, 2)
        game_result = "win"
    elif player_total > dealer_total:
        result = "🎉 Вы победили!"
        payout = round(bet * 2, 2)
        game_result = "win"
    elif player_total < dealer_total:
        result = "💼 Дилер побеждает"
        payout = 0.0
        game_result = "loss"
    else:
        result = "🤝 Ничья! Возврат ставки"
        payout = bet
        game_result = "cashout"

    uid = message.chat.id 
    details = {"player_total": player_total, "dealer_total": dealer_total}
    settle_game(uid, "blackjack", game_result, bet, payout, details)

    # Анимация
    for i in range(len(dealer_hand)):
        revealed = dealer_hand[:i+1]
        try:
            await message.edit_text(
                f"💼 Карты дилера:\n{render_hand(revealed)}\n"
                f"➖ Сумма: {calculate_hand(revealed) if i > 0 else '?'}\n\n"
                f"🃏 Твои карты:\n{render_hand(player_hand)}\n"
                f"➖ Сумма: {player_total}"
            )
            await asyncio.sleep(0.8)
        except Exception:
            pass

    balance = get_user(uid)[0]
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Играть снова", callback_data="game_blackjack")
    kb.button(text="🔙 В меню", callback_data="play_menu")
    kb.adjust(1, 1)

    final_text = (
        f"{result}\n\n"
        f"💼 Карты дилера:\n{render_hand(dealer_hand)}\n"
        f"➖ Сумма: {dealer_total}\n\n"
        f"🃏 Твои карты:\n{render_hand(player_hand)}\n"
        f"➖ Сумма: {player_total}\n\n"
        f"💵 Изменение: {(payout - bet):+.2f} $\n"
        f"💰 Баланс: {balance:.2f} $"
    )

    try:
        await message.edit_text(final_text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        await message.answer(final_text, reply_markup=kb.as_markup(), parse_mode="HTML")
        
    await state.clear()
