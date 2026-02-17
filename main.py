import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from config import BOT_TOKEN, ADMIN_IDS, FREE_LIMITS
from db_models import Database
import helpers

# Додати ці імпорти після existing імпортів
from album_view import (
    send_recent_start, handle_recent_count,
    send_all_files, send_by_date_start,
    handle_date_input, album_info
)
from album_manage import (
    delete_files_start, delete_file_callback,
    confirm_delete_file, archive_album,
    confirm_archive, delete_album_start,
    handle_delete_confirmation
)

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальний об'єкт БД
db = Database()

# Головне меню (згідно ТЗ)
MAIN_MENU = ReplyKeyboardMarkup([
    [KeyboardButton("📷 Мої альбоми")],
    [KeyboardButton("👥 Спільні альбоми")],
    [KeyboardButton("📝 Мої нотатки"), KeyboardButton("🤝 Спільні нотатки")],
    [KeyboardButton("⚙️ Налаштування")]
], resize_keyboard=True)

# ========== ОБРОБНИК КОМАНДИ /start ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start - реєстрація користувача та головне меню"""
    user = update.effective_user
    
    # Реєструємо користувача в БД
    db.register_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Перевіряємо чи це адмін
    is_admin = user.id in ADMIN_IDS
    
    # Вітальне повідомлення
    welcome_text = (
        f"👋 Вітаю, {user.first_name}!\n\n"
        f"Я бот для збереження ваших медіа-файлів та нотаток.\n"
        f"📸 Фото, відео, документи, аудіо — все зберігається через file_id Telegram.\n\n"
        f"Оберіть розділ у меню нижче:"
    )
    
    if is_admin:
        welcome_text += "\n\n🔑 Ви увійшли як адміністратор\nДля входу в адмін-панель використовуйте /admin"
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=MAIN_MENU
    )

# ========== КОМАНДА /admin (АДМІН ПАНЕЛЬ) ==========

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin - вхід в адмін панель"""
    user_id = update.effective_user.id
    
    # Перевіряємо чи користувач є адміном
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ У вас немає доступу до адмін панелі.")
        return
    
    # Кнопки адмін панелі
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Користувачі", callback_data="admin_users")],
        [InlineKeyboardButton("💎 Управління Premium", callback_data="admin_premium")],
        [InlineKeyboardButton("📢 Масові розсилки", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⚙️ Налаштування бота", callback_data="admin_settings")],
        [InlineKeyboardButton("📋 Логи", callback_data="admin_logs")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔐 **Адмін-панель**\n\nОберіть дію:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ========== ОБРОБНИК ТЕКСТОВИХ ПОВІДОМЛЕНЬ (ГОЛОВНЕ МЕНЮ) ==========

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник навігації по головному меню"""
    
    # ВАЖЛИВО: Якщо активний режим альбому - ігноруємо головне меню
    if context.user_data.get('album_keyboard_active'):
        return  # Просто виходимо, нічого не робимо
    
    text = update.message.text
    user_id = update.effective_user.id
    
    # Перевіряємо чи користувач не заблокований
    user = db.get_user(user_id)
    if user and user['is_blocked']:
        await update.message.reply_text("⛔ Ваш обліковий запис заблоковано.")
        return
    
    if text == "📷 Мої альбоми":
        await show_my_albums(update, context)
    
    elif text == "👥 Спільні альбоми":
        await show_shared_albums(update, context)
    
    elif text == "📝 Мої нотатки":
        await show_my_notes(update, context)
    
    elif text == "🤝 Спільні нотатки":
        await show_shared_notes(update, context)
    
    elif text == "⚙️ Налаштування":
        await show_settings(update, context)
    
    else:
        # Якщо текст не з меню - просто показуємо меню знову
        await update.message.reply_text(
            "Оберіть розділ у меню:",
            reply_markup=MAIN_MENU
        )

# ========== РОЗДІЛ "МОЇ АЛЬБОМИ" ==========

