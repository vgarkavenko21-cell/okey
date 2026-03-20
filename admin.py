from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from datetime import datetime, timedelta

from config import ADMIN_IDS
from db_models import Database

db = Database()
ADMIN_PASSWORD = "123"

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
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
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
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
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
            [InlineKeyboardButton("🕐 За весь час", callback_data="admin_stats_range_all")],
            [InlineKeyboardButton("📅 За день", callback_data="admin_stats_range_day")],
            [InlineKeyboardButton("📆 За тиждень", callback_data="admin_stats_range_week")],
            [InlineKeyboardButton("🗓 За місяць", callback_data="admin_stats_range_month")],
            [InlineKeyboardButton("✍️ Свій період", callback_data="admin_stats_range_custom")],
            [InlineKeyboardButton("◀️ В адмін-меню", callback_data="admin_back")],
        ]
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        await update.message.reply_text("📊 **Статистика Premium**\n\nОберіть період:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return True

    if text == "👥 Користувачі":
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [InlineKeyboardButton("🧾 Надіслати список (всі)", callback_data="admin_users_send_all")],
            [InlineKeyboardButton("◀️ В адмін-меню", callback_data="admin_back")],
        ]
        await update.message.reply_text("👥 **Користувачі / Premium статус**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return True

    if text == "💎 Управління Premium":
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton

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
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton

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

        from telegram import InlineKeyboardMarkup, InlineKeyboardButton

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

