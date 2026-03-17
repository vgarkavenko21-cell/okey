import logging
import asyncio
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
from file_delete import (
    delete_this_file,
    confirm_file_delete,
    cancel_file_delete,
    delete_handle_recent_input,     # Змінено назву
    delete_handle_first_input,       # Змінено назву
    delete_handle_range_input,       # Змінено назву
    delete_handle_date_input,        # Змінено назву
    delete_send_file_with_button,    # Ця назва правильна
    handle_delete_menu_buttons,
    handle_delete_text               # Додайте це
)
# Додати ці імпорти після existing імпортів
from album_view import (
    send_recent_start, handle_recent_count,
    send_all_files, send_by_date_start,
    handle_date_input, album_info,
    send_file_by_type,
    handle_first_count,          # ДОДАНО
    handle_range_input_normal    # ДОДАНО
)
from album_manage import (
    delete_files_start, delete_file_callback,
    confirm_delete_file, archive_album,
    confirm_archive, delete_album_start,
    handle_delete_confirmation
)
# Імпорти функцій спільного альбому для головного файлу (main.py)
# Імпорти для роботи зі спільними альбомами в main.py
# На початку main.py, де інші імпорти
from shared_albums import (
    shared_albums_main, shared_create_start, shared_handle_name,
    shared_open_album, shared_additional_menu, shared_members_main,
    shared_view_all_members, shared_add_member, shared_handle_member_input,
    shared_manage_roles, shared_handle_role_text_input, shared_show_role_options,
    handle_shared_role_back_button, shared_set_role, shared_remove_member_menu,
    shared_handle_remove_selection, shared_confirm_remove_member,
    shared_handle_remove_confirmation, shared_handle_members_navigation,
    shared_album_info, shared_return_to_album, shared_exit_album,
    shared_handle_file, shared_handle_main_buttons, shared_send_all,
    shared_send_recent_start, shared_handle_recent_count, shared_send_first_start,
    shared_handle_first_count, shared_send_range_start, shared_handle_range_input,
    shared_send_by_date_start, shared_handle_date_input, send_file_by_type_shared,
    shared_start_delete_menu, send_shared_file_for_deletion,
    handle_shared_delete_choices, shared_handle_del_inputs,
    shared_handle_delete_confirmation
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
    [KeyboardButton("📷 Мої альбоми"), KeyboardButton("👥 Спільні альбоми")],
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


# ========== ПЕРЕГЛЯД АРХІВОВАНИХ АЛЬБОМІВ ==========

async def show_archived_albums(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати список архівованих альбомів"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Отримуємо ТІЛЬКИ архівовані альбоми
    archived_albums = db.cursor.execute(
        "SELECT * FROM albums WHERE user_id = ? AND is_archived = 1 ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    
    if not archived_albums:
        await query.edit_message_text(
            "🗂 У вас немає архівованих альбомів.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_albums")
            ]])
        )
        return
    
    text = "🗂 **Архівовані альбоми**\n\n"
    keyboard = []
    
    for album in archived_albums:
        album_text = f"{album['name']} ({album['files_count']} файлів)"
        keyboard.append([InlineKeyboardButton(
            album_text, 
            callback_data=f"unarchive_album_{album['album_id']}"
        )])
    
    # Додаємо кнопку "Назад" внизу
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_albums")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
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
    """Обробник навігації по головному меню з розумним скиданням станів"""
    text = update.message.text
    user_id = update.effective_user.id
    ud = context.user_data

    # Список кнопок головного меню
    main_menu_buttons = ["📷 Мої альбоми", "👥 Спільні альбоми", "📝 Мої нотатки", "🤝 Спільні нотатки", "⚙️ Налаштування"]

    # ЯКЩО НАТИСНУТО КНОПКУ МЕНЮ — примусово виходимо з усіх режимів альбомів
    if text in main_menu_buttons:
        ud['shared_album_active'] = False
        ud['album_keyboard_active'] = False
        ud.pop('current_shared_album', None)
        ud.pop('current_album', None)
        ud.pop('shared_in_additional', None)
        ud.pop('shared_in_members_main', None)
    else:
        # Тільки якщо це НЕ кнопка меню і активний альбом — ігноруємо (щоб не плутати з підписом до фото)
        if ud.get('shared_album_active') or ud.get('album_keyboard_active'):
            return

    # --- Далі твоя звичайна логіка перевірки блокування та навігації ---
    user = db.get_user(user_id)
    if user and user['is_blocked']:
        await update.message.reply_text("⛔ Ваш обліковий запис заблоковано.")
        return
    
    if text == "📷 Мої альбоми":
        await show_my_albums(update, context) # Тут ми зараз поправимо SQL
    elif text == "👥 Спільні альбоми":
        await shared_albums_main(update, context)
    
    elif text == "📝 Мої нотатки":
        await show_my_notes(update, context)
    
    elif text == "🤝 Спільні нотатки":
        await show_shared_notes(update, context)
    
    elif text == "⚙️ Налаштування":
        await show_settings(update, context)
    
    else:
        # Якщо текст не з меню - просто показуємо меню знову
        await update.message.reply_text(
            "Оберіть наступну дію:",
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
    text = "📷 **Мої альбоми**\n\n"
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

# ========== ОБРОБНИК ТЕКСТУ ДЛЯ СТВОРЕННЯ АЛЬБОМУ ==========

async def handle_album_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник введення назви альбому (із захистом від дублів та кнопок)"""
    # Перевіряємо чи ми в стані очікування назви
    if not context.user_data.get('awaiting_album_name'):
        return False
    
    album_name = update.message.text.strip()
    user_id = update.effective_user.id
    
    # 1. ЗАХИСТ ВІД КНОПОК МЕНЮ
    # Список текстів кнопок, які не можна використовувати як назву
    forbidden_names = [
        "📷 Мої альбоми", "👥 Спільні альбоми", 
        "📝 Мої нотатки", "🤝 Спільні нотатки", 
        "⚙️ Налаштування", "◀️ Вийти з альбому",
        "📤 Надіслати весь альбом", "⏳ Надіслати останні",
        "📅 Надіслати за датою", "⋯ Додаткові дії",
        "⏮ Надіслати перші", "🔢 Надіслати проміжок"
    ]
    
    if album_name in forbidden_names or album_name.startswith("/"):
        await update.message.reply_text(
            "❌ Цю назву не можна використовувати (це команда або кнопка).\n"
            "Будь ласка, введіть іншу назву для альбому:"
        )
        return True

    # Перевіряємо довжину назви
    if len(album_name) > 50:
        await update.message.reply_text(
            "❌ Назва занадто довга (максимум 50 символів).\n"
            "Спробуйте ще раз:"
        )
        return True
    
    if len(album_name) < 2:
        await update.message.reply_text(
            "❌ Назва занадто коротка (мінімум 2 символи).\n"
            "Спробуйте ще раз:"
        )
        return True
        
    # 2. ЗАХИСТ ВІД ДУБЛІКАТІВ
    # Отримуємо всі існуючі альбоми користувача (включно з архівованими)
    existing_albums = db.get_user_albums(user_id, include_archived=True)
    if existing_albums:
        for album in existing_albums:
            # Порівнюємо без врахування регістру
            if album['name'].lower() == album_name.lower():
                await update.message.reply_text(
                    f"❌ Альбом з назвою '{album_name}' вже існує!\n"
                    "Придумайте іншу назву:"
                )
                return True
    
    # Створюємо альбом в БД
    album_id = db.create_album(user_id, album_name)
    
    # Встановлюємо поточний альбом
    context.user_data['current_album'] = album_id
    context.user_data['album_keyboard_active'] = True
    
    # Очищаємо стан очікування
    context.user_data['awaiting_album_name'] = False
    
    # Інформація про альбом
    text = (
        f"📁 **{album_name}**\n"
        f"└ Файлів: 0\n\n"
    )
    
    # РЕПЛАЙ КЛАВІАТУРА для альбому
    album_keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📤 Надіслати весь альбом")],
        [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
        [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
        [KeyboardButton("⋯ Додаткові дії")],
        [KeyboardButton("◀️ Вийти з альбому")]
    ], resize_keyboard=True)
    
    # Відправляємо повідомлення з клавіатурою альбому
    await update.message.reply_text(
        f"✅ Альбом '{album_name}' успішно створено!\n\n"
        f"{text}\n"
        f"Надсилайте файли в цей чат, вони автоматично збережуться в альбом 👇",
        reply_markup=album_keyboard
    )
     # ВАЖЛИВО: Встановлюємо поточний альбом
    context.user_data['current_album'] = album_id
    
    return True
    
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
        [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
        [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
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


# ========== ФУНКЦІЯ ДЛЯ ВИКЛИКУ МЕНЮ ВИДАЛЕННЯ (Файл 1) ==========

async def start_delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Запуск меню видалення файлів з префіксом 'Надіслати:'"""
    files = db.get_album_files(album_id)
    total_files = len(files)
    
    text = (
        f"🗑 **Меню видалення файлів**\n\n"
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
    
    context.user_data['in_delete_menu'] = True
    context.user_data['delete_menu_album'] = album_id
    # Вимикаємо стани звичайного перегляду, щоб не заважали
    context.user_data['awaiting_recent_count'] = False
    context.user_data['awaiting_date'] = False
    
    await update.message.reply_text(
        text,
        reply_markup=delete_keyboard,
        parse_mode='Markdown'
    )

# ========== РОЗАРХІВАЦІЯ АЛЬБОМУ ==========

async def unarchive_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Розархівувати альбом"""
    query = update.callback_query
    await query.answer()
    
    album_id = int(query.data.split('_')[2])
    user_id = query.from_user.id
    
    # Розархівовуємо альбом
    db.unarchive_album(album_id, user_id)
    
    # Показуємо повідомлення про успіх
    await query.edit_message_text(
        "✅ Альбом успішно розархівовано!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🗂 До архіву", callback_data="show_archived"),
            InlineKeyboardButton("📷 Мої альбоми", callback_data="back_to_albums")
        ]])
    )

# ========== ОБРОБНИК КНОПОК АЛЬБОМУ (Файл 1) ==========

async def handle_album_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник кнопок реплай клавіатури альбому (повна версія)"""
    
    # Якщо ми в режимі очікування вводу тексту - пропускаємо обробку кнопок
    if (context.user_data.get('awaiting_recent_count') or 
        context.user_data.get('awaiting_date') or
        context.user_data.get('awaiting_first_count') or # ДОДАНО ЦЕ
        context.user_data.get('awaiting_range') or       # І ДОДАНО ЦЕ
        context.user_data.get('delete_action')):
        return False
    
    # Якщо не активний режим альбому - виходимо
    if not context.user_data.get('album_keyboard_active'):
        return False
    
    text = update.message.text
    album_id = context.user_data.get('current_album')
    
    if not album_id:
        return False

    # ===== ПРІОРИТЕТ 1: КНОПКИ МЕНЮ ВИДАЛЕННЯ =====
    if context.user_data.get('in_delete_menu'):
        from file_delete import handle_delete_menu_buttons
        result = await handle_delete_menu_buttons(update, context, text, album_id)
        
        if result == "back_to_album":
            context.user_data['in_delete_menu'] = False
            context.user_data.pop('delete_action', None)
            context.user_data['in_additional_menu'] = True
            await return_to_album_keyboard(update, context, album_id)
            return True
        elif result:
            return True

    # ===== ПРІОРИТЕТ 2: ОСНОВНІ КНОПКИ АЛЬБОМУ =====
    if text == "📤 Надіслати весь альбом":
        files = db.get_album_files(album_id)
        if not files:
            await update.message.reply_text("📭 В альбомі немає файлів.")
            return True
        
        album = db.get_album(album_id)
        await update.message.reply_text(f"📤 Надсилаю всі {len(files)} файлів з альбому '{album['name']}'...")
        
        for idx, file in enumerate(files, 1):
            await send_file_by_type(update, context, file, index=idx)
        
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
    

    elif text == "⏮ Надіслати перші":
        context.user_data['send_first_album'] = album_id
        context.user_data['awaiting_first_count'] = True
        
        await update.message.reply_text(
            "⏮ Скільки перших файлів надіслати?\n"
            "Введіть число (наприклад: 5, 10, 20):"
        )
        return True
        

    elif text == "🔢 Надіслати проміжок":
        context.user_data['send_range_album'] = album_id
        context.user_data['awaiting_range'] = True
        
        await update.message.reply_text(
            "🔢 Введіть проміжок у форматі X-Y (наприклад: 10-20):\n\n"
            "Файли нумеруються від 1 до загальної кількості."
        )
        return True
    
    elif text == "⋯ Додаткові дії":
        context.user_data['in_additional_menu'] = True
        
        additional_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("ℹ️ Інформація")],
            [KeyboardButton("🗑 Видалити файли")],
            [KeyboardButton("🗂 Архівувати альбом")],
            [KeyboardButton("🗑 Видалити альбом")],
            [KeyboardButton("👥 Зробити спільним")],
            [KeyboardButton("◀️ Назад до альбому")]
        ], resize_keyboard=True)
        
        await update.message.reply_text(
            "📋 **Додаткові дії**\n\nОберіть потрібну дію:",
            reply_markup=additional_keyboard,
            parse_mode='Markdown'
        )
        return True
    
    elif text == "◀️ Вийти з альбому":
        context.user_data['album_keyboard_active'] = False
        context.user_data.pop('current_album', None)
        context.user_data.pop('in_additional_menu', None)
        await show_my_albums(update, context)
        return True
    
    # ===== ПРІОРИТЕТ 3: КНОПКИ ДОДАТКОВОГО МЕНЮ =====
    elif context.user_data.get('in_additional_menu'):
        if text == "ℹ️ Інформація":
            await show_album_info(update, context, album_id)
            return True
        
        elif text == "🗑 Видалити файли":
            # Викликаємо функцію видалення файлів
            context.user_data['in_additional_menu'] = False
            await start_delete_menu(update, context, album_id)
            return True
        
        elif text == "🗂 Архівувати альбом":
            await archive_album_confirm(update, context, album_id)
            return True
            
        elif text == "🗑 Видалити альбом":
            await delete_album_confirm(update, context, album_id)
            return True
            
        elif text == "👥 Зробити спільним":
            await update.message.reply_text("👥 Функція спільних альбомів в розробці")
            return True
            
        elif text == "◀️ Назад до альбому":
            # 1. Глобально чистимо ВСІ прапорці, які стосуються видалення та дод. опцій
            states_to_reset = [
                'in_additional_menu', 
                'in_delete_menu', 
                'delete_awaiting_recent', 
                'delete_awaiting_first',
                'delete_awaiting_range', 
                'delete_awaiting_date'
            ]
            for state in states_to_reset:
                ud.pop(state, None)

            # 2. Дістаємо ID альбому (спробуй обидва варіанти, де він міг бути збережений)
            album_id = ud.get('current_album') or ud.get('delete_menu_album')

            if album_id:
                # Повертаємо звичайну клавіатуру альбому
                await return_to_album_keyboard(update, context, album_id)
            else:
                # Якщо раптом ID загубився — повертаємо в головне меню
                await update.message.reply_text("🔙 Повертаємось...")
                from main import handle_menu # залежно від структури
                await handle_menu(update, context)
            
            return True

