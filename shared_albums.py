from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from db_models import Database
import helpers

db = Database()

# ========== ГОЛОВНЕ МЕНЮ СПІЛЬНИХ АЛЬБОМІВ ==========

async def shared_albums_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Головне меню спільних альбомів"""
    user_id = update.effective_user.id
    
    # Отримуємо спільні альбоми, де користувач є учасником
    shared_albums = db.cursor.execute("""
        SELECT a.*, sa.access_level, u.username as owner_name 
        FROM albums a 
        JOIN shared_albums sa ON a.album_id = sa.album_id 
        JOIN users u ON a.user_id = u.user_id
        WHERE sa.user_id = ? AND a.is_archived = 0
        ORDER BY a.created_at DESC
    """, (user_id,)).fetchall()
    
    # Отримуємо альбоми, де користувач є власником (але ще не спільні)
    owned_albums = db.cursor.execute("""
        SELECT * FROM albums 
        WHERE user_id = ? AND is_shared = 0 AND is_archived = 0
        ORDER BY created_at DESC
    """, (user_id,)).fetchall()
    
    text = "👥 **Спільні альбоми**\n\n"
    keyboard = []
    
    if shared_albums:
        text += "**Альбоми, де ви учасник:**\n"
        for album in shared_albums:
            role_emoji = {
                'owner': '👑', 'admin': '⚙️', 'editor': '✏️', 
                'contributor': '📤', 'viewer': '👁️'
            }.get(album['access_level'], '👤')
            
            album_text = f"{role_emoji} {album['name']} ({album['files_count']} файлів)"
            keyboard.append([InlineKeyboardButton(
                album_text, 
                callback_data=f"shared_open_{album['album_id']}"
            )])
        text += "\n"
    
    if owned_albums:
        text += "**Ваші альбоми (можна зробити спільними):**\n"
        for album in owned_albums:
            keyboard.append([InlineKeyboardButton(
                f"📁 {album['name']} ({album['files_count']} файлів)", 
                callback_data=f"make_shared_{album['album_id']}"
            )])
    
    if not shared_albums and not owned_albums:
        text = "👥 У вас немає спільних альбомів.\n\n"
    
    keyboard.append([InlineKeyboardButton("➕ Створити спільний альбом", callback_data="shared_create")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== СТВОРЕННЯ СПІЛЬНОГО АЛЬБОМУ ==========

async def shared_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок створення спільного альбому"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['shared_awaiting_name'] = True
    context.user_data['shared_creating'] = True
    
    await query.edit_message_text(
        "📝 Введіть назву для нового спільного альбому:"
    )

async def shared_handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення назви спільного альбому"""
    if not context.user_data.get('shared_awaiting_name') or not context.user_data.get('shared_creating'):
        return False
    
    album_name = update.message.text
    user_id = update.effective_user.id
    
    if len(album_name) > 50 or len(album_name) < 2:
        await update.message.reply_text("❌ Назва має бути від 2 до 50 символів")
        return True
    
    album_id = db.create_album(user_id, album_name)
    
    db.cursor.execute(
        "UPDATE albums SET is_shared = 1 WHERE album_id = ?",
        (album_id,)
    )
    
    db.cursor.execute('''
        INSERT INTO shared_albums (album_id, user_id, access_level, added_at)
        VALUES (?, ?, 'owner', CURRENT_TIMESTAMP)
    ''', (album_id, user_id))
    
    db.conn.commit()
    
    context.user_data['shared_awaiting_name'] = False
    context.user_data['shared_creating'] = False
    context.user_data['current_shared_album'] = album_id
    context.user_data['shared_album_active'] = True
    context.user_data['shared_access_level'] = 'owner'
    
    album = db.get_album(album_id)
    
    album_keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📤 Надіслати весь альбом")],
        [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
        [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
        [KeyboardButton("⋯ Додаткові опції")],
        [KeyboardButton("◀️ Вийти з альбому")]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        f"✅ Спільний альбом '{album_name}' створено!\n\n"
        f"📁 **{album_name}**\n"
        f"└ Файлів: 0\n"
        f"└ Ваша роль: Власник 👑\n\n"
        f"Надсилайте файли в цей чат, вони автоматично збережуться в альбом.",
        reply_markup=album_keyboard,
        parse_mode='Markdown'
    )
    return True

# ========== ВІДКРИТТЯ СПІЛЬНОГО АЛЬБОМУ ==========

async def shared_open_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Відкриття спільного альбому"""
    query = update.callback_query
    await query.answer()
    
    album_id = int(query.data.split('_')[2])
    user_id = query.from_user.id
    
    access = db.cursor.execute(
        "SELECT access_level FROM shared_albums WHERE album_id = ? AND user_id = ?",
        (album_id, user_id)
    ).fetchone()
    
    if not access:
        await query.edit_message_text("❌ У вас немає доступу до цього альбому.")
        return
    
    context.user_data['album_keyboard_active'] = False
    context.user_data.pop('current_album', None)
    
    context.user_data['current_shared_album'] = album_id
    context.user_data['shared_album_active'] = True
    context.user_data['shared_access_level'] = access['access_level']
    
    album = db.get_album(album_id)
    
    text = (
        f"👥 **{album['name']}**\n"
        f"└ Файлів: {album['files_count']}\n"
        f"└ Ваша роль: {helpers.get_role_name(access['access_level'])}\n\n"
        f"Надсилайте файли в цей чат, вони автоматично збережуться в альбом."
    )
    
    album_keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📤 Надіслати весь альбом")],
        [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
        [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
        [KeyboardButton("⋯ Додаткові опції")],
        [KeyboardButton("◀️ Вийти з альбому")]
    ], resize_keyboard=True)
    
    await query.edit_message_text(text, parse_mode='Markdown')
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="👥 Спільний альбом",
        reply_markup=album_keyboard
    )

# ========== ДОДАТКОВІ ОПЦІЇ ==========

async def shared_additional_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Додаткове меню для спільного альбому"""
    if not context.user_data.get('shared_album_active'):
        return False
    
    text = update.message.text
    print(f"📌 shared_additional_menu: text='{text}'")  # Для логування
    
    # ... решта коду
    album_id = context.user_data.get('current_shared_album')
    access_level = context.user_data.get('shared_access_level')
    
    if text == "⋯ Додаткові опції":
        context.user_data['shared_in_additional'] = True
        
        # Меню "Додаткові опції"
        additional_buttons = [
            [KeyboardButton("👥 Учасники")],
            [KeyboardButton("ℹ️ Інформація")],
        ]
        
        # Кнопка видалення файлів для тих, хто має права
        if access_level in ['owner', 'admin', 'editor', 'contributor']:
            additional_buttons.append([KeyboardButton("🗑 Видалити файл")])
        
        # Кнопки керування альбомом для власника/адміна
        if access_level in ['owner', 'admin']:
            additional_buttons.append([KeyboardButton("🗂 Архівувати альбом")])
        
        # Видалення альбому тільки для власника
        if access_level == 'owner':
            additional_buttons.append([KeyboardButton("🗑 Видалити альбом")])
        
        additional_buttons.append([KeyboardButton("◀️ Назад до альбому")])
        
        await update.message.reply_text(
            f"📋 **Додаткові опції**\n\nОберіть потрібну дію:",
            reply_markup=ReplyKeyboardMarkup(additional_buttons, resize_keyboard=True),
            parse_mode='Markdown'
        )
        return True
    
    elif context.user_data.get('shared_in_additional'):
        if text == "👥 Учасники":
            await shared_members_main(update, context, album_id, access_level)
            return True
        elif text == "ℹ️ Інформація":
            await shared_album_info(update, context, album_id)
            return True
        elif text == "🗑 Видалити файл" and access_level in ['owner', 'admin', 'editor', 'contributor']:
            await shared_delete_file_menu(update, context, album_id)
            return True
        elif text == "🗂 Архівувати альбом" and access_level in ['owner', 'admin']:
            await shared_archive_confirm(update, context, album_id)
            return True
        elif text == "🗑 Видалити альбом" and access_level == 'owner':
            await shared_delete_confirm(update, context, album_id)
            return True
        elif text == "◀️ Назад до альбому":
            context.user_data['shared_in_additional'] = False
            await shared_return_to_album(update, context, album_id)
            return True
    
    return False

# ========== ПОВЕРНЕННЯ ДО АЛЬБОМУ ==========

async def shared_return_to_album(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Повернення до основної клавіатури альбому"""
    album_keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📤 Надіслати весь альбом")],
        [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
        [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
        [KeyboardButton("⋯ Додаткові опції")],
        [KeyboardButton("◀️ Вийти з альбому")]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        "🔙 Повернення до альбому",
        reply_markup=album_keyboard
    )

# ========== ІНФОРМАЦІЯ ПРО АЛЬБОМ ==========

async def shared_album_info(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Показати інформацію про спільний альбом"""
    album = db.get_album(album_id)
    
    members_count = db.cursor.execute(
        "SELECT COUNT(*) FROM shared_albums WHERE album_id = ?",
        (album_id,)
    ).fetchone()[0]
    
    files_count = album['files_count']
    created = helpers.format_date(album['created_at']).split()[0]
    
    text = (
        f"ℹ️ **Інформація про спільний альбом**\n\n"
        f"**Назва:** {album['name']}\n"
        f"**Створено:** {created}\n"
        f"**Всього файлів:** {files_count}\n"
        f"**Учасників:** {members_count}\n"
    )
    
    if album['last_file_added']:
        last_file = album['last_file_added'][:10]
        text += f"**Останній файл:** {last_file}"
    
    keyboard = [[KeyboardButton("◀️ Назад до додаткових опцій")]]
    
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )

# ========== ГОЛОВНЕ МЕНЮ УЧАСНИКІВ ==========

async def shared_members_main(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id, access_level):
    """Головне меню керування учасниками"""
    context.user_data['shared_in_members_main'] = True
    
    text = "👥 **Керування учасниками**\n\nОберіть дію:"
    
    keyboard = [
        [KeyboardButton("📋 Переглянути всіх учасників")]
    ]
    
    if access_level in ['owner', 'admin']:
        keyboard.append([KeyboardButton("➕ Додати учасника")])
        keyboard.append([KeyboardButton("⚙️ Змінити ролі")])
        keyboard.append([KeyboardButton("🗑 Видалити учасника")])
    
    keyboard.append([KeyboardButton("◀️ Назад до додаткових опцій")])
    
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )

