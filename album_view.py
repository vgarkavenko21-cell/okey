from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from db_models import Database
import helpers

# Глобальний об'єкт БД
db = Database()

# Повна заміна у Файлі 3
async def send_file_by_type(update: Update, context: ContextTypes.DEFAULT_TYPE, file_data, index=None):
    """Надсилання файлу за його типом із врахуванням налаштувань відображення"""
    user_id = update.effective_user.id
    
    # Перетворюємо об'єкт БД на звичайний словник для безпечного доступу до ключів
    try:
        f_dict = dict(file_data)
    except Exception:
        f_dict = file_data
        
    file_id = f_dict.get('telegram_file_id')
    file_type = f_dict.get('file_type')
    
    # Отримуємо налаштування користувача
    settings = helpers.get_user_display_settings(db, user_id)
    
    # Формуємо підпис (caption)
    caption_parts = []
    if settings.get('show_number') and index is not None:
        caption_parts.append(f"📄 Файл #{index}")
        
    if settings.get('show_date'):
        # Пробуємо всі стандартні варіанти назв колонок для дати у БД
        date_val = f_dict.get('created_at') or f_dict.get('added_at') or f_dict.get('date') or f_dict.get('upload_date')
        
        if date_val:
            # Відрізаємо тільки дату (перші 10 символів: РРРР-ММ-ДД)
            date_str = str(date_val)[:10]
            caption_parts.append(f"📅 {date_str}")
        
    # З'єднуємо частини підпису
    caption = " | ".join(caption_parts) if caption_parts else None
    
    try:
        if file_type == 'photo':
            await update.message.reply_photo(photo=file_id, caption=caption)
        elif file_type == 'video':
            await update.message.reply_video(video=file_id, caption=caption)
        elif file_type == 'document':
            await update.message.reply_document(document=file_id, caption=caption)
        elif file_type == 'audio':
            await update.message.reply_audio(audio=file_id, caption=caption)
        elif file_type == 'voice':
            await update.message.reply_voice(voice=file_id, caption=caption)
        elif file_type == 'circle':
            # Кружечки (video_note) не підтримують текст у Telegram
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
    
    # Замість: for file in files: await send_file_by_type(update, context, file)
    # Замість: for file in files: await send_file_by_type(update, context, file)
    for idx, file in enumerate(files, 1):
        await send_file_by_type(update, context, file, index=idx)

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

# ========== НАДІСЛАТИ ОСТАННІ (Файл 3) ==========

