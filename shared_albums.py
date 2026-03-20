from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from db_models import Database
import helpers
from telegram import ReplyKeyboardRemove

db = Database()

# ========== ГОЛОВНЕ МЕНЮ СПІЛЬНИХ АЛЬБОМІВ ==========

async def shared_albums_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Головне меню спільних альбомів — ТІЛЬКИ СПІЛЬНІ"""
    user_id = update.effective_user.id
    
    # Отримуємо ТІЛЬКИ ті альбоми, які позначені як спільні (is_shared = 1)
    shared_albums = db.cursor.execute("""
        SELECT a.*, sa.access_level, u.username as owner_name 
        FROM albums a 
        JOIN shared_albums sa ON a.album_id = sa.album_id 
        JOIN users u ON a.user_id = u.user_id
        WHERE sa.user_id = ? 
        AND a.is_shared = 1  -- ФІЛЬТР: Тільки спільні
        AND a.is_archived = 0
        ORDER BY a.created_at DESC
    """, (user_id,)).fetchall()
    
    text = "👥 **Спільні альбоми**\n\n"
    keyboard = []
    
    if shared_albums:
        text += "Альбоми, де ви учасник:\n"
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
    else:
        text += "У вас немає спільних альбомів.\n"
    
    keyboard.append([InlineKeyboardButton("➕ Створити новий спільний", callback_data="shared_create")])
    
    # Видаляємо старі повідомлення для чистоти інтерфейсу
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ========== СТВОРЕННЯ СПІЛЬНОГО АЛЬБОМУ ==========

async def shared_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок створення спільного альбому"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    from helpers import check_user_limit
    # преміум меню відкриваємо через inline-кнопку

    # Ліміт на спільні альбоми: максимум 3, якщо немає Premium
    if not check_user_limit(db, user_id, 'shared_albums'):
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("💎 Отримати Premium", callback_data="premium_info")]]
        )
        await query.edit_message_text(
            "❌ Ліміт безкоштовних спільних альбомів досягнуто (3).\n\n"
            "Щоб зняти обмеження — потрібно отримати Premium.",
            reply_markup=keyboard,
        )
        return

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
    
    # Створюємо альбом
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
    
    # Очищаємо стани
    context.user_data['shared_awaiting_name'] = False
    context.user_data['shared_creating'] = False
    
    # ВАЖЛИВО: Спочатку очищаємо звичайний альбом
    context.user_data['album_keyboard_active'] = False
    context.user_data.pop('current_album', None)
    
    # Встановлюємо активний спільний альбом
    context.user_data['current_shared_album'] = album_id
    context.user_data['shared_album_active'] = True
    context.user_data['shared_access_level'] = 'owner'
    
    album = db.get_album(album_id)
    
    # Клавіатура для спільного альбому
    album_keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📤 Надіслати весь альбом")],
        [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
        [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
        [KeyboardButton("⋯ Додаткові опції")],
        [KeyboardButton("◀️ Вийти з альбому")]
    ], resize_keyboard=True)
    
    # Відправляємо повідомлення
    await update.message.reply_text(
        f"✅ Спільний альбом '{album_name}' створено!\n\n"
        f"👥 **{album_name}**\n"
        f"└ Файлів: 0\n"
        f"└ Ваша роль: Власник 👑\n\n"
        f"Надсилайте файли в цей чат, вони автоматично збережуться в альбом.",
        reply_markup=album_keyboard,
        parse_mode='Markdown'
    )
    
    # Лог для перевірки
    print(f"✅ Спільний альбом створено, active={context.user_data.get('shared_album_active')}")

    # ВАЖЛИВО: Очищаємо стан звичайного альбому, якщо він був активний
    context.user_data['album_keyboard_active'] = False
    context.user_data.pop('current_album', None)
    
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
    album_id = context.user_data.get('current_shared_album')
    access_level = context.user_data.get('shared_access_level')
    
    # ВИПРАВЛЕНО ТУТ: додаємо перевірку кнопки "Назад"
    if text == "⋯ Додаткові опції" or text == "◀️ Назад до додаткових опцій":
        context.user_data['shared_in_additional'] = True
        
        # Створюємо клавіатуру (це те саме меню, що й було)
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
            additional_buttons.append([KeyboardButton("📷 Перенести до моїх альбомів")])
        
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
            await shared_start_delete_menu (update, context, album_id)
            return True
        elif text == "🗂 Архівувати альбом" and access_level in ['owner', 'admin']:
            await shared_archive_confirm(update, context, album_id)
            return True
        elif text == "🗑 Видалити альбом" and access_level == 'owner':
            await shared_delete_confirm(update, context, album_id)
            return True
        elif text == "📷 Перенести до моїх альбомів" and access_level == 'owner':
            ok, reason = db.make_album_personal_if_solo(album_id, update.effective_user.id)
            if ok:
                # Закриваємо спільний режим і повертаємось до списку спільних (альбом зникне звідти)
                context.user_data['shared_album_active'] = False
                context.user_data.pop('current_shared_album', None)
                context.user_data.pop('shared_access_level', None)
                context.user_data.pop('shared_in_additional', None)
                context.user_data.pop('shared_in_delete_menu', None)
                context.user_data.pop('shared_delete_album_id', None)

                await update.message.reply_text(
                    "✅ Альбом перенесено до **моїх альбомів**.",
                    reply_markup=ReplyKeyboardRemove(),
                    parse_mode='Markdown'
                )
                from main import show_my_albums
                await show_my_albums(update, context)
                return True

            if reason == "has_members":
                await update.message.reply_text(
                    "❌ Вибачте, але перенести альбом не можна, бо в ньому є ще учасники.\n"
                    "Спочатку видаліть їх і повторіть дію."
                )
                return True
            if reason == "not_owner":
                await update.message.reply_text("❌ Тільки власник може перенести альбом до звичайних.")
                return True
            if reason == "not_found":
                await update.message.reply_text("❌ Альбом не знайдено.")
                return True

            await update.message.reply_text("❌ Не вдалося перенести альбом (помилка бази даних).")
            return True
        elif context.user_data.get('shared_in_additional'):
        # ПЕРЕВІР ТУТ НАЗВУ КНОПКИ
            if text == "◀️ Назад до альбому":
                context.user_data['shared_in_additional'] = False
                await shared_return_to_album(update, context, album_id)
                return True
    
    return False

async def handle_shared_delete_choices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вибір режиму видалення в меню спільного альбому"""
    text = update.message.text
    ud = context.user_data
    album_id = ud.get('shared_delete_album_id')
    
    if not ud.get('shared_in_delete_menu') or not album_id:
        return False

    if text == "Видалити: Весь альбом":
        files = db.get_album_files(album_id)
        await update.message.reply_text(f"📤 Надсилаю {len(files)} файлів для видалення...")
        for idx, file in enumerate(files, 1):
            # Перетворюємо sqlite3.Row у словник
            file_dict = dict(file)
            await send_shared_file_for_deletion(update, context, file_dict, index=idx)
        return True

    elif text == "Видалити: Останні":
        ud['shared_del_awaiting_recent'] = True
        await update.message.reply_text("⏳ Скільки останніх файлів надіслати для видалення?")
        return True

    elif text == "Видалити: Перші":
        ud['shared_del_awaiting_first'] = True
        await update.message.reply_text("⏮ Скільки перших файлів надіслати для видалення?")
        return True

    elif text == "Видалити: Проміжок":
        ud['shared_del_awaiting_range'] = True
        await update.message.reply_text("🔢 Введіть проміжок для видалення (наприклад: 1-10):")
        return True

    elif text == "Видалити: За датою":
        ud['shared_del_awaiting_date'] = True
        await update.message.reply_text("📅 Введіть дату (РРРР-ММ-ДД):")
        return True

    return False