async def show_my_albums(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати список особистих альбомів"""
    user_id = update.effective_user.id
    
    # Отримуємо альбоми з БД
    albums = db.get_user_albums(user_id, include_archived=False)
    
    if not albums:
        # Якщо альбомів немає
        keyboard = [
            [InlineKeyboardButton("➕ Створити альбом", callback_data="create_album")],
            [InlineKeyboardButton("🗂 Архівовані", callback_data="show_archived")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📷 У вас ще немає альбомів.\n\n"
            "Створіть перший альбом, щоб почати зберігати файли!",
            reply_markup=reply_markup
        )
        return
    
    # Формуємо список альбомів
    text = "📷 **Мої альбоми:**\n\n"
    keyboard = []
    
    for album in albums:
        # Формат: 🌊 Море 2018 (24 файли)
        album_text = f"{album['name']} ({album['files_count']} файлів)"
        keyboard.append([InlineKeyboardButton(
            album_text, 
            callback_data=f"open_album_{album['album_id']}"
        )])
    
    # Додаємо кнопки керування
    keyboard.append([
        InlineKeyboardButton("➕ Створити", callback_data="create_album"),
        InlineKeyboardButton("🗑 Видалити", callback_data="delete_album_menu"),
        InlineKeyboardButton("🗂 Архів", callback_data="show_archived")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def create_album_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок створення альбому"""
    query = update.callback_query
    await query.answer()
    
    # Перевіряємо ліміти
    user_id = query.from_user.id
    if not helpers.check_user_limit(db, user_id, 'albums'):
        # Показуємо пропозицію Premium
        keyboard = [[InlineKeyboardButton("💎 Отримати Premium", callback_data="premium_info")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ Ви досягли ліміту безкоштовних альбомів ({FREE_LIMITS['albums']}).\n\n"
            "Оформіть Premium для необмеженої кількості альбомів!",
            reply_markup=reply_markup
        )
        return
    
    # Запитуємо назву альбому
    context.user_data['awaiting_album_name'] = True
    
    await query.edit_message_text(
        "📝 Введіть назву для нового альбому:"
    )

# ========== ОБРОБНИК ТЕКСТУ ДЛЯ СТВОРЕННЯ АЛЬБОМУ ==========

async def handle_album_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення назви альбому"""
    # Перевіряємо чи ми в стані очікування назви
    if not context.user_data.get('awaiting_album_name'):
        return  # Просто виходимо, нічого не відповідаємо
    
    album_name = update.message.text
    user_id = update.effective_user.id
    
    # Перевіряємо довжину назви
    if len(album_name) > 50:
        await update.message.reply_text(
            "❌ Назва занадто довга (максимум 50 символів).\n"
            "Спробуйте ще раз:"
        )
        return
    
    if len(album_name) < 2:
        await update.message.reply_text(
            "❌ Назва занадто коротка (мінімум 2 символи).\n"
            "Спробуйте ще раз:"
        )
        return
    
    # Створюємо альбом в БД
    album_id = db.create_album(user_id, album_name)
    
    # ВАЖЛИВО: Встановлюємо поточний альбом
    context.user_data['current_album'] = album_id
    
    # Очищаємо стан очікування
    context.user_data['awaiting_album_name'] = False
    
    # Показуємо успішне створення з ІНЛАЙН КНОПКАМИ
    keyboard = [
        [InlineKeyboardButton("📂 Відкрити альбом", callback_data=f"open_album_{album_id}")],
        [InlineKeyboardButton("📷 До списку альбомів", callback_data="back_to_albums")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ Альбом '{album_name}' успішно створено!\n\n"
        f"Тепер ви можете надсилати в цей чат:\n"
        f"📸 Фото\n🎥 Відео\n📄 Документи\n🎵 Аудіо\n🎤 Голосові повідомлення\n\n"
        f"Всі файли автоматично зберігатимуться в альбом.",
        reply_markup=reply_markup
    )
    
    # ВАЖЛИВО: Встановлюємо поточний альбом
    context.user_data['current_album'] = album_id

# ========== ВІДКРИТТЯ АЛЬБОМУ ==========

async def open_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Відкриття конкретного альбому"""
    query = update.callback_query
    await query.answer()
    
    # Отримуємо album_id з callback_data
    album_id = int(query.data.split('_')[2])
    
    # ВАЖЛИВО: Зберігаємо поточний альбом в контексті
    context.user_data['current_album'] = album_id
    context.user_data['album_keyboard_active'] = True
    
    # Отримуємо дані альбому
    album = db.get_album(album_id)
    
    if not album:
        await query.edit_message_text("❌ Альбом не знайдено.")
        return
    
    # Інформація про альбом
    text = (
        f"📁 **{album['name']}**\n"
        f"└ Файлів: {album['files_count']}\n\n"
    )
    
    # РЕПЛАЙ КЛАВІАТУРА (всі кнопки)
    album_keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📤 Надіслати весь альбом")],
        [KeyboardButton("⏳ Надіслати останні")],
        [KeyboardButton("📅 Надіслати за датою")],
        [KeyboardButton("⋯ Додаткові дії")],
        [KeyboardButton("◀️ Вийти з альбому")]
    ], resize_keyboard=True)
    
    # Спочатку редагуємо повідомлення (без зміни клавіатури)
    await query.edit_message_text(
        text,
        parse_mode='Markdown'
    )
    
    # Потім надсилаємо нове повідомлення з реплай клавіатурою
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Надсилайте файли в цей чат, вони автоматично збережуться в альбом 👇",  # Непомітна крапка
        reply_markup=album_keyboard
    )

