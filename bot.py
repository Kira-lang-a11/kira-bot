#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Kira Studio Bot — канал + личка + мост "админ ↔ пользователь"
# python-telegram-bot v21+
# Команды: /start /prices /order /post /myid  (+ /channel_id в канале)

import os
import logging
from typing import List, Dict, Optional

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------- Load .env ----------
load_dotenv()  # подтянет BOT_TOKEN, ADMIN_IDS, CHANNEL_ID из .env

# ---------- Config ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))  # e.g. -1001234567890
ADMIN_IDS: List[int] = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().lstrip("-").isdigit()
]

# Conversation state(s)
ORDER_DETAILS = 1

# Память: какой цели сейчас отвечает админ: {admin_id: target_chat_id}
PENDING_REPLY: Dict[int, int] = {}

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("kira-bot")


# ---------- Helpers ----------
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def send_to_admins(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
):
    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS is empty — no one to notify")
        return
    for admin in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin, text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
            )
        except Exception as e:
            logger.exception(f"Failed to notify admin {admin}: {e}")


def build_reply_keyboard(target_chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 Ответить", callback_data=f"reply:{target_chat_id}")]]
    )


def safe_username(u) -> str:
    return f"@{u.username}" if getattr(u, "username", None) else "(без username)"


# ---------- UI: Text & Keyboards ----------
def build_prices_text() -> str:
    return (
        "<b>Актуальные услуги и цены</b>\n\n"
        "<b>Фото на документы</b>\n"
        "• 4 фото 3×4 (цифровой файл) — 500₽\n\n"
        "<b>Визуалы для Instagram</b>\n"
        "• 5 визуалов — 2 500₽\n"
        "• 10 визуалов — 4 500₽ 🔥 Хит\n\n"
        "<b>Нейрофотосессия</b>\n"
        "• Lite (10 образов) — 3 900₽\n"
        "• Standard (20 образов) — 6 900₽ 🔥 Хит\n"
        "• Pro (40 образов) — 11 900₽\n\n"
        "<b>Детские фото в сказочном стиле</b>\n"
        "• Lite (5 образов из 1 фото) — 2 900₽\n"
        "• Standard (12 образов из 2 фото) — 5 900₽ 🔥 Хит\n"
        "• Pro (25 образов из 3–4 фото) — 9 900₽\n\n"
        "<b>Фото-обнимашки с близкими</b> — от 1 500₽\n"
        "<b>Логотип</b> — от 3 000₽\n"
        "<b>Бот для TG/WhatsApp</b> — от 12 000₽\n"
        "<b>Афиша / Постер</b> — от 1 500₽\n"
        "<b>Видео с нейросетью</b> — от 4 000₽\n"
        "<b>Обложка для YouTube</b> — 1 500₽\n"
        "<b>Карточки для Wildberries</b> — от 3 000₽\n"
        "<b>Арт-портрет</b> — 2 000₽\n"
        "\n"
        "<b>FAQ:</b>\n"
        "• Сроки: 1–3 дня (по объёму)\n"
        "• Правки: 1–2 лёгкие правки включены\n"
        "• Оплата: 50% предоплата, остальное после\n"
    )


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ Визуалы для Instagram", callback_data="menu_instagram")],
        [InlineKeyboardButton("🎭 Нейрофотосессия", callback_data="menu_neuro")],
        [InlineKeyboardButton("🧚 Детские: сказочный стиль", callback_data="menu_fairy")],
        [InlineKeyboardButton("💌 Заказать", callback_data="order"),
         InlineKeyboardButton("❓ Вопрос", url="https://t.me/miller_mua")],
        [InlineKeyboardButton("📢 Перейти в канал", url="https://t.me/katerinamillermua")],
    ])


def instagram_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("5 визуалов — 2 500₽", callback_data="pkg_instagram_5")],
        [InlineKeyboardButton("10 визуалов — 4 500₽ 🔥", callback_data="pkg_instagram_10")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")],
    ])


def neuro_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Lite — 3 900₽", callback_data="pkg_neuro_lite")],
        [InlineKeyboardButton("Standard — 6 900₽ 🔥", callback_data="pkg_neuro_std")],
        [InlineKeyboardButton("Pro — 11 900₽", callback_data="pkg_neuro_pro")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")],
    ])


def fairy_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Lite — 2 900₽ (5 образов)", callback_data="pkg_fairy_lite")],
        [InlineKeyboardButton("Standard — 5 900₽ (12 образов) 🔥", callback_data="pkg_fairy_std")],
        [InlineKeyboardButton("Pro — 9 900₽ (25 образов)", callback_data="pkg_fairy_pro")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")],
    ])