# ========== ФУНКЦІЇ ДЛЯ ДОДАТКОВОГО МЕНЮ ==========

async def return_to_album_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Повернення до основної клавіатури альбому"""
    album_keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📤 Надіслати весь альбом")],
        [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
        [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
        [KeyboardButton("⋯ Додаткові дії")],
        [KeyboardButton("◀️ Вийти з альбому")]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        "🔙 Повернення до альбому",
        reply_markup=album_keyboard
    )

async def show_album_info(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Показати інформацію про альбом"""
    album = db.get_album(album_id)
    if not album:
        await update.message.reply_text("❌ Альбом не знайдено.")
        return
    
    files = db.get_album_files(album_id)
    file_types = {}
    for file in files:
        ftype = file['file_type']
        file_types[ftype] = file_types.get(ftype, 0) + 1
    
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
        # Беремо тільки дату (перші 10 символів)
        date_only = album['last_file_added'][:10]
        text += f"\n**Останній файл:** {date_only}"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def archive_album_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Підтвердження архівації альбому"""
    album = db.get_album(album_id)
    keyboard = [
        [InlineKeyboardButton("✅ Так, архівувати", callback_data=f"confirm_archive_{album_id}")],
        [InlineKeyboardButton("❌ Ні", callback_data="cancel_action")]
    ]
    
    await update.message.reply_text(
        f"🗂 Архівувати альбом '{album['name']}'?\n\n"
        f"Архівовані альбоми не показуються в списку, але файли зберігаються.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def delete_album_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Підтвердження видалення альбому (виклик з текстового меню)"""
    album = db.get_album(album_id)
    
    if not album:
        await update.message.reply_text("❌ Альбом не знайдено.")
        return
        
    context.user_data['deleting_album'] = album_id
    context.user_data['awaiting_album_name_confirm'] = True
    context.user_data['album_name_to_delete'] = album['name']  # Зберігаємо назву для перевірки
    
    await update.message.reply_text(
        f"🗑 **Видалення альбому**\n\n"
        f"Для підтвердження введіть назву альбому:",
        parse_mode='Markdown'
    )