# ========== ПЕРЕГЛЯД ВСІХ УЧАСНИКІВ ==========

async def shared_view_all_members(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Показати список всіх учасників"""
    members = db.cursor.execute("""
        SELECT u.user_id, u.username, u.first_name, sa.access_level, sa.added_at
        FROM shared_albums sa
        JOIN users u ON sa.user_id = u.user_id
        WHERE sa.album_id = ?
        ORDER BY 
            CASE sa.access_level 
                WHEN 'owner' THEN 1
                WHEN 'admin' THEN 2
                WHEN 'editor' THEN 3
                WHEN 'contributor' THEN 4
                ELSE 5
            END
    """, (album_id,)).fetchall()
    
    text = "👥 **Всі учасники альбому:**\n\n"
    
    for member in members:
        role_emoji = {
            'owner': '👑', 'admin': '⚙️', 'editor': '✏️',
            'contributor': '📤', 'viewer': '👁️'
        }.get(member['access_level'], '👤')
        
        name = member['first_name'] or member['username'] or f"ID:{member['user_id']}"
        added = helpers.format_date(member['added_at']).split()[0] if member['added_at'] else "невідомо"
        role_name = helpers.get_role_name(member['access_level'])
        
        text += f"{role_emoji} **{name}** — *{role_name}*\n"
        text += f"└ Доданий: {added}\n\n"
    
    keyboard = [[KeyboardButton("◀️ Назад до меню учасників")]]
    
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )

# ========== ДОДАВАННЯ УЧАСНИКА ==========

async def shared_add_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок додавання учасника"""
    context.user_data['shared_awaiting_member'] = True
    
    await update.message.reply_text(
        "👤 Введіть username користувача (наприклад: @username)\n\n"
        "Або натисніть кнопку нижче, щоб скасувати:",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("❌ Скасувати")]
        ], resize_keyboard=True)
    )

