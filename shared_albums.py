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
    
    # Отримуємо альбоми, де користувач є власником (але не спільні)
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
    
    keyboard.append([InlineKeyboardButton("➕ Створити спільний альбом", callback_data="shared_create")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
    
    await update.message.reply_text(
        text or "👥 У вас немає спільних альбомів.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== СТВОРЕННЯ СПІЛЬНОГО АЛЬБОМУ ==========

async def shared_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок створення спільного альбому"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['shared_awaiting_name'] = True
    await query.edit_message_text(
        "📝 Введіть назву для нового спільного альбому:"
    )

async def shared_handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення назви спільного альбому"""
    if not context.user_data.get('shared_awaiting_name'):
        return False
    
    album_name = update.message.text
    user_id = update.effective_user.id
    
    if len(album_name) > 50 or len(album_name) < 2:
        await update.message.reply_text("❌ Назва має бути від 2 до 50 символів")
        return True
    
    # Створюємо альбом
    album_id = db.create_album(user_id, album_name)
    
    # Позначаємо як спільний
    db.cursor.execute(
        "UPDATE albums SET is_shared = 1 WHERE album_id = ?",
        (album_id,)
    )
    
    # Додаємо власника як учасника з повними правами
    db.cursor.execute('''
        INSERT INTO shared_albums (album_id, user_id, access_level, added_at)
        VALUES (?, ?, 'owner', CURRENT_TIMESTAMP)
    ''', (album_id, user_id))
    
    db.conn.commit()
    
    context.user_data['shared_awaiting_name'] = False
    context.user_data['current_shared_album'] = album_id
    
    await update.message.reply_text(
        f"✅ Спільний альбом '{album_name}' створено!\n\n"
        f"Тепер ви можете додавати учасників та налаштовувати права доступу.",
        reply_markup=await shared_album_keyboard(album_id, user_id)
    )
    return True

# ========== КЛАВІАТУРА СПІЛЬНОГО АЛЬБОМУ ==========

async def shared_album_keyboard(album_id, user_id):
    """Створити клавіатуру для спільного альбому з урахуванням прав"""
    role = db.cursor.execute(
        "SELECT access_level FROM shared_albums WHERE album_id = ? AND user_id = ?",
        (album_id, user_id)
    ).fetchone()
    
    access_level = role['access_level'] if role else None
    
    buttons = [
        [KeyboardButton("📤 Надіслати весь альбом")],
        [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
        [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")]
    ]
    
    # Додаткові кнопки залежно від прав
    additional = []
    if access_level in ['owner', 'admin', 'editor']:
        additional.append(KeyboardButton("👥 Учасники"))
    if access_level in ['owner', 'admin', 'editor', 'contributor']:
        additional.append(KeyboardButton("➕ Додати файли"))
    if access_level in ['owner', 'admin']:
        additional.append(KeyboardButton("⚙️ Налаштування альбому"))
    
    if additional:
        buttons.append(additional)
    
    buttons.append([KeyboardButton("⋯ Додаткові дії")])
    buttons.append([KeyboardButton("◀️ Вийти з альбому")])
    
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ========== ВІДКРИТТЯ СПІЛЬНОГО АЛЬБОМУ ==========

async def shared_open_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Відкриття спільного альбому"""
    query = update.callback_query
    await query.answer()
    
    album_id = int(query.data.split('_')[2])
    user_id = query.from_user.id
    
    # Перевіряємо права доступу
    access = db.cursor.execute(
        "SELECT access_level FROM shared_albums WHERE album_id = ? AND user_id = ?",
        (album_id, user_id)
    ).fetchone()
    
    if not access:
        await query.edit_message_text("❌ У вас немає доступу до цього альбому.")
        return
    
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
    
    await query.edit_message_text(text, parse_mode='Markdown')
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="👥 Спільний альбом",
        reply_markup=await shared_album_keyboard(album_id, user_id)
    )

# ========== УПРАВЛІННЯ УЧАСНИКАМИ ==========

async def shared_manage_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управління учасниками"""
    query = update.callback_query
    await query.answer()
    
    album_id = context.user_data.get('current_shared_album')
    if not album_id:
        return
    
    # Отримуємо список учасників
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
    
    text = "👥 **Учасники альбому**\n\n"
    keyboard = []
    
    for member in members:
        role_emoji = {
            'owner': '👑', 'admin': '⚙️', 'editor': '✏️',
            'contributor': '📤', 'viewer': '👁️'
        }.get(member['access_level'], '👤')
        
        name = member['first_name'] or member['username'] or f"ID:{member['user_id']}"
        added = helpers.format_date(member['added_at']).split()[0]
        
        text += f"{role_emoji} **{name}** — *{helpers.get_role_name(member['access_level'])}*\n"
        text += f"└ Доданий: {added}\n\n"
        
        if context.user_data.get('shared_access_level') in ['owner', 'admin']:
            if member['access_level'] != 'owner':  # Не можна змінювати власника
                keyboard.append([InlineKeyboardButton(
                    f"Змінити роль: {name}",
                    callback_data=f"shared_role_{member['user_id']}"
                )])
    
    keyboard.append([InlineKeyboardButton("➕ Додати учасника", callback_data="shared_add_member")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="shared_back_to_album")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ========== ДОДАВАННЯ УЧАСНИКА ==========

async def shared_add_member_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок додавання учасника"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['shared_awaiting_member'] = True
    await query.edit_message_text(
        "👤 Введіть username користувача (наприклад: @username)\n\n"
        "Або натисніть кнопку нижче, щоб вибрати з контактів:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📱 З контактів", callback_data="shared_choose_contact")
        ], [
            InlineKeyboardButton("◀️ Назад", callback_data="shared_manage_members")
        ]])
    )

async def shared_handle_member_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення username учасника"""
    if not context.user_data.get('shared_awaiting_member'):
        return False
    
    username = update.message.text.strip()
    if username.startswith('@'):
        username = username[1:]
    
    # Шукаємо користувача в БД
    user = db.cursor.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    
    if not user:
        await update.message.reply_text(
            "❌ Користувача не знайдено. Можливо, він ще не користувався ботом.\n"
            "Спробуйте інший username або поділіться з ним посиланням на бота."
        )
        return True
    
    album_id = context.user_data.get('current_shared_album')
    
    # Перевіряємо, чи вже є учасником
    exists = db.cursor.execute(
        "SELECT * FROM shared_albums WHERE album_id = ? AND user_id = ?",
        (album_id, user['user_id'])
    ).fetchone()
    
    if exists:
        await update.message.reply_text("❌ Цей користувач вже є учасником альбому.")
        return True
    
    # Додаємо з роллю 'viewer' за замовчуванням
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
    
    # Показуємо оновлений список учасників
    fake_update = update
    fake_update.callback_query = type('obj', (object,), {
        'data': 'shared_manage_members',
        'answer': lambda: None,
        'edit_message_text': lambda text, reply_markup=None, parse_mode=None: None,
        'message': update.message
    })
    await shared_manage_members(fake_update, context)
    return True

# ========== УПРАВЛІННЯ РОЛЯМИ ==========

async def shared_manage_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управління ролями"""
    query = update.callback_query
    await query.answer()
    
    target_user_id = int(query.data.split('_')[2])
    album_id = context.user_data.get('current_shared_album')
    
    # Отримуємо інформацію про користувача
    user = db.cursor.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (target_user_id,)
    ).fetchone()
    
    current_role = db.cursor.execute(
        "SELECT access_level FROM shared_albums WHERE album_id = ? AND user_id = ?",
        (album_id, target_user_id)
    ).fetchone()
    
    name = user['first_name'] or user['username'] or f"ID:{target_user_id}"
    
    text = (
        f"👤 **{name}**\n"
        f"Поточна роль: **{helpers.get_role_name(current_role['access_level'])}**\n\n"
        f"Оберіть нову роль:"
    )
    
    keyboard = [
        [InlineKeyboardButton("👑 Власник (повний доступ)", callback_data=f"shared_set_role_{target_user_id}_owner")],
        [InlineKeyboardButton("⚙️ Адмін (керування + редагування)", callback_data=f"shared_set_role_{target_user_id}_admin")],
        [InlineKeyboardButton("✏️ Редактор (редагування + додавання)", callback_data=f"shared_set_role_{target_user_id}_editor")],
        [InlineKeyboardButton("📤 Автор (додавання + перегляд)", callback_data=f"shared_set_role_{target_user_id}_contributor")],
        [InlineKeyboardButton("👁️ Спостерігач (тільки перегляд)", callback_data=f"shared_set_role_{target_user_id}_viewer")],
        [InlineKeyboardButton("◀️ Назад", callback_data="shared_manage_members")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def shared_set_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Встановлення ролі для учасника"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    target_user_id = int(parts[3])
    new_role = parts[4]
    album_id = context.user_data.get('current_shared_album')
    
    # Оновлюємо роль
    db.cursor.execute('''
        UPDATE shared_albums 
        SET access_level = ? 
        WHERE album_id = ? AND user_id = ?
    ''', (new_role, album_id, target_user_id))
    db.conn.commit()
    
    await query.edit_message_text(
        f"✅ Роль успішно змінено!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👥 До списку учасників", callback_data="shared_manage_members")
        ]])
    )

# ========== НАЛАШТУВАННЯ ВІДОБРАЖЕННЯ ==========

async def shared_display_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати меню налаштувань відображення для спільних альбомів"""
    query = update.callback_query
    user_id = query.from_user.id
    
    settings = helpers.get_user_display_settings(db, user_id)
    
    num_btn = "✅ Відображати номер файлу" if settings.get('show_number', True) else "❌ Не відображати номер"
    date_btn = "✅ Відображати дату додавання" if settings.get('show_date', True) else "❌ Не відображати дату"
    
    keyboard = [
        [InlineKeyboardButton(num_btn, callback_data="shared_toggle_number")],
        [InlineKeyboardButton(date_btn, callback_data="shared_toggle_date")],
        [InlineKeyboardButton("◀️ Назад", callback_data="shared_back_to_album")]
    ]
    
    await query.edit_message_text(
        "👁 **Налаштування відображення**\n\n"
        "Оберіть, яку інформацію додавати до файлів під час перегляду в спільних альбомах:\n"
        "*(ці налаштування індивідуальні для вашого облікового запису)*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def shared_toggle_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перемикання відображення номера файлу"""
    query = update.callback_query
    user_id = query.from_user.id
    
    settings = helpers.get_user_display_settings(db, user_id)
    settings['show_number'] = not settings.get('show_number', True)
    helpers.save_user_display_settings(db, user_id, settings)
    
    await shared_display_settings(update, context)

async def shared_toggle_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перемикання відображення дати додавання"""
    query = update.callback_query
    user_id = query.from_user.id
    
    settings = helpers.get_user_display_settings(db, user_id)
    settings['show_date'] = not settings.get('show_date', True)
    helpers.save_user_display_settings(db, user_id, settings)
    
    await shared_display_settings(update, context)

# ========== ДОДАТКОВІ ДІЇ В СПІЛЬНОМУ АЛЬБОМІ ==========

async def shared_additional_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Додаткове меню для спільного альбому"""
    text = update.message.text
    album_id = context.user_data.get('current_shared_album')
    user_id = update.effective_user.id
    
    if text == "👥 Учасники":
        # Показуємо список учасників
        keyboard = [[InlineKeyboardButton("👥 Керувати учасниками", callback_data="shared_manage_members")]]
        await update.message.reply_text(
            "👥 Управління учасниками",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True
    
    elif text == "⚙️ Налаштування альбому":
        # Налаштування альбому (назва, архівація тощо)
        keyboard = [
            [InlineKeyboardButton("👁 Налаштування відображення", callback_data="shared_display_settings")],
            [InlineKeyboardButton("🗂 Архівувати альбом", callback_data="shared_archive")]
        ]
        await update.message.reply_text(
            "⚙️ Налаштування спільного альбому",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True
    
    return False

# ========== ДОДАВАННЯ ФАЙЛІВ У СПІЛЬНИЙ АЛЬБОМ ==========

async def shared_handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник отримання файлів для спільного альбому"""
    if not context.user_data.get('shared_album_active'):
        return False
    
    album_id = context.user_data.get('current_shared_album')
    user_id = update.effective_user.id
    
    # Перевіряємо права на додавання файлів
    access = db.cursor.execute(
        "SELECT access_level FROM shared_albums WHERE album_id = ? AND user_id = ?",
        (album_id, user_id)
    ).fetchone()
    
    if not access or access['access_level'] not in ['owner', 'admin', 'editor', 'contributor']:
        await update.message.reply_text("❌ У вас немає прав на додавання файлів.")
        return True
    
    # Визначаємо тип файлу
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
    
    # Зберігаємо файл
    db.add_file(album_id, file_id, file_type, file_name, file_size, user_id)
    
    # Отримуємо налаштування відображення
    settings = helpers.get_user_display_settings(db, user_id)
    
    # Формуємо підтвердження з урахуванням налаштувань
    confirm = "✅ Файл збережено!"
    if settings.get('show_number'):
        total = db.cursor.execute(
            "SELECT COUNT(*) FROM files WHERE album_id = ?",
            (album_id,)
        ).fetchone()[0]
        confirm += f" (файл #{total})"
    
    await update.message.reply_text(confirm)
    return True