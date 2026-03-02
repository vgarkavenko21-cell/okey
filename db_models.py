import sqlite3
import json
from datetime import datetime
from config import DATABASE_NAME

class Database:
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.connect()
        self.create_tables()
    
    def connect(self):
        """Підключення до SQLite БД"""
        self.conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Дозволяє звертатись по назві колонок
        self.cursor = self.conn.cursor()
        # Включаємо підтримку зовнішніх ключів
        self.cursor.execute("PRAGMA foreign_keys = ON")
    
    def create_tables(self):
        """Створення всіх таблиць згідно ТЗ"""
        
        # Таблиця користувачів
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_premium BOOLEAN DEFAULT 0,
                premium_until TIMESTAMP,
                privacy_settings TEXT DEFAULT '{"allow_invites": "all", "allow_add_to_shared": true, "allow_add_to_shared_notes": true}',
                is_blocked BOOLEAN DEFAULT 0
            )
        ''')
        
        # Таблиця альбомів
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS albums (
                album_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_archived BOOLEAN DEFAULT 0,
                is_shared BOOLEAN DEFAULT 0,
                files_count INTEGER DEFAULT 0,
                last_file_added TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        ''')
        
        # Таблиця файлів (тільки file_id, самі файли не зберігаємо!)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                album_id INTEGER NOT NULL,
                telegram_file_id TEXT NOT NULL,
                file_type TEXT CHECK(file_type IN ('photo', 'video', 'document', 'audio', 'voice', 'circle')),
                file_name TEXT,
                file_size INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                added_by INTEGER,
                FOREIGN KEY (album_id) REFERENCES albums (album_id) ON DELETE CASCADE,
                FOREIGN KEY (added_by) REFERENCES users (user_id)
            )
        ''')
        
        # Таблиця спільних альбомів (учасники)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS shared_albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                album_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                access_level TEXT CHECK(access_level IN ('view', 'add', 'full')) DEFAULT 'view',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (album_id) REFERENCES albums (album_id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                UNIQUE(album_id, user_id)
            )
        ''')
        
        # Таблиця нотаток
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_shared BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        ''')
        
        # Таблиця спільних нотаток
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS shared_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                access_level TEXT CHECK(access_level IN ('view', 'edit')) DEFAULT 'view',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (note_id) REFERENCES notes (note_id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                UNIQUE(note_id, user_id)
            )
        ''')
        
        # Таблиця преміум підписок
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS premium_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subscription_type TEXT CHECK(subscription_type IN ('channel', 'paid', 'manual')),
                channel_id TEXT,
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        ''')
        
        # Таблиця для архівації (додатково, для зручності)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS archive_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                album_id INTEGER,
                user_id INTEGER,
                action TEXT CHECK(action IN ('archive', 'unarchive')),
                action_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (album_id) REFERENCES albums (album_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        self.conn.commit()
        print("✅ Таблиці SQLite успішно створені")
    
    # ========== МЕТОДИ ДЛЯ РОБОТИ З КОРИСТУВАЧАМИ ==========
    
    def register_user(self, user_id, username, first_name, last_name):
        """Реєстрація нового користувача"""
        try:
            self.cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, registered_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, username, first_name, last_name))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Помилка реєстрації: {e}")
            return False
    
    def get_user(self, user_id):
        """Отримати дані користувача"""
        return self.cursor.execute(
            "SELECT * FROM users WHERE user_id = ?", 
            (user_id,)
        ).fetchone()
    
    # ========== МЕТОДИ ДЛЯ РОБОТИ З АЛЬБОМАМИ ==========
    
    def create_album(self, user_id, name):
        """Створення нового альбому"""
        self.cursor.execute('''
            INSERT INTO albums (user_id, name, created_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, name))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_user_albums(self, user_id, include_archived=False):
        """Отримати список альбомів користувача"""
        query = "SELECT * FROM albums WHERE user_id = ?"
        if not include_archived:
            query += " AND is_archived = 0"
        query += " ORDER BY created_at DESC"
        
        return self.cursor.execute(query, (user_id,)).fetchall()
    
    def get_album(self, album_id):
        """Отримати дані альбому"""
        return self.cursor.execute(
            "SELECT * FROM albums WHERE album_id = ?", 
            (album_id,)
        ).fetchone()
    
    def archive_album(self, album_id, user_id):
        """Архівувати альбом"""
        self.cursor.execute(
            "UPDATE albums SET is_archived = 1 WHERE album_id = ?",
            (album_id,)
        )
        # Логуємо архівацію
        self.cursor.execute('''
            INSERT INTO archive_log (album_id, user_id, action)
            VALUES (?, ?, 'archive')
        ''', (album_id, user_id))
        self.conn.commit()
    
    def unarchive_album(self, album_id, user_id):
        """Розархівувати альбом"""
        self.cursor.execute(
            "UPDATE albums SET is_archived = 0 WHERE album_id = ?",
            (album_id,)
        )  
        # Логуємо розархівацію
        self.cursor.execute('''
        INSERT INTO archive_log (album_id, user_id, action)
        VALUES (?, ?, 'unarchive')
        ''', (album_id, user_id))
        self.conn.commit()



