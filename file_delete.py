from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from db_models import Database
import helpers

db = Database()

# ========== ОБРОБНИК КНОПОК МЕНЮ ВИДАЛЕННЯ ==========

# Повна заміна функції у Файлі 2
async def handle_delete_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE, text, album_id):
    """Обробка кнопок видалення з префіксом 'Надіслати:'"""
    
    if text == "Надіслати: Весь альбом":
        files = db.get_album_files(album_id)
        if not files:
            await update.message.reply_text("📭 В альбомі немає файлів.")
            return True
        await update.message.reply_text(f"🗑 Надсилаю всі {len(files)} файлів з кнопкою видалення:")
        for index, file in enumerate(files, 1):
            await delete_send_file_with_button(update, context, file, index)
        return True
    
    elif text == "Надіслати: Останні":
        context.user_data['delete_action'] = 'recent'
        context.user_data['awaiting_delete_input'] = True
        await update.message.reply_text("⏳ Скільки останніх файлів надіслати для видалення?")
        return True
    
    elif text == "Надіслати: Перші":
        context.user_data['delete_action'] = 'first'
        context.user_data['awaiting_delete_input'] = True
        await update.message.reply_text("⏮ Скільки перших файлів надіслати для видалення?")
        return True
    
    elif text == "Надіслати: Проміжок":
        context.user_data['delete_action'] = 'range'
        context.user_data['awaiting_delete_input'] = True
        await update.message.reply_text("🔢 Введіть проміжок (наприклад: 1-10):")
        return True
    
    elif text == "Надіслати: За датою":
        context.user_data['delete_action'] = 'date'
        context.user_data['awaiting_delete_input'] = True
        await update.message.reply_text("📅 Введіть дату для видалення (РРРР-ММ-ДД):")
        return True
    
    elif text == "◀️ Назад до альбому":
        return "back_to_album"
    
    return False

# ========== УНІВЕРСАЛЬНИЙ ОБРОБНИК ТЕКСТУ ==========

async def handle_delete_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Універсальний обробник текстових повідомлень для видалення"""
    
    print(f"🔍 handle_delete_text: text='{update.message.text}'")
    print(f"📊 in_delete_menu={context.user_data.get('in_delete_menu')}, delete_action={context.user_data.get('delete_action')}")
    
    # Якщо не в режимі видалення - пропускаємо
    if not context.user_data.get('in_delete_menu'):
        print("❌ Не в режимі видалення")
        return False
    
    # Якщо немає активної дії - пропускаємо
    if not context.user_data.get('delete_action'):
        print("❌ Немає активної дії")
        return False
    
    action = context.user_data.get('delete_action')
    print(f"✅ Обробляємо дію: {action} з текстом: {update.message.text}")
    
    # Обробляємо відповідно до дії
    if action == 'recent':
        return await delete_handle_recent_input(update, context)
    elif action == 'first':
        return await delete_handle_first_input(update, context)
    elif action == 'range':
        return await delete_handle_range_input(update, context)
    elif action == 'date':
        return await delete_handle_date_input(update, context)
    
    return False
# ========== ОБРОБНИКИ ВВЕДЕННЯ ==========

async def delete_handle_recent_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення кількості останніх файлів для видалення"""
    
    print(f"🔢 delete_handle_recent_input: {update.message.text}")
    
    try:
        count = int(update.message.text)
        if count <= 0 or count > 50:
            await update.message.reply_text("❌ Введіть число від 1 до 50:")
            return True
        
        album_id = context.user_data.get('current_album')
        files = db.get_album_files(album_id)
        
        if not files:
            await update.message.reply_text("📭 В альбомі немає файлів.")
            context.user_data.pop('delete_action', None)
            return True
        
        total_files = len(files)
        selected_files = files[-count:]
        start_num = total_files - len(selected_files) + 1
        
        await update.message.reply_text(f"📤 Надсилаю останні {len(selected_files)} файлів для видалення...")
        
        for idx, file in enumerate(selected_files, start_num):
            await delete_send_file_with_button(update, context, file, idx)
        
        context.user_data.pop('delete_action', None)
        return True
        
    except ValueError:
        await update.message.reply_text("❌ Введіть число.")
        return True
    