# ========== ОБРОБНИК КНОПОК АЛЬБОМУ ==========

async def handle_album_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник кнопок реплай клавіатури альбому"""
    # Перевіряємо чи активний режим альбому
    if not context.user_data.get('album_keyboard_active'):
        return False
    
    text = update.message.text
    album_id = context.user_data.get('current_album')
    
    if not album_id:
        return False
    
    # Отримуємо дані альбому
    album = db.get_album(album_id)
    if not album:
        return False
    
    if text == "📤 Надіслати весь альбом":
        files = db.get_album_files(album_id)
        
        if not files:
            await update.message.reply_text("📭 В альбомі немає файлів.")
            return True
        
        await update.message.reply_text(f"📤 Надсилаю всі {len(files)} файлів з альбому '{album['name']}'...")
        
        for file in files:
            await send_file_by_type(update, context, file)
        
        await update.message.reply_text("✅ Готово!")
        return True
    
    elif text == "⏳ Надіслати останні":
        context.user_data['send_recent_album'] = album_id
        context.user_data['awaiting_recent_count'] = True
        
        await update.message.reply_text(
            "⏳ Скільки останніх файлів надіслати?\n"
            "Введіть число (наприклад: 5, 10, 20):"
        )
        return True
    
    elif text == "📅 Надіслати за датою":
        context.user_data['send_date_album'] = album_id
        context.user_data['awaiting_date'] = True
        
        await update.message.reply_text(
            "📅 Введіть дату у форматі РРРР-ММ-ДД\n"
            "Наприклад: 2024-01-31"
        )
        return True
    
    elif text == "⋯ Додаткові дії":
        # ВАЖЛИВО: Зберігаємо стан альбому
        context.user_data['album_keyboard_active'] = True
        context.user_data['current_album'] = album_id
        
        # Показуємо інлайн меню з додатковими діями
        keyboard = [
            [InlineKeyboardButton("ℹ️ Інформація", callback_data=f"album_info_{album_id}")],
            [InlineKeyboardButton("🗑 Видалити файли", callback_data=f"delete_files_{album_id}")],
            [InlineKeyboardButton("🗂 Архівувати", callback_data=f"archive_album_{album_id}")],
            [InlineKeyboardButton("🗑 Видалити альбом", callback_data=f"delete_album_{album_id}")],
            [InlineKeyboardButton("👥 Зробити спільним", callback_data=f"make_shared_{album_id}")]
        ]
        
        await update.message.reply_text(
            "⋯ **Додаткові дії**\n\nОберіть потрібну дію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return True
    
    elif text == "◀️ Вийти з альбому":
        # Виходимо з альбому
        context.user_data['album_keyboard_active'] = False
        context.user_data.pop('current_album', None)
        
        await update.message.reply_text(
            "Ви вийшли з альбому",
            reply_markup=MAIN_MENU
        )
        return True
    
    return False

# ========== ФУНКЦІЯ ДЛЯ НАДСИЛАННЯ ФАЙЛІВ ==========

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
    
# ========== ЗБЕРЕЖЕННЯ ФАЙЛІВ ==========

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник отримання файлів (фото, відео, документи тощо)"""
    user_id = update.effective_user.id
    
    # Перевіряємо чи є активний альбом
    current_album = context.user_data.get('current_album')
    if not current_album:
        # Якщо немає активного альбому, ігноруємо
        return
    
    # Отримуємо дані альбому
    album = db.get_album(current_album)
    if not album:
        return
    
    # Визначаємо тип файлу і отримуємо file_id
    file_id = None
    file_type = None
    file_name = None
    file_size = None
    
    if update.message.photo:
        photo = update.message.photo[-1]
        file_id = photo.file_id
        file_type = 'photo'
        file_size = photo.file_size
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
    elif update.message.audio:
        file_id = update.message.audio.file_id
        file_type = 'audio'
        file_name = update.message.audio.file_name
        file_size = update.message.audio.file_size
    elif update.message.voice:
        file_id = update.message.voice.file_id
        file_type = 'voice'
        file_size = update.message.voice.file_size
    elif update.message.video_note:
        file_id = update.message.video_note.file_id
        file_type = 'circle'
        file_size = update.message.video_note.file_size
    else:
        return
    
    # Зберігаємо файл в БД
    db.add_file(
        album_id=current_album,
        telegram_file_id=file_id,
        file_type=file_type,
        file_name=file_name,
        file_size=file_size,
        added_by=user_id
    )
    
    # Підтвердження збереження
    emoji = helpers.get_file_emoji(file_type)
    await update.message.reply_text(
        f"{emoji} Файл збережено в альбом '{album['name']}'"
    )