async def handle_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник підтвердження назви для видалення альбому"""
    if not context.user_data.get('awaiting_album_name_confirm'):
        return False
    
    user_input = update.message.text.strip()
    album_id = context.user_data.get('deleting_album')
    correct_name = context.user_data.get('album_name_to_delete')
    
    if album_id and not correct_name:
        # Підтвердження могло бути запущене з іншого місця (наприклад, інлайн-меню),
        # де назву не зберегли в user_data. Дістаємо її з БД як фолбек.
        album = db.get_album(album_id)
        if album:
            correct_name = album.get('name')
            if correct_name:
                context.user_data['album_name_to_delete'] = correct_name

    if not correct_name or not album_id:
        return False
    
    if user_input == correct_name:
        # Отримуємо альбом для перевірки
        album = db.get_album(album_id)
        
        if not album:
            await update.message.reply_text("❌ Альбом не знайдено в базі даних.")
            context.user_data['awaiting_album_name_confirm'] = False
            context.user_data.pop('deleting_album', None)
            context.user_data.pop('album_name_to_delete', None)
            return True
        
        # Перевіряємо, чи успішно видалила база даних!
        success = db.delete_album(album_id)
        
        if success:
            # Очищаємо всі дані тільки якщо видалення пройшло успішно
            context.user_data['awaiting_album_name_confirm'] = False
            context.user_data.pop('deleting_album', None)
            context.user_data.pop('album_name_to_delete', None)
            context.user_data.pop('in_additional_menu', None)
            context.user_data.pop('current_album', None)
            context.user_data['album_keyboard_active'] = False
            
            await update.message.reply_text(
                f"✅ Альбом '{correct_name}' остаточно видалено з бази!",
                reply_markup=MAIN_MENU
            )
        else:
            await update.message.reply_text(
                f"❌ Помилка: база даних відхилила видалення альбому '{correct_name}'. "
                f"Можливо, до нього прив'язані інші дані."
            )
            
        # Показуємо оновлений список альбомів
        await show_my_albums(update, context)
        return True
    else:
        # Назва не співпадає
        await update.message.reply_text("❌ Назва не співпадає. Видалення скасовано.")
        
        # Очищаємо дані очікування
        context.user_data['awaiting_album_name_confirm'] = False
        context.user_data.pop('deleting_album', None)
        context.user_data.pop('album_name_to_delete', None)
        
        # Повертаємось в додаткове меню альбому
        if album_id:
            context.user_data['in_additional_menu'] = True
            await return_to_album_keyboard(update, context, album_id)
        return True
        
async def make_shared_start(update: Update, context: ContextTypes.DEFAULT_TYPE, album_id):
    """Початок створення спільного альбому"""
    await update.message.reply_text("👥 Функція спільних альбомів в розробці")

    
# ========== ЗБЕРЕЖЕННЯ ФАЙЛІВ ==========

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
    
    # Зберігаємо файл в БД (це відбувається для КОЖНОГО файлу)
    db.add_file(
        album_id=current_album,
        telegram_file_id=file_id,
        file_type=file_type,
        file_name=file_name,
        file_size=file_size,
        added_by=user_id
    )
    
    # УГРУПОВАННЯ ПІДТВЕРДЖЕНЬ
    media_group_id = update.message.media_group_id
    
    if media_group_id:
        # Якщо файли надіслані групою (альбомом)
        notified_key = f"notified_{media_group_id}"
        
        # Перевіряємо, чи ми вже відправляли підтвердження для цієї групи
        if not context.user_data.get(notified_key):
            context.user_data[notified_key] = True
            await update.message.reply_text(
                f"✅ Групу файлів успішно збережено в альбом '{album['name']}'!"
            )
            
            # Фонове завдання: очистити пам'ять про цю групу через 10 секунд
            async def clear_media_cache():
                await asyncio.sleep(10)
                context.user_data.pop(notified_key, None)
                
            asyncio.create_task(clear_media_cache())
    else:
        # Якщо файл надіслано один (не групою)
        emoji = helpers.get_file_emoji(file_type)
        await update.message.reply_text(
            f"{emoji} Файл збережено в альбом '{album['name']}'"
        )
# ========== СПІЛЬНІ АЛЬБОМИ ==========

async def show_shared_albums(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати список спільних альбомів"""
    # Просто викликаємо функцію з shared_albums.py
    from shared_albums import shared_albums_main
    await shared_albums_main(update, context)

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

