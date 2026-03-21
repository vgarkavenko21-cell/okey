import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
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
from premium import show_premium_menu, handle_premium_callback
from admin import admin_start, handle_admin_text, handle_admin_broadcast_message
from notes import (
    show_my_notes as notes_show_my_notes,
    notes_create_start,
    notes_open_folder,
    notes_show_archived,
    notes_unarchive,
    notes_back_to_list,
    handle_note_folder_name,
    handle_note_folder_buttons,
    handle_note_media,
)
from notes_shared import (
    show_shared_notes as shared_notes_show,
    shared_notes_create_start,
    open_shared_note_folder,
    handle_shared_note_folder_name,
    handle_shared_note_buttons,
    handle_shared_note_media,
    handle_shared_note_delete_callback,
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
    shared_handle_remove_confirmation, shared_handle_members_navigation, handle_shared_member_delete_callback,
    shared_album_info, shared_return_to_album, shared_exit_album,
    shared_handle_file, shared_handle_main_buttons, shared_send_all,
    shared_send_recent_start, shared_handle_recent_count, shared_send_first_start,
    shared_handle_first_count, shared_send_range_start, shared_handle_range_input,
    shared_send_by_date_start, shared_handle_date_input, send_file_by_type_shared,
    shared_start_delete_menu, send_shared_file_for_deletion,
    handle_shared_delete_choices, shared_handle_del_inputs,
    shared_handle_delete_confirmation, handle_shared_delete_callback
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


async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати адмін-меню (для callback)."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Користувачі", callback_data="admin_users")],
        [InlineKeyboardButton("💎 Premium / Управління", callback_data="admin_premium")],
        [InlineKeyboardButton("🔗 Канали Premium", callback_data="admin_premium_channels_manage")],
        [InlineKeyboardButton("📢 Масові розсилки", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⚙️ Налаштування бота", callback_data="admin_settings")],
        [InlineKeyboardButton("📋 Логи", callback_data="admin_logs")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.message.reply_text(
            "🔐 **Адмін-панель**\n\nОберіть дію:",
            reply_markup=reply_markup,
            # без Markdown, щоб імена/нікнейми не ламали розмітку
        )
    else:
        await update.message.reply_text(
            "🔐 **Адмін-панель**\n\nОберіть дію:",
            reply_markup=reply_markup,
            # без Markdown, щоб імена/нікнейми не ламали розмітку
        )

# ========== ОБРОБНИК ТЕКСТОВИХ ПОВІДОМЛЕНЬ (ГОЛОВНЕ МЕНЮ) ==========

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник навігації по головному меню з розумним скиданням станів"""
    text = update.message.text
    user_id = update.effective_user.id
    ud = context.user_data

    # Якщо користувач у адмін-режимі, не показуємо головне меню у фолбеку,
    # щоб reply keyboard адміна не перекривався.
    if ud.get("awaiting_admin_password") or ud.get("is_admin"):
        return

    # Список кнопок головного меню
    main_menu_buttons = ["📷 Мої альбоми", "👥 Спільні альбоми", "📝 Мої нотатки", "🤝 Спільні нотатки", "⚙️ Налаштування"]

    # ЯКЩО НАТИСНУТО КНОПКУ МЕНЮ — примусово виходимо з усіх режимів альбомів
    if text in main_menu_buttons:
        ud['shared_album_active'] = False
        ud['album_keyboard_active'] = False
        ud['note_folder_active'] = False
        ud['shared_note_active'] = False
        ud.pop('current_shared_album', None)
        ud.pop('current_album', None)
        ud.pop('current_note_folder', None)
        ud.pop('current_shared_note_folder', None)
        ud.pop('shared_in_additional', None)
        ud.pop('shared_in_members_main', None)
    else:
        # Тільки якщо це НЕ кнопка меню і активний альбом — ігноруємо (щоб не плутати з підписом до фото)
        if ud.get('shared_album_active') or ud.get('album_keyboard_active') or ud.get('note_folder_active') or ud.get('shared_note_active'):
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
    
    # Перевіряємо ліміти (особисті альбоми: максимум 3 без Premium)
    user_id = query.from_user.id
    if not helpers.check_user_limit(db, user_id, 'albums'):
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("💎 Отримати Premium", callback_data="premium_info")]]
        )
        await query.edit_message_text(
            "❌ Ліміт безкоштовних альбомів досягнуто (3).\n\n"
            "Щоб зняти обмеження — потрібно отримати Premium.",
            reply_markup=keyboard,
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

    user_id = query.from_user.id
    if helpers.exceeded_album_limits_without_premium(db, user_id):
        await query.edit_message_text(
            "❌ У вас перевищено безкоштовний ліміт альбомів і Premium неактивний.\n\n"
            "Щоб знову відкрити альбоми — активуйте Premium.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("💎 Отримати Premium", callback_data="premium_info")]]
            ),
        )
        return
    
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
            [KeyboardButton("ℹ️ Інформація"), KeyboardButton("🗑 Видалити файли")],
            [KeyboardButton("🗂 Архівувати альбом"), KeyboardButton("🗑 Видалити альбом")],
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
            user_id = update.effective_user.id
            ok, reason = db.make_album_shared(album_id, user_id)
            if ok:
                # Переключаємося зі звичайного режиму на спільний
                context.user_data['album_keyboard_active'] = False
                context.user_data.pop('current_album', None)
                context.user_data.pop('in_additional_menu', None)

                context.user_data['shared_album_active'] = False
                context.user_data.pop('current_shared_album', None)
                context.user_data.pop('shared_access_level', None)

                await update.message.reply_text("✅ Альбом перенесено до **Спільних альбомів**.", parse_mode='Markdown')
                await shared_albums_main(update, context)
                return True

            if reason == "not_owner":
                await update.message.reply_text("❌ Тільки власник альбому може зробити його спільним.")
                return True
            if reason == "not_found":
                await update.message.reply_text("❌ Альбом не знайдено.")
                return True

            await update.message.reply_text("❌ Не вдалося зробити альбом спільним (помилка бази даних).")
            return True
            
        elif text == "◀️ Назад до альбому":
            # 1. Глобально чистимо ВСІ прапорці, які стосуються видалення та дод. опцій
            states_to_reset = [
                'in_additional_menu',
                'in_delete_menu',
                'delete_awaiting_recent',
                'delete_awaiting_first',
                'delete_awaiting_range',
                'delete_awaiting_date',
                'delete_action',
                'awaiting_delete_input',
                'awaiting_recent_count',
                'awaiting_first_count',
                'awaiting_range',
                'awaiting_date'
            ]
            for state in states_to_reset:
                context.user_data.pop(state, None)

            # 2. Дістаємо ID альбому (спробуй обидва варіанти, де він міг бути збережений)
            album_id = context.user_data.get('current_album') or context.user_data.get('delete_menu_album')

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
    await notes_show_my_notes(update, context)

async def show_shared_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати спільні нотатки"""
    await shared_notes_show(update, context)

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
        [InlineKeyboardButton("💎 Premium", callback_data="premium_info")]
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
    
    num_btn = "✅ Відображати номер запису/файлу" if settings.get('show_number', True) else "❌ Відображати номер"
    date_btn = "✅ Відображати дату запису/додавання" if settings.get('show_date', True) else "❌ Відображати дату"
    
    keyboard = [
        [InlineKeyboardButton(num_btn, callback_data="toggle_show_number")],
        [InlineKeyboardButton(date_btn, callback_data="toggle_show_date")],
        [InlineKeyboardButton("◀️ Назад до налаштувань", callback_data="back_to_settings")]
    ]
    
    # Використовуємо try/except, щоб бот не падав, якщо повідомлення не змінилось
    try:
        await query.edit_message_text(
            "👁 **Налаштування відображення**\n\n"
            "Оберіть, яку інформацію додавати до записів/файлів під час перегляду:\n"
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

    # Якщо адмін чекає вводу тексту (старі callback) — не блокуємо навігацію
    if context.user_data.get("admin_premium_input"):
        allow_prefixes = ("admin_premium_active_list_page_",)
        allow_callbacks = {"admin_back", "admin_premium", "admin_premium_channels_manage"}
        if not (data in allow_callbacks or data.startswith(allow_prefixes)):
            await query.answer("Спочатку введіть ID/@username або натисніть «Переглянути всіх Premium».")
            return
    # Якщо адмін чекає вводу кількості днів — інші callback ігноруємо
    if context.user_data.get("admin_premium_grant_days"):
        allow_prefixes = ("admin_premium_active_list_page_",)
        allow_callbacks = {
            "admin_back",
            "admin_premium",
            "admin_premium_channels_manage",
            "admin_premium_cancel_grant_days",
        }
        if not (data in allow_callbacks or data.startswith(allow_prefixes)):
            await query.answer("Спочатку введіть кількість днів або скасуйте дію.")
            return
    if context.user_data.get("admin_stats_custom_phase"):
        # Якщо адмін передумав і натиснув будь-яку кнопку статистики/навігації,
        # скидаємо режим ручного вводу дат і дозволяємо перейти далі.
        if data != "admin_stats_range_custom":
            context.user_data.pop("admin_stats_custom_phase", None)
            context.user_data.pop("admin_stats_custom_start", None)

    # Меню Premium (кнопка в налаштуваннях + кнопки з повідомлень про ліміти)
    if data == "premium_info":
        from premium import show_premium_menu
        await show_premium_menu(update, context)
        return

    # Адмін-меню бек
    if data == "admin_back":
        await show_admin_menu(update, context)
        return

    # Управління Premium каналами
    if data == "admin_premium_channels_manage":
        # відкриваємо вже існуюче меню через admin_premium_add_link/список
        await admin_premium_channels_manage(update, context)
        return

    # ---- Admin: statistics ranges ----
    if data == "admin_stats_range_all":
        await admin_stats_show_period(update, context, None, datetime.now())
        return
    if data == "admin_stats_period_menu":
        await admin_stats_period_menu(update, context)
        return
    if data == "admin_stats_range_day":
        await admin_stats_show_period(update, context, datetime.now() - timedelta(days=1), datetime.now())
        return
    if data == "admin_stats_range_week":
        await admin_stats_show_period(update, context, datetime.now() - timedelta(weeks=1), datetime.now())
        return
    if data == "admin_stats_range_month":
        await admin_stats_show_period(update, context, datetime.now() - timedelta(days=30), datetime.now())
        return
    if data == "admin_stats_range_year":
        await admin_stats_show_period(update, context, datetime.now() - timedelta(days=365), datetime.now())
        return
    if data == "admin_stats_range_custom":
        context.user_data["admin_stats_custom_phase"] = "a"
        await query.edit_message_text(
            "✍️ Введіть початкову дату `ВІД` у форматі `YYYY-MM-DD`.\n"
            "Наприклад: `2026-03-01`",
            parse_mode="Markdown",
        )
        return

    # ---- Admin: users list ----
    if data == "admin_users_send_all":
        await admin_users_send_all(update, context)
        return

    # ---- Admin: premium list / actions ----
    if data.startswith("admin_premium_active_list_page_"):
        rest = data[len("admin_premium_active_list_page_") :]
        # rest: "0" OR "{mode}_{page}"
        parts = rest.split("_")
        if len(parts) == 1:
            mode = "view"
            page_str = parts[0]
        else:
            page_str = parts[-1]
            mode = "_".join(parts[:-1])

        try:
            page = int(page_str)
        except Exception:
            page = 0

        await admin_premium_active_list_page(update, context, page, mode=mode)
        return

    if data.startswith("admin_premium_remove_uid_"):
        if query.from_user.id not in ADMIN_IDS:
            return
        # Формат: admin_premium_remove_uid_{uid}_page_{page}
        rest = data[len("admin_premium_remove_uid_") :]
        page = 0
        if "_page_" in rest:
            uid_str, page_str = rest.split("_page_", 1)
            try:
                page = int(page_str)
            except Exception:
                page = 0
        else:
            uid_str = rest

        try:
            uid = int(uid_str)
        except Exception:
            uid = None

        if uid is not None:
            db.remove_premium(uid)

        await admin_premium_active_list_page(update, context, page, mode="remove")
        return

    if data == "admin_premium_cancel_grant_days":
        if query.from_user.id not in ADMIN_IDS:
            return
        ud = context.user_data.get("admin_premium_grant_days") or {}
        page = ud.get("page", 0)
        action = ud.get("action")
        context.user_data.pop("admin_premium_grant_days", None)
        mode = "view"
        if action == "grant_paid":
            mode = "grant_paid"
        elif action == "grant_channel":
            mode = "grant_channel"
        await admin_premium_active_list_page(
            update,
            context,
            int(page) if isinstance(page, int) else 0,
            mode=mode,
        )
        return

    if data.startswith("admin_premium_grant_paid_uid_"):
        if query.from_user.id not in ADMIN_IDS:
            return
        rest = data[len("admin_premium_grant_paid_uid_") :]
        page = 0
        if "_page_" in rest:
            uid_str, page_str = rest.split("_page_", 1)
            try:
                page = int(page_str)
            except Exception:
                page = 0
        else:
            uid_str = rest

        try:
            uid = int(uid_str)
        except Exception:
            uid = None

        if uid is not None:
            # просимо кількість днів
            context.user_data["admin_premium_grant_days"] = {
                "action": "grant_paid",
                "uid": uid,
                "page": page,
            }
            await query.edit_message_text(
                "💳 Введіть кількість днів для видачі paid Premium (наприклад: 7):",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Скасувати", callback_data="admin_premium_cancel_grant_days")]]
                ),
            )
            return

        await admin_premium_active_list_page(update, context, page)
        return

    if data.startswith("admin_premium_grant_channel_uid_"):
        if query.from_user.id not in ADMIN_IDS:
            return
        rest = data[len("admin_premium_grant_channel_uid_") :]
        page = 0
        if "_page_" in rest:
            uid_str, page_str = rest.split("_page_", 1)
            try:
                page = int(page_str)
            except Exception:
                page = 0
        else:
            uid_str = rest

        try:
            uid = int(uid_str)
        except Exception:
            uid = None

        if uid is not None:
            # просимо кількість днів
            context.user_data["admin_premium_grant_days"] = {
                "action": "grant_channel",
                "uid": uid,
                "page": page,
            }
            await query.edit_message_text(
                "🔗 Введіть кількість днів для видачі sub Premium (channel) (наприклад: 7):",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Скасувати", callback_data="admin_premium_cancel_grant_days")]]
                ),
            )
            return

        await admin_premium_active_list_page(update, context, page)
        return

    if data == "admin_premium_input_remove":
        if query.from_user.id not in ADMIN_IDS:
            return
        # Старий callback: більше не використовуємо ввід текстом.
        # Відкриваємо список активних Premium, де є кнопки дій.
        context.user_data.pop("admin_premium_input", None)
        await admin_premium_active_list_page(update, context, 0)
        return

    if data == "admin_premium_input_grant_paid":
        if query.from_user.id not in ADMIN_IDS:
            return
        # Новий сценарій: вводимо конкретного користувача вручну (ID/@username).
        context.user_data["admin_premium_input"] = {"action": "grant_paid"}
        await query.edit_message_text(
            "💳 Видача Premium (гів)\n\n"
            "Надішліть ID або @username користувача.\n"
            "Далі бот запитає кількість днів.\n\n"
            "Приклад: `123456789` або `@nickname`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ В Premium-меню", callback_data="admin_premium")],
            ]),
        )
        return

    if data == "admin_premium_input_grant_channel":
        if query.from_user.id not in ADMIN_IDS:
            return
        # Старий callback: більше не використовуємо ввід текстом.
        context.user_data.pop("admin_premium_input", None)
        await admin_premium_active_list_page(update, context, 0)
        return
    
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

    elif data == "notes_create":
        await notes_create_start(update, context)

    elif data.startswith("notes_open_"):
        await notes_open_folder(update, context)

    elif data == "notes_archived":
        await notes_show_archived(update, context)

    elif data.startswith("notes_unarchive_"):
        await notes_unarchive(update, context)

    elif data == "notes_back":
        await notes_back_to_list(update, context)

    elif data.startswith("snotes_open_"):
        await open_shared_note_folder(update, context)

    elif data == "snotes_create":
        await shared_notes_create_start(update, context)

    elif data.startswith("note_"):
        from notes import handle_note_delete_callback
        if await handle_note_delete_callback(update, context):
            return

    elif data.startswith("snote_") or data.startswith("snotes_member_"):
        if await handle_shared_note_delete_callback(update, context):
            return

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
        album_row = None
        try:
            album_row = db.cursor.execute("SELECT album_id FROM files WHERE id = ?", (f_id,)).fetchone()
            db.cursor.execute("DELETE FROM files WHERE id = ?", (f_id,))
        except Exception:
            album_row = db.cursor.execute("SELECT album_id FROM files WHERE file_id = ?", (f_id,)).fetchone()
            db.cursor.execute("DELETE FROM files WHERE file_id = ?", (f_id,))

        if album_row is not None:
            album_id = album_row['album_id']
            db.cursor.execute(
                "UPDATE albums SET files_count = (SELECT COUNT(*) FROM files WHERE album_id = ?) WHERE album_id = ?",
                (album_id, album_id)
            )

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

    elif data.startswith("shared_member_del_"):
        if await handle_shared_member_delete_callback(update, context):
            return
    
    elif data == "shared_add_member":
        from shared_albums import shared_add_member_start
        await shared_add_member_start(update, context)
    
    elif data == "shared_back_to_members_main":
        # Повернення до головного меню учасників
        album_id = context.user_data.get('current_shared_album')
        access_level = context.user_data.get('shared_access_level')
        from shared_albums import shared_members_main
        # Робимо lightweight update-like об'єкт, бо telegram.Update immutable
        class _U:
            pass
        u = _U()
        u.message = query.message
        u.effective_user = query.from_user
        await shared_members_main(u, context, album_id, access_level)
    
    elif data == "shared_back_to_role_selection":
        # Повернення до вибору ролі
        album_id = context.user_data.get('current_shared_album')
        from shared_albums import shared_manage_roles
        class _U:
            pass
        u = _U()
        u.message = query.message
        u.effective_user = query.from_user
        await shared_manage_roles(u, context, album_id)
    
    elif data.startswith("shared_role_"):
        # Вибір учасника для зміни ролі
        target_user_id = int(data.split('_')[2])
        from shared_albums import shared_show_role_options
        await shared_show_role_options(update, context, target_user_id)

    # ---------- ПІДТВЕРДЖЕННЯ ВИДАЛЕННЯ ФАЙЛУ (СПІЛЬНІ) ----------
    elif data.startswith("shared_askdel_"):
        # Формат: shared_askdel_{file_id_db}_{album_id}
        parts = data.split('_')
        f_id, alb_id = parts[2], parts[3]
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Так, видалити", callback_data=f"shared_confirm_delete_{f_id}_{alb_id}"),
            InlineKeyboardButton("❌ Ні", callback_data=f"shared_cancel_del_{f_id}_{alb_id}")
        ]])
        await query.edit_message_caption(
            caption="🗑 Ви впевнені, що хочете видалити цей файл зі спільного альбому?",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    elif data.startswith("shared_cancel_del_"):
        # Повертаємо вихідну кнопку "Видалити №N" без видалення файлу
        parts = data.split('_')
        f_id, alb_id = parts[3], parts[4]
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑 Видалити", callback_data=f"shared_askdel_{f_id}_{alb_id}")
        ]])
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

    elif data == "admin_premium_add_link":
        await admin_premium_add_link(update, context)
    
    elif data == "admin_broadcast":
        await admin_broadcast(update, context)

    elif data == "admin_broadcast_all":
        await query.answer()
        context.user_data["admin_broadcast_wait_mode"] = "all"
        await query.edit_message_text(
            "📨 Надішліть повідомлення для розсилки ВСІМ (користувачі + групи/канали).\n"
            "Підтримується будь-який формат повідомлення.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В меню розсилки", callback_data="admin_broadcast")]]),
        )

    elif data == "admin_broadcast_subs":
        await query.answer()
        context.user_data["admin_broadcast_wait_mode"] = "subs"
        await query.edit_message_text(
            "🔔 Надішліть повідомлення для розсилки підписникам бота (private).\n"
            "Підтримується будь-який формат повідомлення.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В меню розсилки", callback_data="admin_broadcast")]]),
        )

    elif data == "admin_broadcast_groups":
        await query.answer()
        context.user_data["admin_broadcast_wait_mode"] = "groups"
        await query.edit_message_text(
            "👥 Надішліть повідомлення для розсилки по групах/каналах.\n"
            "Підтримується будь-який формат повідомлення.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В меню розсилки", callback_data="admin_broadcast")]]),
        )

    elif data == "admin_broadcast_one_user":
        await query.answer()
        context.user_data["admin_broadcast_wait_user"] = True
        context.user_data.pop("admin_broadcast_wait_mode", None)
        await query.edit_message_text(
            "👤 Введіть ID або @username користувача для тестової розсилки.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В меню розсилки", callback_data="admin_broadcast")]]),
        )

    elif data == "admin_broadcast_delete_menu":
        await query.answer()
        await query.edit_message_text(
            "🗑 Видалення розсилок\n\nОберіть варіант:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Останнє повідомлення", callback_data="admin_broadcast_delete_last")],
                [InlineKeyboardButton("📩 Надіслати ідентичне для видалення", callback_data="admin_broadcast_delete_by_sample")],
                [InlineKeyboardButton("◀️ В меню розсилки", callback_data="admin_broadcast")],
            ]),
        )

    elif data == "admin_broadcast_delete_last":
        await query.answer()
        row = db.cursor.execute(
            "SELECT id FROM broadcasts WHERE admin_id = ? ORDER BY id DESC LIMIT 1",
            (query.from_user.id,),
        ).fetchone()
        if not row:
            await query.edit_message_text(
                "❌ Немає розсилок для видалення.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В меню розсилки", callback_data="admin_broadcast")]]),
            )
            return
        b_id = int(row["id"])
        rows = db.cursor.execute(
            "SELECT target_chat_id, target_message_id FROM broadcast_deliveries WHERE broadcast_id = ?",
            (b_id,),
        ).fetchall()
        deleted = 0
        failed = 0
        for r in rows:
            try:
                await context.bot.delete_message(chat_id=int(r["target_chat_id"]), message_id=int(r["target_message_id"]))
                deleted += 1
            except Exception:
                failed += 1
        await query.edit_message_text(
            f"🗑 Видалення останньої розсилки завершено.\nВидалено: {deleted}\nПомилок: {failed}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В меню розсилки", callback_data="admin_broadcast")]]),
        )

    elif data == "admin_broadcast_delete_by_sample":
        await query.answer()
        context.user_data["admin_broadcast_delete_by_sample"] = True
        context.user_data.pop("admin_broadcast_wait_mode", None)
        await query.edit_message_text(
            "📩 Надішліть ідентичне повідомлення (як шаблон), і бот видалить відповідну розсилку.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В меню розсилки", callback_data="admin_broadcast")]]),
        )
    
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

