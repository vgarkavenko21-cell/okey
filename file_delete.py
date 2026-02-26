from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from db_models import Database
import helpers

db = Database()

# ========== ОБРОБНИК КНОПОК МЕНЮ ВИДАЛЕННЯ (РЕПЛАЙ КЛАВІАТУРА) ==========

async def handle_delete_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE, text, album_id):
    """Обробка кнопок меню видалення (реплай клавіатура)"""
    
    if text == "📤 Надіслати всі файли":
        files = db.get_album_files(album_id)
        if not files:
            await update.message.reply_text("📭 В альбомі немає файлів.")
            return True
        
        await update.message.reply_text(f"📤 Надсилаю всі {len(files)} файлів для видалення...")
        
        for index, file in enumerate(files, 1):
            await send_file_with_delete_button(update, context, file, index)
        return True
    
    elif text == "⏳ Надіслати останні":
        context.user_data['delete_action'] = 'recent'
        await update.message.reply_text(
            "⏳ Введіть кількість останніх файлів (наприклад: 5, 10, 20):"
        )
        return True
    
    elif text == "⏮ Надіслати перші":
        context.user_data['delete_action'] = 'first'
        await update.message.reply_text(
            "⏮ Введіть кількість перших файлів (наприклад: 5, 10, 20):"
        )
        return True
    
    elif text == "🔢 Надіслати проміжок":
        context.user_data['delete_action'] = 'range'
        await update.message.reply_text(
            "🔢 Введіть проміжок у форматі X-Y (наприклад: 10-20):\n\n"
            "Файли нумеруються від 1 до загальної кількості."
        )
        return True
    
    elif text == "📅 Надіслати за датою":
        context.user_data['delete_action'] = 'date'
        await update.message.reply_text(
            "📅 Введіть дату у форматі РРРР-ММ-ДД\n"
            "Наприклад: 2024-01-31"
        )
        return True
    
    elif text == "◀️ Назад до альбому":
        context.user_data['in_delete_menu'] = False
        context.user_data.pop('delete_action', None)
        return "back_to_album"  # Важливо повертати саме це значення
    
    return False

# ========== УНІВЕРСАЛЬНИЙ ОБРОБНИК ==========

async def handle_delete_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Універсальний обробник текстових повідомлень для видалення"""
    if not context.user_data.get('delete_action'):
        return False
    
    action = context.user_data.get('delete_action')
    
    if action in ['recent', 'first']:
        return await handle_delete_number_input(update, context)
    elif action == 'range':
        return await handle_delete_range_input(update, context)
    elif action == 'date':
        return await handle_delete_date_input(update, context)
    
    return False

# ========== ОБРОБНИК ВВЕДЕННЯ ДАТИ ==========

async def handle_delete_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення дати для видалення"""
    if context.user_data.get('delete_action') != 'date':
        return False
    
    date_str = update.message.text
    album_id = context.user_data.get('current_album')
    
    try:
        from datetime import datetime
        # Перевіряємо формат дати
        if '-' in date_str:
            parts = date_str.split('-')
            if len(parts) == 3:
                year, month, day = parts
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
        
        if not files:
            await update.message.reply_text(f"📭 Немає файлів за {date_str}")
        else:
            await update.message.reply_text(f"📤 Надсилаю {len(files)} файлів за {date_str}...")
            
            for index, file in enumerate(files, 1):
                from album_view import send_file_by_type
                await send_file_by_type(update, context, file)
        
        context.user_data.pop('delete_action', None)
        return True
        
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Невірний формат. Введіть дату як РРРР-ММ-ДД\n"
            "Наприклад: 2024-01-31"
        )
        return True

# ========== ОБРОБНИК ЧИСЛОВИХ ВВОДІВ ==========

