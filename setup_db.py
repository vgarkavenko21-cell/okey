from db_models import Database

def setup_indexes():
    """Створення індексів для прискорення запитів"""
    db = Database()
    
    # Індекси для швидкого пошуку
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_users_premium ON users(is_premium)",
        "CREATE INDEX IF NOT EXISTS idx_albums_user ON albums(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_albums_archived ON albums(is_archived)",
        "CREATE INDEX IF NOT EXISTS idx_files_album ON files(album_id)",
        "CREATE INDEX IF NOT EXISTS idx_files_date ON files(added_at)",
        "CREATE INDEX IF NOT EXISTS idx_shared_album_user ON shared_albums(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id)",
    ]
    
    for index in indexes:
        try:
            db.cursor.execute(index)
        except:
            pass
    
    db.conn.commit()
    db.close()

if __name__ == "__main__":
    setup_indexes()