# ========== НАЛАШТУВАННЯ (Файл 1) ==========

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати налаштування (адаптовано для виклику з меню та інлайн-кнопок)"""
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
        [InlineKeyboardButton("👁 Відображення файлів", callback_data="display_settings")],
        [InlineKeyboardButton("🔒 Налаштування приватності", callback_data="privacy_settings")],
        [InlineKeyboardButton("💎 Premium", callback_data="premium_info")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Перевіряємо, звідки викликана функція
    query = update.callback_query
    
    if query:
        # Якщо викликано з інлайн-кнопки (callback)
        await query.answer()
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # Якщо викликано з головного реплай-меню
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
    
    # Отримуємо user_id
    user_id = query.from_user.id
    
    # Очищаємо стан альбому
    context.user_data['album_keyboard_active'] = False
    context.user_data.pop('current_album', None)
    context.user_data.pop('in_additional_menu', None)
    
    # Отримуємо альбоми з БД
    albums = db.get_user_albums(user_id, include_archived=False)
    
    if not albums:
        # Якщо альбомів немає
        keyboard = [
            [InlineKeyboardButton("➕ Створити альбом", callback_data="create_album")],
            [InlineKeyboardButton("🗂 Архівовані", callback_data="show_archived")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📷 У вас ще немає альбомів.\n\n"
            "Створіть перший альбом, щоб почати зберігати файли!",
            reply_markup=reply_markup
        )
        return
    
    # Формуємо список альбомів
    text = "📷 **Мої альбоми**\n\n"
    keyboard = []
    
    for album in albums:
        album_text = f"{album['name']} ({album['files_count']} файлів)"
        keyboard.append([InlineKeyboardButton(
            album_text, 
            callback_data=f"open_album_{album['album_id']}"
        )])
    
    # Додаємо кнопки керування
    keyboard.append([
        InlineKeyboardButton("➕ Створити", callback_data="create_album"),
        InlineKeyboardButton("🗂 Архів", callback_data="show_archived")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )



from telegram.error import BadRequest

async def show_display_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    settings = helpers.get_user_display_settings(db, user_id)
    
    num_btn = "✅ Відображати номер файлу" if settings.get('show_number', True) else "❌ Відображати номер"
    date_btn = "✅ Відображати дату додавання" if settings.get('show_date', True) else "❌ Відображати дату"
    
    keyboard = [
        [InlineKeyboardButton(num_btn, callback_data="toggle_show_number")],
        [InlineKeyboardButton(date_btn, callback_data="toggle_show_date")],
        [InlineKeyboardButton("◀️ Назад до налаштувань", callback_data="back_to_settings")]
    ]
    
    # Використовуємо try/except, щоб бот не падав, якщо повідомлення не змінилось
    try:
        await query.edit_message_text(
            "👁 **Налаштування відображення**\n\n"
            "Оберіть, яку інформацію додавати до файлів під час їх перегляду:\n"
            "*(✅ - увімкнено, ❌ - приховано)*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            print("Інтерфейс вже актуальний, редагування не потрібне.")
        else:
            raise e # Якщо помилка інша — прокидаємо її далі
        

async def toggle_display_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    action = query.data
    
    # Обов'язково відповідаємо на запит, щоб кнопка відтиснулася
    await query.answer()
    
    settings = helpers.get_user_display_settings(db, user_id)
    
    if action == "toggle_show_number":
        settings['show_number'] = not settings.get('show_number', True)
    elif action == "toggle_show_date":
        settings['show_date'] = not settings.get('show_date', True)
        
    helpers.save_user_display_settings(db, user_id, settings)
    
    # Оновлюємо меню
    await show_display_settings(update, context)


# ========== ОБРОБНИК ВСІХ CALLBACK ==========

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Головний обробник всіх callback запитів"""
    query = update.callback_query
    data = query.data
    
    # Обробляємо різні callback_data
    if data == "create_album":
        await create_album_start(update, context)
    
    elif data.startswith("unarchive_album_"):
        await unarchive_album(update, context)
    
    elif data == "back_to_albums":
        await back_to_albums(update, context)

    elif data == "show_archived":
        await show_archived_albums(update, context)
    
    elif data == "back_to_main":
        await back_to_main_menu(update, context)
    
    elif data.startswith("open_album_"):
        await open_album(update, context)

    # Додати всередині callback_handler
    elif data == "display_settings":
        await show_display_settings(update, context)
        
    elif data in ["toggle_show_number", "toggle_show_date"]:
        await toggle_display_setting(update, context)
        
    elif data == "back_to_settings":
        await show_settings(update, context)


    if data.startswith("ask_del_"):
        parts = data.split('_')
        f_id, alb_id = parts[2], parts[3]
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Так, видалити", callback_data=f"do_del_{f_id}"),
                InlineKeyboardButton("❌ Ні", callback_data=f"cancel_del_{f_id}_{alb_id}")
            ]
        ])
        
        await query.edit_message_caption(
            caption="⚠️ Видалити цей файл?",
            reply_markup=keyboard
        )
        return

    if data.startswith("do_del_"):
        f_id = int(data.split('_')[2])

        try:
            db.cursor.execute("DELETE FROM files WHERE id = ?", (f_id,))
        except:
            db.cursor.execute("DELETE FROM files WHERE file_id = ?", (f_id,))
        
        db.conn.commit()
        await query.message.delete()
        return

    if data.startswith("cancel_del_"):
        parts = data.split('_')
        f_id, alb_id = parts[2], parts[3]

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑 Видалити", callback_data=f"ask_del_{f_id}_{alb_id}")
        ]])

        await query.edit_message_caption(
            caption=None,
            reply_markup=keyboard
        )
        return

    # ===== СПІЛЬНІ АЛЬБОМИ =====
    elif data == "shared_create":
        from shared_albums import shared_create_start
        await shared_create_start(update, context)
    
    elif data.startswith("shared_open_"):
        from shared_albums import shared_open_album
        await shared_open_album(update, context)
    
    elif data == "shared_manage_members":
        from shared_albums import shared_manage_members
        await shared_manage_members(update, context)
    
    elif data.startswith("shared_edit_role_"):
        from shared_albums import shared_edit_role
        await shared_edit_role(update, context)
    
    elif data.startswith("shared_set_role_"):
        from shared_albums import shared_set_role
        await shared_set_role(update, context)
    
    elif data == "shared_add_member":
        from shared_albums import shared_add_member_start
        await shared_add_member_start(update, context)
    
    elif data == "shared_back_to_members_main":
        # Повернення до головного меню учасників
        album_id = context.user_data.get('current_shared_album')
        access_level = context.user_data.get('shared_access_level')
        from shared_albums import shared_members_main
        # Створюємо фейковий update для виклику
        fake_update = update
        fake_update.message = query.message
        await shared_members_main(fake_update, context, album_id, access_level)
    
    elif data == "shared_back_to_role_selection":
        # Повернення до вибору ролі
        album_id = context.user_data.get('current_shared_album')
        from shared_albums import shared_manage_roles
        fake_update = update
        fake_update.message = query.message
        await shared_manage_roles(fake_update, context, album_id)
    
    elif data.startswith("shared_role_"):
        # Вибір учасника для зміни ролі
        target_user_id = int(data.split('_')[2])
        from shared_albums import shared_show_role_options
        await shared_show_role_options(update, context, target_user_id)