async def shared_handle_del_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник цифрового вводу для видалення в спільному альбомі"""
    ud = context.user_data
    text = update.message.text
    album_id = ud.get('shared_delete_album_id')
    
    if not album_id: 
        return False
        
    all_files = db.get_album_files(album_id)
    # Перетворюємо в список словників
    all_files = [dict(f) for f in all_files]

    try:
        # 1. Останні
        if ud.get('shared_del_awaiting_recent'):
            count = int(text)
            selected = list(enumerate(all_files, 1))[-count:]
            await update.message.reply_text(f"📤 Надсилаю останні {len(selected)} файлів...")
            for idx, f in selected: 
                await send_shared_file_for_deletion(update, context, f, idx)
            ud['shared_del_awaiting_recent'] = False
            return True

        # 2. Перші
        if ud.get('shared_del_awaiting_first'):
            count = int(text)
            selected = list(enumerate(all_files, 1))[:count]
            await update.message.reply_text(f"📤 Надсилаю перші {len(selected)} файлів...")
            for idx, f in selected: 
                await send_shared_file_for_deletion(update, context, f, idx)
            ud['shared_del_awaiting_first'] = False
            return True

        # 3. Проміжок
        if ud.get('shared_del_awaiting_range'):
            start, end = map(int, text.split('-'))
            selected = all_files[start-1:end]
            await update.message.reply_text(f"📤 Надсилаю файли з {start} по {end}...")
            for i, f in enumerate(selected): 
                await send_shared_file_for_deletion(update, context, f, start+i)
            ud['shared_del_awaiting_range'] = False
            return True
            
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка формату: {e}")
        return True

    return False

async def shared_handle_del_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник цифрового вводу для видалення (спільні альбоми)"""
    ud = context.user_data
    text = update.message.text
    album_id = ud.get('shared_delete_album_id')
    
    print(f"🔍 [shared_handle_del_inputs] text={text}, album_id={album_id}")
    
    if not album_id: 
        return False
        
    all_files = db.get_album_files(album_id)
    print(f"🔍 Всього файлів в альбомі: {len(all_files)}")

    try:
        # 1. Останні
        if ud.get('shared_del_awaiting_recent'):
            count = int(text)
            print(f"🔍 Вибрано останні {count} файлів")
            selected = list(enumerate(all_files, 1))[-count:]
            await update.message.reply_text(f"📤 Надсилаю останні {len(selected)} файлів...")
            for idx, f in selected: 
                await send_shared_file_for_deletion(update, context, f, idx)
            ud['shared_del_awaiting_recent'] = False
            return True

        # 2. Перші
        if ud.get('shared_del_awaiting_first'):
            count = int(text)
            print(f"🔍 Вибрано перші {count} файлів")
            selected = list(enumerate(all_files, 1))[:count]
            await update.message.reply_text(f"📤 Надсилаю перші {len(selected)} файлів...")
            for idx, f in selected: 
                await send_shared_file_for_deletion(update, context, f, idx)
            ud['shared_del_awaiting_first'] = False
            return True

        # 3. Проміжок
        if ud.get('shared_del_awaiting_range'):
            start, end = map(int, text.split('-'))
            print(f"🔍 Вибрано проміжок {start}-{end}")
            selected = all_files[start-1:end]
            await update.message.reply_text(f"📤 Надсилаю файли з {start} по {end}...")
            for i, f in enumerate(selected): 
                await send_shared_file_for_deletion(update, context, f, start+i)
            ud['shared_del_awaiting_range'] = False
            return True
            
    except Exception as e:
        print(f"❌ Помилка формату: {e}")
        await update.message.reply_text(f"❌ Помилка формату: {e}")
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
            [KeyboardButton("◀️ Назад до додаткових опцій")]
        ], resize_keyboard=True)
    )