# === ВСТАВЛЯТИ СЮДИ (після unarchive_album) ===

    def delete_album(self, album_id):
        """Видалити альбом з усіма файлами та зв'язками"""
        try:
            album_id = int(album_id) # Гарантуємо, що це число
            
            # 1. Видаляємо всі файли альбому
            self.cursor.execute("DELETE FROM files WHERE album_id = ?", (album_id,))
            
            # 2. Видаляємо лог архівації (якщо альбом колись архівувався)
            try:
                self.cursor.execute("DELETE FROM archive_log WHERE album_id = ?", (album_id,))
            except:
                pass 
                
            # 3. Видаляємо зі спільних альбомів (якщо вони є у твоїй структурі)
            try:
                self.cursor.execute("DELETE FROM shared_albums WHERE album_id = ?", (album_id,))
            except:
                pass
                
            # 4. Видаляємо сам альбом
            self.cursor.execute("DELETE FROM albums WHERE album_id = ?", (album_id,))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Помилка БД при видаленні альбому {album_id}: {e}")
            self.conn.rollback()
            return False

    # ============================================
    
    # ВИПРАВЛЕНО: Додано правильні відступи (4 пробіли), щоб метод був усередині класу
    
    
    # ========== МЕТОДИ ДЛЯ РОБОТИ З ФАЙЛАМИ ==========
    
    def add_file(self, album_id, telegram_file_id, file_type, file_name=None, file_size=None, added_by=None):
        """Додати файл до альбому (зберігаємо тільки file_id!)"""
        self.cursor.execute('''
            INSERT INTO files (album_id, telegram_file_id, file_type, file_name, file_size, added_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (album_id, telegram_file_id, file_type, file_name, file_size, added_by))
        
        # Оновлюємо лічильник файлів в альбомі
        self.cursor.execute('''
            UPDATE albums 
            SET files_count = files_count + 1,
                last_file_added = CURRENT_TIMESTAMP
            WHERE album_id = ?
        ''', (album_id,))
        
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_album_files(self, album_id, limit=None, order='ASC'):
        """Отримати файли з альбому
        order: 'ASC' - від найстаріших до найновіших (хронологічно)
           'DESC' - від найновіших до найстаріших
        """
        query = "SELECT * FROM files WHERE album_id = ? ORDER BY added_at " + order
        if limit:
            query += f" LIMIT {limit}"
    
        return self.cursor.execute(query, (album_id,)).fetchall()
    
    def get_files_by_date(self, album_id, date):
        """Отримати файли за конкретну дату"""
        return self.cursor.execute('''
            SELECT * FROM files 
            WHERE album_id = ? AND DATE(added_at) = DATE(?)
            ORDER BY added_at DESC
        ''', (album_id, date)).fetchall()
    
    def delete_file(self, file_id):
        """Видалити файл"""
        # Спочатку отримуємо album_id
        file = self.cursor.execute(
            "SELECT album_id FROM files WHERE file_id = ?", 
            (file_id,)
        ).fetchone()
        
        if file:
            # Видаляємо файл
            self.cursor.execute(
                "DELETE FROM files WHERE file_id = ?", 
                (file_id,)
            )
            # Оновлюємо лічильник
            self.cursor.execute('''
                UPDATE albums 
                SET files_count = files_count - 1 
                WHERE album_id = ?
            ''', (file['album_id'],))
            
            self.conn.commit()
            return True
        return False
    
    # ========== МЕТОДИ ДЛЯ ПРЕМІУМ ==========
    
    def set_premium(self, user_id, expires_at=None):
        """Встановити преміум статус"""
        self.cursor.execute('''
            UPDATE users 
            SET is_premium = 1, premium_until = ?
            WHERE user_id = ?
        ''', (expires_at, user_id))
        self.conn.commit()
    
    def remove_premium(self, user_id):
        """Забрати преміум статус"""
        self.cursor.execute('''
            UPDATE users 
            SET is_premium = 0, premium_until = NULL
            WHERE user_id = ?
        ''', (user_id,))
        self.conn.commit()
    
    def check_premium(self, user_id):
        """Перевірити чи активний преміум"""
        user = self.get_user(user_id)
        if not user or not user['is_premium']:
            return False
        
        # Перевіряємо термін дії
        if user['premium_until']:
            from datetime import datetime
            try:
                expires = datetime.strptime(user['premium_until'], '%Y-%m-%d %H:%M:%S')
                if expires < datetime.now():
                    # Термін вийшов
                    self.remove_premium(user_id)
                    return False
            except:
                pass
        
        return True
    
    def close(self):
        """Закриття з'єднання з БД"""
        if self.conn:
            self.conn.close()