async def shared_handle_member_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення username учасника"""
    if not context.user_data.get('shared_awaiting_member'):
        return False
    
    text = update.message.text
    
    if text == "❌ Скасувати":
        context.user_data['shared_awaiting_member'] = False
        album_id = context.user_data.get('current_shared_album')
        access_level = context.user_data.get('shared_access_level')
        await shared_members_main(update, context, album_id, access_level)
        return True
    
    username = text.strip()
    if username.startswith('@'):
        username = username[1:]
    
    user = db.cursor.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    
    if not user:
        await update.message.reply_text(
            "❌ Користувача не знайдено. Можливо, він ще не користувався ботом.\n"
            "Спробуйте інший username."
        )
        return True
    
    album_id = context.user_data.get('current_shared_album')
    
    exists = db.cursor.execute(
        "SELECT * FROM shared_albums WHERE album_id = ? AND user_id = ?",
        (album_id, user['user_id'])
    ).fetchone()
    
    if exists:
        await update.message.reply_text("❌ Цей користувач вже є учасником альбому.")
        return True
    
    db.cursor.execute('''
        INSERT INTO shared_albums (album_id, user_id, access_level, added_at)
        VALUES (?, ?, 'viewer', CURRENT_TIMESTAMP)
    ''', (album_id, user['user_id']))
    db.conn.commit()
    
    context.user_data['shared_awaiting_member'] = False
    
    await update.message.reply_text(
        f"✅ Користувача @{username} додано до альбому!\n"
        f"Його поточна роль: Спостерігач (може тільки переглядати)"
    )
    
    album_id = context.user_data.get('current_shared_album')
    access_level = context.user_data.get('shared_access_level')
    await shared_members_main(update, context, album_id, access_level)
    return True

# ========== ЗМІНА РОЛЕЙ ==========

async def shared_manage_roles(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Меню керування ролями"""
    members = db.cursor.execute("""
        SELECT u.user_id, u.username, u.first_name, sa.access_level
        FROM shared_albums sa
        JOIN users u ON sa.user_id = u.user_id
        WHERE sa.album_id = ? AND sa.access_level != 'owner'
        ORDER BY u.first_name
    """, (album_id,)).fetchall()
    
    if not members:
        await update.message.reply_text("👥 Немає учасників для зміни ролей.")
        return
    
    text = "⚙️ **Зміна ролей учасників**\n\n"
    text += "Для зміни ролі оберіть учасника зі списку нижче,\n"
    text += "або введіть його нікнейм через @\n\n"
    
    # Формуємо інлайн клавіатуру
    keyboard = []
    for member in members:
        name = member['first_name'] or member['username'] or f"ID:{member['user_id']}"
        role_name = helpers.get_role_name(member['access_level'])
        button_text = f"{name} — {role_name}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"shared_role_{member['user_id']}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="shared_back_to_members_main")])
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['shared_in_role_selection'] = True

