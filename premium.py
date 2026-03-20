from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db_models import Database

db = Database()


PREMIUM_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔗 Підписатися на канали", callback_data="premium_subscribe")],
    [InlineKeyboardButton("💳 Купити Premium", callback_data="premium_buy")],
])


async def show_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Головне меню преміуму, викликається з текстової кнопки/обмеження."""
    text = (
        "💎 **Premium**\n\n"
        "Щоб збільшити ліміти (3 особистих + 3 спільних альбоми) та зняти обмеження:\n\n"
        "• Ви можете щотижня підписуватись за новими посиланнями та **залишатися** підписаними.\n"
        "• При відписці Premium буде анульовано.\n"
        "• Купівля платної підписки поки що недоступна.\n"
    )
    await update.message.reply_text(text, reply_markup=PREMIUM_MENU, parse_mode="Markdown")


async def handle_premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник inline‑кнопок преміуму (callback_data починається з 'premium_')."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "premium_subscribe":
        channels = db.cursor.execute("SELECT * FROM premium_channels").fetchall()
        if not channels:
            await query.edit_message_text(
                "🔗 Канали для підписки ще не налаштовані.\n"
                "Адміністратор може додати їх в адмін‑панелі."
            )
            return

        lines = ["🔗 **Канали для підписки:**\n"]
        for ch in channels:
            link = ch["link"]
            title = ch["title"] or ""
            if title:
                lines.append(f"• [{title}]({link})")
            else:
                lines.append(f"• {link}")
        lines.append("\nПісля підписки напишіть боту ще раз, щоб оновити статус.")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")

    elif data == "premium_buy":
        await query.edit_message_text(
            "💳 Купівля Premium поки що недоступна.\n\n"
            "Слідкуйте за оновленнями."
        )

