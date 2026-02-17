from datetime import datetime
import json
from typing import Optional

def format_date(date_str):
    """Форматування дати для відображення"""
    if not date_str:
        return "ніколи"
    
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        return date.strftime('%d.%m.%Y %H:%M')
    except:
        return date_str

def get_file_emoji(file_type):
    """Отримати емодзі для типу файлу"""
    emojis = {
        'photo': '📷',
        'video': '🎥',
        'document': '📄',
        'audio': '🎵',
        'voice': '🎤',
        'circle': '🔄'
    }
    return emojis.get(file_type, '📁')

def check_user_limit(db, user_id, limit_type):
    """Перевірка лімітів користувача"""
    from config import FREE_LIMITS
    
    # Перевіряємо чи користувач Premium
    user = db.cursor.execute(
        "SELECT is_premium FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    
    if user and user['is_premium']:
        return True  # Для Premium лімітів немає
    
    # Підрахунок кількості
    counts = {
        'albums': "SELECT COUNT(*) FROM albums WHERE user_id = ? AND is_archived = 0",
        'shared_albums': "SELECT COUNT(*) FROM shared_albums WHERE user_id = ?",
        'notes': "SELECT COUNT(*) FROM notes WHERE user_id = ?",
        'shared_notes': "SELECT COUNT(*) FROM shared_notes WHERE user_id = ?"
    }
    
    if limit_type in counts:
        count = db.cursor.execute(counts[limit_type], (user_id,)).fetchone()[0]
        return count < FREE_LIMITS.get(limit_type, 0)
    
    return True

def get_privacy_settings(db, user_id):
    """Отримати налаштування приватності"""
    result = db.cursor.execute(
        "SELECT privacy_settings FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    
    if result and result['privacy_settings']:
        return json.loads(result['privacy_settings'])
    
    from config import DEFAULT_PRIVACY
    return DEFAULT_PRIVACY

def save_privacy_settings(db, user_id, settings):
    """Зберегти налаштування приватності"""
    db.cursor.execute(
        "UPDATE users SET privacy_settings = ? WHERE user_id = ?",
        (json.dumps(settings), user_id)
    )
    db.conn.commit()