async def shared_handle_member_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення username учасника"""

    text = (update.message.text or "").strip()
    ud = context.user_data

    # 🔹 КНОПКА СКАСУВАТИ (ПЕРЕВІРЯЄМО ПЕРШОЮ)
    if text == "❌ Скасувати":
        if ud.get('shared_awaiting_member'):
            ud['shared_awaiting_member'] = False

            album_id = ud.get('current_shared_album')
            access_level = ud.get('shared_access_level', 'contributor')

            await update.message.reply_text("🚫 Додавання скасовано.")

            if album_id:
                await shared_members_main(update, context, album_id, access_level)

            return True

        return False


    # 🔹 ЯКЩО БОТ НЕ ЧЕКАЄ USERNAME
    if not ud.get('shared_awaiting_member'):
        return False


    # 🔹 ОБРОБКА USERNAME
    username = text
    if username.startswith('@'):
        username = username[1:]

    # якщо юзер натиснув іншу кнопку
    if len(username.split()) > 1:
        ud['shared_awaiting_member'] = False
        return False


    user = db.cursor.execute(
        "SELECT * FROM users WHERE username = ?", 
        (username,)
    ).fetchone()

    if not user:
        await update.message.reply_text(
            "❌ Користувача не знайдено. Спробуйте інший @username або натисніть «Скасувати»."
        )
        return True


    album_id = ud.get('current_shared_album')

    exists = db.cursor.execute(
        "SELECT * FROM shared_albums WHERE album_id = ? AND user_id = ?",
        (album_id, user['user_id'])
    ).fetchone()

    if exists:
        await update.message.reply_text("❌ Цей користувач вже є учасником.")
        return True


    # 🔹 ДОДАЄМО В БАЗУ
    db.cursor.execute(
        '''
        INSERT INTO shared_albums (album_id, user_id, access_level, added_at)
        VALUES (?, ?, 'viewer', CURRENT_TIMESTAMP)
        ''',
        (album_id, user['user_id'])
    )
    db.conn.commit()

    ud['shared_awaiting_member'] = False

    await update.message.reply_text(f"✅ Користувача @{username} додано (Спостерігач)")

    await shared_members_main(update, context, album_id, ud.get('shared_access_level'))

    return True
# ========== ЗМІНА РОЛЕЙ ==========
async def shared_manage_roles(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Меню керування ролями (Кнопку 'Назад' видалено)"""
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
    
    # Формуємо інлайн клавіатуру тільки з учасниками
    keyboard = []
    for member in members:
        name = member['first_name'] or member['username'] or f"ID:{member['user_id']}"
        role_name = helpers.get_role_name(member['access_level'])
        button_text = f"{name} — {role_name}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"shared_role_{member['user_id']}")])
    
    # Кнопку "Назад" тут видалено
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['shared_in_role_selection'] = True

async def shared_handle_role_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник текстового введення для зміни ролі (З ПЕРЕВІРКОЮ НА КНОПКИ)"""
    if not context.user_data.get('shared_in_role_selection'):
        return False
    
    text = update.message.text.strip()

    # --- ГЛОБАЛЬНИЙ ЗАПОБІЖНИК ---
    # Список ВСІХ кнопок, які мають вимикати цей режим
    SYSTEM_BUTTONS = [
        "👥 Учасники", "ℹ️ Інформація", "🗑 Видалити файл", 
        "🗂 Архівувати альбом", "🗑 Видалити альбом", 
        "◀️ Назад до альбому", "◀️ Назад до додаткових опцій",
        "📤 Надіслати весь альбом", "📷 Перенести до моїх альбомів",
        "◀️ Вийти з альбому"
    ]
    
    # Якщо текст — це кнопка або починається зі стрілки
    if text in SYSTEM_BUTTONS or text.startswith("◀️"):
        context.user_data['shared_in_role_selection'] = False
        return False # Повертаємо False, щоб текст пішов далі в навігатор
    # -----------------------------

    album_id = context.user_data.get('current_shared_album')
    # ... далі твій код пошуку юзера ...
    
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
        await update.message.reply_text("❌ Учасника не знайдено. Спробуйте ще раз або натисніть «Назад».")
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
        [InlineKeyboardButton("👁️ Спостерігач (тільки перегляд)", callback_data=f"shared_set_role_{target_user_id}_viewer")]
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


# === ДОДАЙ ЦЕ ОДРАЗУ ПІСЛЯ ФУНКЦІЇ shared_show_role_options ===

async def handle_shared_role_back_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логіка кнопки 'Назад' у меню вибору ролей"""
    query = update.callback_query
    # 1. Підтверджуємо Telegram, що ми прийняли натискання
    await query.answer()
    
    # 2. Перевіряємо, чи це саме наша кнопка
    if query.data == "shared_back_to_role_selection":
        # 3. Дістаємо ID альбому з пам'яті
        album_id = context.user_data.get('current_shared_album')
        
        # 4. Скидаємо вибір юзера
        context.user_data.pop('shared_changing_role_for', None)
        
        # 5. Повертаємось до списку учасників (викликаємо сусідню функцію)
        if album_id:
            await shared_manage_roles(update, context, album_id)
        return True
    
    return False


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
    album_id = context.user_data.get('current_shared_album')
    text = update.message.text
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
            additional_buttons.append([KeyboardButton("📷 Перенести до моїх альбомів")])
        
        additional_buttons.append([KeyboardButton("◀️ Назад до альбому")])
        
        await update.message.reply_text(
            f"📋 **Додаткові опції**\n\nОберіть потрібну дію:",
            reply_markup=ReplyKeyboardMarkup(additional_buttons, resize_keyboard=True),
            parse_mode='Markdown'
        )
        return True
    

    return False