async def shared_handle_role_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник текстового введення для зміни ролі"""
    if not context.user_data.get('shared_in_role_selection'):
        return False
    
    text = update.message.text.strip()
    album_id = context.user_data.get('current_shared_album')
    
    if text.startswith('@'):
        username = text[1:]
    else:
        username = text
    
    user = db.cursor.execute("""
        SELECT u.user_id, u.username, u.first_name
        FROM users u
        JOIN shared_albums sa ON u.user_id = sa.user_id
        WHERE sa.album_id = ? AND (u.username = ? OR u.first_name = ?)
    """, (album_id, username, username)).fetchone()
    
    if not user:
        await update.message.reply_text("❌ Учасника не знайдено. Спробуйте ще раз.")
        return True
    
    await shared_show_role_options(update, context, user['user_id'])
    return True

async def shared_show_role_options(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id):
    """Показати опції ролей для вибраного учасника"""
    user = db.cursor.execute(
        "SELECT first_name, username FROM users WHERE user_id = ?",
        (target_user_id,)
    ).fetchone()
    
    name = user['first_name'] or user['username'] or f"ID:{target_user_id}"
    
    text = f"👤 **{name}**\n\nОберіть нову роль:"
    
    keyboard = [
        [InlineKeyboardButton("⚙️ Адмін (керування + редагування)", callback_data=f"shared_set_role_{target_user_id}_admin")],
        [InlineKeyboardButton("✏️ Редактор (редагування + додавання)", callback_data=f"shared_set_role_{target_user_id}_editor")],
        [InlineKeyboardButton("📤 Автор (додавання + перегляд)", callback_data=f"shared_set_role_{target_user_id}_contributor")],
        [InlineKeyboardButton("👁️ Спостерігач (тільки перегляд)", callback_data=f"shared_set_role_{target_user_id}_viewer")],
        [InlineKeyboardButton("◀️ Назад", callback_data="shared_back_to_role_selection")]
    ]
    
    query = update.callback_query if hasattr(update, 'callback_query') else None
    if query:
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    context.user_data['shared_changing_role_for'] = target_user_id

async def shared_set_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Встановлення ролі для учасника"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    target_user_id = int(parts[3])
    new_role = parts[4]
    album_id = context.user_data.get('current_shared_album')
    
    db.cursor.execute('''
        UPDATE shared_albums 
        SET access_level = ? 
        WHERE album_id = ? AND user_id = ?
    ''', (new_role, album_id, target_user_id))
    db.conn.commit()
    
    user = db.cursor.execute(
        "SELECT first_name, username FROM users WHERE user_id = ?",
        (target_user_id,)
    ).fetchone()
    
    name = user['first_name'] or user['username'] or f"ID:{target_user_id}"
    role_name = helpers.get_role_name(new_role)
    
    await query.edit_message_text(
        f"✅ Роль для **{name}** змінено на **{role_name}**!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ До списку ролей", callback_data="shared_back_to_role_selection")
        ]]),
        parse_mode='Markdown'
    )

# ========== ВИДАЛЕННЯ УЧАСНИКА ==========

async def shared_remove_member_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Меню видалення учасника"""
    members = db.cursor.execute("""
        SELECT u.user_id, u.username, u.first_name, sa.access_level
        FROM shared_albums sa
        JOIN users u ON sa.user_id = u.user_id
        WHERE sa.album_id = ? AND sa.access_level != 'owner'
        ORDER BY u.first_name
    """, (album_id,)).fetchall()
    
    if not members:
        await update.message.reply_text("👥 Немає учасників для видалення.")
        return
    
    text = "🗑 **Виберіть учасника для видалення:**\n\n"
    keyboard = []
    
    for member in members:
        name = member['first_name'] or member['username'] or f"ID:{member['user_id']}"
        role_name = helpers.get_role_name(member['access_level'])
        keyboard.append([KeyboardButton(f"🗑 {name} — {role_name}")])
    
    keyboard.append([KeyboardButton("◀️ Назад до меню учасників")])
    
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )
    
    context.user_data['shared_selecting_member_for_removal'] = True