async def handle_recent_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення кількості останніх файлів для звичайного перегляду"""
    
    # Захист: якщо ми в меню видалення - ігноруємо
    if context.user_data.get('in_delete_menu'):
        return False
        
    if not context.user_data.get('awaiting_recent_count'):
        return False
    
    try:
        count = int(update.message.text)
        
        if count <= 0 or count > 50:
            await update.message.reply_text("❌ Введіть число від 1 до 50:")
            return True
        
        album_id = context.user_data.get('send_recent_album')
        
        if not album_id:
            return False
        
        # ВИПРАВЛЕННЯ: Отримуємо всі файли і беремо ОСТАННІ з кінця списку
        all_files = db.get_album_files(album_id)
        files = all_files[-count:] if all_files else []
        
        album = db.get_album(album_id)
        
        if not files:
            await update.message.reply_text("📭 В альбомі немає файлів.")
        else:
            await update.message.reply_text(f"📤 Надсилаю останні {len(files)} файлів з альбому '{album['name']}'...")
            
            for file in files:
                await send_file_by_type(update, context, file)
        
        # Очищаємо стан
        context.user_data['awaiting_recent_count'] = False
        context.user_data.pop('send_recent_album', None)
        
        # Показуємо кнопку повернення
        album_keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📤 Надіслати весь альбом")],
        [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
        [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
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
    # Захист від режиму видалення
    if context.user_data.get('in_delete_menu'): return False
    
    if not context.user_data.get('awaiting_date'):
        return False
    
    date_str = update.message.text
    album_id = context.user_data.get('send_date_album')
    
    if not album_id:
        return False
    
    try:
        from datetime import datetime
        # Перевіряємо формат дати
        datetime.strptime(date_str, '%Y-%m-%d')
        
        files = db.get_files_by_date(album_id, date_str)
        album = db.get_album(album_id)
        
        if not files:
            await update.message.reply_text(f"📭 Немає файлів за {date_str}")
        else:
            await update.message.reply_text(f"📤 Надсилаю {len(files)} файлів за {date_str} з альбому '{album['name']}'...")
            
            # ВИПРАВЛЕНО: Додано enumerate для передачі номера файлу
            for idx, file in enumerate(files, 1):
                await send_file_by_type(update, context, file, index=idx)
        
        # Очищаємо стан
        context.user_data['awaiting_date'] = False
        context.user_data.pop('send_date_album', None)
        
        # Повертаємо клавіатуру альбому
        album_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("📤 Надіслати весь альбом")],
            [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
            [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
            [KeyboardButton("⋯ Додаткові дії")],
            [KeyboardButton("◀️ Вийти з альбому")]
        ], resize_keyboard=True)
        
        await update.message.reply_text(
            "✅ Готово!",
            reply_markup=album_keyboard
        )
        return True
        
    except ValueError:
        await update.message.reply_text(
            "❌ Невірний формат. Введіть дату як РРРР-ММ-ДД\n"
            "Наприклад: 2024-01-31"
        )
        return True
    

# ========== НАДІСЛАТИ ПЕРШІ (Файл 3) ==========
async def handle_first_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('in_delete_menu'): return False
    if not context.user_data.get('awaiting_first_count'): return False

    try:
        count = int(update.message.text)
        if count <= 0 or count > 50:
            await update.message.reply_text("❌ Введіть число від 1 до 50:")
            return True
        
        album_id = context.user_data.get('send_first_album')
        all_files = db.get_album_files(album_id)
        
        # Беремо перші файли з початку масиву
        files = all_files[:count] if all_files else []
        album = db.get_album(album_id)
        
        if not files:
            await update.message.reply_text("📭 В альбомі немає файлів.")
        else:
            await update.message.reply_text(f"📤 Надсилаю перші {len(files)} файлів з альбому '{album['name']}'...")
            
            # ВИПРАВЛЕНО: Додано enumerate
            for idx, file in enumerate(files, 1):
                await send_file_by_type(update, context, file, index=idx)
        
        context.user_data['awaiting_first_count'] = False
        context.user_data.pop('send_first_album', None)
        
        album_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("📤 Надіслати весь альбом")],
            [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
            [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
            [KeyboardButton("⋯ Додаткові дії")],
            [KeyboardButton("◀️ Вийти з альбому")]
        ], resize_keyboard=True)
        
        await update.message.reply_text("✅ Готово!", reply_markup=album_keyboard)
        return True
    except ValueError:
        await update.message.reply_text("❌ Будь ласка, введіть число:")
        return True

# ========== НАДІСЛАТИ ПРОМІЖОК (Файл 3) ==========
async def handle_range_input_normal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('in_delete_menu'): return False
    if not context.user_data.get('awaiting_range'): return False
    
    text = update.message.text.strip().replace(' ', '')
    if '-' not in text:
        await update.message.reply_text("❌ Використовуйте формат X-Y (наприклад: 10-20)")
        return True
    
    try:
        start, end = map(int, text.split('-'))
        if start <= 0 or end <= 0 or start > end:
            await update.message.reply_text("❌ Невірний проміжок. X має бути менше Y")
            return True
        
        album_id = context.user_data.get('send_range_album')
        all_files = db.get_album_files(album_id)
        total_files = len(all_files) if all_files else 0
        
        if start > total_files:
            await update.message.reply_text(f"❌ Початкове число більше загальної кількості ({total_files})")
            return True
        if end > total_files:
            end = total_files
            await update.message.reply_text(f"⚠️ Кінцеве число скориговано до {total_files}")
            
        files = all_files[start-1:end]
        album = db.get_album(album_id)
        
        await update.message.reply_text(f"📤 Надсилаю файли з {start} по {end} з альбому '{album['name']}'...")
        
        # ВИПРАВЛЕНО: Додано enumerate, старт з потрібного номера
        for idx, file in enumerate(files, start=start):
            await send_file_by_type(update, context, file, index=idx)
            
        context.user_data['awaiting_range'] = False
        context.user_data.pop('send_range_album', None)
        
        album_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("📤 Надіслати весь альбом")],
            [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
            [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
            [KeyboardButton("⋯ Додаткові дії")],
            [KeyboardButton("◀️ Вийти з альбому")]
        ], resize_keyboard=True)
        
        await update.message.reply_text("✅ Готово!", reply_markup=album_keyboard)
        return True
    except ValueError:
        await update.message.reply_text("❌ Невірний формат. Введіть числа через дефіс:")
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