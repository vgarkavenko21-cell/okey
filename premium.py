from datetime import datetime, timedelta
import re
from typing import Any, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from db_models import Database
from config import PREMIUM_CHANNEL_SUBSCRIPTION_DAYS

db = Database()


PREMIUM_MENU = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("🔗 Підписатися на канали", callback_data="premium_subscribe")],
        [InlineKeyboardButton("💳 Купити Premium", callback_data="premium_buy")],
        [InlineKeyboardButton("◀️ Назад", callback_data="premium_back_to_settings")],
    ]
)


def premium_channel_link_verifiable(link: str) -> bool:
    """
    Сумісність з admin.py.
    Реальна перевірка підписки в боті — по натисканнях кнопок; тут лише мінімальна валідація тексту.
    """
    return len((link or "").strip()) >= 3


def premium_link_needs_bind(link: str) -> bool:
    """Сумісність з admin.py; поточна логіка не використовує /bindpremium."""
    return False


def _premium_expiry_str(days: int | None = None) -> str:
    d = int(PREMIUM_CHANNEL_SUBSCRIPTION_DAYS if days is None else days)
    expires = datetime.now() + timedelta(days=d)
    return expires.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_channel_url(link: Optional[str]) -> Optional[str]:
    """
    Нормалізує link з БД у валідний URL для InlineKeyboardButton(url=...).
    Підтримує @username, t.me/..., https://..., у т.ч. t.me/+invite.
    """
    raw = (link or "").strip()
    if not raw:
        return None

    raw_no_scheme = re.sub(r"^https?://", "", raw, flags=re.IGNORECASE)

    if raw_no_scheme.startswith("@"):
        username = raw_no_scheme[1:].strip()
        return f"https://t.me/{username}" if username else None

    m = re.match(r"^t\.me/(.+)$", raw_no_scheme, flags=re.IGNORECASE)
    if m:
        return f"https://t.me/{m.group(1)}"

    if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        return raw

    return raw


def _get_premium_channels_rows() -> list[Any]:
    return db.cursor.execute(
        "SELECT id, link, title FROM premium_channels ORDER BY id ASC"
    ).fetchall()