async def shared_handle_all_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Універсальний обробник для всіх кнопок спільного альбому"""
    text = update.message.text
    ud = context.user_data
    
    if not ud.get('shared_album_active'):
        return False
    
    album_id = ud.get('current_shared_album')
    
    print(f"🔵 [shared_handle_all_buttons] Обробка: '{text}'")
    print(f"🔵 Стан: in_delete_menu={ud.get('shared_in_delete_menu')}")
    
    # --- 1. СПЕЦІАЛЬНІ РЕЖИМИ (ВВІД ЧИСЕЛ/ДАТ) ---
    if ud.get('shared_awaiting_recent_count') or ud.get('shared_awaiting_first_count') or \
       ud.get('shared_awaiting_range') or ud.get('shared_awaiting_date'):
        # Ці обробники вже є окремо
        return False
    
    # --- 2. КНОПКИ НАВІГАЦІЇ ТА МЕНЮ (НАЙВИЩИЙ ПРІОРИТЕТ) ---
    if text == "◀️ Назад до альбому":
        ud['shared_in_delete_menu'] = False
        ud['shared_in_additional'] = False
        await shared_return_to_album(update, context, album_id)
        return True
        
    if text == "◀️ Назад до додаткових опцій":
        ud['shared_in_delete_menu'] = False
        ud['shared_in_additional'] = True
        # Показуємо додаткове меню
        access_level = ud.get('shared_access_level')
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
            additional_buttons.append([KeyboardButton("📷 Перенести до моїх альбомів")])
        additional_buttons.append([KeyboardButton("◀️ Назад до альбому")])
        
        await update.message.reply_text(
            f"📋 **Додаткові опції**\n\nОберіть потрібну дію:",
            reply_markup=ReplyKeyboardMarkup(additional_buttons, resize_keyboard=True),
            parse_mode='Markdown'
        )
        return True
    
    if text == "◀️ Вийти з альбому":
        return await shared_exit_album(update, context)
    
    # --- 3. КНОПКИ МЕНЮ ВИДАЛЕННЯ ---
    if text.startswith("Надіслати:"):
        if await handle_shared_delete_choices(update, context):
            return True
    
    # --- 4. ІНШІ КНОПКИ (ОСНОВНІ ТА ДОДАТКОВІ) ---
    # Не блокуємо основні кнопки, навіть якщо shared_in_delete_menu=True.
    
    # --- 5. ОСНОВНІ КНОПКИ АЛЬБОМУ ---
    if "Надіслати весь альбом" in text:
        return await shared_send_all(update, context, album_id)
    elif "Надіслати останні" in text:
        return await shared_send_recent_start(update, context, album_id)
    elif "Надіслати перші" in text:
        return await shared_send_first_start(update, context, album_id)
    elif "Надіслати проміжок" in text:
        return await shared_send_range_start(update, context, album_id)
    elif "Надіслати за датою" in text:
        return await shared_send_by_date_start(update, context, album_id)
    elif "⋯ Додаткові опції" in text:
        ud['shared_in_additional'] = True
        return await shared_additional_menu(update, context)
    
    # --- 6. ДОДАТКОВЕ МЕНЮ ---
    if ud.get('shared_in_additional'):
        if text == "👥 Учасники":
            await shared_members_main(update, context, album_id, ud.get('shared_access_level'))
            return True
        elif text == "ℹ️ Інформація":
            await shared_album_info(update, context, album_id)
            return True
        elif text == "🗑 Видалити файл":
            await shared_start_delete_menu(update, context, album_id)
            return True
        elif text == "🗂 Архівувати альбом":
            await shared_archive_confirm(update, context, album_id)
            return True
        elif text == "🗑 Видалити альбом":
            await shared_delete_confirm(update, context, album_id)
            return True
        elif text == "📷 Перенести до моїх альбомів":
            access_level = ud.get('shared_access_level')
            if access_level != 'owner':
                await update.message.reply_text("❌ Тільки власник може перенести альбом до звичайних.")
                return True

            ok, reason = db.make_album_personal_if_solo(album_id, update.effective_user.id)
            if ok:
                ud['shared_album_active'] = False
                ud.pop('current_shared_album', None)
                ud.pop('shared_access_level', None)
                ud.pop('shared_in_additional', None)
                ud.pop('shared_in_delete_menu', None)
                ud.pop('shared_delete_album_id', None)

                await update.message.reply_text(
                    "✅ Альбом перенесено до **моїх альбомів**.",
                    reply_markup=ReplyKeyboardRemove(),
                    parse_mode='Markdown'
                )
                from main import show_my_albums
                await show_my_albums(update, context)
                return True

            if reason == "has_members":
                await update.message.reply_text(
                    "❌ Вибачте, але перенести альбом не можна, бо в ньому є ще учасники.\n"
                    "Спочатку видаліть їх і повторіть дію."
                )
                return True
            if reason == "not_owner":
                await update.message.reply_text("❌ Тільки власник може перенести альбом до звичайних.")
                return True
            if reason == "not_found":
                await update.message.reply_text("❌ Альбом не знайдено.")
                return True

            await update.message.reply_text("❌ Не вдалося перенести альбом (помилка бази даних).")
            return True
    
    return False

# ========== ВИДАЛЕННЯ ФАЙЛУ ==========

async def shared_start_delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Запуск меню видалення файлів для спільного альбому з префіксом 'Видалити:'"""
    files = db.get_album_files(album_id)
    total_files = len(files)
    
    text = (
        f"🗑 **Меню видалення файлів (Спільний альбом)**\n\n"
        f"Оберіть, які файли надіслати для видалення (біля кожного файлу буде кнопка 🗑):\n"
        f"Всього в альбомі: {total_files}"
    )
    
    # Використовуємо префікс "Надіслати:", щоб відрізнити від звичайного меню
    delete_keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("Надіслати: Весь альбом")],
        [KeyboardButton("Надіслати: Останні"), KeyboardButton("Надіслати: Перші")],
        [KeyboardButton("Надіслати: Проміжок")],
        [KeyboardButton("Надіслати: За датою")],
        [KeyboardButton("◀️ Назад до альбому")]
    ], resize_keyboard=True)
    
    context.user_data['shared_in_delete_menu'] = True
    context.user_data['shared_delete_album_id'] = album_id
    # Вимикаємо стани звичайного перегляду, щоб не заважали
    context.user_data['shared_awaiting_recent_count'] = False
    context.user_data['shared_awaiting_first_count'] = False
    context.user_data['shared_awaiting_range'] = False
    context.user_data['shared_awaiting_date'] = False
    
    await update.message.reply_text(
        text,
        reply_markup=delete_keyboard,
        parse_mode='Markdown'
    )

