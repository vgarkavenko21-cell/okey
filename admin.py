from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes

from config import ADMIN_IDS
from db_models import Database

db = Database()
ADMIN_PASSWORD = "123"

ADMIN_MENU = ReplyKeyboardMarkup([
    [KeyboardButton("🔗 Канали Premium")],
    [KeyboardButton("📊 Статистика")],
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

    # ----- КАНАЛИ PREMIUM -----
    if text == "🔗 Канали Premium":
        channels = db.cursor.execute("SELECT * FROM premium_channels").fetchall()
        if not channels:
            await update.message.reply_text("🔗 Список каналів пустий.")
        else:
            lines = ["🔗 **Канали Premium:**"]
            for ch in channels:
                lines.append(f"- {ch['id']}: {ch['title'] or ''} {ch['link']}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        await update.message.reply_text(
            "📝 Надішліть новий канал у форматі:\n"
            "`link || title`\n"
            "або `del ID` щоб видалити.",
            parse_mode="Markdown"
        )
        ud["admin_in_channels"] = True
        return True

    if ud.get("admin_in_channels"):
        if text.startswith("del "):
            try:
                cid = int(text.split()[1])
                db.cursor.execute("DELETE FROM premium_channels WHERE id = ?", (cid,))
                db.conn.commit()
                await update.message.reply_text("✅ Канал видалено.")
            except Exception as e:
                await update.message.reply_text(f"❌ Помилка: {e}")
            ud["admin_in_channels"] = False
            return True
        else:
            try:
                link, title = [p.strip() for p in text.split("||", 1)]
            except ValueError:
                await update.message.reply_text("❌ Формат: `link || title`", parse_mode="Markdown")
                return True
            db.cursor.execute(
                "INSERT INTO premium_channels (link, title) VALUES (?, ?)",
                (link, title)
            )
            db.conn.commit()
            await update.message.reply_text("✅ Канал додано.")
            ud["admin_in_channels"] = False
            return True

    # ----- ВИХІД -----
    if text == "◀️ Вийти з адмін‑панелі":
        ud["is_admin"] = False
        await update.message.reply_text("◀️ Вихід з адмін‑панелі.", reply_markup=ReplyKeyboardRemove())
        return True

    # Інші розділи (статистика, розсилка) можна додати пізніше
    return True

