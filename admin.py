from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes

from config import ADMIN_IDS
from db_models import Database

db = Database()
ADMIN_PASSWORD = "123"

ADMIN_MENU = ReplyKeyboardMarkup([
    [KeyboardButton("🔗 Канали Premium")],
    [KeyboardButton("📊 Статистика")],
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

    if text == "💎 Управління Premium":
        # Тут просто підказка: керування Premium-каналами робиться через "🔗 Канали Premium"
        await update.message.reply_text(
            "Керування Premium-каналами відкрий через пункт «🔗 Канали Premium».\n"
            "Там показуються діючі посилання і є кнопка «➕ Додати посилання»."
        )
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