# ========== АДМІН ФУНКЦІЇ (реалізовано) ==========

def _fmt_user_ref(urow):
    username = (urow["username"] or "").strip() if urow["username"] else ""
    if username:
        return f"@{username}"
    return f"ID:{urow['user_id']}"


async def admin_stats_show_period(update: Update, context: ContextTypes.DEFAULT_TYPE, start_dt: datetime | None, end_dt: datetime | None):
    query = update.callback_query
    await query.answer()

    # Підготовка меж
    if start_dt is None:
        start_str = None
    else:
        start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S") if end_dt else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _count(sql: str, params: tuple):
        return db.cursor.execute(sql, params).fetchone()[0]

    where_events = "1=1"
    params_events: tuple = ()
    if start_str:
        where_events += " AND event_at >= ?"
        params_events = (start_str,)
    where_events += " AND event_at <= ?"
    params_events = (*params_events, end_str)

    # Для періоду рахуємо унікальних користувачів по фактах видачі у premium_subscriptions.
    # Так не буде "накрутки" через повторні події одного і того ж користувача.
    where_subs = "1=1"
    params_subs: tuple = ()
    if start_str:
        where_subs += " AND granted_at >= ?"
        params_subs = (start_str,)
    where_subs += " AND granted_at <= ?"
    params_subs = (*params_subs, end_str)

    giv_paid = _count(
        f"SELECT COUNT(DISTINCT user_id) FROM premium_subscriptions "
        f"WHERE subscription_type='paid' AND COALESCE(channel_id,'')='admin' AND {where_subs}",
        params_subs,
    )
    bought = _count(
        f"SELECT COUNT(DISTINCT user_id) FROM premium_subscriptions "
        f"WHERE (subscription_type='manual' OR (subscription_type='paid' AND COALESCE(channel_id,'')!='admin')) "
        f"AND {where_subs}",
        params_subs,
    )
    subs = _count(
        f"SELECT COUNT(DISTINCT user_id) FROM premium_subscriptions "
        f"WHERE subscription_type='channel' AND {where_subs}",
        params_subs,
    )
    removed = _count(
        f"SELECT COUNT(*) FROM premium_events WHERE event_type='remove' AND {where_events}",
        params_events,
    )

    # Учасники = нові користувачі за період
    if start_str:
        participants = db.cursor.execute(
            "SELECT COUNT(*) FROM users WHERE registered_at >= ? AND registered_at <= ?",
            (start_str, end_str),
        ).fetchone()[0]
    else:
        participants = db.cursor.execute(
            "SELECT COUNT(*) FROM users WHERE registered_at <= ?",
            (end_str,),
        ).fetchone()[0]

    groups_added = db.cursor.execute(
        f"SELECT COUNT(*) FROM bot_chat_events WHERE event_type='added' "
        f"AND chat_type IN ('group','supergroup','channel') AND {where_events}",
        params_events,
    ).fetchone()[0]
    bot_unsubscribed = db.cursor.execute(
        f"SELECT COUNT(*) FROM bot_chat_events WHERE event_type='removed' "
        f"AND chat_type = 'private' AND {where_events}",
        params_events,
    ).fetchone()[0]
    # Поточний синхронізований стан Premium (не історія подій).
    active_paid_now = db.cursor.execute(
        "SELECT COUNT(*) FROM premium_subscriptions "
        "WHERE is_active = 1 AND subscription_type = 'paid' "
        "AND expires_at IS NOT NULL AND expires_at >= CURRENT_TIMESTAMP"
    ).fetchone()[0]
    active_giv_now = db.cursor.execute(
        "SELECT COUNT(*) FROM premium_subscriptions "
        "WHERE is_active = 1 AND subscription_type = 'paid' "
        "AND COALESCE(channel_id,'')='admin' "
        "AND expires_at IS NOT NULL AND expires_at >= CURRENT_TIMESTAMP"
    ).fetchone()[0]
    active_buy_now = db.cursor.execute(
        "SELECT COUNT(*) FROM premium_subscriptions "
        "WHERE is_active = 1 AND (subscription_type='manual' "
        "OR (subscription_type='paid' AND COALESCE(channel_id,'')!='admin')) "
        "AND expires_at IS NOT NULL AND expires_at >= CURRENT_TIMESTAMP"
    ).fetchone()[0]
    active_sub_now = db.cursor.execute(
        "SELECT COUNT(*) FROM premium_subscriptions "
        "WHERE is_active = 1 AND subscription_type = 'channel' "
        "AND expires_at IS NOT NULL AND expires_at >= CURRENT_TIMESTAMP"
    ).fetchone()[0]
    active_premium_now = active_paid_now + active_sub_now
    total_users_now = db.cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    no_premium_now = max(total_users_now - active_premium_now, 0)

    text = (
        "📊 **Статистика за період**\n\n"
        f"Період: {start_str or 'з початку'} → {end_str}\n\n"
        f"👥 Нові підписники (реєстрації): {participants}\n"
        f"🏘 Додавань бота в групи/канали: {groups_added}\n"
        f"💎 Загальний Premium зараз: {active_premium_now}\n"
        f"💳 Куплено Premium (buy): {active_buy_now}\n"
        f"🎁 Видано Premium (give): {active_giv_now}\n"
        f"🔗 Підписок Premium (sub): {active_sub_now}\n"
        f"🗑 Втрачено / забрано Premium: {removed}\n"
        f"🆓 Без Premium зараз: {no_premium_now}\n"
        f"🚫 Відписки від бота: {bot_unsubscribed}\n"
    )

    keyboard = [[InlineKeyboardButton("◀️ До вибору періоду", callback_data="admin_stats_period_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    total_users = db.cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_subscribers = db.cursor.execute(
        "SELECT COUNT(*) FROM bot_chats WHERE chat_type = 'private' AND is_active = 1"
    ).fetchone()[0]
    if total_subscribers == 0:
        total_subscribers = total_users

    active_groups_channels = db.cursor.execute(
        "SELECT COUNT(*) FROM bot_chats WHERE chat_type IN ('group','supergroup','channel') AND is_active = 1"
    ).fetchone()[0]
    added_groups_channels_total = db.cursor.execute(
        "SELECT COUNT(*) FROM bot_chat_events WHERE event_type='added' AND chat_type IN ('group','supergroup','channel')"
    ).fetchone()[0]

    # Рахуємо поточний Premium по активних підписках, а не по історії premium_events.
    active_paid = db.cursor.execute(
        "SELECT COUNT(*) FROM premium_subscriptions "
        "WHERE is_active = 1 AND subscription_type = 'paid' "
        "AND expires_at IS NOT NULL AND expires_at >= CURRENT_TIMESTAMP"
    ).fetchone()[0]
    active_giv = db.cursor.execute(
        "SELECT COUNT(*) FROM premium_subscriptions "
        "WHERE is_active = 1 AND subscription_type='paid' "
        "AND COALESCE(channel_id,'')='admin' "
        "AND expires_at IS NOT NULL AND expires_at >= CURRENT_TIMESTAMP"
    ).fetchone()[0]
    active_buy = db.cursor.execute(
        "SELECT COUNT(*) FROM premium_subscriptions "
        "WHERE is_active = 1 AND (subscription_type='manual' "
        "OR (subscription_type='paid' AND COALESCE(channel_id,'')!='admin')) "
        "AND expires_at IS NOT NULL AND expires_at >= CURRENT_TIMESTAMP"
    ).fetchone()[0]
    active_sub = db.cursor.execute(
        "SELECT COUNT(*) FROM premium_subscriptions "
        "WHERE is_active = 1 AND subscription_type = 'channel' "
        "AND expires_at IS NOT NULL AND expires_at >= CURRENT_TIMESTAMP"
    ).fetchone()[0]
    premium_total = active_paid + active_sub
    no_premium_total = max(total_users - premium_total, 0)

    removed_total = db.cursor.execute(
        "SELECT COUNT(*) FROM premium_events WHERE event_type='remove'"
    ).fetchone()[0]

    text = (
        "📊 **Загальна статистика**\n\n"
        f"👥 Загальна кількість користувачів: {total_users}\n"
        f"🏘 Групи/канали з ботом: {active_groups_channels} активних, {added_groups_channels_total} додавань всього\n"
        f"💎 Активних Premium зараз: {premium_total}\n"
        f"🎁 Гів: {active_giv}\n"
        f"🔗 Саб: {active_sub}\n"
        f"💳 Бай: {active_buy}\n"
        f"🆓 Без Premium зараз: {no_premium_total}\n"
        f"🗑 Втрачено / забрано Premium: {removed_total}\n"
    )

    keyboard = [
        [InlineKeyboardButton("🗓 Переглянути за період", callback_data="admin_stats_period_menu")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def admin_stats_period_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🕐 За весь час", callback_data="admin_stats_range_all")],
        [InlineKeyboardButton("📅 За день", callback_data="admin_stats_range_day")],
        [InlineKeyboardButton("📆 За тиждень", callback_data="admin_stats_range_week")],
        [InlineKeyboardButton("🗓 За місяць", callback_data="admin_stats_range_month")],
        [InlineKeyboardButton("📘 За рік", callback_data="admin_stats_range_year")],
        [InlineKeyboardButton("✍️ Свій період", callback_data="admin_stats_range_custom")],
        [InlineKeyboardButton("◀️ До загальної статистики", callback_data="admin_stats")],
    ]

    await query.edit_message_text(
        "📊 **Статистика за період**\n\nОберіть період:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def handle_my_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логує додавання/видалення бота в чатах (включно з private block/unblock)."""
    cmu = update.my_chat_member
    if not cmu:
        return

    chat = cmu.chat
    old_status = cmu.old_chat_member.status
    new_status = cmu.new_chat_member.status

    was_active = old_status in {"member", "administrator", "creator", "restricted"}
    is_active = new_status in {"member", "administrator", "creator", "restricted"}

    if was_active == is_active:
        return

    event_type = "added" if is_active else "removed"
    db.log_bot_chat_event(chat.id, chat.type, event_type)


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Одразу відправляємо всіх користувачів без зайвих кнопок
    await admin_users_send_all(update, context)


async def admin_users_send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        return

    # Беремо всіх користувачів
    users = db.cursor.execute(
        "SELECT user_id, username, first_name, is_premium, premium_until FROM users ORDER BY registered_at DESC"
    ).fetchall()
    total_users = len(users)
    total_groups_channels = db.cursor.execute(
        "SELECT COUNT(*) FROM bot_chats WHERE chat_type IN ('group','supergroup','channel')"
    ).fetchone()[0]

    lines: list[str] = []
    chunk_size = 25

    def user_status(urow):
        uid = urow["user_id"]
        # перевіряємо активність Premium (щоб не показувати прострочений)
        if not urow["is_premium"] or not db.check_premium(uid):
            return "free"
        sub = db.cursor.execute(
            "SELECT subscription_type FROM premium_subscriptions WHERE user_id = ? AND is_active = 1 ORDER BY granted_at DESC LIMIT 1",
            (uid,),
        ).fetchone()
        st = sub["subscription_type"] if sub else None
        if st == "paid":
            return "paid"
        if st == "channel":
            return "sub"

        # Legacy-дані: інферимо з premium_events
        ev = db.cursor.execute(
            "SELECT event_type FROM premium_events "
            "WHERE user_id = ? AND event_type IN ('grant_paid','grant_channel') "
            "ORDER BY event_at DESC LIMIT 1",
            (uid,),
        ).fetchone()
        if not ev:
            # дефолт: вважаємо, що це sub (щоб не показувати paid без доказів)
            return "sub"
        if ev["event_type"] == "grant_paid":
            return "paid"
        if ev["event_type"] == "grant_channel":
            return "sub"
        return "sub"

    messages_sent = 0
    for i, u in enumerate(users):
        st = user_status(u)
        name = (u["first_name"] or "").strip()
        user_ref = _fmt_user_ref(u)
        premium_until = (u["premium_until"] or "").strip() if u["premium_until"] else ""
        if st == "free":
            line = f"{user_ref} {('- ' + name) if name else ''} — free"
        else:
            label = "гів" if st == "paid" else "sub"
            line = f"{user_ref} {('- ' + name) if name else ''} — {label} до {premium_until}"
        lines.append(line)

        if i == 0:
            header = (
                "👥 **Користувачі**\n\n"
                f"Загальна кількість користувачів: {total_users}\n"
                f"Кількість доданих груп/каналів: {total_groups_channels}\n\n"
                "Список:\n"
            )
            lines.insert(0, header)

        if (i + 1) % chunk_size == 0:
            await query.message.reply_text("\n".join(lines))
            messages_sent += 1
            lines = []

    if lines:
        if total_users == 0:
            lines = [
                "👥 **Користувачі**\n\n"
                f"Загальна кількість користувачів: {total_users}\n"
                f"Кількість доданих груп/каналів: {total_groups_channels}\n\n"
                "Список порожній."
            ]
        await query.message.reply_text("\n".join(lines))
        messages_sent += 1

    # без "Готово ..." повідомлення (щоб було менше шуму)


async def admin_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("⛔ Немає доступу.")
        return

    keyboard = [
        [InlineKeyboardButton("👥 Переглянути всіх з преміумом", callback_data="admin_premium_active_list_page_view_0")],
        [InlineKeyboardButton("🗑 Забрати преміум", callback_data="admin_premium_active_list_page_remove_0")],
        [InlineKeyboardButton("💳 Видати преміум (гів)", callback_data="admin_premium_input_grant_paid")],
        [InlineKeyboardButton("🔗 Канали Premium", callback_data="admin_premium_channels_manage")],
    ]
    try:
        await query.edit_message_text(
            "💎 Управління Premium. Оберіть дію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise


async def admin_premium_active_list_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
    mode: str = "view",
):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        return

    page_size = 12
    offset = page * page_size

    all_prem = db.cursor.execute(
        "SELECT user_id FROM users WHERE is_premium = 1 ORDER BY premium_until DESC"
    ).fetchall()
    user_ids = [int(r["user_id"]) for r in all_prem]

    # відфільтровуємо прострочені через check_premium
    active_users: list[int] = []
    for uid in user_ids:
        if db.check_premium(uid):
            active_users.append(uid)

    total = len(active_users)
    slice_ids = active_users[offset : offset + page_size]

    # сформуємо текст та кнопки
    lines: list[str] = []
    kb_rows: list[list[InlineKeyboardButton]] = []

    mode = (mode or "view").lower().strip()
    if mode not in {"view", "remove", "grant_paid", "grant_channel"}:
        mode = "view"

    for uid in slice_ids:
        u = db.get_user(uid)
        if not u:
            continue

        st_row = db.cursor.execute(
            "SELECT subscription_type FROM premium_subscriptions WHERE user_id = ? AND is_active = 1 ORDER BY granted_at DESC LIMIT 1",
            (uid,),
        ).fetchone()
        st = st_row["subscription_type"] if st_row else None

        if st == "paid":
            label = "гів"
        elif st == "channel":
            label = "sub"
        else:
            # Legacy-дані: інферимо через premium_events
            ev = db.cursor.execute(
                "SELECT event_type FROM premium_events "
                "WHERE user_id = ? AND event_type IN ('grant_paid','grant_channel') "
                "ORDER BY event_at DESC LIMIT 1",
                (uid,),
            ).fetchone()
            if not ev:
                label = "sub"
            elif ev["event_type"] == "grant_paid":
                label = "гів"
            else:
                label = "sub"

        ref = _fmt_user_ref(u)
        expires = (u["premium_until"] or "").strip() if u["premium_until"] else ""
        lines.append(f"{ref} — {label} до {expires}")

        # У різних режимах хочемо, щоб кнопка знімала неоднозначність:
        # - remove: кнопка = нік/ID, по кліку забираємо Premium
        # - grant_paid: кнопка = нік/ID, по кліку просимо скільки днів
        if mode == "remove":
            kb_rows.append([
                InlineKeyboardButton(
                    ref,
                    callback_data=f"admin_premium_remove_uid_{uid}_page_{page}",
                )
            ])
        elif mode == "grant_paid":
            kb_rows.append([
                InlineKeyboardButton(
                    ref,
                    callback_data=f"admin_premium_grant_paid_uid_{uid}_page_{page}",
                )
            ])
        elif mode == "grant_channel":
            kb_rows.append([
                InlineKeyboardButton(
                    ref,
                    callback_data=f"admin_premium_grant_channel_uid_{uid}_page_{page}",
                )
            ])
        else:
            # view: список тільки для перегляду, без кнопок дій по користувачах
            pass

    if not lines:
        await query.edit_message_text(
            "Немає активних Premium користувачів.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В Premium-меню", callback_data="admin_premium")]]),
        )
        return

    # У режимі перегляду залишаємо тільки кнопку повернення в Premium-меню.
    if mode == "view":
        kb_rows = [[InlineKeyboardButton("◀️ В Premium-меню", callback_data="admin_premium")]]
    else:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"admin_premium_active_list_page_{mode}_{page-1}"))
        if offset + page_size < total:
            nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"admin_premium_active_list_page_{mode}_{page+1}"))
        if nav:
            kb_rows.append(nav)
        kb_rows.append([InlineKeyboardButton("◀️ В Premium-меню", callback_data="admin_premium")])

    text = "👥 **Активні Premium**\n\n" + "\n".join(lines) + f"\n\nСторінка: {page+1}"
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb_rows))
    except BadRequest as e:
        # Натискання "◀️ В Premium-меню" з цієї ж сторінки може дати ідентичний контент.
        if "Message is not modified" not in str(e):
            raise