# ========== СПІЛЬНІ АЛЬБОМИ ==========

async def show_shared_albums(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати список спільних альбомів"""
    # Тимчасово заглушка
    await update.message.reply_text(
        "👥 Розділ спільних альбомів в розробці.\n\n"
        "Незабаром тут з'явиться функціонал для спільного доступу!",
        reply_markup=MAIN_MENU
    )

# ========== НОТАТКИ ==========

async def show_my_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати особисті нотатки"""
    # Тимчасово заглушка
    await update.message.reply_text(
        "📝 Розділ нотаток в розробці.\n\n"
        "Незабаром ви зможете створювати текстові нотатки!",
        reply_markup=MAIN_MENU
    )

async def show_shared_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати спільні нотатки"""
    # Тимчасово заглушка
    await update.message.reply_text(
        "🤝 Спільні нотатки в розробці.\n\n"
        "Незабаром ви зможете ділитися нотатками!",
        reply_markup=MAIN_MENU
    )

# ========== НАЛАШТУВАННЯ ==========

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати налаштування"""
    user_id = update.effective_user.id
    
    # Отримуємо поточні налаштування
    settings = helpers.get_privacy_settings(db, user_id)
    
    # Перевіряємо Premium статус
    is_premium = db.check_premium(user_id)
    
    text = "⚙️ **Налаштування**\n\n"
    
    if is_premium:
        text += "💎 Статус: **Premium активний**\n"
    else:
        text += "💎 Статус: **Безкоштовний**\n"
    
    text += f"\n🔒 **Приватність:**\n"
    text += f"• Запрошення: {settings.get('allow_invites', 'all')}\n"
    text += f"• Додавання в спільні альбоми: {'✓' if settings.get('allow_add_to_shared') else '✗'}\n"
    
    keyboard = [
        [InlineKeyboardButton("🔒 Налаштування приватності", callback_data="privacy_settings")],
        [InlineKeyboardButton("💎 Premium", callback_data="premium_info")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ========== ОБРОБНИК КНОПОК ПОВЕРНЕННЯ ==========

async def back_to_albums(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повернення до списку альбомів"""
    query = update.callback_query
    await query.answer()
    
    # Створюємо фейковий update для виклику show_my_albums
    fake_update = update
    fake_update.message = query.message
    await show_my_albums(fake_update, context)

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повернення до головного меню"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Головне меню:",
        reply_markup=MAIN_MENU
    )

# ========== ОБРОБНИК ВСІХ CALLBACK ==========

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Головний обробник всіх callback запитів"""
    query = update.callback_query
    data = query.data
    
    # Обробляємо різні callback_data
    if data == "create_album":
        await create_album_start(update, context)
    
    elif data == "back_to_albums":
        await back_to_albums(update, context)
    
    elif data == "back_to_main":
        await back_to_main_menu(update, context)
    
    elif data.startswith("open_album_"):
        await open_album(update, context)
    
    # ===== ДОДАТКОВІ ДІЇ =====
    elif data.startswith("album_info_"):
        await album_info(update, context)
        # Після інформації повертаємось в альбом
        album_id = int(data.split('_')[2])
        await return_to_album_callback(update, context, album_id)
    
    elif data.startswith("delete_files_"):
        await delete_files_start(update, context)
    
    elif data.startswith("delete_file_"):
        await delete_file_callback(update, context)
    
    elif data.startswith("confirm_delete_"):
        await confirm_delete_file(update, context)
        # Після видалення повертаємось в альбом
        file_id = int(data.split('_')[2])
        file = db.cursor.execute("SELECT album_id FROM files WHERE file_id = ?", (file_id,)).fetchone()
        if file:
            await return_to_album_callback(update, context, file['album_id'])
    
    elif data.startswith("archive_album_"):
        await archive_album(update, context)
    
    elif data.startswith("confirm_archive_"):
        await confirm_archive(update, context)
        # Після архівації повертаємось до списку альбомів
        await back_to_albums(update, context)
    
    elif data.startswith("delete_album_"):
        await delete_album_start(update, context)
    
    elif data.startswith("del_page_"):
        parts = data.split('_')
        album_id = int(parts[2])
        page = int(parts[3])
        files = db.get_album_files(album_id)
        from album_manage import show_files_for_deletion
        await show_files_for_deletion(query, album_id, files, page)
    
    # ===== АДМІНКА =====
    elif data == "admin_stats":
        await admin_stats(update, context)
    
    elif data == "admin_users":
        await admin_users(update, context)
    
    elif data == "admin_premium":
        await admin_premium(update, context)
    
    elif data == "admin_broadcast":
        await admin_broadcast(update, context)
    
    elif data == "admin_settings":
        await admin_settings(update, context)
    
    elif data == "admin_logs":
        await admin_logs(update, context)
    
    elif data == "show_archived":
        await query.answer()
        await query.edit_message_text(
            "🗂 Архівовані альбоми в розробці",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_albums")
            ]])
        )
    
    elif data == "delete_album_menu":
        await query.answer()
        await query.edit_message_text(
            "🗑 Видалення альбомів в розробці",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_albums")
            ]])
        )
    
    else:
        await query.answer("Функція в розробці")

