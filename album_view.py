from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from db_models import Database
import helpers

# Глобальний об'єкт БД
db = Database()

async def send_file_by_type(update: Update, context: ContextTypes.DEFAULT_TYPE, file_data):
    """Надсилання файлу за його типом"""
    file_id = file_data['telegram_file_id']
    file_type = file_data['file_type']
    
    try:
        if file_type == 'photo':
            await update.message.reply_photo(photo=file_id)
        elif file_type == 'video':
            await update.message.reply_video(video=file_id)
        elif file_type == 'document':
            await update.message.reply_document(document=file_id)
        elif file_type == 'audio':
            await update.message.reply_audio(audio=file_id)
        elif file_type == 'voice':
            await update.message.reply_voice(voice=file_id)
        elif file_type == 'circle':
            await update.message.reply_video_note(video_note=file_id)
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка надсилання: {e}")

# ========== НАДІСЛАТИ ВСІ ФАЙЛИ ==========

async def send_all_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Надіслати всі файли з альбому"""
    query = update.callback_query
    await query.answer()
    
    album_id = int(query.data.split('_')[2])
    files = db.get_album_files(album_id)
    album = db.get_album(album_id)
    
    if not files:
        await query.edit_message_text(
            "📭 В альбомі немає файлів.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ До альбому", callback_data=f"open_album_{album_id}")
            ]])
        )
        return
    
    await query.edit_message_text(f"📤 Надсилаю всі {len(files)} файлів з альбому '{album['name']}'...")
    
    for file in files:
        await send_file_by_type(update, context, file)
    
    keyboard = [[InlineKeyboardButton("◀️ До альбому", callback_data=f"open_album_{album_id}")]]
    await query.message.reply_text(
        "✅ Готово!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== НАДІСЛАТИ ОСТАННІ ==========

async def send_recent_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок процесу надсилання останніх файлів"""
    query = update.callback_query
    await query.answer()
    
    album_id = int(query.data.split('_')[2])
    context.user_data['send_recent_album'] = album_id
    
    await query.edit_message_text(
        "⏳ Скільки останніх файлів надіслати?\n"
        "Введіть число (наприклад: 5, 10, 20):",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data=f"open_album_{album_id}")
        ]])
    )
    
    context.user_data['awaiting_recent_count'] = True

async def handle_recent_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення кількості останніх файлів"""
    # Лог для діагностики
    print(f"📌 handle_recent_count викликано з текстом: {update.message.text}")
    print(f"📌 awaiting_recent_count: {context.user_data.get('awaiting_recent_count')}")
    
    if not context.user_data.get('awaiting_recent_count'):
        return False
    
    try:
        count = int(update.message.text)
        print(f"📌 count = {count}")
        
        if count <= 0 or count > 50:
            await update.message.reply_text("❌ Введіть число від 1 до 50:")
            return True
        
        album_id = context.user_data.get('send_recent_album')
        print(f"📌 album_id = {album_id}")
        
        if not album_id:
            return False
        
        files = db.get_album_files(album_id, limit=count)
        album = db.get_album(album_id)
        
        if not files:
            await update.message.reply_text("📭 В альбомі немає файлів.")
        else:
            await update.message.reply_text(f"📤 Надсилаю {len(files)} файлів з альбому '{album['name']}'...")
            
            for file in files:
                await send_file_by_type(update, context, file)
        
        # Очищаємо стан
        context.user_data['awaiting_recent_count'] = False
        context.user_data.pop('send_recent_album', None)
        
        # Показуємо кнопку повернення
        album_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("📤 Надіслати весь альбом")],
            [KeyboardButton("⏳ Надіслати останні")],
            [KeyboardButton("📅 Надіслати за датою")],
            [KeyboardButton("⋯ Додаткові дії")],
            [KeyboardButton("◀️ Вийти з альбому")]
        ], resize_keyboard=True)
        
        await update.message.reply_text(
            "✅ Готово!",
            reply_markup=album_keyboard
        )
        return True
        
    except ValueError:
        await update.message.reply_text("❌ Будь ласка, введіть число:")
        return True
# ========== НАДІСЛАТИ ЗА ДАТОЮ ==========

async def send_by_date_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок процесу надсилання за датою"""
    query = update.callback_query
    await query.answer()
    
    album_id = int(query.data.split('_')[3])
    context.user_data['send_date_album'] = album_id
    
    await query.edit_message_text(
        "📅 Введіть дату у форматі РРРР-ММ-ДД\n"
        "Наприклад: 2024-01-31",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data=f"open_album_{album_id}")
        ]])
    )
    
    context.user_data['awaiting_date'] = True