# ---------- Commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    kb = [[InlineKeyboardButton("Оформить заказ", callback_data="order")]]
    await update.message.reply_text(
        f"Привет, {user.first_name or 'друг'}! Я Кира-бот. Помогу оформить нейро-фотосессию, "
        "арт-портреты и контент для соцсетей.\n\n"
        "Команды:\n"
        "• /order — оформить заказ\n"
        "• /prices — тарифы\n"
        "• просто напиши, что нужно — отвечу\n",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        build_prices_text() + "\nНапиши /order и расскажи, что нужно — помогу выбрать 🙌",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb()
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.message.reply_text(f"Your chat id: <code>{chat.id}</code>", parse_mode=ParseMode.HTML)


async def channel_id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Работает, если бот админ канала и в канале отправить /channel_id
    chat = update.effective_chat
    try:
        await update.channel_post.reply_text(f"Channel id: <code>{chat.id}</code>", parse_mode=ParseMode.HTML)
    except Exception:
        await context.bot.send_message(chat.id, f"Channel id: <code>{chat.id}</code>", parse_mode=ParseMode.HTML)


# ---------- Order flow ----------
async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Опиши заказ: стиль/референсы, сколько визуалов, сроки.\n"
        "Можно прикрепить фото/видео — я всё передам админам."
    )
    return ORDER_DETAILS


async def order_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    header = (
        f"<b>Новый заказ</b>\n"
        f"From: <code>{user.full_name}</code> (id: <code>{user.id}</code>, {safe_username(user)})\n"
        f"Chat: <code>{chat.type}</code> (id: <code>{chat.id}</code>)\n"
    )

    # карточка с кнопкой "Ответить"
    await send_to_admins(
        context,
        header + "Прикреплённые материалы ниже (если были) или текст в следующем сообщении.",
        reply_markup=build_reply_keyboard(chat.id),
    )

    if update.message.photo:
        photo = update.message.photo[-1]
        caption = (update.message.caption or "").strip()
        for admin in ADMIN_IDS:
            try:
                await context.bot.send_photo(admin, photo.file_id, caption=(caption or "Фотка из заказа"))
            except Exception as e:
                logger.exception(f"Failed to forward photo to {admin}: {e}")
    elif update.message.document:
        doc = update.message.document
        for admin in ADMIN_IDS:
            try:
                await context.bot.send_document(admin, doc.file_id, caption="Документ из заказа")
            except Exception as e:
                logger.exception(f"Failed to forward doc to {admin}: {e}")
    else:
        text = (update.message.text or "").strip()
        await send_to_admins(context, f"Текст заказа:\n{text or '(пусто)'}")

    await update.message.reply_text("Приняла! Передала админам 💌 Мы свяжемся в ближайшее время.")
    return ConversationHandler.END


async def order_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Окей, отменила. Если что — /order 👌")
    return ConversationHandler.END


# ---------- Admin-only posting ----------
async def post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Недостаточно прав.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /post <текст>")
        return

    text = " ".join(context.args)
    if CHANNEL_ID == 0:
        await update.message.reply_text("CHANNEL_ID не задан.")
        return

    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode=ParseMode.HTML)
        await update.message.reply_text("Отправлено в канал ✔️")
    except Exception as e:
        logger.exception(f"/post failed: {e}")
        await update.message.reply_text(f"Не получилось отправить: {e}")


