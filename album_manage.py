from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db_models import Database
import helpers

db = Database()

# ========== ВИДАЛЕННЯ ФАЙЛІВ ==========

async def delete_files_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок процесу видалення файлів"""
    query = update.callback_query
    await query.answer()
    
    album_id = int(query.data.split('_')[2])
    files = db.get_album_files(album_id)
    
    if not files:
        await query.edit_message_text(
            "📭 В альбомі немає файлів для видалення.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data=f"open_album_{album_id}")
            ]])
        )
        return
    
    # Показуємо перші 10 файлів для видалення
    await show_files_for_deletion(query, album_id, files, page=0)

async def show_files_for_deletion(query, album_id, files, page=0):
    """Показати файли для видалення посторінково"""
    items_per_page = 5
    start = page * items_per_page
    end = start + items_per_page
    current_files = files[start:end]
    total_pages = (len(files) + items_per_page - 1) // items_per_page
    
    text = f"🗑 **Виберіть файли для видалення**\n"
    text += f"Сторінка {page + 1} з {total_pages}\n\n"
    
    keyboard = []
    
    for file in current_files:
        emoji = helpers.get_file_emoji(file['file_type'])
        file_date = helpers.format_date(file['added_at']).split()[0]
        btn_text = f"{emoji} {file_date} - {file['file_name'] or file['file_type']}"
        # Обрізаємо довгі назви
        if len(btn_text) > 40:
            btn_text = btn_text[:37] + "..."
        
        keyboard.append([InlineKeyboardButton(
            btn_text,
            callback_data=f"delete_file_{file['file_id']}"
        )])
    
    # Кнопки навігації
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"del_page_{album_id}_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"del_page_{album_id}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=f"open_album_{album_id}")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def delete_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Видалення конкретного файлу"""
    query = update.callback_query
    await query.answer()
    
    file_id = int(query.data.split('_')[2])
    
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
            InlineKeyboardButton("✅ Так, видалити", callback_data=f"confirm_delete_{file_id}"),
            InlineKeyboardButton("❌ Ні", callback_data=f"open_album_{file['album_id']}")
        ]
    ]
    
    await query.edit_message_text(
        "🗑 Ви впевнені, що хочете видалити цей файл?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_delete_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Підтвердження видалення файлу"""
    query = update.callback_query
    await query.answer()
    
    file_id = int(query.data.split('_')[2])
    
    # Отримуємо album_id до видалення
    file = db.cursor.execute(
        "SELECT album_id FROM files WHERE file_id = ?", (file_id,)
    ).fetchone()
    
    if file:
        album_id = file['album_id']
        db.delete_file(file_id)
        
        await query.edit_message_text(
            "✅ Файл успішно видалено!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ До альбому", callback_data=f"open_album_{album_id}")
            ]])
        )
    else:
        await query.edit_message_text("❌ Файл не знайдено.")

# ========== АРХІВАЦІЯ АЛЬБОМУ ==========

async def archive_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Архівування альбому"""
    query = update.callback_query
    await query.answer()
    
    album_id = int(query.data.split('_')[2])
    album = db.get_album(album_id)
    
    if not album:
        await query.edit_message_text("❌ Альбом не знайдено.")
        return
    
    text = (
        f"🗂 **Архівація альбому '{album['name']}'**\n\n"
        f"Архівація лише прибирає альбом зі списку.\n"
        f"Файли не видаляються.\n\n"
        f"Ви можете розархівувати альбом у будь-який момент."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Так, архівувати", callback_data=f"confirm_archive_{album_id}"),
            InlineKeyboardButton("❌ Ні", callback_data=f"open_album_{album_id}")
        ]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def confirm_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Підтвердження архівації"""
    query = update.callback_query
    await query.answer()
    
    album_id = int(query.data.split('_')[2])
    user_id = query.from_user.id
    
    db.archive_album(album_id, user_id)
    
    await query.edit_message_text(
        "✅ Альбом успішно архівовано!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📷 До моїх альбомів", callback_data="back_to_albums")
        ]])
    )

# ========== ВИДАЛЕННЯ АЛЬБОМУ ==========

async def delete_album_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок видалення альбому"""
    query = update.callback_query
    await query.answer()
    
    album_id = int(query.data.split('_')[2])
    album = db.get_album(album_id)
    
    if not album:
        await query.edit_message_text("❌ Альбом не знайдено.")
        return
    
    context.user_data['deleting_album'] = album_id
    context.user_data['awaiting_album_name_confirm'] = True
    
    await query.edit_message_text(
        f"🗑 **Видалення альбому**\n\n"
        f"Для підтвердження введіть точну назву альбому:\n"
        f"`{album['name']}`",
        parse_mode='Markdown'
    )

async def handle_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник підтвердження назви для видалення"""
    if not context.user_data.get('awaiting_album_name_confirm'):
        return False
    
    album_id = context.user_data.get('deleting_album')
    if not album_id:
        return False
    
    album = db.get_album(album_id)
    if not album:
        return False
    
    if update.message.text.strip() == album['name']:
        # Назва співпадає - видаляємо
        db.delete_album(album_id)
        
        context.user_data['awaiting_album_name_confirm'] = False
        context.user_data.pop('deleting_album', None)
        
        await update.message.reply_text(
            "✅ Альбом успішно видалено!",
            reply_markup=ReplyKeyboardMarkup([["📷 Мої альбоми"]], resize_keyboard=True)
        )
        return True
    else:
        await update.message.reply_text(
            "❌ Назва не співпадає. Видалення скасовано.",
            reply_markup=ReplyKeyboardMarkup([["📷 Мої альбоми"]], resize_keyboard=True)
        )
        
        context.user_data['awaiting_album_name_confirm'] = False
        context.user_data.pop('deleting_album', None)
        return True