async def handle_shared_delete_choices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вибір режиму видалення в меню спільного альбому"""
    text = update.message.text
    ud = context.user_data
    album_id = ud.get('shared_delete_album_id')
    
    if not ud.get('shared_in_delete_menu') or not album_id:
        return False

    if text == "Надіслати: Весь альбом":
        files = db.get_album_files(album_id)
        await update.message.reply_text(f"📤 Надсилаю {len(files)} файлів для видалення...")
        for idx, file in enumerate(files, 1):
            # Перетворюємо sqlite3.Row у словник
            file_dict = dict(file)
            await send_shared_file_for_deletion(update, context, file_dict, index=idx)
        return True

    elif text == "Надіслати: Останні":
        ud['shared_del_awaiting_recent'] = True
        await update.message.reply_text("⏳ Скільки останніх файлів надіслати для видалення?")
        return True

    elif text == "Надіслати: Перші":
        ud['shared_del_awaiting_first'] = True
        await update.message.reply_text("⏮ Скільки перших файлів надіслати для видалення?")
        return True

    elif text == "Надіслати: Проміжок":
        ud['shared_del_awaiting_range'] = True
        await update.message.reply_text("🔢 Введіть проміжок для видалення (наприклад: 1-10):")
        return True

    elif text == "Надіслати: За датою":
        ud['shared_del_awaiting_date'] = True
        await update.message.reply_text("📅 Введіть дату (РРРР-ММ-ДД):")
        return True

    return False

async def shared_handle_del_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник цифрового вводу для видалення в спільному альбомі"""
    ud = context.user_data
    text = update.message.text
    album_id = ud.get('shared_delete_album_id')
    
    if not album_id: 
        return False
        
    all_files = db.get_album_files(album_id)
    # Перетворюємо в список словників
    all_files = [dict(f) for f in all_files]

    try:
        # 1. Останні
        if ud.get('shared_del_awaiting_recent'):
            count = int(text)
            selected = list(enumerate(all_files, 1))[-count:]
            await update.message.reply_text(f"📤 Надсилаю останні {len(selected)} файлів...")
            for idx, f in selected: 
                await send_shared_file_for_deletion(update, context, f, idx)
            ud['shared_del_awaiting_recent'] = False
            return True

        # 2. Перші
        if ud.get('shared_del_awaiting_first'):
            count = int(text)
            selected = list(enumerate(all_files, 1))[:count]
            await update.message.reply_text(f"📤 Надсилаю перші {len(selected)} файлів...")
            for idx, f in selected: 
                await send_shared_file_for_deletion(update, context, f, idx)
            ud['shared_del_awaiting_first'] = False
            return True

        # 3. Проміжок
        if ud.get('shared_del_awaiting_range'):
            start, end = map(int, text.split('-'))
            if start < 1 or end > len(all_files) or start > end:
                await update.message.reply_text(f"❌ Невірний проміжок. Всього файлів: {len(all_files)}")
                return True
            selected = all_files[start-1:end]
            await update.message.reply_text(f"📤 Надсилаю файли з {start} по {end}...")
            for i, f in enumerate(selected): 
                await send_shared_file_for_deletion(update, context, f, start+i)
            ud['shared_del_awaiting_range'] = False
            return True
            
    except ValueError:
        await update.message.reply_text("❌ Введіть число або проміжок у правильному форматі")
        return True
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")
        return True

    return False

async def send_shared_file_for_deletion(update: Update, context: ContextTypes.DEFAULT_TYPE, file_data, index=None):
    """Надсилає файл з кнопкою для видалення"""
    print(f"🔍 [send_shared_file_for_deletion] Початок для файлу #{index}")
    
    # Переконуємося, що file_data - це словник
    try:
        if not isinstance(file_data, dict):
            f = dict(file_data)
        else:
            f = file_data
        print(f"🔍 Дані файлу: {f}")
    except Exception as e:
        print(f"❌ Помилка перетворення file_data: {e}")
        return
    
    # Використовуємо правильні назви полів з бази даних
    file_id_db = f.get('file_id')
    file_id = f.get('telegram_file_id')
    file_type = f.get('file_type')
    album_id = f.get('album_id')
    
    print(f"🔍 file_id_db={file_id_db}, file_id={file_id}, file_type={file_type}, album_id={album_id}")
    
    if not file_id:
        print(f"❌ Немає telegram_file_id для файлу #{index}")
        await update.message.reply_text(f"❌ Помилка: файл #{index} не має telegram_file_id")
        return
    
    if not file_id_db:
        print(f"❌ Немає file_id в базі даних для файлу #{index}")
        await update.message.reply_text(f"❌ Помилка: файл #{index} не має ID в базі даних")
        return

    # КРОК 1: кнопка "Видалити №N" лише запитує підтвердження
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"🗑 Видалити №{index}", 
            callback_data=f"shared_askdel_{file_id_db}_{album_id}"
        )
    ]])

    try:
        if file_type == 'photo':
            await update.message.reply_photo(photo=file_id, reply_markup=keyboard)
            print(f"✅ Фото #{index} надіслано")
        elif file_type == 'video':
            await update.message.reply_video(video=file_id, reply_markup=keyboard)
            print(f"✅ Відео #{index} надіслано")
        elif file_type == 'document':
            await update.message.reply_document(document=file_id, reply_markup=keyboard)
            print(f"✅ Документ #{index} надіслано")
        elif file_type == 'circle':
            await update.message.reply_video_note(video_note=file_id, reply_markup=keyboard)
            print(f"✅ Кружечок #{index} надіслано")
        else:
            print(f"❌ Невідомий тип файлу: {file_type}")
            await update.message.reply_text(f"❌ Файл #{index} має невідомий тип: {file_type}")
    except Exception as e:
        print(f"❌ Помилка надсилання файлу #{index}: {e}")
        await update.message.reply_text(f"❌ Помилка надсилання файлу #{index}: {e}")

