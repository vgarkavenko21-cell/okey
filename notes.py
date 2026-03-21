from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

import helpers
from db_models import Database

db = Database()


def ensure_notes_tables() -> None:
    db.cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS note_folders (
            folder_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_archived BOOLEAN DEFAULT 0,
            is_shared BOOLEAN DEFAULT 0,
            entries_count INTEGER DEFAULT 0,
            last_entry_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
            UNIQUE(user_id, name)
        )
        '''
    )
    db.cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS note_entries (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (folder_id) REFERENCES note_folders (folder_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        )
        '''
    )
    db.cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS shared_note_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            access_level TEXT CHECK(access_level IN ('owner', 'admin', 'editor', 'contributor', 'viewer')),
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (folder_id) REFERENCES note_folders (folder_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
            UNIQUE(folder_id, user_id)
        )
        '''
    )
    db.cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS note_entry_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            telegram_file_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (entry_id) REFERENCES note_entries (entry_id) ON DELETE CASCADE
        )
        '''
    )
    db.conn.commit()


ensure_notes_tables()

NOTES_MAIN_BUTTONS = {
    "📷 Мої альбоми", "👥 Спільні альбоми", "📝 Мої нотатки", "🤝 Спільні нотатки", "⚙️ Налаштування",
}
NOTES_FOLDER_BUTTONS = {
    "📤 Надіслати всю папку", "⏳ Надіслати останні", "⏮ Надіслати перші",
    "🔢 Надіслати проміжок", "📅 Надіслати за датою", "⋯ Додаткові дії", "◀️ Вийти з папки",
    "ℹ️ Інформація папки", "🗑 Видалити запис", "🗂 Архівувати папку", "🔥 Видалити папку",
    "📦 Зробити спільною", "◀️ Назад до папки",
    "Надіслати: Весь альбом", "Надіслати: Останні", "Надіслати: Перші",
    "Надіслати: Проміжок", "Надіслати: За датою",
}


def notes_folder_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📤 Надіслати всю папку")],
            [KeyboardButton("⏳ Надіслати останні"), KeyboardButton("⏮ Надіслати перші")],
            [KeyboardButton("🔢 Надіслати проміжок"), KeyboardButton("📅 Надіслати за датою")],
            [KeyboardButton("⋯ Додаткові дії")],
            [KeyboardButton("◀️ Вийти з папки")],
        ],
        resize_keyboard=True,
    )


def notes_additional_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("ℹ️ Інформація папки"), KeyboardButton("📦 Зробити спільною")],
            [KeyboardButton("🗑 Видалити запис"), KeyboardButton("🗂 Архівувати папку")],
            [KeyboardButton("🔥 Видалити папку")],
            [KeyboardButton("◀️ Назад до папки")],
        ],
        resize_keyboard=True,
    )


def notes_delete_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Надіслати: Весь альбом")],
            [KeyboardButton("Надіслати: Останні"), KeyboardButton("Надіслати: Перші")],
            [KeyboardButton("Надіслати: Проміжок"), KeyboardButton("Надіслати: За датою")],
            [KeyboardButton("◀️ Назад до папки")],
        ],
        resize_keyboard=True,
    )


def _is_manual_note_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t.startswith("/"):
        return False
    if t in NOTES_MAIN_BUTTONS or t in NOTES_FOLDER_BUTTONS:
        return False
    return True


def _format_entry_line(idx: int, row, show_number: bool, show_date: bool) -> str:
    title = (row["title"] or "Запис").strip()
    dt = row["created_at"]
    parts = []
    if show_number:
        parts.append(f"#{idx}")
    parts.append(title)
    if show_date and dt:
        parts.append(f"({helpers.format_date(dt)})")
    return " ".join(parts)


async def show_my_notes(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_notes_tables()

    folders = db.cursor.execute(
        "SELECT * FROM note_folders WHERE user_id = ? AND is_archived = 0 ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()

    if not folders:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Створити папку", callback_data="notes_create")],
            [InlineKeyboardButton("🗂 Архів папок", callback_data="notes_archived")],
        ])
        await update.message.reply_text(
            "📝 У вас ще немає папок з нотатками.",
            reply_markup=kb,
        )
        return

    lines = ["📝 **Мої нотатки**"]
    kb_rows = []
    for f in folders:
        kb_rows.append([InlineKeyboardButton(f"{f['name']} ({f['entries_count']})", callback_data=f"notes_open_{f['folder_id']}")])

    kb_rows.append([
        InlineKeyboardButton("➕ Створити", callback_data="notes_create"),
        InlineKeyboardButton("🗂 Архів", callback_data="notes_archived"),
    ])

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(kb_rows),
        parse_mode="Markdown",
    )