async def admin_premium_channels_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        return

    channels = db.cursor.execute(
        "SELECT id, link, title FROM premium_channels ORDER BY id ASC"
    ).fetchall()

    if not channels:
        text = "🔗 **Канали Premium**\n\nПоки що немає доданих каналів."
    else:
        lines = ["🔗 **Канали Premium**\n"]
        for ch in channels:
            title = (ch["title"] or "").strip()
            if title:
                lines.append(f"- {ch['id']}: {title} ({ch['link']})")
            else:
                lines.append(f"- {ch['id']}: {ch['link']}")
        text = "\n".join(lines)

    keyboard = [
        [InlineKeyboardButton("➕ Додати посилання", callback_data="admin_premium_add_link")],
        [InlineKeyboardButton("◀️ В Premium-меню", callback_data="admin_premium")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_premium_add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок послідовного додавання link -> title (Premium channels)."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.edit_message_text("⛔ Немає доступу.")
        return

    context.user_data["admin_premium_awaiting_link"] = True
    context.user_data.pop("admin_premium_pending_link", None)
    context.user_data["admin_premium_awaiting_title"] = False

    await query.edit_message_text(
        "1) Надішліть link Premium-каналу.\n"
        "Підійде `@username` або `t.me/username`.\n\n"
        "Натисніть /admin ще раз, якщо заплутаєтесь, або просто надішліть посилання.",
        reply_markup=None,
    )

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Масові розсилки"""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("admin_broadcast_wait_mode", None)
    context.user_data.pop("admin_broadcast_wait_user", None)
    context.user_data.pop("admin_broadcast_target_user", None)
    context.user_data.pop("admin_broadcast_delete_by_sample", None)

    text = (
        "📢 **Розсилка**\n\n"
        "Оберіть тип розсилки або видалення повідомлень."
    )

    keyboard = [
        [InlineKeyboardButton("📨 Відправити всім", callback_data="admin_broadcast_all")],
        [InlineKeyboardButton("👤 Відправити певному користувачу", callback_data="admin_broadcast_one_user")],
        [InlineKeyboardButton("🔔 Розсилка підписникам бота", callback_data="admin_broadcast_subs")],
        [InlineKeyboardButton("👥 Розсилка по групах/каналах", callback_data="admin_broadcast_groups")],
        [InlineKeyboardButton("🗑 Видалити повідомлення", callback_data="admin_broadcast_delete_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

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
        "Надіслати: Весь альбом",
        "Надіслати: Останні",
        "Надіслати: Перші",
        "Надіслати: Проміжок",
        "Надіслати: За датою"
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

    # Адмін‑панель: обробляємо текст першою, якщо активна
    from admin import handle_admin_text
    if await handle_admin_text(update, context):
        return True

    # Якщо користувач натискає кнопки спільного альбому, але прапорець shared_album_active
    # з якихось причин злетів — відновлюємо стан з того, що вже є в user_data.
    SHARED_MENU_BUTTONS = {
        "📤 Надіслати весь альбом",
        "⏳ Надіслати останні",
        "⏮ Надіслати перші",
        "🔢 Надіслати проміжок",
        "📅 Надіслати за датою",
        "⋯ Додаткові опції",
        "◀️ Вийти з альбому",
        "◀️ Назад до альбому",
        "◀️ Назад до додаткових опцій",
    }
    if text in SHARED_MENU_BUTTONS and ud.get('current_shared_album') and not ud.get('shared_album_active'):
        ud['shared_album_active'] = True
        if not ud.get('shared_access_level'):
            try:
                row = db.cursor.execute(
                    "SELECT access_level FROM shared_albums WHERE album_id = ? AND user_id = ?",
                    (ud.get('current_shared_album'), update.effective_user.id)
                ).fetchone()
                if row and row.get('access_level'):
                    ud['shared_access_level'] = row['access_level']
            except Exception:
                pass
    
    # --- 1. ПРІОРИТЕТНА НАВІГАЦІЯ (ОБРОБКА ТОГО, ЩО ПРИЙШЛО З GROUP 1) ---
    if text == "◀️ Назад до альбому":
        print(f"✅ Головний обробник: повертаємось до альбому з тексту '{text}'")
        
        # Миттєво чистимо ВСІ режими, щоб бот "протверезів"
        states_to_reset = [
            'in_delete_menu', 'in_additional_menu', 
            'delete_awaiting_recent', 'delete_awaiting_first', 
            'delete_awaiting_range', 'delete_awaiting_date',
            'delete_action', 'awaiting_delete_input',
            'awaiting_recent_count', 'awaiting_first_count',
            'awaiting_range', 'awaiting_date',
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
                # Звичайний особистий альбом: використовуємо локальну функцію
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
    if ud.get('awaiting_shared_note_folder_name'): return await handle_shared_note_folder_name(update, context)
    if ud.get('awaiting_note_folder_name'): return await handle_note_folder_name(update, context)
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
            res = await shared_handle_remove_selection(update, context)
            if res:
                return True
            
        if ud.get('shared_in_role_selection'):
            res = await shared_handle_role_text_input(update, context)
            if res:
                return True
            
        if ud.get('shared_in_members_main'):
            res = await shared_handle_members_navigation(update, context)
            if res:
                return True
        
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

    # --- 8. МОЇ НОТАТКИ ---
    if ud.get('note_folder_active') or ud.get('current_note_folder'):
        res = await handle_note_folder_buttons(update, context)
        if res:
            return True

    # --- 9. СПІЛЬНІ НОТАТКИ ---
    if ud.get('shared_note_active') or ud.get('current_shared_note_folder'):
        res = await handle_shared_note_buttons(update, context)
        if res:
            return True

    return False

async def handle_all_files_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Єдиний вхід для всіх медіа"""
    ud = context.user_data

    # Адмінська розсилка: якщо очікуємо шаблон повідомлення (будь-який формат),
    # обробляємо медіа тут до альбомної логіки.
    if await handle_admin_broadcast_message(update, context):
        return True

    # Нотатки: фото з підписом зберігаємо як запис
    if context.user_data.get('shared_note_active'):
        if await handle_shared_note_media(update, context):
            return True
    if context.user_data.get('note_folder_active'):
        if await handle_note_media(update, context):
            return True
    
    # 1. Пріоритет спільним альбомам (якщо юзер зайшов у спільний)
    if ud.get('shared_album_active'):
        # Важливо: функція shared_handle_file має бути імпортована!
        return await shared_handle_file(update, context)
    
    # 2. Особисті альбоми
    if ud.get('current_album') or ud.get('album_keyboard_active'):
        return await handle_file(update, context)
    
    # 3. Фолбек
    await update.message.reply_text("⚠️ Для медіа відкрийте альбом. Для нотаток: надсилайте текст або фото з підписом у папці нотаток.")
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
    application.add_handler(CommandHandler("admin", admin_start))
    application.add_handler(ChatMemberHandler(handle_my_chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(CallbackQueryHandler(handle_premium_callback, pattern="^premium_"))
    application.add_handler(CallbackQueryHandler(callback_handler))

    print("🚀 Маршрутизатори оновлені. Запускаємося!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
if __name__ == '__main__':
    main()