# ===== ДОПОМІЖНА ФУНКЦІЯ ДЛЯ ПОВЕРНЕННЯ В АЛЬБОМ =====

async def return_to_album_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Повернення в режим альбому після callback"""
    context.user_data['current_album'] = album_id
    context.user_data['album_keyboard_active'] = True
    
    album = db.get_album(album_id)
    if album:
        album_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("📤 Надіслати весь альбом")],
            [KeyboardButton("⏳ Надіслати останні")],
            [KeyboardButton("📅 Надіслати за датою")],
            [KeyboardButton("⋯ Додаткові дії")],
            [KeyboardButton("◀️ Вийти з альбому")]
        ], resize_keyboard=True)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=".",  # Непомітна крапка
            reply_markup=album_keyboard
        )

# ========== АДМІН ФУНКЦІЇ (заглушки) ==========

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика для адміна"""
    query = update.callback_query
    await query.answer()
    
    # Отримуємо статистику з БД
    total_users = db.cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    premium_users = db.cursor.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1").fetchone()[0]
    total_albums = db.cursor.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
    total_files = db.cursor.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    
    text = (
        "📊 **Статистика бота**\n\n"
        f"👥 Всього користувачів: {total_users}\n"
        f"💎 Premium користувачів: {premium_users}\n"
        f"📷 Всього альбомів: {total_albums}\n"
        f"📁 Всього файлів: {total_files}\n\n"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управління користувачами"""
    query = update.callback_query
    await query.answer()
    
    text = "👥 **Управління користувачами**\n\nФункція в розробці"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Управління Premium"""
    query = update.callback_query
    await query.answer()
    
    text = "💎 **Управління Premium**\n\nФункція в розробці"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Масові розсилки"""
    query = update.callback_query
    await query.answer()
    
    text = "📢 **Масові розсилки**\n\nФункція в розробці"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Налаштування бота"""
    query = update.callback_query
    await query.answer()
    
    text = "⚙️ **Налаштування бота**\n\nФункція в розробці"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логи"""
    query = update.callback_query
    await query.answer()
    
    text = "📋 **Логи бота**\n\nФункція в розробці"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ========== ГОЛОВНА ФУНКЦІЯ ==========

def main():
    """Головна функція запуску бота"""
    # Створюємо додаток
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Додаємо обробники команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    
    # ВАЖЛИВО: Спочатку обробники конкретних станів (вищий пріоритет)
    
    # Обробник для кнопок альбому - НАЙВИЩИЙ ПРІОРИТЕТ
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_album_buttons
    ), group=1)
    
    # Обробник для назви альбому
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_album_name
    ), group=1)
    
    # Обробник для кількості останніх файлів
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_recent_count
    ), group=1)
    
    # Обробник для дати
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_date_input
    ), group=1)
    
    # Обробник для підтвердження видалення альбому
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_delete_confirmation
    ), group=1)
    
    # Основний обробник меню (найнижчий пріоритет)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_menu
    ), group=2)
    
    # Обробник для файлів
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.ALL | 
        filters.AUDIO | filters.VOICE | filters.VIDEO_NOTE,
        handle_file
    ))
    
    # Додаємо обробник callback запитів
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Запускаємо бота
    print("🚀 Бот запускається...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()