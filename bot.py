"""
RecipeBot — Telegram bot that suggests recipes based on available ingredients,
tracks user preferences, allergens, and provides calorie information.
"""

import logging
import re
import time

last_request = {}

from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

from storage import UserStorage

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
import os
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    timeout=60,
    max_retries=0,  # отключаем авто-retry — сами управляем fallback
)

# ── Список моделей (перебираются при ошибке 429 / 404) ───────────────────────
# openrouter/free — специальный роутер, сам выбирает любую доступную
# бесплатную модель. Остальные — конкретные запасные варианты.
FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-14b:free",
    "mistralai/mistral-7b-instruct:free",
    "qwen/qwen3-8b:free",
    "openrouter/free", 
]

SETTING_ALLERGY = 1
SETTING_PREFERENCE = 2

DIET_LABELS = {
    "🥩 Обычное": "regular",
    "🥗 Вегетарианское": "vegetarian",
    "🌱 Веганское": "vegan",
}

storage = UserStorage("users.json")


# ── Helpers ────────────────────────────────────────────────────────────────────

def build_system_prompt(user_data: dict) -> str:
    """Construct a personalised system prompt for the AI chef."""
    allergens = ", ".join(user_data.get("allergens", [])) or "нет"
    diet = user_data.get("diet", "regular")
    history = user_data.get("liked_dishes", [])[-10:]

    diet_map = {"regular": "обычное", "vegetarian": "вегетарианское", "vegan": "веганское"}
    diet_label = diet_map.get(diet, "обычное")

    history_str = (
        "Пользователь раньше любил: " + ", ".join(history) + "."
        if history else "Нет истории предпочтений."
    )

    return f"""Ты — дружелюбный AI-шеф-повар в Telegram-боте. Отвечай ТОЛЬКО на русском языке.

Профиль пользователя:
- Тип питания: {diet_label}
- Аллергены (ЗАПРЕЩЕНО использовать): {allergens}
- {history_str}

Когда пользователь присылает список ингредиентов:
1. Предложи 2–3 блюда, которые можно приготовить из этих ингредиентов.
2. Для каждого блюда укажи:
   - Название блюда (жирным, если используешь Markdown)
   - Краткое описание (1–2 предложения)
   - Примерную калорийность на порцию (ккал)
   - Список необходимых ингредиентов из предложенных
   - Короткий рецепт (3–5 шагов)
3. Иногда (примерно раз в 3–4 запроса) в конце добавляй один совет по питанию или
   предлагай попробовать блюдо соответствующего типа диеты (веганское/вегетарианское/обычное).
4. НИКОГДА не используй запрещённые аллергены.
5. Если ингредиентов мало, предложи чем можно дополнить.

Отвечай структурированно и дружелюбно. Используй эмодзи умеренно."""


def strip_thinking(text: str) -> str:
    """Убираем внутренний монолог модели (Qwen3 и другие thinking-модели)."""
    # Убираем блоки <think>...</think>
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Убираем строки которые выглядят как внутренние размышления на русском
    # (повторяющиеся "Вариант 1:", "Но бананы...", "Ингредиенты:" без структуры)
    text = text.strip()
    return text

def is_garbage(text: str) -> bool:
    """Проверяем что ответ не мусор."""
    if len(text) < 50:
        return True
    # Арабские, китайские, японские символы в русском тексте = мусор
    import unicodedata
    foreign_count = sum(
        1 for c in text
        if unicodedata.name(c, "").startswith(("ARABIC", "CJK", "HEBREW"))
    )
    if foreign_count > 3:
        return True
    # Слишком много повторяющихся слов = зацикленная генерация
    words = text.split()
    if len(words) > 20:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.4:
            return True
    return False

async def ask_ai(user_id: int, user_message: str) -> str:
    """Send message to AI model and return response. Tries multiple free models on 429."""

    user_data = storage.get(user_id)
    history = user_data.get("conversation", [])
    system_prompt = build_system_prompt(user_data)

    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_message},
    ]

    assistant_text = None
    used_model = None

    for model in FREE_MODELS:
        try:
            logger.info(f"Trying model: {model}")
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1200,
                extra_body={
                    "reasoning": {"enabled": False},  # отключаем thinking-режим (Qwen3 и др.)
                },
            )
            raw = response.choices[0].message.content or ""
            cleaned = strip_thinking(raw)

            # Проверка качества ответа
            if is_garbage(cleaned):
                logger.warning(f"Model {model} returned garbage response, trying next...")
                continue

            assistant_text = cleaned
            used_model = model
            break

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "404" in err_str:
                logger.warning(f"Model {model} unavailable, trying next...")
                continue  # пробуем следующую модель
            else:
                logger.error(f"AI ERROR with model {model}: {e}")
                return "😔 Ошибка AI. Попробуй ещё раз."

    if assistant_text is None:
        return "😔 Все бесплатные модели сейчас перегружены. Попробуй через минуту!"

    logger.info(f"Got response from model: {used_model}")

    # сохраняем историю диалога
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": assistant_text})

    storage.update(user_id, {"conversation": history[-6:]})

    return assistant_text