async def delete_handle_first_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення кількості перших файлів для видалення"""
    
    try:
        count = int(update.message.text)
        if count <= 0 or count > 50:
            await update.message.reply_text("❌ Введіть число від 1 до 50:")
            return True
        
        album_id = context.user_data.get('current_album')
        files = db.get_album_files(album_id)
        
        if not files:
            await update.message.reply_text("📭 В альбомі немає файлів.")
            context.user_data.pop('delete_action', None)
            context.user_data.pop('awaiting_delete_input', None)
            return True
        
        selected_files = files[:count]
        
        await update.message.reply_text(f"📤 Надсилаю перші {len(selected_files)} файлів для видалення...")
        
        for idx, file in enumerate(selected_files, 1):
            await delete_send_file_with_button(update, context, file, idx)
        
        context.user_data.pop('delete_action', None)
        context.user_data.pop('awaiting_delete_input', None)
        return True
        
    except ValueError:
        await update.message.reply_text("❌ Введіть число.")
        return True

async def delete_handle_range_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення проміжку X-Y для видалення"""
    
    text = update.message.text.strip().replace(' ', '')
    if '-' not in text:
        await update.message.reply_text("❌ Використовуйте формат X-Y (наприклад: 10-20)")
        return True
    
    try:
        start, end = map(int, text.split('-'))
        
        if start <= 0 or end <= 0 or start > end:
            await update.message.reply_text("❌ Невірний проміжок. X має бути менше Y")
            return True
        
        album_id = context.user_data.get('current_album')
        files = db.get_album_files(album_id)
        total_files = len(files)
        
        if start > total_files:
            await update.message.reply_text(f"❌ Початкове число більше {total_files}")
            return True
        
        if end > total_files:
            end = total_files
            await update.message.reply_text(f"⚠️ Кінцеве число скориговано до {total_files}")
        
        selected_files = files[start-1:end]
        
        await update.message.reply_text(f"📤 Надсилаю файли з {start} по {end} (всього {len(selected_files)}) для видалення...")
        
        for idx, file in enumerate(selected_files, start):
            await delete_send_file_with_button(update, context, file, idx)
        
        context.user_data.pop('delete_action', None)
        context.user_data.pop('awaiting_delete_input', None)
        return True
        
    except ValueError:
        await update.message.reply_text("❌ Невірний формат. Введіть числа через дефіс")
        return True

async def delete_handle_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення дати для видалення"""
    
    date_str = update.message.text
    album_id = context.user_data.get('current_album')
    
    try:
        from datetime import datetime
        datetime.strptime(date_str, '%Y-%m-%d')
        
        files = db.get_files_by_date(album_id, date_str)
        
        if not files:
            await update.message.reply_text(f"📭 Немає файлів за {date_str}")
        else:
            await update.message.reply_text(f"📤 Надсилаю {len(files)} файлів за {date_str} для видалення...")
            
            for idx, file in enumerate(files, 1):
                await delete_send_file_with_button(update, context, file, idx)
        
        context.user_data.pop('delete_action', None)
        context.user_data.pop('awaiting_delete_input', None)
        return True
        
    except ValueError:
        await update.message.reply_text("❌ Невірний формат. Введіть дату як РРРР-ММ-ДД")
        return True

# ========== НАДСИЛАННЯ ФАЙЛУ З КНОПКОЮ ВИДАЛЕННЯ ==========

async def delete_send_file_with_button(update: Update, context: ContextTypes.DEFAULT_TYPE, file_data, file_number):
    """Надсилання файлу з інлайн кнопкою видалення"""
    file_id = file_data['telegram_file_id']
    file_type = file_data['file_type']
    
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
    
    file = db.cursor.execute(
        "SELECT * FROM files WHERE file_id = ?", (file_id,)
    ).fetchone()
    
    if not file:
        await query.edit_message_text("❌ Файл не знайдено.")
        return
    
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