async def handle_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення дати"""
    # Лог для діагностики
    print(f"📌 handle_date_input викликано з текстом: {update.message.text}")
    print(f"📌 awaiting_date: {context.user_data.get('awaiting_date')}")
    
    if not context.user_data.get('awaiting_date'):
        return False
    
    date_str = update.message.text
    album_id = context.user_data.get('send_date_album')
    print(f"📌 album_id = {album_id}")
    print(f"📌 date_str = {date_str}")
    
    
    if not album_id:
        return False
    
    try:
        # Перевіряємо формат дати (РРРР-ММ-ДД)
        from datetime import datetime
        # Спробуємо розпарсити дату
        if '-' in date_str:
            parts = date_str.split('-')
            if len(parts) == 3:
                year, month, day = parts
                # Перевіряємо чи це числа
                int(year); int(month); int(day)
                # Форматуємо правильно якщо треба
                if len(year) == 4 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                    formatted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    datetime.strptime(formatted_date, '%Y-%m-%d')
                    date_str = formatted_date
                else:
                    raise ValueError
            else:
                raise ValueError
        else:
            raise ValueError
        
        files = db.get_files_by_date(album_id, date_str)
        album = db.get_album(album_id)
        
        if not files:
            await update.message.reply_text(
                f"📭 Немає файлів за {date_str}"
            )
        else:
            await update.message.reply_text(f"📤 Надсилаю {len(files)} файлів за {date_str} з альбому '{album['name']}'...")
            
            for file in files:
                await send_file_by_type(update, context, file)
        
        # Очищаємо стан
        context.user_data['awaiting_date'] = False
        context.user_data.pop('send_date_album', None)
        
        # Повертаємо клавіатуру альбому
        album_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("📤 Надіслати весь альбом")],
            [KeyboardButton("⏳ Надіслати останні")],
            [KeyboardButton("📅 Надіслати за датою")],
            [KeyboardButton("⋯ Додаткові дії")],
            [KeyboardButton("◀️ Вийти з альбому")]
        ], resize_keyboard=True)
        
        await update.message.reply_text(
            "✅ Готово!",
            reply_markup=album_keyboard
        )
        return True
        
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Невірний формат. Введіть дату як РРРР-ММ-ДД\n"
            "Наприклад: 2024-01-31"
        )
        return True
# ========== ІНФОРМАЦІЯ ПРО АЛЬБОМ ==========

async def album_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати інформацію про альбом"""
    query = update.callback_query
    await query.answer()
    
    album_id = int(query.data.split('_')[2])
    album = db.get_album(album_id)
    
    if not album:
        await query.edit_message_text("❌ Альбом не знайдено.")
        return
    
    # Отримуємо додаткову інформацію
    files = db.get_album_files(album_id)
    file_types = {}
    for file in files:
        ftype = file['file_type']
        file_types[ftype] = file_types.get(ftype, 0) + 1
    
    # Формуємо текст
    text = f"ℹ️ **Інформація про альбом**\n\n"
    text += f"**Назва:** {album['name']}\n"
    text += f"**Створено:** {helpers.format_date(album['created_at'])}\n"
    text += f"**Всього файлів:** {album['files_count']}\n\n"
    
    if file_types:
        text += "**Типи файлів:**\n"
        for ftype, count in file_types.items():
            emoji = helpers.get_file_emoji(ftype)
            text += f"{emoji} {ftype}: {count}\n"
    
    if album['last_file_added']:
        # Використовуємо тільки дату
        date_only = album['last_file_added'][:10]
        text += f"\n**Останній файл:** {date_only}"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data=f"open_album_{album_id}")]]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )