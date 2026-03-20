from datetime import datetime, timedelta
import re
from typing import Any, Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from db_models import Database

db = Database()


PREMIUM_MENU = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("🔗 Підписатися на канали", callback_data="premium_subscribe")],
        [InlineKeyboardButton("💳 Купити Premium", callback_data="premium_buy")],
    ]
)


def _normalize_channel_chat_id(link: str) -> str | int:
    """
    Приводимо link з БД до того формату, який приймає `bot.get_chat_member`.
    Підтримує:
    - `@username`
    - `t.me/username`
    - числовий chat_id (наприклад -1001234567890)
    """
    raw = (link or "").strip()
    if not raw:
        return ""

    # Приберемо схему/хост + query/hash
    raw = re.sub(r"^https?://", "", raw)
    raw = raw.replace("www.", "")
    raw = raw.split("?", 1)[0].split("#", 1)[0].strip()

    # t.me/username
    m = re.match(r"^t\.me/(.+?)(?:/.*)?$", raw, flags=re.IGNORECASE)
    if m:
        raw = m.group(1)

    # t.me/c/<id>/<msg> (private channels internal format)
    m2 = re.match(r"^c/(\d+)(?:/.*)?$", raw, flags=re.IGNORECASE)
    if m2:
        # chat_id for Bot API is typically -100<id>
        return int(f"-100{m2.group(1)}")

    # t.me/c/<id>... might have been stripped incorrectly above
    m3 = re.match(r"^t\.me/c/(\d+)(?:/.*)?$", (link or "").strip(), flags=re.IGNORECASE)
    if m3:
        return int(f"-100{m3.group(1)}")

    if raw.startswith("@"):
        return raw

    # numeric chat id
    if re.fullmatch(r"-?\d+", raw):
        try:
            return int(raw)
        except Exception:
            pass

    # fallback: як є (інколи можуть зберегти username без @)
    return raw


async def _is_user_member_of_channel(context: ContextTypes.DEFAULT_TYPE, channel_chat_id: str | int, user_id: int) -> bool:
    """Перевірка membership через Telegram API."""
    status = await _get_user_channel_status(context, channel_chat_id, user_id)
    return status in {"member", "administrator", "creator", "restricted"}


async def _get_user_channel_status(
    context: ContextTypes.DEFAULT_TYPE,
    channel_chat_id: str | int,
    user_id: int,
) -> Optional[str]:
    """Повертає status з get_chat_member або None."""
    try:
        member = await context.bot.get_chat_member(chat_id=channel_chat_id, user_id=user_id)
        status = getattr(member, "status", None)
        return str(status) if status is not None else None
    except TelegramError:
        return None
    except Exception:
        return None


def _premium_expiry_str(days: int = 7) -> str:
    expires = datetime.now() + timedelta(days=days)
    return expires.strftime("%Y-%m-%d %H:%M:%S")


