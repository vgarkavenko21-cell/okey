import os
# Прибираємо dotenv якщо не використовуєте
# from dotenv import load_dotenv

# Завантажуємо змінні оточення (якщо будете використовувати .env файл)
# load_dotenv()

# Токен бота (ваш)
BOT_TOKEN = "7311015667:AAEop3uG9tpriZXS7YXV7cRg_yPRYAakcyc"

# ID адміністратора (ви)
ADMIN_IDS = [523651165]

# Назва БД
DATABASE_NAME = "media_bot.db"

# Ліміти для безкоштовних користувачів
FREE_LIMITS = {
    "albums": 3,
    "shared_albums": 3,
    "notes": 3,
    "shared_notes": 3
}

# Налаштування за замовчуванням
DEFAULT_PRIVACY = {
    "allow_invites": "all",  # all, contacts, nobody
    "allow_add_to_shared": True,
    "allow_add_to_shared_notes": True
}

# Шляхи до файлів (якщо будете зберігати щось тимчасово)
TEMP_DIR = "temp"

# Створюємо тимчасову папку якщо її немає
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)