async def handle_delete_number_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення числа для останніх/перших файлів"""
    if not context.user_data.get('delete_action'):
        return False
    
    try:
        number = int(update.message.text)
        if number <= 0:
            await update.message.reply_text("❌ Введіть додатнє число.")
            return True
        
        album_id = context.user_data.get('current_album')
        files = db.get_album_files(album_id)
        
        if not files:
            await update.message.reply_text("📭 В альбомі немає файлів.")
            return True
        
        action = context.user_data.get('delete_action')
        
        if action == 'recent':
            selected_files = files[-number:]  # Останні
            text = f"📤 Надсилаю останні {len(selected_files)} файлів..."
        elif action == 'first':
            selected_files = files[:number]  # Перші
            text = f"📤 Надсилаю перші {len(selected_files)} файлів..."
        else:
            return False
        
        await update.message.reply_text(text)
        
        # Нумеруємо файли
        for index, file in enumerate(selected_files, 1):
            await send_file_with_delete_button(update, context, file, index)
        
        # Очищаємо стан
        context.user_data.pop('delete_action', None)
        
        return True
        
    except ValueError:
        await update.message.reply_text("❌ Введіть число.")
        return True

# ========== ОБРОБНИК ПРОМІЖКУ ==========

async def handle_delete_range_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення проміжку X-Y"""
    if context.user_data.get('delete_action') != 'range':
        return False
    
    try:
        text = update.message.text.strip().replace(' ', '')
        if '-' not in text:
            await update.message.reply_text("❌ Невірний формат. Використовуйте X-Y (наприклад: 10-20)")
            return True
        
        start, end = map(int, text.split('-'))
        
        if start <= 0 or end <= 0 or start > end:
            await update.message.reply_text("❌ Невірний проміжок. X має бути менше Y, і обидва додатні.")
            return True
        
        album_id = context.user_data.get('current_album')
        files = db.get_album_files(album_id)
        total_files = len(files)
        
        if start > total_files:
            await update.message.reply_text(f"❌ Початкове число більше загальної кількості файлів ({total_files})")
            return True
        
        if end > total_files:
            end = total_files
            await update.message.reply_text(f"⚠️ Кінцеве число скориговано до {total_files}")
        
        selected_files = files[start-1:end]  # -1 бо індексація з 0
        await update.message.reply_text(f"📤 Надсилаю файли з {start} по {end} (всього {len(selected_files)})...")
        
        # Нумеруємо файли
        for index, file in enumerate(selected_files, start):
            await send_file_with_delete_button(update, context, file, index)
        
        # Очищаємо стан
        context.user_data.pop('delete_action', None)
        
        return True
        
    except ValueError:
        await update.message.reply_text("❌ Невірний формат. Введіть числа через дефіс (наприклад: 10-20)")
        return True

# ========== НАДІСЛАННЯ ФАЙЛУ З КНОПКОЮ ВИДАЛЕННЯ ==========

async def send_file_with_delete_button(update: Update, context: ContextTypes.DEFAULT_TYPE, file_data, file_number):
    """Надсилання файлу з інлайн кнопкою видалення"""
    file_id = file_data['telegram_file_id']
    file_type = file_data['file_type']
    file_name = file_data['file_name'] or f"файл {file_number}"
    
    # Створюємо інлайн кнопку видалення
    keyboard = [[InlineKeyboardButton(
        f"🗑 Видалити файл #{file_number}", 
        callback_data=f"delete_this_file_{file_data['file_id']}"
    )]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if file_type == 'photo':
            await update.message.reply_photo(
                photo=file_id,
                caption=f"📸 Файл #{file_number}",
                reply_markup=reply_markup
            )
        elif file_type == 'video':
            await update.message.reply_video(
                video=file_id,
                caption=f"🎥 Файл #{file_number}",
                reply_markup=reply_markup
            )
        elif file_type == 'document':
            await update.message.reply_document(
                document=file_id,
                caption=f"📄 Файл #{file_number}",
                reply_markup=reply_markup
            )
        elif file_type == 'audio':
            await update.message.reply_audio(
                audio=file_id,
                caption=f"🎵 Файл #{file_number}",
                reply_markup=reply_markup
            )
        elif file_type == 'voice':
            await update.message.reply_voice(
                voice=file_id,
                caption=f"🎤 Файл #{file_number}",
                reply_markup=reply_markup
            )
        elif file_type == 'circle':
            await update.message.reply_video_note(
                video_note=file_id,
                reply_markup=reply_markup
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка надсилання файлу #{file_number}: {e}")

# ========== ВИДАЛЕННЯ КОНКРЕТНОГО ФАЙЛУ ==========

async def delete_this_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Видалення конкретного файлу за його ID"""
    query = update.callback_query
    await query.answer()
    
    file_id = int(query.data.split('_')[-1])
    
    # Отримуємо інформацію про файл
    file = db.cursor.execute(
        "SELECT * FROM files WHERE file_id = ?", (file_id,)
    ).fetchone()
    
    if not file:
        await query.edit_message_text("❌ Файл не знайдено.")
        return
    
    # Підтвердження видалення
    keyboard = [
        [
            InlineKeyboardButton("✅ Так, видалити", callback_data=f"confirm_file_delete_{file_id}"),
            InlineKeyboardButton("❌ Ні", callback_data="cancel_file_delete")
        ]
    ]
    
    await query.edit_message_caption(
        caption="🗑 Видалити цей файл?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_file_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Підтвердження видалення файлу"""
    query = update.callback_query
    await query.answer()
    
    file_id = int(query.data.split('_')[-1])
    
    # Отримуємо album_id до видалення
    file = db.cursor.execute(
        "SELECT album_id FROM files WHERE file_id = ?", (file_id,)
    ).fetchone()
    
    if file:
        album_id = file['album_id']
        db.delete_file(file_id)
        
        await query.edit_message_caption(
            caption="✅ Файл успішно видалено!",
            reply_markup=None
        )
    else:
        await query.edit_message_caption(
            caption="❌ Файл не знайдено.",
            reply_markup=None
        )

async def cancel_file_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скасування видалення файлу"""
    query = update.callback_query
    await query.answer()
    await query.delete_message()