def _get_latest_channel_grant_row(user_id: int) -> Optional[dict[str, Any]]:
    return db.cursor.execute(
        """
        SELECT channel_id, granted_at, expires_at
        FROM premium_subscriptions
        WHERE user_id = ? AND subscription_type = 'channel' AND is_active = 1
        ORDER BY granted_at DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()


def _get_premium_channels_rows() -> list[Any]:
    return db.cursor.execute(
        "SELECT id, link, title FROM premium_channels ORDER BY id ASC"
    ).fetchall()


async def try_grant_premium_from_channels(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    *,
    extend_days: int = 7,
) -> Tuple[bool, str]:
    """
    Логіка Premium:
    - користувач має бути учасником каналу(ів)
    - Premium видається щотижня при вступі в "наступний" канал за порядком id
    - з Premium Premium буде анульовано, якщо користувач відписався від каналів, які він "закрив" (id <= останнього каналу видачі)
    """
    channels = _get_premium_channels_rows()
    if not channels:
        return False, "🔗 Канали для Premium ще не налаштовані."

    user_active_premium = db.check_premium(user_id)
    latest_row = _get_latest_channel_grant_row(user_id)

    last_granted_channel_id: Optional[int] = None
    if latest_row and latest_row.get("channel_id") is not None:
        try:
            last_granted_channel_id = int(latest_row["channel_id"])
        except Exception:
            last_granted_channel_id = None

    # Якщо Premium активний, спочатку перевіряємо "залишатися підписаними"
    if user_active_premium and last_granted_channel_id is not None:
        required_channels = [ch for ch in channels if int(ch["id"]) <= last_granted_channel_id]
        for ch in required_channels:
            chat_id = _normalize_channel_chat_id(ch["link"])
            status = await _get_user_channel_status(context, chat_id, user_id) if chat_id else None
            if not chat_id or status not in {"member", "administrator", "creator", "restricted"}:
                db.remove_premium(user_id)
                return False, (
                    "❌ Premium анульовано: ви не є учасником одного з потрібних каналів "
                    f"(status={status})."
                )

    # Якщо Premium активний, але немає історії видач (старі дані) - перевіряємо membership хоча б в одному каналі.
    if user_active_premium and last_granted_channel_id is None:
        any_member = False
        for ch in channels:
            chat_id = _normalize_channel_chat_id(ch["link"])
            status = await _get_user_channel_status(context, chat_id, user_id) if chat_id else None
            if chat_id and status in {"member", "administrator", "creator", "restricted"}:
                any_member = True
                break
        if not any_member:
            db.remove_premium(user_id)
            return False, "❌ Premium анульовано: ви не підписані на жоден з Premium каналів."

    # Далі намагаємось видати/продовжити на наступному каналі за порядком id
    checked_statuses: list[tuple[int, Optional[str]]] = []
    start_id = last_granted_channel_id or 0
    next_eligible_channel = None
    for ch in channels:
        if int(ch["id"]) <= start_id:
            continue
        chat_id = _normalize_channel_chat_id(ch["link"])
        if not chat_id:
            continue
        status = await _get_user_channel_status(context, chat_id, user_id)
        checked_statuses.append((int(ch["id"]), status))
        if status in {"member", "administrator", "creator", "restricted"}:
            next_eligible_channel = ch
            break

    if next_eligible_channel is None:
        if user_active_premium:
            user = db.get_user(user_id)
            until = user.get("premium_until") if user else None
            until_str = until or "невідомо"
            return True, f"✅ Premium активний. Діє до: {until_str}"
        # Покажемо, що Telegram реально повернув по status для діючого(ів) каналів
        parts = []
        for cid, st in checked_statuses[:6]:
            parts.append(f"{cid}:{st or 'None'}")
        tail = f"\nStatus (перші канали): {', '.join(parts)}" if parts else ""
        return False, f"⏳ Щоб отримати Premium, підпишіться на наступний канал зі списку.{tail}"

    expires_at = _premium_expiry_str(days=extend_days)

    # 1) Оновлюємо статус
    db.set_premium(user_id, expires_at=expires_at)

    # 2) Записуємо факт видачі Premium під конкретний канал
    # Деактивуємо попередні "активні" записи, щоб зберігати чисту історію
    db.cursor.execute(
        "UPDATE premium_subscriptions SET is_active = 0 WHERE user_id = ? AND is_active = 1",
        (user_id,),
    )
    db.cursor.execute(
        """
        INSERT INTO premium_subscriptions (user_id, subscription_type, channel_id, granted_at, expires_at, is_active)
        VALUES (?, 'channel', ?, CURRENT_TIMESTAMP, ?, 1)
        """,
        (user_id, str(next_eligible_channel["id"]), expires_at),
    )
    db.conn.commit()

    title = next_eligible_channel["title"] or next_eligible_channel["link"]
    return True, f"💎 Premium активовано! Канал: {title}. Термін: {expires_at}"


async def show_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Екран Premium статусу: Free/Premium + відповідні кнопки."""
    user_id = update.effective_user.id
    is_premium = db.check_premium(user_id)

    if is_premium:
        text = (
            "💎 **Premium активний**\n\n"
            "Ліміти зняті. Ви можете створювати більше альбомів.\n\n"
            "Якщо відписатись від потрібних каналів, Premium буде анульовано."
        )
    else:
        text = (
            "🆓 **Статус: Free**\n\n"
            "Без Premium діють ліміти на альбоми:\n"
            "• 3 персональних\n"
            "• 3 спільних\n\n"
            "Щоб зняти обмеження — оформіть підписку на Premium-канали (щотижня автоматично)."
        )

    keyboard = [*list(PREMIUM_MENU.inline_keyboard)]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, reply_markup=reply_markup, parse_mode="Markdown"
            )
        except Exception:
            await update.callback_query.message.reply_text(
                text, reply_markup=reply_markup, parse_mode="Markdown"
            )
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def handle_premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник inline‑кнопок преміуму (callback_data починається з 'premium_')."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "premium_info":
        # Відкриваємо меню Premium з кнопок у налаштуваннях та з повідомлень про ліміти
        await show_premium_menu(update, context)
        return

    if data == "premium_subscribe":
        channels = _get_premium_channels_rows()
        if not channels:
            await query.edit_message_text(
                "🔗 Посилань на Premium-канали поки що немає.\n\n"
                "Адміністратор може додати їх в адмін‑панелі."
            )
            return

        # Без реальної перевірки підписки (щоб не залежати від getChatMember):
        # натискання на канал фіксуємо в БД, а відкриття робимо URL-кнопкою у службовому повідомленні.
        keyboard: list[list[InlineKeyboardButton]] = []
        for ch in channels:
            ch_id = int(ch["id"])
            title = (ch["title"] or "").strip() if ch["title"] is not None else ""
            title = title or f"Канал {ch_id}"
            keyboard.append([InlineKeyboardButton(title, callback_data=f"premium_click_{ch_id}")])

        keyboard.append(
            [InlineKeyboardButton("✅ Перевірити підписку", callback_data="premium_check")]
        )

        await query.edit_message_text(
            "🔗 **Premium-канали**\n\n"
            "Натисніть на всі канали зі списку (бот збере ваші натискання). "
            "Після цього натисніть **«✅ Перевірити підписку»**.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return

    if data.startswith("premium_click_"):
        # Клік по каналу = запис прогресу в БД
        try:
            ch_id = int(data.split("_")[-1])
        except Exception:
            return

        db.cursor.execute(
            "INSERT OR IGNORE INTO premium_channel_clicks (user_id, channel_id) VALUES (?, ?)",
            (query.from_user.id, ch_id),
        )
        db.conn.commit()

        # Надсилаємо URL-кнопку, щоб користувач міг відкрити канал
        row = db.cursor.execute(
            "SELECT title, link FROM premium_channels WHERE id = ?",
            (ch_id,),
        ).fetchone()
        title = (row["title"] or "").strip() if row and row["title"] is not None else ""
        title = title or f"Канал {ch_id}"
        link = row["link"] if row and row["link"] is not None else None

        if link:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"Відкрийте канал: {title}",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Відкрити канал", url=link)]]
                ),
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"Відкрийте канал: {title}",
            )
        return

    if data == "premium_check":
        # Підтверджуємо Premium через кількість натискань.
        channels = _get_premium_channels_rows()
        channel_ids = [int(ch["id"]) for ch in channels]

        clicked_rows = db.cursor.execute(
            "SELECT channel_id FROM premium_channel_clicks WHERE user_id = ?",
            (query.from_user.id,),
        ).fetchall()
        clicked_set = {int(r["channel_id"]) for r in clicked_rows if r["channel_id"] is not None}

        if not channel_ids:
            await query.edit_message_text(
                "🔗 Посилань на Premium-канали поки що немає."
            )
            return

        if set(channel_ids) != clicked_set:
            # Не показуємо прогрес/галочки, просто кажемо що треба натиснути всі
            await query.edit_message_text(
                "🆓 **Статус: Free**\n\n"
                "Щоб отримати Premium — натисніть на всі канали зі списку, потім ще раз натисніть «Перевірити підписку».",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🔗 Підписатися на канали", callback_data="premium_subscribe")],
                        [InlineKeyboardButton("💳 Купити Premium", callback_data="premium_buy")],
                    ]
                ),
            )
            return

        expires_at = _premium_expiry_str(days=7)
        db.set_premium(query.from_user.id, expires_at=expires_at)
        db.cursor.execute(
            "DELETE FROM premium_channel_clicks WHERE user_id = ?",
            (query.from_user.id,),
        )
        db.conn.commit()

        await show_premium_menu(update, context)
        return

    if data == "premium_buy":
        await query.edit_message_text(
            "💳 Купівля Premium тимчасово недоступна.\n\n"
            "Щоб зняти ліміти — підпишіться на Premium-канали (кнопка «Підписатися на канали»)."
        )
        return