# ── Command Handlers ───────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    storage.ensure(user.id, user.full_name)

    await update.message.reply_text(
        f"👨‍🍳 Привет, {user.first_name}! Я твой личный шеф-повар.\n\n"
        "Просто напиши мне список ингредиентов, которые у тебя есть, "
        "и я предложу вкусные блюда с калорийностью и рецептом!\n\n"
        "Полезные команды:\n"
        "/allergy — указать аллергены\n"
        "/diet — выбрать тип питания\n"
        "/profile — посмотреть твой профиль\n"
        "/reset — сбросить историю беседы\n"
        "/help — помощь"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🍽 *Как пользоваться ботом:*\n\n"
        "• Напиши список ингредиентов (например: *курица, рис, лук, чеснок*)\n"
        "• Получи рецепты с калорийностью\n\n"
        "*Команды:*\n"
        "/allergy — добавить/изменить аллергены\n"
        "/diet — выбрать тип питания (обычное / вегетарианское / веганское)\n"
        "/profile — посмотреть свой профиль\n"
        "/reset — сбросить историю разговора\n"
        "/start — начало работы",
        parse_mode="Markdown",
    )


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = storage.get(update.effective_user.id)
    allergens = ", ".join(user_data.get("allergens", [])) or "не указаны"
    diet_map = {"regular": "🥩 Обычное", "vegetarian": "🥗 Вегетарианское", "vegan": "🌱 Веганское"}
    diet = diet_map.get(user_data.get("diet", "regular"), "🥩 Обычное")
    liked = user_data.get("liked_dishes", [])
    liked_str = ", ".join(liked[-5:]) if liked else "пока нет"

    await update.message.reply_text(
        f"👤 *Твой профиль:*\n\n"
        f"🍽 Тип питания: {diet}\n"
        f"⚠️ Аллергены: {allergens}\n"
        f"❤️ Недавние предпочтения: {liked_str}",
        parse_mode="Markdown",
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage.update(update.effective_user.id, {"conversation": []})
    await update.message.reply_text("🔄 История беседы сброшена. Начнём заново!")


# ── Allergy ConversationHandler ────────────────────────────────────────────────

async def cmd_allergy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = storage.get(update.effective_user.id)
    current = ", ".join(user_data.get("allergens", [])) or "не указаны"
    await update.message.reply_text(
        f"⚠️ Текущие аллергены: *{current}*\n\n"
        "Напиши список аллергенов через запятую (например: *орехи, молоко, глютен*).\n"
        "Чтобы удалить все аллергены, отправь *нет*.\n"
        "Для отмены — /cancel",
        parse_mode="Markdown",
    )
    return SETTING_ALLERGY


async def receive_allergy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text == "нет":
        allergens = []
    else:
        allergens = [a.strip() for a in re.split(r"[,;]+", text) if a.strip()]

    storage.update(update.effective_user.id, {"allergens": allergens})
    result = ", ".join(allergens) if allergens else "нет"
    await update.message.reply_text(f"✅ Аллергены сохранены: *{result}*", parse_mode="Markdown")
    return ConversationHandler.END


# ── Diet ConversationHandler ───────────────────────────────────────────────────

async def cmd_diet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[KeyboardButton(label)] for label in DIET_LABELS]
    await update.message.reply_text(
        "🥗 Выбери тип питания:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return SETTING_PREFERENCE


async def receive_diet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chosen = update.message.text.strip()
    diet_value = DIET_LABELS.get(chosen)
    if not diet_value:
        await update.message.reply_text("Пожалуйста, выбери один из предложенных вариантов.")
        return SETTING_PREFERENCE

    storage.update(update.effective_user.id, {"diet": diet_value})
    await update.message.reply_text(
        f"✅ Тип питания сохранён: *{chosen}*",
        parse_mode="Markdown",
        reply_markup=__default_keyboard(),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END


def __default_keyboard():
    from telegram import ReplyKeyboardRemove
    return ReplyKeyboardRemove()


# ── Main Message Handler ───────────────────────────────────────────────────────

async def handle_ingredients(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    storage.ensure(user_id, update.effective_user.full_name)

    await update.message.reply_chat_action("typing")

    now = time.time()
    if user_id in last_request and now - last_request[user_id] < 5:
        await update.message.reply_text("⏳ Подожди пару секунд перед следующим запросом")
        return

    last_request[user_id] = now

    try:
        reply = await ask_ai(user_id, update.message.text)

        names = re.findall(r"\*\*(.+?)\*\*", reply)
        if names:
            user_data = storage.get(user_id)
            liked = user_data.get("liked_dishes", [])
            liked.extend(names[:2])
            storage.update(user_id, {"liked_dishes": liked[-20:]})

        await update.message.reply_text(reply)

    except Exception as exc:
        logger.error(f"handle_ingredients error: {exc}")
        await update.message.reply_text("😔 Что-то пошло не так. Попробуй ещё раз!")


# ── Application Bootstrap ──────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    allergy_conv = ConversationHandler(
        entry_points=[CommandHandler("allergy", cmd_allergy)],
        states={SETTING_ALLERGY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_allergy)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    diet_conv = ConversationHandler(
        entry_points=[CommandHandler("diet", cmd_diet)],
        states={SETTING_PREFERENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_diet)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(allergy_conv)
    app.add_handler(diet_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ingredients))

    logger.info("RecipeBot started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    main()