async def shared_handle_remove_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник вибору учасника для видалення"""
    if not context.user_data.get('shared_selecting_member_for_removal'):
        return False
    
    text = update.message.text
    album_id = context.user_data.get('current_shared_album')
    
    if text == "◀️ Назад до меню учасників":
        context.user_data['shared_selecting_member_for_removal'] = False
        access_level = context.user_data.get('shared_access_level')
        await shared_members_main(update, context, album_id, access_level)
        return True
    
    if text.startswith("🗑 "):
        name_part = text[2:].split(" — ")[0]
        
        user = db.cursor.execute("""
            SELECT u.user_id
            FROM users u
            JOIN shared_albums sa ON u.user_id = sa.user_id
            WHERE sa.album_id = ? AND (u.first_name = ? OR u.username = ?)
        """, (album_id, name_part, name_part)).fetchone()
        
        if user:
            await shared_confirm_remove_member(update, context, user['user_id'])
            return True
    
    return False

async def shared_confirm_remove_member(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id):
    """Підтвердження видалення учасника"""
    user = db.cursor.execute(
        "SELECT first_name, username FROM users WHERE user_id = ?",
        (target_user_id,)
    ).fetchone()
    
    name = user['first_name'] or user['username'] or f"ID:{target_user_id}"
    
    context.user_data['shared_removing_member'] = target_user_id
    
    await update.message.reply_text(
        f"🗑 Видалити учасника **{name}** з альбому?",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("✅ Так, видалити")],
            [KeyboardButton("❌ Ні, скасувати")]
        ], resize_keyboard=True),
        parse_mode='Markdown'
    )

async def shared_handle_remove_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник підтвердження видалення учасника"""
    if not context.user_data.get('shared_removing_member'):
        return False
    
    text = update.message.text
    target_user_id = context.user_data.get('shared_removing_member')
    album_id = context.user_data.get('current_shared_album')
    
    if text == "✅ Так, видалити":
        db.cursor.execute(
            "DELETE FROM shared_albums WHERE album_id = ? AND user_id = ?",
            (album_id, target_user_id)
        )
        db.conn.commit()
        
        await update.message.reply_text("✅ Учасника видалено з альбому!")
        
        context.user_data['shared_removing_member'] = None
        context.user_data['shared_selecting_member_for_removal'] = False
        access_level = context.user_data.get('shared_access_level')
        await shared_members_main(update, context, album_id, access_level)
        return True
    
    elif text == "❌ Ні, скасувати":
        context.user_data['shared_removing_member'] = None
        access_level = context.user_data.get('shared_access_level')
        await shared_members_main(update, context, album_id, access_level)
        return True
    
    return False