async def show_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Екран Premium статусу: Free/Premium + відповідні кнопки."""
    user_id = update.effective_user.id
    is_premium = db.check_premium(user_id)

    if is_premium:
        user = db.get_user(user_id)
        premium_until_raw = user["premium_until"] if user and "premium_until" in user.keys() else None
        premium_until_date = None
        days_left = None
        if premium_until_raw:
            try:
                premium_until_dt = datetime.strptime(premium_until_raw, "%Y-%m-%d %H:%M:%S")
                premium_until_date = premium_until_dt.strftime("%Y-%m-%d")
                days_left = max((premium_until_dt.date() - datetime.now().date()).days, 0)
            except Exception:
                premium_until_date = None

        until_line = ""
        if premium_until_date is not None and days_left is not None:
            until_line = f"Активний до: {premium_until_date} ({days_left} дн.)\n\n"

        text = (
            "💎 **Premium активний**\n\n"
            f"{until_line}"
            "Ліміти зняті. Ви можете створювати більше альбомів.\n\n"
            "Якщо відписатись від потрібних каналів, Premium може бути анульовано."
        )
    else:
        text = (
            "🆓 **Статус: Free**\n\n"
            "Без Premium діють ліміти на альбоми:\n"
            "• 3 персональних\n"
            "• 3 спільних\n\n"
            "Щоб зняти обмеження — підпишіться на Premium-канали через меню нижче."
        )

    keyboard = [*list(PREMIUM_MENU.inline_keyboard)]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, reply_markup=reply_markup, parse_mode="Markdown"
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        except Exception:
            await update.callback_query.message.reply_text(
                text, reply_markup=reply_markup, parse_mode="Markdown"
            )
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник inline‑кнопок преміуму (callback_data починається з 'premium_')."""
    query = update.callback_query
    data = query.data

    if data == "premium_info":
        await query.answer()
        await show_premium_menu(update, context)
        return

    if data == "premium_back_to_settings":
        await query.answer()
        from main import show_settings
        await show_settings(update, context)
        return

    if data == "premium_subscribe":
        await query.answer()
        channels = _get_premium_channels_rows()
        if not channels:
            await query.edit_message_text(
                "🔗 Посилань на Premium-канали поки що немає.\n\n"
                "Адміністратор може додати їх в адмін‑панелі.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Назад", callback_data="premium_info")]
                ]),
            )
            return

        keyboard: list[list[InlineKeyboardButton]] = []
        for ch in channels:
            ch_id = int(ch["id"])
            title = (ch["title"] or "").strip() if ch["title"] is not None else ""
            title = title or f"Канал {ch_id}"
            keyboard.append([InlineKeyboardButton(title, callback_data=f"premium_click_{ch_id}")])

        keyboard.append(
            [InlineKeyboardButton("✅ Перевірити підписку", callback_data="premium_check")]
        )
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="premium_info")])

        try:
            await query.edit_message_text(
                "🔗 **Premium-канали**\n\n"
                "Натисніть **кожну** кнопку каналу по черзі (бот фіксує натискання). "
                "Потім відкрийте канал через «Відкрити канал» і підпишіться.\n\n"
                "Коли все зробите — натисніть **«✅ Перевірити підписку»**.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        return

    if data.startswith("premium_click_"):
        try:
            ch_id = int(data.split("_")[-1])
        except Exception:
            return

        db.cursor.execute(
            "INSERT OR IGNORE INTO premium_channel_clicks (user_id, channel_id) VALUES (?, ?)",
            (query.from_user.id, ch_id),
        )
        db.conn.commit()

        row = db.cursor.execute(
            "SELECT title, link FROM premium_channels WHERE id = ?",
            (ch_id,),
        ).fetchone()
        title = (row["title"] or "").strip() if row and row["title"] is not None else ""
        title = title or f"Канал {ch_id}"
        link = row["link"] if row and row["link"] is not None else None
        url = _normalize_channel_url(link)

        await query.answer("Зафіксовано. Відкрийте канал нижче.")

        if url:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"Відкрийте канал: {title}",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Відкрити канал", url=url)]]
                ),
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"Відкрийте канал вручну: {title}\n(Посилання не задано в адмінці.)",
            )
        return

    if data == "premium_check":
        await query.answer()
        channels = _get_premium_channels_rows()
        channel_ids = [int(ch["id"]) for ch in channels]

        clicked_rows = db.cursor.execute(
            "SELECT channel_id FROM premium_channel_clicks WHERE user_id = ?",
            (query.from_user.id,),
        ).fetchall()
        clicked_set = {int(r["channel_id"]) for r in clicked_rows if r["channel_id"] is not None}

        if not channel_ids:
            await query.edit_message_text(
                "🔗 Посилань на Premium-канали поки що немає.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Назад", callback_data="premium_info")]
                ]),
            )
            return

        if set(channel_ids) != clicked_set:
            missing = [cid for cid in channel_ids if cid not in clicked_set]
            miss_txt = ", ".join(str(x) for x in missing[:5])
            more = "…" if len(missing) > 5 else ""
            try:
                await query.edit_message_text(
                    "🆓 **Статус: Free**\n\n"
                    f"Спочатку натисніть кнопки всіх каналів зі списку "
                    f"(залишилось: {miss_txt}{more}), потім знову «Перевірити підписку».",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton("🔗 Підписатися на канали", callback_data="premium_subscribe")],
                            [InlineKeyboardButton("💳 Купити Premium", callback_data="premium_buy")],
                            [InlineKeyboardButton("◀️ Назад", callback_data="premium_info")],
                        ]
                    ),
                )
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    raise
            return

        days = int(PREMIUM_CHANNEL_SUBSCRIPTION_DAYS)
        expires_at = _premium_expiry_str(days=days)
        db.set_premium(
            query.from_user.id,
            expires_at=expires_at,
            subscription_type="channel",
            channel_id="all",
        )
        db.cursor.execute(
            "DELETE FROM premium_channel_clicks WHERE user_id = ?",
            (query.from_user.id,),
        )
        db.conn.commit()

        await show_premium_menu(update, context)
        return

    if data == "premium_buy":
        await query.answer()
        await query.edit_message_text(
            "💳 Купівля Premium тимчасово недоступна.\n\n"
            "Щоб зняти ліміти — підпишіться на Premium-канали (кнопка «Підписатися на канали»).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="premium_info")]
            ]),
        )
        return