# ---------- Inline menu + REPLY router ----------
async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = (q.data or "").strip()
    await q.answer()

    # ====== Режим "Ответить пользователю" для админа ======
    if data.startswith("reply:"):
        if q.message.chat.type != ChatType.PRIVATE or not is_admin(q.from_user.id):
            return
        target_chat_id = int(data.split(":", 1)[1])
        PENDING_REPLY[q.from_user.id] = target_chat_id
        await q.message.reply_text(
            f"✍️ Введи сообщение — я отправлю пользователю (chat_id <code>{target_chat_id}</code>).",
            parse_mode=ParseMode.HTML,
        )
        return

    # ====== Меню пакетов/цен ======
    if data == "menu_instagram":
        await q.message.edit_text(build_prices_text(), parse_mode=ParseMode.HTML, reply_markup=instagram_menu_kb())
        return
    if data == "menu_neuro":
        await q.message.edit_text(build_prices_text(), parse_mode=ParseMode.HTML, reply_markup=neuro_menu_kb())
        return
    if data == "menu_fairy":
        await q.message.edit_text(build_prices_text(), parse_mode=ParseMode.HTML, reply_markup=fairy_menu_kb())
        return
    if data == "back_main":
        await q.message.edit_text(build_prices_text(), parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())
        return

    # Предзаполнение заказа по пакету
    pkg_map = {
        "pkg_instagram_5":  "Хочу пакет: Визуалы для Instagram — 5 шт (2 500₽). Рефы/стиль: ... Срок: ...",
        "pkg_instagram_10": "Хочу пакет: Визуалы для Instagram — 10 шт (4 500₽). Рефы/стиль: ... Срок: ...",
        "pkg_neuro_lite":   "Хочу пакет: Нейрофотосессия — Lite (3 900₽). Образы: 10. Исходные фото: 1. Стиль: ...",
        "pkg_neuro_std":    "Хочу пакет: Нейрофотосессия — Standard (6 900₽). Образы: 20. Исходные фото: 2. Стиль: ...",
        "pkg_neuro_pro":    "Хочу пакет: Нейрофотосессия — Pro (11 900₽). Образы: 40. Исходные фото: 4. Стиль: ...",
        "pkg_fairy_lite":   "Хочу пакет: Детские фото в сказочном стиле — Lite (2 900₽). 5 образов из 1 фото. Сказка/сеттинг: ...",
        "pkg_fairy_std":    "Хочу пакет: Детские фото в сказочном стиле — Standard (5 900₽). 12 образов из 2 фото. Сказка/сеттинг: ...",
        "pkg_fairy_pro":    "Хочу пакет: Детские фото в сказочном стиле — Pro (9 900₽). 25 образов из 3–4 фото. Сказка/сеттинг: ...",
    }
    if data in pkg_map:
        await q.message.reply_text(
            pkg_map[data] + "\n\nНажми /order и прикрепи фото ребёнка + примеры сказочного стиля — я всё передам 💌"
        )
        return

    if data == "order":
        await q.message.reply_text(
            "Окей! Опиши, пожалуйста, заказ: стиль/референс, сколько визуалов, сроки. Можно прикрепить фото."
        )
        return


# ---------- Fallback / Routing сообщений ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Единая точка: если пишет админ — проверяем режим ответа. Если пишет пользователь — карточка админам."""
    user = update.effective_user
    chat = update.effective_chat
    text = (update.message.text or "").strip()

    # 1) Админ пишет
    if is_admin(user.id):
        target = PENDING_REPLY.pop(user.id, None)
        if target:
            try:
                await context.bot.send_message(chat_id=target, text=text)
                await update.message.reply_text("✅ Отправлено.")
            except Exception as e:
                logger.exception(f"Admin reply failed: {e}")
                await update.message.reply_text(f"❌ Не удалось отправить: {e}")
        else:
            await update.message.reply_text("ℹ️ Нажми «💬 Ответить» под карточкой пользователя, затем введи сообщение.")
        return

    # 2) Обычный пользователь пишет — уведомляем админов карточкой
    caption = (
        f"<b>Входящее сообщение</b>\n"
        f"• Имя: <code>{user.full_name}</code>\n"
        f"• Username: {safe_username(user)}\n"
        f"• User ID: <code>{user.id}</code>\n"
        f"• Chat ID: <code>{chat.id}</code>\n\n"
        f"Текст: {text or '(пусто)'}"
    )
    await send_to_admins(context, caption, reply_markup=build_reply_keyboard(chat.id))
    await update.message.reply_text("Спасибо! Ваше сообщение передано администратору 💌")


# ---------- Main ----------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Exception in handler:", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set. Add it to .env or env vars.")

    application: Application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("prices", prices))
    application.add_handler(CommandHandler("myid", myid))
    application.add_handler(CommandHandler("post", post))

    # /channel_id из канала (бот должен быть админом)
    application.add_handler(
        MessageHandler(filters.ChatType.CHANNEL & filters.Regex(r"^/channel_id$"), channel_id_cmd)
    )

    # Order conversation
    conv = ConversationHandler(
        entry_points=[CommandHandler("order", order_start)],
        states={ORDER_DETAILS: [
            MessageHandler(~filters.COMMAND & (filters.TEXT | filters.PHOTO | filters.Document.ALL), order_details)
        ]},
        fallbacks=[CommandHandler("cancel", order_cancel)],
    )
    application.add_handler(conv)

    # Inline buttons router (меню + ответ)
    application.add_handler(CallbackQueryHandler(menu_router))

    # Текстовые сообщения (админ/пользователь)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Errors
    application.add_error_handler(error_handler)

    logger.info("Starting Kira bot…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