# ========== НАВІГАЦІЯ ПО МЕНЮ УЧАСНИКІВ ==========

async def shared_handle_members_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник навігації в меню учасників"""
    if not context.user_data.get('shared_in_members_main'):
        return False
    
    text = update.message.text
    album_id = context.user_data.get('current_shared_album')
    access_level = context.user_data.get('shared_access_level')
    
    if text == "📋 Переглянути всіх учасників":
        await shared_view_all_members(update, context, album_id)
        return True
    
    elif text == "➕ Додати учасника" and access_level in ['owner', 'admin']:
        await shared_add_member(update, context)
        return True
    
    elif text == "⚙️ Змінити ролі" and access_level in ['owner', 'admin']:
        await shared_manage_roles(update, context, album_id)
        return True
    
    elif text == "🗑 Видалити учасника" and access_level in ['owner', 'admin']:
        await shared_remove_member_menu(update, context, album_id)
        return True
    
    elif text == "◀️ Назад до додаткових опцій":
        context.user_data['shared_in_members_main'] = False
        context.user_data['shared_in_additional'] = True
        
        additional_buttons = [
            [KeyboardButton("👥 Учасники")],
            [KeyboardButton("ℹ️ Інформація")],
        ]
        
        if access_level in ['owner', 'admin', 'editor', 'contributor']:
            additional_buttons.append([KeyboardButton("🗑 Видалити файл")])
        
        if access_level in ['owner', 'admin']:
            additional_buttons.append([KeyboardButton("🗂 Архівувати альбом")])
        
        if access_level == 'owner':
            additional_buttons.append([KeyboardButton("🗑 Видалити альбом")])
        
        additional_buttons.append([KeyboardButton("◀️ Назад до альбому")])
        
        await update.message.reply_text(
            f"📋 **Додаткові опції**\n\nОберіть потрібну дію:",
            reply_markup=ReplyKeyboardMarkup(additional_buttons, resize_keyboard=True),
            parse_mode='Markdown'
        )
        return True
    
    return False

# ========== ВИДАЛЕННЯ ФАЙЛУ ==========

async def shared_delete_file_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Меню видалення файлів"""
    await update.message.reply_text(
        "🗑 **Видалення файлів**\n\nФункція в розробці",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("◀️ Назад до додаткових опцій")]
        ], resize_keyboard=True)
    )

# ========== АРХІВАЦІЯ АЛЬБОМУ ==========

async def shared_archive_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Підтвердження архівації альбому"""
    album = db.get_album(album_id)
    
    await update.message.reply_text(
        f"🗂 Архівувати альбом '{album['name']}'?\n\n"
        f"Архівовані альбоми не показуються в списку, але файли зберігаються.",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("✅ Так, архівувати")],
            [KeyboardButton("❌ Ні, скасувати")]
        ], resize_keyboard=True)
    )
    
    context.user_data['shared_awaiting_archive'] = album_id

async def shared_handle_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник архівації альбому"""
    if not context.user_data.get('shared_awaiting_archive'):
        return False
    
    text = update.message.text
    album_id = context.user_data.get('shared_awaiting_archive')
    user_id = update.effective_user.id
    
    if text == "✅ Так, архівувати":
        db.archive_album(album_id, user_id)
        
        context.user_data['shared_album_active'] = False
        context.user_data.pop('current_shared_album', None)
        context.user_data.pop('shared_access_level', None)
        context.user_data.pop('shared_in_additional', None)
        context.user_data.pop('shared_awaiting_archive', None)
        
        await update.message.reply_text(
            "✅ Альбом успішно архівовано!",
            reply_markup=MAIN_MENU
        )
        return True
    
    elif text == "❌ Ні, скасувати":
        context.user_data.pop('shared_awaiting_archive', None)
        context.user_data['shared_in_additional'] = True
        await shared_return_to_album(update, context, album_id)
        return True
    
    return False

# ========== ВИДАЛЕННЯ АЛЬБОМУ ==========