async def notes_create_start(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    user_id = q.from_user.id
    if not helpers.check_user_limit(db, user_id, "notes"):
        await q.edit_message_text("❌ Ліміт папок нотаток без Premium досягнуто.")
        return

    context.user_data["awaiting_note_folder_name"] = True
    await q.edit_message_text("📝 Введіть назву нової папки нотаток:")


async def notes_show_archived(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    rows = db.cursor.execute(
        "SELECT * FROM note_folders WHERE user_id = ? AND is_archived = 1 ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    if not rows:
        await q.edit_message_text(
            "🗂 Архів порожній.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="notes_back")]]),
        )
        return

    kb = [[InlineKeyboardButton(f"♻️ {r['name']}", callback_data=f"notes_unarchive_{r['folder_id']}")] for r in rows]
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="notes_back")])
    await q.edit_message_text("🗂 **Архів папок**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def notes_back_to_list(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    folders = db.cursor.execute(
        "SELECT * FROM note_folders WHERE user_id = ? AND is_archived = 0 ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    kb = [[InlineKeyboardButton(f["name"], callback_data=f"notes_open_{f['folder_id']}")] for f in folders]
    kb.append([InlineKeyboardButton("➕ Створити", callback_data="notes_create"), InlineKeyboardButton("🗂 Архів", callback_data="notes_archived")])
    await q.edit_message_text("📝 **Мої нотатки**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def notes_open_folder(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    folder_id = int(q.data.split("_")[-1])
    user_id = q.from_user.id

    folder = db.cursor.execute(
        "SELECT * FROM note_folders WHERE folder_id = ? AND user_id = ?",
        (folder_id, user_id),
    ).fetchone()
    if not folder:
        await q.edit_message_text("❌ Папку не знайдено.")
        return

    context.user_data["current_note_folder"] = folder_id
    context.user_data["note_folder_active"] = True
    context.user_data.pop("note_additional", None)

    await q.message.reply_text(
        f"📝 **{folder['name']}**\n"
        f"└ Записів: {folder['entries_count']}",
        parse_mode="Markdown",
    )
    await q.message.reply_text(
        "Надсилайте записи в цей чат, вони автоматично збережуться в папку.",
        reply_markup=notes_folder_keyboard(),
    )


async def handle_note_folder_name(update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("awaiting_note_folder_name"):
        return False

    name = (update.message.text or "").strip()
    user_id = update.effective_user.id
    if not _is_manual_note_text(name) or len(name) < 2:
        await update.message.reply_text("❌ Введіть коректну назву папки (мінімум 2 символи).")
        return True

    exists = db.cursor.execute(
        "SELECT 1 FROM note_folders WHERE user_id = ? AND lower(name) = lower(?)",
        (user_id, name),
    ).fetchone()
    if exists:
        await update.message.reply_text("❌ Папка з такою назвою вже існує.")
        return True

    db.cursor.execute(
        "INSERT INTO note_folders (user_id, name, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (user_id, name),
    )
    folder_id = db.cursor.lastrowid
    db.conn.commit()

    context.user_data["awaiting_note_folder_name"] = False
    context.user_data["current_note_folder"] = folder_id
    context.user_data["note_folder_active"] = True

    await update.message.reply_text(
        f"✅ Папку '{name}' успішно створено!\n\n"
        f"📝 **{name}**\n"
        f"└ Записів: 0",
        parse_mode="Markdown",
    )
    await update.message.reply_text(
        "Надсилайте записи в цей чат, вони автоматично збережуться в папку.",
        reply_markup=notes_folder_keyboard(),
    )
    return True


async def _save_note_entry(folder_id: int, user_id: int, text: str) -> int:
    title = text.strip().split("\n", 1)[0][:60] or "Новий запис"
    db.cursor.execute(
        "INSERT INTO note_entries (folder_id, user_id, title, content, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (folder_id, user_id, title, text),
    )
    entry_id = db.cursor.lastrowid
    db.cursor.execute(
        "UPDATE note_folders SET entries_count = entries_count + 1, last_entry_at = CURRENT_TIMESTAMP WHERE folder_id = ?",
        (folder_id,),
    )
    db.conn.commit()
    return entry_id


async def _save_note_entry_with_photo(folder_id: int, user_id: int, text: str, photo_file_id: str) -> int:
    title = text.strip().split("\n", 1)[0][:60] or "Новий запис"
    db.cursor.execute(
        "INSERT INTO note_entries (folder_id, user_id, title, content, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (folder_id, user_id, title, text),
    )
    entry_id = db.cursor.lastrowid
    db.cursor.execute(
        "UPDATE note_folders SET entries_count = entries_count + 1, last_entry_at = CURRENT_TIMESTAMP WHERE folder_id = ?",
        (folder_id,),
    )
    db.cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS note_entry_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            telegram_file_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (entry_id) REFERENCES note_entries (entry_id) ON DELETE CASCADE
        )
        '''
    )
    db.cursor.execute(
        "INSERT INTO note_entry_photos (entry_id, telegram_file_id) VALUES (?, ?)",
        (entry_id, photo_file_id),
    )
    db.conn.commit()
    return entry_id


def _entries_for_folder(folder_id: int):
    return db.cursor.execute(
        "SELECT * FROM note_entries WHERE folder_id = ? ORDER BY created_at ASC",
        (folder_id,),
    ).fetchall()


async def _send_entries(update, context, folder_id: int, entries, title: str):
    ensure_notes_tables()
    settings = helpers.get_user_display_settings(db, update.effective_user.id)
    show_number = settings.get("show_number", True)
    show_date = settings.get("show_date", True)

    if not entries:
        await update.message.reply_text("📭 У папці немає записів.")
        return True

    for i, e in enumerate(entries, start=1):
        footer_parts = []
        if show_number:
            footer_parts.append(f"📄 Запис #{i}")
        if show_date and e["created_at"]:
            try:
                d = datetime.strptime(e["created_at"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
            except Exception:
                d = str(e["created_at"])[:10]
            footer_parts.append(f"📅 {d}")
        footer = " | ".join(footer_parts) if footer_parts else None
        try:
            photo_row = db.cursor.execute(
                "SELECT telegram_file_id FROM note_entry_photos WHERE entry_id = ? ORDER BY id DESC LIMIT 1",
                (e["entry_id"],),
            ).fetchone()
        except Exception:
            photo_row = None
        if photo_row:
            text_out = e["content"]
            if footer:
                text_out = f"{text_out}\n\n{footer}"
            # Щоб запис завжди йшов одним повідомленням, підганяємо під ліміт caption.
            if len(text_out) > 1024:
                text_out = text_out[:1021] + "..."
            await update.message.reply_photo(
                photo=photo_row["telegram_file_id"],
                caption=text_out,
            )
        else:
            text_out = e["content"]
            if footer:
                text_out = f"{text_out}\n\n{footer}"
            await update.message.reply_text(text_out)
    return True


async def _send_entry_for_deletion(update, entry_row, index: int):
    photo_row = None
    try:
        photo_row = db.cursor.execute(
            "SELECT telegram_file_id FROM note_entry_photos WHERE entry_id = ? ORDER BY id DESC LIMIT 1",
            (entry_row["entry_id"],),
        ).fetchone()
    except Exception:
        photo_row = None

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"🗑 Видалити запис #{index}", callback_data=f"note_askdel_{entry_row['entry_id']}")]]
    )
    content = entry_row["content"]
    if photo_row:
        if len(content) > 1024:
            content = content[:1021] + "..."
        await update.message.reply_photo(photo=photo_row["telegram_file_id"], caption=content, reply_markup=kb)
    else:
        await update.message.reply_text(content, reply_markup=kb)


async def handle_note_folder_buttons(update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("note_folder_active"):
        return False

    text = update.message.text
    folder_id = context.user_data.get("current_note_folder")
    user_id = update.effective_user.id
    if not folder_id:
        return False

    folder = db.cursor.execute("SELECT * FROM note_folders WHERE folder_id = ?", (folder_id,)).fetchone()
    if not folder:
        await update.message.reply_text("❌ Папку не знайдено.")
        return True

    if text == "◀️ Вийти з папки":
        context.user_data["note_folder_active"] = False
        context.user_data.pop("current_note_folder", None)
        context.user_data.pop("note_additional", None)
        context.user_data.pop("note_in_delete_menu", None)
        context.user_data.pop("note_del_await_recent", None)
        context.user_data.pop("note_del_await_first", None)
        context.user_data.pop("note_del_await_range", None)
        context.user_data.pop("note_del_await_date", None)
        await show_my_notes(update, context)
        return True

    if context.user_data.get("awaiting_note_folder_name_confirm"):
        context.user_data["awaiting_note_folder_name_confirm"] = False
        deleting_id = context.user_data.pop("deleting_note_folder", None)
        if not deleting_id:
            await update.message.reply_text("❌ Не знайдено папку для видалення.")
            return True
        row = db.cursor.execute(
            "SELECT name FROM note_folders WHERE folder_id = ? AND user_id = ?",
            (deleting_id, user_id),
        ).fetchone()
        if not row:
            await update.message.reply_text("❌ Папку не знайдено.")
            return True
        if text.strip() != row["name"]:
            await update.message.reply_text("❌ Назва не співпадає. Видалення скасовано.")
            return True
        db.cursor.execute("DELETE FROM note_folders WHERE folder_id = ? AND user_id = ?", (deleting_id, user_id))
        db.conn.commit()
        context.user_data["note_folder_active"] = False
        context.user_data.pop("current_note_folder", None)
        context.user_data.pop("note_additional", None)
        context.user_data.pop("note_in_delete_menu", None)
        await update.message.reply_text("🔥 Папку видалено.")
        return True

    if text == "📤 Надіслати всю папку":
        return await _send_entries(update, context, folder_id, _entries_for_folder(folder_id), f"Вся папка '{folder['name']}'")

    if text == "⏳ Надіслати останні":
        context.user_data["awaiting_note_recent_count"] = True
        await update.message.reply_text("Введіть кількість останніх записів:")
        return True

    if context.user_data.get("awaiting_note_recent_count"):
        context.user_data["awaiting_note_recent_count"] = False
        try:
            n = max(1, int(text.strip()))
        except Exception:
            await update.message.reply_text("❌ Введіть число.")
            return True
        all_e = _entries_for_folder(folder_id)
        return await _send_entries(update, context, folder_id, all_e[-n:], f"Останні {n}")

    if text == "⏮ Надіслати перші":
        context.user_data["awaiting_note_first_count"] = True
        await update.message.reply_text("Введіть кількість перших записів:")
        return True

    if context.user_data.get("awaiting_note_first_count"):
        context.user_data["awaiting_note_first_count"] = False
        try:
            n = max(1, int(text.strip()))
        except Exception:
            await update.message.reply_text("❌ Введіть число.")
            return True
        all_e = _entries_for_folder(folder_id)
        return await _send_entries(update, context, folder_id, all_e[:n], f"Перші {n}")

    if text == "🔢 Надіслати проміжок":
        context.user_data["awaiting_note_range"] = True
        await update.message.reply_text("Введіть проміжок: наприклад 2-5")
        return True

    if context.user_data.get("awaiting_note_range"):
        context.user_data["awaiting_note_range"] = False
        try:
            a, b = [int(x.strip()) for x in text.split("-", 1)]
            if a < 1 or b < a:
                raise ValueError
        except Exception:
            await update.message.reply_text("❌ Формат має бути 2-5")
            return True
        all_e = _entries_for_folder(folder_id)
        return await _send_entries(update, context, folder_id, all_e[a-1:b], f"Проміжок {a}-{b}")

    if text == "📅 Надіслати за датою":
        context.user_data["awaiting_note_date"] = True
        await update.message.reply_text("Введіть дату YYYY-MM-DD")
        return True

    if context.user_data.get("awaiting_note_date"):
        context.user_data["awaiting_note_date"] = False
        d = text.strip()
        rows = db.cursor.execute(
            "SELECT * FROM note_entries WHERE folder_id = ? AND date(created_at) = date(?) ORDER BY created_at ASC",
            (folder_id, d),
        ).fetchall()
        return await _send_entries(update, context, folder_id, rows, f"Записи за {d}")

    # Меню видалення записів (як у видаленні файлів в альбомах)
    if context.user_data.get("note_in_delete_menu"):
        all_e = _entries_for_folder(folder_id)
        if text == "Надіслати: Весь альбом":
            await update.message.reply_text(f"📤 Надсилаю всі записи ({len(all_e)}) для видалення...")
            for idx, e in enumerate(all_e, 1):
                await _send_entry_for_deletion(update, e, idx)
            return True
        if text == "Надіслати: Останні":
            context.user_data["note_del_await_recent"] = True
            await update.message.reply_text("⏳ Скільки останніх записів надіслати для видалення?")
            return True
        if text == "Надіслати: Перші":
            context.user_data["note_del_await_first"] = True
            await update.message.reply_text("⏮ Скільки перших записів надіслати для видалення?")
            return True
        if text == "Надіслати: Проміжок":
            context.user_data["note_del_await_range"] = True
            await update.message.reply_text("🔢 Введіть проміжок X-Y (наприклад 2-5):")
            return True
        if text == "Надіслати: За датою":
            context.user_data["note_del_await_date"] = True
            await update.message.reply_text("📅 Введіть дату YYYY-MM-DD:")
            return True

        if context.user_data.get("note_del_await_recent"):
            context.user_data["note_del_await_recent"] = False
            try:
                n = max(1, int(text.strip()))
            except Exception:
                await update.message.reply_text("❌ Введіть число.")
                return True
            chosen = all_e[-n:]
            await update.message.reply_text(f"📤 Надсилаю останні {len(chosen)} записів для видалення...")
            for idx, e in enumerate(chosen, len(all_e) - len(chosen) + 1):
                await _send_entry_for_deletion(update, e, idx)
            return True

        if context.user_data.get("note_del_await_first"):
            context.user_data["note_del_await_first"] = False
            try:
                n = max(1, int(text.strip()))
            except Exception:
                await update.message.reply_text("❌ Введіть число.")
                return True
            chosen = all_e[:n]
            await update.message.reply_text(f"📤 Надсилаю перші {len(chosen)} записів для видалення...")
            for idx, e in enumerate(chosen, 1):
                await _send_entry_for_deletion(update, e, idx)
            return True

        if context.user_data.get("note_del_await_range"):
            context.user_data["note_del_await_range"] = False
            try:
                a, b = [int(x.strip()) for x in text.split("-", 1)]
                if a < 1 or b < a:
                    raise ValueError
            except Exception:
                await update.message.reply_text("❌ Формат X-Y (наприклад 2-5).")
                return True
            b = min(b, len(all_e))
            chosen = all_e[a - 1:b]
            await update.message.reply_text(f"📤 Надсилаю записи з {a} по {b} для видалення...")
            for idx, e in enumerate(chosen, a):
                await _send_entry_for_deletion(update, e, idx)
            return True

        if context.user_data.get("note_del_await_date"):
            context.user_data["note_del_await_date"] = False
            d = text.strip()
            chosen = db.cursor.execute(
                "SELECT * FROM note_entries WHERE folder_id = ? AND date(created_at) = date(?) ORDER BY created_at ASC",
                (folder_id, d),
            ).fetchall()
            await update.message.reply_text(f"📤 Надсилаю {len(chosen)} записів за {d} для видалення...")
            for idx, e in enumerate(chosen, 1):
                await _send_entry_for_deletion(update, e, idx)
            return True

    if text == "⋯ Додаткові дії":
        context.user_data["note_additional"] = True
        await update.message.reply_text("⚙️ Додаткові дії з папкою:", reply_markup=notes_additional_keyboard())
        return True

    if text == "◀️ Назад до папки":
        context.user_data.pop("note_additional", None)
        context.user_data.pop("note_in_delete_menu", None)
        context.user_data.pop("note_del_await_recent", None)
        context.user_data.pop("note_del_await_first", None)
        context.user_data.pop("note_del_await_range", None)
        context.user_data.pop("note_del_await_date", None)
        await update.message.reply_text("📁 Повернулись до папки.", reply_markup=notes_folder_keyboard())
        return True

    if context.user_data.get("note_additional"):
        if text == "ℹ️ Інформація папки":
            await update.message.reply_text(
                f"📁 {folder['name']}\n"
                f"Записів: {folder['entries_count']}\n"
                f"Створено: {helpers.format_date(folder['created_at'])}"
            )
            return True

        if text == "📦 Зробити спільною":
            db.cursor.execute("UPDATE note_folders SET is_shared = 1 WHERE folder_id = ?", (folder_id,))
            db.cursor.execute(
                "INSERT OR IGNORE INTO shared_note_folders (folder_id, user_id, access_level) VALUES (?, ?, 'owner')",
                (folder_id, user_id),
            )
            db.conn.commit()
            await update.message.reply_text("✅ Папку зроблено спільною. Відкрийте «🤝 Спільні нотатки».")
            return True

        if text == "🗑 Видалити запис":
            context.user_data["note_in_delete_menu"] = True
            context.user_data.pop("note_del_await_recent", None)
            context.user_data.pop("note_del_await_first", None)
            context.user_data.pop("note_del_await_range", None)
            context.user_data.pop("note_del_await_date", None)
            await update.message.reply_text("🗑 Оберіть спосіб надсилання записів для видалення:", reply_markup=notes_delete_menu_keyboard())
            return True

        if text == "🗂 Архівувати папку":
            db.cursor.execute("UPDATE note_folders SET is_archived = 1 WHERE folder_id = ?", (folder_id,))
            db.conn.commit()
            context.user_data["note_folder_active"] = False
            context.user_data.pop("current_note_folder", None)
            await update.message.reply_text("✅ Папку архівовано.")
            return True

        if text == "🔥 Видалити папку":
            context.user_data["awaiting_note_folder_name_confirm"] = True
            context.user_data["deleting_note_folder"] = folder_id
            await update.message.reply_text(
                "🗑 Для видалення введіть точну назву папки:\n"
                f"{folder['name']}",
            )
            return True

    if _is_manual_note_text(text):
        await _save_note_entry(folder_id, user_id, text)
        await update.message.reply_text("✅ Запис збережено.")
        return True

    return False


async def handle_note_media(update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("note_folder_active"):
        return False
    folder_id = context.user_data.get("current_note_folder")
    if not folder_id:
        return False
    msg = update.message
    if not msg.photo:
        return False
    caption = (msg.caption or "").strip()
    if not _is_manual_note_text(caption):
        await msg.reply_text("⚠️ Для нотаток фото зберігається тільки разом із текстом у підписі.")
        return True
    await _save_note_entry_with_photo(folder_id, update.effective_user.id, caption, msg.photo[-1].file_id)
    await msg.reply_text("✅ Фото з текстом збережено як запис.")
    return True


async def notes_unarchive(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    folder_id = int(q.data.split("_")[-1])
    db.cursor.execute("UPDATE note_folders SET is_archived = 0 WHERE folder_id = ?", (folder_id,))
    db.conn.commit()
    await notes_show_archived(update, context)


async def handle_note_delete_callback(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    await q.answer()

    if data.startswith("note_askdel_"):
        entry_id = int(data.split("_")[-1])
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Так, видалити", callback_data=f"note_confirmdel_{entry_id}"),
            InlineKeyboardButton("❌ Ні", callback_data=f"note_canceldel_{entry_id}"),
        ]])
        try:
            await q.edit_message_caption("🗑 Видалити цей запис?", reply_markup=kb)
        except Exception:
            await q.edit_message_text("🗑 Видалити цей запис?", reply_markup=kb)
        return True

    if data.startswith("note_confirmdel_"):
        entry_id = int(data.split("_")[-1])
        row = db.cursor.execute("SELECT folder_id FROM note_entries WHERE entry_id = ?", (entry_id,)).fetchone()
        if row:
            db.cursor.execute("DELETE FROM note_entries WHERE entry_id = ?", (entry_id,))
            db.cursor.execute(
                "UPDATE note_folders SET entries_count = CASE WHEN entries_count > 0 THEN entries_count - 1 ELSE 0 END WHERE folder_id = ?",
                (row["folder_id"],),
            )
            db.conn.commit()
        try:
            await q.edit_message_caption("✅ Запис видалено.", reply_markup=None)
        except Exception:
            await q.edit_message_text("✅ Запис видалено.", reply_markup=None)
        return True

    if data.startswith("note_canceldel_"):
        entry_id = int(data.split("_")[-1])
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Видалити запис", callback_data=f"note_askdel_{entry_id}")]])
        try:
            await q.edit_message_reply_markup(reply_markup=kb)
        except Exception:
            pass
        return True

    return False