# ---------- ПІДТВЕРДЖЕННЯ ВИДАЛЕННЯ (СПІЛЬНІ) ----------
    elif data.startswith("shared_ask_del_"):
        parts = data.split('_')
        f_id, alb_id = parts[3], parts[4]
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Так", callback_data=f"shared_do_del_{f_id}_{alb_id}"),
            InlineKeyboardButton("❌ Ні", callback_data=f"shared_cancel_del_{f_id}_{alb_id}")
        ]])
        await query.edit_message_caption(caption="⚠️ **Видалити цей файл для всіх?**", reply_markup=keyboard, parse_mode='Markdown')

    elif data.startswith("shared_do_del_"):
        parts = data.split('_')
        f_id, alb_id = int(parts[3]), int(parts[4])
        # Перевірка прав (можна додати)
        try:
            db.cursor.execute("DELETE FROM files WHERE id = ?", (f_id,))
        except:
            db.cursor.execute("DELETE FROM files WHERE file_id = ?", (f_id,))
        db.conn.commit()
        await query.message.delete()
        await query.answer("🗑 Видалено для всіх учасників")

    elif data.startswith("shared_cancel_del_"):
        parts = data.split('_')
        f_id, alb_id = parts[3], parts[4]
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Видалити", callback_data=f"shared_ask_del_{f_id}_{alb_id}")]])
        await query.edit_message_caption(caption=None, reply_markup=keyboard)
    
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
    
    # 1. ЕТАП: Запит на видалення всього альбому (натиснули кнопку в меню)
    elif data.startswith("delete_album_"):
        album_id = data.split('_')[2]
        
        # Отримуємо назву альбому для тексту підтвердження
        album = db.cursor.execute("SELECT title FROM albums WHERE id = ?", (album_id,)).fetchone()
        album_name = album['title'] if album else "цей альбом"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔥 ТАК, видалити все", callback_data=f"confirm_full_del_alb_{album_id}"),
                InlineKeyboardButton("❌ Скасувати", callback_data=f"open_album_{album_id}")
            ]
        ])

        await query.edit_message_text(
            text=f"❓ **Ви впевнені, що хочете видалити альбом «{album_name}»?**\n\n"
                 f"⚠️ Ця дія видалить сам альбом та **УСІ файли** в ньому безповоротно!",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    # 2. ЕТАП: Остаточне підтвердження (натиснули "ТАК")
    elif data.startswith("confirm_full_del_alb_"):
        album_id = int(data.split('_')[4])
        
        try:
            # Видаляємо всі файли альбому
            db.cursor.execute("DELETE FROM files WHERE album_id = ?", (album_id,))
            # Видаляємо сам альбом
            db.cursor.execute("DELETE FROM albums WHERE id = ?", (album_id,))
            
            db.conn.commit()
            
            await query.answer("✅ Альбом та всі файли видалено", show_alert=True)
            # Повертаємо користувача до списку всіх альбомів
            await back_to_albums(update, context) 
            
        except Exception as e:
            await query.answer(f"❌ Помилка при видаленні: {e}", show_alert=True)

    # 3. ЕТАП: Скасування (натиснули "НІ" — повертаємось в меню альбому)
    # Цей етап зазвичай обробляється через data.startswith("open_album_"), 
    # який у вас вже є в коді, тому окремий блок не потрібен.
    
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

        # ===== ВИДАЛЕННЯ ФАЙЛІВ =====
    elif data == "delete_files_menu":
        from file_delete import delete_files_menu
        await delete_files_menu(update, context)
    
    elif data == "delete_send_all":
        from file_delete import delete_send_all
        await delete_send_all(update, context)
    
    # ===== ВИДАЛЕННЯ ФАЙЛІВ =====
    elif data == "delete_send_recent":
        from file_delete import delete_send_recent_start
        await delete_send_recent_start(update, context)
    
    elif data == "delete_send_first":
        from file_delete import delete_send_first_start
        await delete_send_first_start(update, context)
    
    elif data == "delete_send_range":
        from file_delete import delete_send_range_start
        await delete_send_range_start(update, context)
    
    elif data == "delete_send_by_date":
        from file_delete import delete_send_by_date_start
        await delete_send_by_date_start(update, context)
    
    elif data.startswith("delete_this_file_"):
        from file_delete import delete_this_file
        await delete_this_file(update, context)
    
    elif data.startswith("confirm_file_delete_"):
        from file_delete import confirm_file_delete
        await confirm_file_delete(update, context)
    
    elif data == "cancel_file_delete":
        from file_delete import cancel_file_delete
        await cancel_file_delete(update, context)

    elif query.data.startswith('shared_confirm_delete_'):
        await handle_shared_delete_callback(update, context)


    elif data == "show_archived":
        await query.answer()
        await query.edit_message_text(
            "🗂 Архівовані альбоми в розробці",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="back_to_albums")
            ]])
        )
    # Додати в callback_handler після інших умов
    elif data == "cancel_action":
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("❌ Дію скасовано.")
        
        # Повертаємось в додаткове меню
        album_id = context.user_data.get('current_album')
        if album_id:
            context.user_data['in_additional_menu'] = True
    
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
        [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
        [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
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

async def shared_delete_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Хендлер, який запускає видалення у спільному альбомі"""
    ud = context.user_data
    text = update.message.text

    DELETE_BUTTONS = [
        "Видалити: Весь альбом",
        "Видалити: Останні",
        "Видалити: Перші",
        "Видалити: Проміжок",
        "Видалити: За датою"
    ]

    if ud.get('shared_in_delete_menu') and (
        text in DELETE_BUTTONS
        or ud.get('shared_del_awaiting_recent')
        or ud.get('shared_del_awaiting_first')
        or ud.get('shared_del_awaiting_range')
        or ud.get('shared_del_awaiting_date')
    ):
        print("👉 В РЕЖИМІ ВИДАЛЕННЯ")

        res = await handle_shared_delete_choices(update, context)
        if res:
            print("✅ handle_shared_delete_choices СПРАЦЮВАВ")
            return True

        res = await shared_handle_del_inputs(update, context)
        if res:
            print("✅ shared_handle_del_inputs СПРАЦЮВАВ")
            return True

    return False

async def handle_all_text_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    text = update.message.text
    if not text: return False
    
    # --- 1. ПРІОРИТЕТНА НАВІГАЦІЯ (ОБРОБКА ТОГО, ЩО ПРИЙШЛО З GROUP 1) ---
    if text == "◀️ Назад до альбому":
        print(f"✅ Головний обробник: повертаємось до альбому з тексту '{text}'")
        
        # Миттєво чистимо ВСІ режими, щоб бот "протверезів"
        states_to_reset = [
            'in_delete_menu', 'in_additional_menu', 
            'delete_awaiting_recent', 'delete_awaiting_first', 
            'delete_awaiting_range', 'delete_awaiting_date',
            'shared_in_delete_menu', 'shared_del_awaiting_recent',
            'shared_del_awaiting_first', 'shared_del_awaiting_range',
            'shared_del_awaiting_date'
        ]
        for state in states_to_reset:
            ud.pop(state, None)

        # Шукаємо ID альбому (важливо перевірити всі можливі ключі)
        album_id = ud.get('current_album') or ud.get('delete_menu_album') or ud.get('shared_delete_album_id') or ud.get('current_shared_album')

        if album_id:
            # Якщо це спільний альбом
            if ud.get('shared_album_active'):
                from shared_albums import shared_return_to_album
                await shared_return_to_album(update, context, album_id)
            else:
                # Якщо це звичайний особистий альбом
                from albums import return_to_album_keyboard
                await return_to_album_keyboard(update, context, album_id)
        else:
            # Якщо ID зовсім загубився, повертаємо в головне меню
            await update.message.reply_text("🏠 Повернення до головного меню...")
            from main import handle_menu 
            await handle_menu(update, context)
            
        return True

    # --- 2. СПІЛЬНІ АЛЬБОМИ (ПРІОРИТЕТНІ СТАНИ) ---
    if ud.get('shared_awaiting_name'): return await shared_handle_name(update, context)
    if ud.get('shared_awaiting_recent_count'): return await shared_handle_recent_count(update, context)
    if ud.get('shared_awaiting_first_count'): return await shared_handle_first_count(update, context)
    if ud.get('shared_awaiting_range'): return await shared_handle_range_input(update, context)
    if ud.get('shared_awaiting_date'): return await shared_handle_date_input(update, context)
    if ud.get('shared_awaiting_member'): return await shared_handle_member_input(update, context)
    if ud.get('shared_removing_member'): return await shared_handle_remove_confirmation(update, context)
    if ud.get('shared_awaiting_archive'): return await shared_handle_archive(update, context)
    if ud.get('shared_awaiting_delete_confirm'): return await shared_handle_delete_confirmation(update, context)
    
    # --- 3. СПІЛЬНЕ ВИДАЛЕННЯ (ввід чисел) ---
    if ud.get('shared_del_awaiting_recent') or ud.get('shared_del_awaiting_first') or \
       ud.get('shared_del_awaiting_range') or ud.get('shared_del_awaiting_date'):
        if await shared_handle_del_inputs(update, context):
            return True

    # --- 4. ОСОБИСТІ АЛЬБОМИ (СТАНИ) ---
    if ud.get('awaiting_album_name'): return await handle_album_name(update, context)
    if ud.get('awaiting_recent_count'): return await handle_recent_count(update, context)
    if ud.get('awaiting_first_count'): return await handle_first_count(update, context)
    if ud.get('awaiting_range'): return await handle_range_input_normal(update, context)
    if ud.get('awaiting_date'): return await handle_date_input(update, context)
    if ud.get('awaiting_album_name_confirm'): return await handle_delete_confirmation(update, context)

    # --- 5. РЕЖИМ ВИДАЛЕННЯ (ЗВИЧАЙНІ АЛЬБОМИ) ---
    if ud.get('in_delete_menu'):
        album_id = ud.get('delete_menu_album')
        
        # Обробка введення цифр
        if ud.get('delete_awaiting_recent'): return await delete_handle_recent_input(update, context)
        if ud.get('delete_awaiting_first'): return await delete_handle_first_input(update, context)
        if ud.get('delete_awaiting_range'): return await delete_handle_range_input(update, context)
        if ud.get('delete_awaiting_date'): return await delete_handle_date_input(update, context)

        # Обробка кнопок меню видалення
        res = await handle_delete_menu_buttons(update, context, text, album_id)
        if res: return True

    # --- 6. НАВІГАЦІЯ В СПІЛЬНИХ АЛЬБОМАХ ---
    if ud.get('shared_album_active'):
        # Використовуємо універсальний обробник для всіх кнопок спільного альбому
        from shared_albums import shared_handle_all_buttons
        if await shared_handle_all_buttons(update, context):
            return True
        
        # Якщо не спрацювало, пробуємо старі обробники для сумісності
        if ud.get('shared_selecting_member_for_removal'): 
            return await shared_handle_remove_selection(update, context)
            
        if ud.get('shared_in_role_selection'): 
            return await shared_handle_role_text_input(update, context)
            
        if ud.get('shared_in_members_main'): 
            return await shared_handle_members_navigation(update, context)
        
        # Кнопки видалення
        if text.startswith("Видалити:"):
            if await handle_shared_delete_choices(update, context):
                return True
        
        # Основні кнопки
        res = await shared_handle_main_buttons(update, context)
        if res: return True
        
        res = await shared_additional_menu(update, context)
        if res: return True

    # --- 7. КНОПКИ ЗВИЧАЙНИХ АЛЬБОМІВ ---
    if ud.get('album_keyboard_active') or ud.get('current_album'):
        res = await handle_album_buttons(update, context)
        if res: return True

    return False

async def handle_all_files_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Єдиний вхід для всіх медіа"""
    ud = context.user_data
    
    # 1. Пріоритет спільним альбомам (якщо юзер зайшов у спільний)
    if ud.get('shared_album_active'):
        # Важливо: функція shared_handle_file має бути імпортована!
        return await shared_handle_file(update, context)
    
    # 2. Особисті альбоми
    if ud.get('current_album') or ud.get('album_keyboard_active'):
        return await handle_file(update, context)
    
    # 3. Фолбек
    await update.message.reply_text("⚠️ Спочатку відкрийте альбом, щоб зберегти файл.")
    return True

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Group 0: ФАЙЛИ
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.AUDIO | filters.VOICE | filters.VIDEO_NOTE,
        handle_all_files_dispatcher
    ), group=0)

    # Group 1: ГЛОБАЛЬНІ ТЕКСТОВІ КОМАНДИ (Видалення за номером)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_text), group=1)
        
    # Group 2: УНІВЕРСАЛЬНИЙ ДИСПЕТЧЕР (Обробляє стани та кнопки альбомів)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text_inputs), group=2)

    # Group 5: ГОЛОВНЕ МЕНЮ (Фолбек)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu), group=5)

    # Команди та колбеки
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_handler))

    print("🚀 Маршрутизатори оновлені. Запускаємося!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
if __name__ == '__main__':
    main()