async def shared_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Підтвердження видалення альбому"""
    album = db.get_album(album_id)
    context.user_data['shared_deleting_album'] = album_id
    context.user_data['shared_awaiting_delete_confirm'] = True
    context.user_data['shared_album_name_to_delete'] = album['name']
    
    await update.message.reply_text(
        f"🗑 **Видалення альбому**\n\n"
        f"Для підтвердження введіть назву альбому:",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("❌ Скасувати")]
        ], resize_keyboard=True),
        parse_mode='Markdown'
    )

async def shared_handle_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник підтвердження видалення альбому"""
    if not context.user_data.get('shared_awaiting_delete_confirm'):
        return False
    
    user_input = update.message.text.strip()
    correct_name = context.user_data.get('shared_album_name_to_delete')
    album_id = context.user_data.get('shared_deleting_album')
    
    if user_input == "❌ Скасувати":
        context.user_data.pop('shared_awaiting_delete_confirm', None)
        context.user_data.pop('shared_deleting_album', None)
        context.user_data.pop('shared_album_name_to_delete', None)
        context.user_data['shared_in_additional'] = True
        await shared_return_to_album(update, context, album_id)
        return True
    
    if user_input == correct_name:
        db.delete_album(album_id)
        
        context.user_data.pop('shared_awaiting_delete_confirm', None)
        context.user_data.pop('shared_deleting_album', None)
        context.user_data.pop('shared_album_name_to_delete', None)
        context.user_data['shared_album_active'] = False
        context.user_data.pop('current_shared_album', None)
        
        await update.message.reply_text(
            f"✅ Альбом '{correct_name}' успішно видалено!",
            reply_markup=MAIN_MENU
        )
        return True
    else:
        await update.message.reply_text("❌ Назва не співпадає. Спробуйте ще раз:")
        return True

# ========== ВИХІД З АЛЬБОМУ ==========

async def shared_exit_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вихід зі спільного альбому"""
    if update.message.text == "◀️ Вийти з альбому" and context.user_data.get('shared_album_active'):
        context.user_data['shared_album_active'] = False
        context.user_data.pop('current_shared_album', None)
        context.user_data.pop('shared_access_level', None)
        context.user_data.pop('shared_in_additional', None)
        context.user_data.pop('shared_in_members_main', None)
        context.user_data.pop('shared_in_role_selection', None)
        context.user_data.pop('shared_selecting_member_for_removal', None)
        context.user_data.pop('shared_changing_role_for', None)
        context.user_data.pop('shared_removing_member', None)
        
        await update.message.reply_text(
            "Ви вийшли зі спільного альбому",
            reply_markup=MAIN_MENU
        )
        return True
    return False

# ========== ДОДАВАННЯ ФАЙЛІВ ==========

async def shared_handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник отримання файлів для спільного альбому"""
    if not context.user_data.get('shared_album_active'):
        return False
    
    album_id = context.user_data.get('current_shared_album')
    user_id = update.effective_user.id
    
    access = db.cursor.execute(
        "SELECT access_level FROM shared_albums WHERE album_id = ? AND user_id = ?",
        (album_id, user_id)
    ).fetchone()
    
    if not access or access['access_level'] not in ['owner', 'admin', 'editor', 'contributor']:
        await update.message.reply_text("❌ У вас немає прав на додавання файлів.")
        return True
    
    file_id = None
    file_type = None
    file_name = None
    file_size = None
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = 'photo'
        file_size = update.message.photo[-1].file_size
    elif update.message.video:
        file_id = update.message.video.file_id
        file_type = 'video'
        file_name = update.message.video.file_name
        file_size = update.message.video.file_size
    elif update.message.document:
        file_id = update.message.document.file_id
        file_type = 'document'
        file_name = update.message.document.file_name
        file_size = update.message.document.file_size
    else:
        return False
    
    db.add_file(album_id, file_id, file_type, file_name, file_size, user_id)
    
    settings = helpers.get_user_display_settings(db, user_id)
    
    confirm = "✅ Файл збережено!"
    if settings.get('show_number'):
        total = db.cursor.execute(
            "SELECT COUNT(*) FROM files WHERE album_id = ?",
            (album_id,)
        ).fetchone()[0]
        confirm += f" (файл #{total})"
    
    await update.message.reply_text(confirm)
    return True