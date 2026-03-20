from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import ContextTypes
from datetime import datetime, timedelta
from typing import Any

from config import ADMIN_IDS
from db_models import Database

db = Database()
ADMIN_PASSWORD = "123"


def _message_content_key(msg: Any) -> str:
    """Стабільний ключ для порівняння "ідентичних" повідомлень."""
    if msg.text is not None:
        return f"text::{msg.text}"
    if msg.caption is not None:
        base = f"caption::{msg.caption}"
    else:
        base = "caption::"
    if msg.photo:
        return base + f"::photo::{msg.photo[-1].file_unique_id}"
    if msg.video:
        return base + f"::video::{msg.video.file_unique_id}"
    if msg.document:
        return base + f"::document::{msg.document.file_unique_id}"
    if msg.audio:
        return base + f"::audio::{msg.audio.file_unique_id}"
    if msg.voice:
        return base + f"::voice::{msg.voice.file_unique_id}"
    if msg.video_note:
        return base + f"::video_note::{msg.video_note.file_unique_id}"
    if msg.sticker:
        return f"sticker::{msg.sticker.file_unique_id}"
    return "other"


async def _send_broadcast_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str, target_chat_ids: list[int]) -> bool:
    msg = update.message
    if not msg:
        return False
    admin_id = update.effective_user.id
    sent_ok = 0
    failed = 0
    key = _message_content_key(msg)
    broadcast_id = db.create_broadcast(admin_id, mode, msg.chat_id, msg.message_id, key)
    for chat_id in target_chat_ids:
        try:
            copied = await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id,
            )
            db.add_broadcast_delivery(broadcast_id, chat_id, copied.message_id)
            sent_ok += 1
        except Exception:
            failed += 1
    await msg.reply_text(f"✅ Розсилку завершено.\nНадіслано: {sent_ok}\nПомилок: {failed}")
    return True