async def handle_shared_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник підтвердження видалення файлу зі спільного альбому"""
    query = update.callback_query
    await query.answer()
    
    # Формат: shared_confirm_delete_{file_id_db}_{album_id}
    parts = query.data.split('_')
    file_id_db = int(parts[3])  # Тут буде file_id з бази даних
    album_id = int(parts[4])
    
    try:
        # Видаляємо файл з бази даних - використовуємо file_id як ключ
        db.cursor.execute("DELETE FROM files WHERE file_id = ?", (file_id_db,))
        db.conn.commit()
        
        # Оновлюємо лічильник файлів в альбомі
        db.cursor.execute("""
            UPDATE albums 
            SET files_count = (SELECT COUNT(*) FROM files WHERE album_id = ?)
            WHERE album_id = ?
        """, (album_id, album_id))
        db.conn.commit()
        
        # Повідомлення з файлом є медіа, тому редагуємо підпис, а не текст.
        # Reply-клавіатуру меню (Надіслати весь / останні / проміжок / за датою) НЕ змінюємо.
        await query.edit_message_caption(caption="✅ Файл успішно видалено!")
    except Exception as e:
        print(f"❌ Помилка видалення файлу: {e}")
        await query.edit_message_text(f"❌ Помилка видалення файлу: {e}")

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
            [KeyboardButton("◀️ Назад до додаткових опцій")]
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
        context.user_data.pop('shared_access_level', None)
        context.user_data.pop('shared_in_additional', None)
        context.user_data.pop('shared_in_members_main', None)
        context.user_data.pop('shared_in_role_selection', None)
        context.user_data.pop('shared_selecting_member_for_removal', None)
        context.user_data.pop('shared_changing_role_for', None)
        context.user_data.pop('shared_removing_member', None)
        
        await update.message.reply_text(
            f"✅ Альбом '{correct_name}' успішно видалено!",
            reply_markup=ReplyKeyboardRemove()
        )
        await shared_albums_main(update, context)
        return True
    else:
        await update.message.reply_text("❌ Назва не співпадає. Спробуйте ще раз:")
        return True

# ========== ВИХІД З АЛЬБОМУ ==========

async def shared_exit_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вихід зі спільного альбому до меню спільних альбомів"""
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
        
        # Видаляємо реплай клавіатуру
        await update.message.reply_text(
            "◀️ Повернення до списку спільних альбомів",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Викликаємо меню спільних альбомів
        await shared_albums_main(update, context)
        return True
    return False

# ========== ДОДАВАННЯ ФАЙЛІВ ==========

async def shared_handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник отримання файлів для спільного альбому"""
    ud = context.user_data
    if not ud.get('shared_album_active'):
        return False
    
    album_id = ud.get('current_shared_album')
    user_id = update.effective_user.id
    
    # Перевірка прав
    access = db.cursor.execute(
        "SELECT access_level FROM shared_albums WHERE album_id = ? AND user_id = ?",
        (album_id, user_id)
    ).fetchone()
    
    if not access or access['access_level'] not in ['owner', 'admin', 'editor', 'contributor']:
        await update.message.reply_text("❌ У вас немає прав на додавання файлів.")
        return True
    
    file_id, file_type, file_name, file_size = None, None, None, None
    
    # Визначаємо тип файлу (додано кружечки та голос)
    if update.message.photo:
        file_id, file_type, file_size = update.message.photo[-1].file_id, 'photo', update.message.photo[-1].file_size
    elif update.message.video:
        file_id, file_type, file_name, file_size = update.message.video.file_id, 'video', update.message.video.file_name, update.message.video.file_size
    elif update.message.document:
        file_id, file_type, file_name, file_size = update.message.document.file_id, 'document', update.message.document.file_name, update.message.document.file_size
    elif update.message.video_note:
        file_id, file_type, file_size = update.message.video_note.file_id, 'circle', update.message.video_note.file_size
    else:
        return False # Пропускаємо текст
    
    # Зберігаємо в базу
    db.add_file(album_id, file_id, file_type, file_name, file_size, user_id)
    
    # ГРУПУВАННЯ ПІДТВЕРДЖЕНЬ (щоб не спамити при завантаженні альбому)
    media_group_id = update.message.media_group_id
    if media_group_id:
        key = f"shared_notified_{media_group_id}"
        if not ud.get(key):
            ud[key] = True
            await update.message.reply_text("✅ Групу файлів збережено в спільний альбом!")
            # Очищуємо кеш групи через 10 сек
            async def clear(): 
                await asyncio.sleep(10)
                ud.pop(key, None)
            asyncio.create_task(clear())
    else:
        await update.message.reply_text(f"✅ {helpers.get_file_emoji(file_type)} Збережено!")
    
    return True


# ========== ОБРОБНИКИ ОСНОВНИХ КНОПОК СПІЛЬНОГО АЛЬБОМУ ==========

async def shared_send_all(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Надіслати всі файли зі спільного альбому (Повний функціонал)"""
    if not context.user_data.get('shared_album_active'):
        return False
    
    user_id = update.effective_user.id
    files = db.get_album_files(album_id)
    album = db.get_album(album_id)
    
    if not files:
        await update.message.reply_text("📭 В альбомі немає файлів.")
        return True
    
    # Отримуємо налаштування для підписів
    settings = helpers.get_user_display_settings(db, user_id)
    
    await update.message.reply_text(f"📤 Надсилаю всі {len(files)} файлів з альбому '{album['name']}'...")
    
    # ЦИКЛ З НОМЕРАЦІЄЮ
    for idx, file in enumerate(files, 1):
        # Тепер ця функція НЕ видасть помилку, бо ми її оновили вище
        await send_file_by_type_shared(
            update, 
            context, 
            file, 
            index=idx, 
            settings=settings
        )
    
    await update.message.reply_text("✅ Готово!")
    return True

async def shared_send_recent_start(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Початок надсилання останніх файлів"""
    context.user_data['shared_send_recent_album'] = album_id
    context.user_data['shared_awaiting_recent_count'] = True
    
    await update.message.reply_text(
        "⏳ Скільки останніх файлів надіслати?\n"
        "Введіть число (наприклад: 5, 10, 20):"
    )
    return True

async def shared_handle_recent_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення кількості останніх файлів (ПОВНИЙ)"""
    ud = context.user_data
    if not ud.get('shared_awaiting_recent_count'):
        return False
    
    text = update.message.text

    # --- 1. ПЕРЕВІРКА НА КНОПКИ (Твоя логіка) ---
    MENU_BUTTONS = [
        "📤 Надіслати весь альбом", "⏳ Надіслати останні", 
        "⏮ Надіслати перші", "🔢 Надіслати проміжок", 
        "📅 Надіслати за датою", "⋯ Додаткові опції", 
        "◀️ Вийти з альбому"
    ]
    
    if text in MENU_BUTTONS:
        ud.pop('shared_awaiting_recent_count', None)
        ud.pop('shared_send_recent_album', None)
        return False 

    # --- 2. ЛОГІКА ОБРОБКИ ЧИСЛА + НАЛАШТУВАННЯ ---
    try:
        count = int(text)
        if count <= 0 or count > 50:
            await update.message.reply_text("❌ Введіть число від 1 до 50 або натисніть кнопку в меню:")
            return True
        
        album_id = ud.get('shared_send_recent_album')
        user_id = update.effective_user.id # Для налаштувань
        
        all_files = db.get_album_files(album_id)
        album = db.get_album(album_id)
        settings = helpers.get_user_display_settings(db, user_id) # Отримуємо галочки
        
        if not all_files:
            await update.message.reply_text("📭 В альбомі немає файлів.")
        else:
            total = len(all_files)
            start_idx = max(0, total - count)
            # Беремо файли з їхніми "глобальними" номерами в альбомі
            selected_with_idx = list(enumerate(all_files, 1))[start_idx:]
            
            await update.message.reply_text(f"📤 Надсилаю останні {len(selected_with_idx)} файлів...")
            
            for idx, file in selected_with_idx:
                # Передаємо і індекс, і налаштування
                await send_file_by_type_shared(update, context, file, index=idx, settings=settings)
        
        ud.pop('shared_awaiting_recent_count', None)
        ud.pop('shared_send_recent_album', None)
        return True
        
    except ValueError:
        await update.message.reply_text("❌ Будь ласка, введіть число (наприклад: 5) або оберіть дію в меню.")
        return True

async def shared_send_first_start(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Початок надсилання перших файлів"""
    context.user_data['shared_send_first_album'] = album_id
    context.user_data['shared_awaiting_first_count'] = True
    
    await update.message.reply_text(
        "⏮ Скільки перших файлів надіслати?\n"
        "Введіть число (наприклад: 5, 10, 20):"
    )
    return True

async def shared_handle_first_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення кількості перших файлів (ПОВНИЙ)"""
    ud = context.user_data
    if not ud.get('shared_awaiting_first_count'):
        return False
    
    text = update.message.text
    MENU_BUTTONS = ["📤 Надіслати весь альбом", "⏳ Надіслати останні", "⏮ Надіслати перші", "🔢 Надіслати проміжок", "📅 Надіслати за датою", "⋯ Додаткові опції", "◀️ Вийти з альбому"]
    
    if text in MENU_BUTTONS:
        ud.pop('shared_awaiting_first_count', None)
        ud.pop('shared_send_first_album', None)
        return False 

    try:
        count = int(text)
        if count <= 0 or count > 50:
            await update.message.reply_text("❌ Введіть число від 1 до 50:")
            return True
        
        album_id = ud.get('shared_send_first_album')
        user_id = update.effective_user.id
        
        all_files = db.get_album_files(album_id)
        settings = helpers.get_user_display_settings(db, user_id)
        
        selected = all_files[:count]
        if not selected:
            await update.message.reply_text("📭 В альбомі немає файлів.")
        else:
            await update.message.reply_text(f"📤 Надсилаю перші {len(selected)} файлів...")
            for idx, file in enumerate(selected, 1):
                await send_file_by_type_shared(update, context, file, index=idx, settings=settings)
        
        ud.pop('shared_awaiting_first_count', None)
        ud.pop('shared_send_first_album', None)
        return True
    except ValueError:
        await update.message.reply_text("❌ Введіть число.")
        return True

async def shared_send_range_start(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Початок надсилання проміжку"""
    context.user_data['shared_send_range_album'] = album_id
    context.user_data['shared_awaiting_range'] = True
    
    await update.message.reply_text(
        "🔢 Введіть проміжок у форматі X-Y (наприклад: 5-10):"
    )
    return True

async def shared_handle_range_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення проміжку X-Y (ПОВНИЙ)"""
    ud = context.user_data
    if not ud.get('shared_awaiting_range'):
        return False
    
    text = update.message.text.strip()
    MENU_BUTTONS = ["📤 Надіслати весь альбом", "⏳ Надіслати останні", "⏮ Надіслати перші", "🔢 Надіслати проміжок", "📅 Надіслати за датою", "⋯ Додаткові опції", "◀️ Вийти з альбому"]
    
    if text in MENU_BUTTONS:
        ud.pop('shared_awaiting_range', None)
        ud.pop('shared_send_range_album', None)
        return False 

    if '-' not in text:
        await update.message.reply_text("❌ Формат X-Y (наприклад: 5-10)")
        return True
    
    try:
        start, end = map(int, text.split('-'))
        if start <= 0 or start > end:
            await update.message.reply_text("❌ Невірний проміжок.")
            return True
        
        album_id = ud.get('shared_send_range_album')
        user_id = update.effective_user.id
        
        all_files = db.get_album_files(album_id)
        settings = helpers.get_user_display_settings(db, user_id)
        total = len(all_files)
        
        if start > total:
            await update.message.reply_text(f"❌ В альбомі всього {total} файлів.")
            return True
        
        end = min(end, total)
        selected = all_files[start-1:end]
        
        await update.message.reply_text(f"📤 Надсилаю файли з {start} по {end}...")
        for i, file in enumerate(selected):
            # Реальний індекс = початок проміжку + номер у зрізі
            await send_file_by_type_shared(update, context, file, index=start+i, settings=settings)
        
        ud.pop('shared_awaiting_range', None)
        ud.pop('shared_send_range_album', None)
        return True
    except ValueError:
        await update.message.reply_text("❌ Невірний формат.")
        return True
    

async def shared_send_by_date_start(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Початок надсилання за датою"""
    context.user_data['shared_send_date_album'] = album_id
    context.user_data['shared_awaiting_date'] = True
    
    await update.message.reply_text(
        "📅 Введіть дату (РРРР-ММ-ДД):"
    )
    return True

async def shared_handle_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення дати (ПОВНИЙ)"""
    ud = context.user_data
    if not ud.get('shared_awaiting_date'):
        return False
    
    text = update.message.text
    MENU_BUTTONS = ["📤 Надіслати весь альбом", "⏳ Надіслати останні", "⏮ Надіслати перші", "🔢 Надіслати проміжок", "📅 Надіслати за датою", "⋯ Додаткові опції", "◀️ Вийти з альбому"]
    
    if text in MENU_BUTTONS:
        ud.pop('shared_awaiting_date', None)
        ud.pop('shared_send_date_album', None)
        return False

    try:
        from datetime import datetime
        datetime.strptime(text, '%Y-%m-%d')
        
        album_id = ud.get('shared_send_date_album')
        user_id = update.effective_user.id
        
        all_files = db.get_album_files(album_id)
        settings = helpers.get_user_display_settings(db, user_id)
        
        # Шукаємо файли за датою, зберігаючи їх "глобальний" номер idx
        to_send = []
        for idx, file in enumerate(all_files, 1):
            file_date = str(file.get('added_at') or file.get('created_at'))
            if file_date.startswith(text):
                to_send.append((idx, file))
        
        if not to_send:
            await update.message.reply_text(f"📭 Немає файлів за {text}")
        else:
            await update.message.reply_text(f"📤 Надсилаю {len(to_send)} файлів за {text}...")
            for idx, file in to_send:
                await send_file_by_type_shared(update, context, file, index=idx, settings=settings)
        
        ud.pop('shared_awaiting_date', None)
        ud.pop('shared_send_date_album', None)
        return True
    except ValueError:
        await update.message.reply_text("❌ Невірний формат. Введіть РРРР-ММ-ДД:")
        return True
    


async def send_file_by_type_shared(update: Update, context: ContextTypes.DEFAULT_TYPE, file_data, index=None, settings=None):
    """Надсилання файлу зі спільного альбому з підписом (caption)"""
    # Перетворюємо дані у словник, якщо це об'єкт БД
    try:
        f_dict = dict(file_data)
    except:
        f_dict = file_data

    file_id = f_dict.get('telegram_file_id')
    file_type = f_dict.get('file_type')
    
    # --- ФОРМУЄМО ПІДПИС ---
    caption_parts = []
    if settings:
        # Додаємо номер, якщо ввімкнено
        if settings.get('show_number') and index is not None:
            caption_parts.append(f"📄 Файл #{index}")
            
        # Додаємо дату, якщо ввімкнено
        if settings.get('show_date'):
            date_val = f_dict.get('added_at') or f_dict.get('created_at')
            if date_val:
                date_str = str(date_val)[:10]
                caption_parts.append(f"📅 {date_str}")
    
    caption = " | ".join(caption_parts) if caption_parts else None

    try:
        if file_type == 'photo':
            await update.message.reply_photo(photo=file_id, caption=caption)
        elif file_type == 'video':
            await update.message.reply_video(video=file_id, caption=caption)
        elif file_type == 'document':
            await update.message.reply_document(document=file_id, caption=caption)
        elif file_type == 'circle':
            # Кружечки не підтримують підписи
            await update.message.reply_video_note(video_note=file_id)
    except Exception as e:
        print(f"❌ Помилка: {e}")


async def shared_handle_main_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник основних кнопок спільного альбому"""
    
    print(f"🔵 shared_handle_main_buttons: text='{update.message.text}'")
    
    # ПЕРЕВІРКА: Якщо число - пропускаємо для інших обробників
    try:
        int(update.message.text)
        print("🔵 Це число, пропускаємо для shared_handle_recent_count")
        return False
    except ValueError:
        pass
    
    # Якщо зараз очікується будь-який текстовий ввід — пропускаємо
    if (context.user_data.get("shared_awaiting_recent_count") or
        context.user_data.get("shared_awaiting_first_count") or
        context.user_data.get("shared_awaiting_range") or
        context.user_data.get("shared_awaiting_date")):
        print("🔵 Є активне очікування, пропускаємо")
        return False
    
    # Якщо не відкритий спільний альбом — пропускаємо
    if not context.user_data.get("shared_album_active"):
        print("🔵 Не активний спільний альбом")
        return False
    
    text = update.message.text
    album_id = context.user_data.get("current_shared_album")
    
    # ВАЖЛИВО: Спочатку перевіряємо кнопки видалення, щоб вони не блокувалися
    if text.startswith("Видалити:"):
        print(f"🔵 Це кнопка видалення: {text}, повертаємо False, щоб піти далі в інші обробники")
        return False  # Повертаємо False, щоб текст пішов далі в інші обробники
    
    if "Надіслати весь альбом" in text:
        return await shared_send_all(update, context, album_id)
    elif "Надіслати останні" in text:
        return await shared_send_recent_start(update, context, album_id)
    elif "Надіслати перші" in text:
        return await shared_send_first_start(update, context, album_id)
    elif "Надіслати проміжок" in text:
        return await shared_send_range_start(update, context, album_id)
    elif "Надіслати за датою" in text:
        return await shared_send_by_date_start(update, context, album_id)
    elif "Додаткові опції" in text:
        return False
    elif "Вийти з альбому" in text:
        return await shared_exit_album(update, context)
    
    return False