async def handle_admin_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обробка будь-якого повідомлення адміна для розсилок/видалення."""
    ud = context.user_data
    if not ud.get("is_admin"):
        return False
    msg = update.message
    if not msg:
        return False

    # Видалення "за зразком" (ідентичне повідомлення)
    if ud.get("admin_broadcast_delete_by_sample"):
        key = _message_content_key(msg)
        row = db.cursor.execute(
            "SELECT id FROM broadcasts WHERE admin_id = ? AND content_key = ? ORDER BY id DESC LIMIT 1",
            (update.effective_user.id, key),
        ).fetchone()
        if not row:
            await msg.reply_text("❌ Не знайдено ідентичної розсилки для видалення.")
            ud.pop("admin_broadcast_delete_by_sample", None)
            return True
        b_id = int(row["id"])
        rows = db.cursor.execute(
            "SELECT target_chat_id, target_message_id FROM broadcast_deliveries WHERE broadcast_id = ?",
            (b_id,),
        ).fetchall()
        deleted = 0
        failed = 0
        for r in rows:
            try:
                await context.bot.delete_message(chat_id=int(r["target_chat_id"]), message_id=int(r["target_message_id"]))
                deleted += 1
            except Exception:
                failed += 1
        await msg.reply_text(f"🗑 Видалення завершено.\nВидалено: {deleted}\nПомилок: {failed}")
        ud.pop("admin_broadcast_delete_by_sample", None)
        return True

    mode = ud.get("admin_broadcast_wait_mode")
    if not mode:
        return False

    if mode == "all":
        user_ids = [int(r["user_id"]) for r in db.cursor.execute("SELECT user_id FROM users").fetchall()]
        group_ids = [int(r["chat_id"]) for r in db.cursor.execute(
            "SELECT chat_id FROM bot_chats WHERE chat_type IN ('group','supergroup','channel') AND is_active = 1"
        ).fetchall()]
        targets = list(dict.fromkeys(user_ids + group_ids))
        ud.pop("admin_broadcast_wait_mode", None)
        return await _send_broadcast_from_message(update, context, "all", targets)

    if mode == "subs":
        targets = [int(r["user_id"]) for r in db.cursor.execute("SELECT user_id FROM users").fetchall()]
        ud.pop("admin_broadcast_wait_mode", None)
        return await _send_broadcast_from_message(update, context, "subs", targets)

    if mode == "groups":
        targets = [int(r["chat_id"]) for r in db.cursor.execute(
            "SELECT chat_id FROM bot_chats WHERE chat_type IN ('group','supergroup','channel') AND is_active = 1"
        ).fetchall()]
        ud.pop("admin_broadcast_wait_mode", None)
        return await _send_broadcast_from_message(update, context, "groups", targets)

    if mode == "one_user":
        target_chat_id = ud.get("admin_broadcast_target_user")
        if not target_chat_id:
            await msg.reply_text("❌ Не задано користувача. Оберіть ще раз у меню розсилки.")
            ud.pop("admin_broadcast_wait_mode", None)
            return True
        ud.pop("admin_broadcast_wait_mode", None)
        ud.pop("admin_broadcast_target_user", None)
        return await _send_broadcast_from_message(update, context, "one_user", [int(target_chat_id)])

    return False

ADMIN_MENU = ReplyKeyboardMarkup([
    [KeyboardButton("🔗 Канали Premium")],
    [KeyboardButton("📊 Статистика")],
    [KeyboardButton("👥 Користувачі")],
    [KeyboardButton("💎 Управління Premium")],
    [KeyboardButton("📨 Розсилка")],
    [KeyboardButton("◀️ Вийти з адмін‑панелі")],
], resize_keyboard=True)


async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin — запитує пароль у адміністратора."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас немає прав адміністратора.")
        return

    context.user_data["awaiting_admin_password"] = True
    await update.message.reply_text("🔐 Введіть пароль адміністратора:")


async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обробка тексту, що стосується адмін‑панелі. Повертає True, якщо оброблено."""
    ud = context.user_data
    text = update.message.text

    # Ввід пароля
    if ud.get("awaiting_admin_password"):
        if text.strip() == ADMIN_PASSWORD:
            ud["awaiting_admin_password"] = False
            ud["is_admin"] = True
            await update.message.reply_text("✅ Вхід в адмін‑панель.", reply_markup=ADMIN_MENU)
        else:
            await update.message.reply_text("❌ Невірний пароль.")
        return True

    if not ud.get("is_admin"):
        return False

    # ===== Admin: розсилка (ввід користувача) =====
    if ud.get("admin_broadcast_wait_user"):
        raw = (text or "").strip()
        if raw.startswith("@"):
            uname = raw[1:].strip()
            row = db.cursor.execute("SELECT user_id FROM users WHERE username = ?", (uname,)).fetchone()
            if not row:
                await update.message.reply_text("❌ Користувача не знайдено. Введіть ID або @username.")
                return True
            target_id = int(row["user_id"])
        else:
            try:
                target_id = int(raw)
            except Exception:
                await update.message.reply_text("❌ Введіть коректний ID або @username.")
                return True
        ud.pop("admin_broadcast_wait_user", None)
        ud["admin_broadcast_wait_mode"] = "one_user"
        ud["admin_broadcast_target_user"] = target_id
        await update.message.reply_text(
            f"✅ Користувача обрано: {target_id}\n"
            "Тепер надішліть повідомлення для тестової відправки (будь-який формат)."
        )
        return True

    # ===== Admin: розсилка (очікуємо саме повідомлення) =====
    if ud.get("admin_broadcast_wait_mode") or ud.get("admin_broadcast_delete_by_sample"):
        return await handle_admin_broadcast_message(update, context)

    # ===== Admin: ввід кількості днів для видачі Premium =====
    if ud.get("admin_premium_grant_days"):
        state = ud.get("admin_premium_grant_days") or {}
        action = state.get("action")
        try:
            days_raw = (text or "").strip()
            days = int(days_raw)
        except Exception:
            await update.message.reply_text("❌ Введіть число днів (наприклад: 7).")
            return True

        if days < 1 or days > 3650:
            await update.message.reply_text("❌ Кількість днів має бути від 1 до 3650.")
            return True

        uid = state.get("uid")
        page = state.get("page", 0)

        if not uid:
            ud.pop("admin_premium_grant_days", None)
            await update.message.reply_text("❌ Не вдалося зчитати користувача. Спробуйте ще раз.")
            return True

        expires_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        if action == "grant_paid":
            db.set_premium(uid, expires_at=expires_at, subscription_type="paid", channel_id="admin")
            await update.message.reply_text(
                f"✅ Видано гів Premium на {days} днів (uid={uid}).",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("◀️ В Premium-меню", callback_data="admin_premium")],
                    ]
                ),
            )
        elif action == "grant_channel":
            db.set_premium(uid, expires_at=expires_at, subscription_type="channel", channel_id="admin")
            await update.message.reply_text(
                f"✅ Видано гів Premium (sub/channel) на {days} днів (uid={uid}).",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("◀️ В Premium-меню", callback_data="admin_premium")],
                    ]
                ),
            )
        else:
            await update.message.reply_text("❌ Невідома дія видачі.")

        ud.pop("admin_premium_grant_days", None)
        return True

    # ===== Admin: команди на Premium (без кнопок-очікувань) =====
    # remove <id/@username>
    # grant paid <id/@username>
    # grant sub <id/@username>
    if text.startswith("remove ") or text.startswith("grant "):
        action_text = text.strip()

        def resolve_target_id(token: str) -> int | None:
            token = token.strip()
            if token.startswith("@"):
                uname = token[1:]
                row = db.cursor.execute("SELECT user_id FROM users WHERE username = ?", (uname,)).fetchone()
                return int(row["user_id"]) if row else None
            try:
                return int(token)
            except Exception:
                return None

        user_id = None
        expires_at = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        if action_text.startswith("remove "):
            token = action_text.split(" ", 1)[1]
            user_id = resolve_target_id(token)
            if user_id is None:
                await update.message.reply_text("❌ Не вдалося знайти користувача. Вкажіть ID або @username.")
                return True
            db.remove_premium(user_id)
            await update.message.reply_text(f"✅ Premium забрано у {token}.")
            return True

        if action_text.startswith("grant "):
            # grant paid X | grant sub X
            parts = action_text.split()
            if len(parts) < 3:
                await update.message.reply_text("❌ Формат: grant paid <id/@> або grant sub <id/@>")
                return True
            grant_type = parts[1].lower()
            token = " ".join(parts[2:])
            user_id = resolve_target_id(token)
            if user_id is None:
                await update.message.reply_text("❌ Не вдалося знайти користувача. Вкажіть ID або @username.")
                return True
            if grant_type == "paid":
                db.set_premium(user_id, expires_at=expires_at, subscription_type="paid", channel_id="admin")
                await update.message.reply_text(f"✅ Видано paid Premium: {token}.")
                return True
            if grant_type in {"sub", "channel"}:
                db.set_premium(user_id, expires_at=expires_at, subscription_type="channel", channel_id="admin")
                await update.message.reply_text(f"✅ Видано sub Premium: {token}.")
                return True

            await update.message.reply_text("❌ Невідомий тип. Використайте: paid або sub.")
            return True

    # ===== Admin: введення ID/нік для Premium =====
    if ud.get("admin_premium_input"):
        action = ud["admin_premium_input"].get("action")
        raw = (text or "").strip()
        cancel_words = {"◀️ В адмін-меню", "Скасувати", "❌ Скасувати", "cancel"}
        if raw in cancel_words:
            ud.pop("admin_premium_input", None)
            await update.message.reply_text("Скасовано.")
            return True

        # Приймаємо тільки рядки, схожі на @username або число (ID)
        if not (raw.isdigit() or raw.startswith("@")):
            await update.message.reply_text("⚠️ Введіть тільки ID або @username (або ◀️ В адмін-меню щоб скасувати).")
            return True

        # resolve user_id
        user_id = None
        if raw.startswith("@"):
            uname = raw[1:].strip()
            row = db.cursor.execute("SELECT user_id FROM users WHERE username = ?", (uname,)).fetchone()
            if row:
                user_id = int(row["user_id"])
        else:
            try:
                user_id = int(raw)
            except Exception:
                user_id = None

        if user_id is None:
            await update.message.reply_text("❌ Не вдалося знайти користувача. Перевірте ID або @username і спробуйте ще раз.")
            return True

        if action == "remove":
            expires_at = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            db.remove_premium(user_id)
            await update.message.reply_text(f"✅ Забрано Premium у користувача ID:{user_id} (або @...).")
        elif action == "grant_paid":
            # Якщо такого користувача ще немає в БД — створюємо технічний запис,
            # щоб можна було видати premium лише по user_id.
            if not db.get_user(user_id):
                db.register_user(user_id, None, None, None)

            ud["admin_premium_grant_days"] = {
                "action": "grant_paid",
                "uid": user_id,
                "page": 0,
            }
            await update.message.reply_text(
                f"🧾 Обрано користувача ID:{user_id}.\n"
                "Введіть кількість днів для гів Premium (1-3650):"
            )
            ud.pop("admin_premium_input", None)
            return True
        elif action == "grant_channel":
            expires_at = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            db.set_premium(user_id, expires_at=expires_at, subscription_type="channel", channel_id="admin")
            await update.message.reply_text(f"✅ Видано sub Premium користувачу ID:{user_id}.")
        else:
            await update.message.reply_text("❌ Невідома дія.")

        ud.pop("admin_premium_input", None)
        return True

    # ===== Admin: custom period for stats =====
    # Якщо адмін передумав вводити "свій період" і натиснув іншу кнопку меню —
    # скидаємо стан очікування дат.
    if ud.get("admin_stats_custom_phase") and text in {
        "📊 Статистика",
        "👥 Користувачі",
        "💎 Управління Premium",
        "🔗 Канали Premium",
        "📨 Розсилка",
        "◀️ Вийти з адмін‑панелі",
    }:
        ud.pop("admin_stats_custom_phase", None)
        ud.pop("admin_stats_custom_start", None)

    if ud.get("admin_stats_custom_phase") == "a":
        try:
            start_dt = datetime.strptime(text.strip(), "%Y-%m-%d")
        except Exception:
            await update.message.reply_text("❌ Невірний формат. Введіть дату A як `YYYY-MM-DD`.")
            return True
        ud["admin_stats_custom_start"] = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        ud["admin_stats_custom_phase"] = "b"
        await update.message.reply_text("Введіть дату B як `YYYY-MM-DD`:")
        return True

    if ud.get("admin_stats_custom_phase") == "b":
        try:
            end_dt = datetime.strptime(text.strip(), "%Y-%m-%d") + timedelta(days=1)
        except Exception:
            await update.message.reply_text("❌ Невірний формат. Введіть дату B як `YYYY-MM-DD`.")
            return True
        start_str = ud.get("admin_stats_custom_start")
        end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

        # counts from premium_events
        where_events = "event_at >= ? AND event_at <= ?"
        params = (start_str, end_str)
        bought = db.cursor.execute(f"SELECT COUNT(*) FROM premium_events WHERE event_type='grant_paid' AND {where_events}", params).fetchone()[0]
        subs = db.cursor.execute(f"SELECT COUNT(*) FROM premium_events WHERE event_type='grant_channel' AND {where_events}", params).fetchone()[0]
        removed = db.cursor.execute(f"SELECT COUNT(*) FROM premium_events WHERE event_type='remove' AND {where_events}", params).fetchone()[0]
        participants = db.cursor.execute(
            "SELECT COUNT(*) FROM users WHERE registered_at >= ? AND registered_at <= ?",
            params,
        ).fetchone()[0]

        await update.message.reply_text(
            "📊 **Статистика Premium (custom)**\n\n"
            f"Період: {start_str} → {end_str}\n\n"
            f"💳 paid: {bought}\n"
            f"🔗 channel: {subs}\n"
            f"🗑 removed: {removed}\n"
            f"👥 учасників: {participants}",
            parse_mode="Markdown",
        )

        ud.pop("admin_stats_custom_phase", None)
        ud.pop("admin_stats_custom_start", None)
        return True

    # ===== Admin menu via reply keyboard =====
    if text == "📊 Статистика":
        keyboard = [
            [InlineKeyboardButton("📊 Відкрити статистику", callback_data="admin_stats")],
        ]
        await update.message.reply_text(
            "📊 Статистика бота.\n\nНатисніть кнопку нижче, щоб переглянути зведення.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True

    if text == "👥 Користувачі":
        keyboard = [
            [InlineKeyboardButton("🧾 Надіслати список (всі)", callback_data="admin_users_send_all")],
            [InlineKeyboardButton("◀️ В адмін-меню", callback_data="admin_back")],
        ]
        await update.message.reply_text("👥 **Користувачі / Premium статус**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return True

    if text == "💎 Управління Premium":
        keyboard = [
            [InlineKeyboardButton("👥 Переглянути всіх з преміумом", callback_data="admin_premium_active_list_page_view_0")],
            [InlineKeyboardButton("🗑 Забрати преміум", callback_data="admin_premium_active_list_page_remove_0")],
            [InlineKeyboardButton("💳 Видати преміум (гів)", callback_data="admin_premium_input_grant_paid")],
            [InlineKeyboardButton("🔗 Канали Premium", callback_data="admin_premium_channels_manage")],
        ]

        await update.message.reply_text(
            "💎 Управління Premium. Оберіть дію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True

    if text == "📨 Розсилка":
        keyboard = [
            [InlineKeyboardButton("📨 Відкрити меню розсилки", callback_data="admin_broadcast")],
        ]
        await update.message.reply_text(
            "📨 Розсилка.\n\nНатисніть кнопку нижче, щоб відкрити інструменти розсилки.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return True

    # Видалення Premium-каналу командою: `del ID`
    if text.startswith("del "):
        try:
            cid = int(text.split()[1])
        except Exception:
            await update.message.reply_text("❌ Формат: del ID (наприклад: del 1)")
            return True

        db.cursor.execute("DELETE FROM premium_channels WHERE id = ?", (cid,))
        db.conn.commit()
        await update.message.reply_text("✅ Канал видалено (якщо існував).")
        return True

    # ===== Premium канали (послідовне додавання: link -> title) =====
    if ud.get("admin_premium_awaiting_link"):
        cancel_words = {"❌ Скасувати", "◀️ Назад", "/cancel", "cancel"}
        if (text or "").strip() in cancel_words:
            ud["admin_premium_awaiting_link"] = False
            ud["admin_premium_awaiting_title"] = False
            ud.pop("admin_premium_pending_link", None)
            await update.message.reply_text("Скасовано.")
            return True

        link = (text or "").strip()
        if not link:
            await update.message.reply_text("Посилання порожнє. Надішліть ще раз.")
            return True

        ud["admin_premium_pending_link"] = link
        ud["admin_premium_awaiting_link"] = False
        ud["admin_premium_awaiting_title"] = True

        await update.message.reply_text(
            "2) Тепер напишіть назву каналу, яка буде відображатись в меню Premium.\n"
            "Наприклад: Новини/Офіційні оновлення/Група підтримки."
        )
        return True

    if ud.get("admin_premium_awaiting_title"):
        cancel_words = {"❌ Скасувати", "◀️ Назад", "/cancel", "cancel"}
        if (text or "").strip() in cancel_words:
            ud["admin_premium_awaiting_title"] = False
            ud["admin_premium_awaiting_link"] = False
            ud.pop("admin_premium_pending_link", None)
            await update.message.reply_text("Скасовано.")
            return True

        title = (text or "").strip()
        link = ud.get("admin_premium_pending_link")
        if not link:
            ud["admin_premium_awaiting_title"] = False
            await update.message.reply_text("❌ Знайшли помилку в стані. Спробуйте додати заново через кнопку.")
            return True

        if not title:
            await update.message.reply_text("Назва порожня. Надішліть ще раз.")
            return True

        db.cursor.execute(
            "INSERT INTO premium_channels (link, title) VALUES (?, ?)",
            (link, title),
        )
        db.conn.commit()

        ud["admin_premium_awaiting_title"] = False
        ud.pop("admin_premium_pending_link", None)

        # Покажемо список знову (щоб адмін бачив діючі посилання)
        channels = db.cursor.execute(
            "SELECT id, link, title FROM premium_channels ORDER BY id ASC"
        ).fetchall()

        if not channels:
            await update.message.reply_text("✅ Додано, але зараз список порожній (очікувано не повинно бути).")
        else:
            lines = ["✅ Додано Premium-канал:", ""]
            for ch in channels:
                t = (ch["title"] or "").strip()
                if t:
                    lines.append(f"- {ch['id']}: {t} ({ch['link']})")
                else:
                    lines.append(f"- {ch['id']}: {ch['link']}")

            # Інлайн-кнопка для повторного додавання
            keyboard = [[InlineKeyboardButton("➕ Додати посилання", callback_data="admin_premium_add_link")]]
            await update.message.reply_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

        return True

    # ----- КАНАЛИ PREMIUM -----
    if text == "🔗 Канали Premium":
        channels = db.cursor.execute(
            "SELECT id, link, title FROM premium_channels ORDER BY id ASC"
        ).fetchall()

        if not channels:
            await update.message.reply_text("Поки що немає доданих Premium-каналів.")
        else:
            lines = ["Діючі Premium-канали:\n"]
            for ch in channels:
                t = (ch["title"] or "").strip()
                if t:
                    lines.append(f"- {ch['id']}: {t} ({ch['link']})")
                else:
                    lines.append(f"- {ch['id']}: {ch['link']}")
            await update.message.reply_text("\n".join(lines))

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("➕ Додати посилання", callback_data="admin_premium_add_link")]]
        )
        await update.message.reply_text("Натисніть кнопку, щоб додати новий канал:", reply_markup=keyboard)
        await update.message.reply_text("Щоб видалити канал — напишіть: `del ID` (наприклад: del 3).", parse_mode="Markdown")
        return True

    # ----- ВИХІД -----
    if text == "◀️ Вийти з адмін‑панелі":
        ud["is_admin"] = False
        await update.message.reply_text("◀️ Вихід з адмін‑панелі.", reply_markup=ReplyKeyboardRemove())
        return True

    # Інші розділи (статистика, розсилка) можна додати пізніше
    return True

