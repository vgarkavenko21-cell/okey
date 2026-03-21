from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

import helpers
from db_models import Database
from notes import ensure_notes_tables, _is_manual_note_text, notes_folder_keyboard

db = Database()
ensure_notes_tables()


def shared_notes_keyboard() -> ReplyKeyboardMarkup:
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


def shared_notes_additional_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("ℹ️ Інформація папки"), KeyboardButton("👥 Учасники")],
            [KeyboardButton("🗑 Видалити запис"), KeyboardButton("🗂 Архівувати папку")],
            [KeyboardButton("🔥 Видалити папку"), KeyboardButton("↩️ Перенести в Мої нотатки")],
            [KeyboardButton("◀️ Назад до папки")],
        ],
        resize_keyboard=True,
    )


def shared_notes_delete_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Надіслати: Весь альбом")],
            [KeyboardButton("Надіслати: Останні"), KeyboardButton("Надіслати: Перші")],
            [KeyboardButton("Надіслати: Проміжок"), KeyboardButton("Надіслати: За датою")],
            [KeyboardButton("◀️ Назад до папки")],
        ],
        resize_keyboard=True,
    )


def shared_notes_members_keyboard(can_manage: bool) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton("📋 Всі учасники")]]
    if can_manage:
        rows.append([KeyboardButton("➕ Додати учасника")])
        rows.append([KeyboardButton("✏️ Змінити роль")])
        rows.append([KeyboardButton("🗑 Видалити учасника")])
    rows.append([KeyboardButton("◀️ Назад до додаткових дій")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def shared_notes_change_role_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📋 Надіслати всіх учасників для зміни ролі")],
            [KeyboardButton("✏️ Змінити роль за юзернеймом")],
            [KeyboardButton("◀️ Назад до учасників")],
        ],
        resize_keyboard=True,
    )


def shared_notes_delete_member_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📋 Надіслати всіх учасників для видалення")],
            [KeyboardButton("🗑 Видалити за юзернеймом")],
            [KeyboardButton("◀️ Назад до учасників")],
        ],
        resize_keyboard=True,
    )


def shared_notes_roles_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("⚙️ Адмін"), KeyboardButton("✏️ Редактор")],
            [KeyboardButton("📤 Автор"), KeyboardButton("👁️ Спостерігач")],
            [KeyboardButton("◀️ Назад до учасників")],
        ],
        resize_keyboard=True,
    )

def _member_name_row(member) -> str:
    uname = f"@{member['username']}" if member["username"] else str(member["user_id"])
    return f"{uname} • {helpers.get_role_name(member['access_level'])}"


async def _send_members_for_role_change(update, members):
    kb = []
    for m in members:
        if m["access_level"] == "owner":
            continue
        kb.append([InlineKeyboardButton(_member_name_row(m), callback_data=f"snotes_member_role_pick_{m['user_id']}")])
    if kb:
        await update.message.reply_text(
            "Ви можете обрати учасника зі списку для зміни ролі або ввести його @username.",
            reply_markup=InlineKeyboardMarkup(kb),
        )
    else:
        await update.message.reply_text("Немає учасників для зміни ролі.")


async def _send_members_for_delete(update, members):
    kb = []
    for m in members:
        if m["access_level"] == "owner":
            continue
        kb.append([InlineKeyboardButton(f"🗑 {_member_name_row(m)}", callback_data=f"snotes_member_del_{m['user_id']}")])
    if kb:
        await update.message.reply_text(
            "Для видалення учасника ви можете обрати його зі списку або ввести його @username через собачку.",
            reply_markup=InlineKeyboardMarkup(kb),
        )
    else:
        await update.message.reply_text("Немає учасників для видалення.")


async def _prompt_role_select(update, uid: int):
    user = db.cursor.execute("SELECT username, first_name FROM users WHERE user_id = ?", (uid,)).fetchone()
    display = f"@{user['username']}" if user and user["username"] else (user["first_name"] if user and user["first_name"] else str(uid))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Адмін (керування + редагування)", callback_data=f"snotes_member_role_set_{uid}_admin")],
        [InlineKeyboardButton("🛠 Редактор (редагування + додавання)", callback_data=f"snotes_member_role_set_{uid}_editor")],
        [InlineKeyboardButton("✍️ Автор (додавання + перегляд)", callback_data=f"snotes_member_role_set_{uid}_contributor")],
        [InlineKeyboardButton("👁️ Спостерігач (тільки перегляд)", callback_data=f"snotes_member_role_set_{uid}_viewer")],
    ])
    await update.message.reply_text(
        f"👤 {display}\nОберіть роль для заміни:",
        reply_markup=kb,
    )


async def _prompt_delete_confirm(update, uid: int):
    user = db.cursor.execute("SELECT username, first_name FROM users WHERE user_id = ?", (uid,)).fetchone()
    display = f"@{user['username']}" if user and user["username"] else (user["first_name"] if user and user["first_name"] else str(uid))
    await update.message.reply_text(
        f"Видалити учасника {display}?",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("✅ Так"), KeyboardButton("❌ Ні")], [KeyboardButton("◀️ Назад до учасників")]],
            resize_keyboard=True,
        ),
    )


async def show_shared_notes(update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = db.cursor.execute(
        '''
        SELECT nf.folder_id, nf.name, nf.entries_count, snf.access_level
        FROM shared_note_folders snf
        JOIN note_folders nf ON nf.folder_id = snf.folder_id
        WHERE snf.user_id = ? AND nf.is_archived = 0
        ORDER BY nf.created_at DESC
        ''',
        (user_id,),
    ).fetchall()

    if not rows:
        await update.message.reply_text(
            "🤝 У вас поки немає спільних папок нотаток.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Створити спільну папку", callback_data="snotes_create")]]),
        )
        return

    kb = []
    lines = ["🤝 **Спільні нотатки**"]
    for r in rows:
        role = helpers.get_role_name(r["access_level"])
        kb.append([InlineKeyboardButton(f"{r['name']} ({r['entries_count']}) • {role}", callback_data=f"snotes_open_{r['folder_id']}")])

    kb.append([InlineKeyboardButton("➕ Створити спільну папку", callback_data="snotes_create")])
    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def shared_notes_create_start(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    if not helpers.check_user_limit(db, user_id, "shared_notes"):
        await q.edit_message_text("❌ Ліміт спільних папок без Premium досягнуто.")
        return
    context.user_data["awaiting_shared_note_folder_name"] = True
    await q.edit_message_text("🤝 Введіть назву нової спільної папки нотаток:")


async def handle_shared_note_folder_name(update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("awaiting_shared_note_folder_name"):
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
        "INSERT INTO note_folders (user_id, name, is_shared, created_at) VALUES (?, ?, 1, CURRENT_TIMESTAMP)",
        (user_id, name),
    )
    folder_id = db.cursor.lastrowid
    db.cursor.execute(
        "INSERT OR IGNORE INTO shared_note_folders (folder_id, user_id, access_level, added_at) VALUES (?, ?, 'owner', CURRENT_TIMESTAMP)",
        (folder_id, user_id),
    )
    db.conn.commit()
    context.user_data["awaiting_shared_note_folder_name"] = False
    context.user_data["current_shared_note_folder"] = folder_id
    context.user_data["shared_note_active"] = True
    context.user_data["shared_note_access"] = "owner"
    await update.message.reply_text(
        f"✅ Створено спільну папку '{name}'.\nНадішліть текст — він автоматично збережеться як запис.",
        reply_markup=shared_notes_keyboard(),
    )
    return True


async def open_shared_note_folder(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    folder_id = int(q.data.split("_")[-1])
    user_id = q.from_user.id

    row = db.cursor.execute(
        '''
        SELECT nf.*, snf.access_level
        FROM shared_note_folders snf
        JOIN note_folders nf ON nf.folder_id = snf.folder_id
        WHERE nf.folder_id = ? AND snf.user_id = ?
        ''',
        (folder_id, user_id),
    ).fetchone()
    if not row:
        await q.edit_message_text("❌ Немає доступу до цієї папки.")
        return

    context.user_data["current_shared_note_folder"] = folder_id
    context.user_data["shared_note_active"] = True
    context.user_data["shared_note_access"] = row["access_level"]

    await q.message.reply_text(
        f"📁 {row['name']}\n"
        f"Записів: {row['entries_count']}\n\n"
        "Надсилайте свої записи в цей чат — вони автоматично збережуться в папку.\n"
        "Також можна надсилати фото з підписом — збережеться фото і підпис у цьому записі.",
        reply_markup=shared_notes_keyboard(),
    )


def _shared_entries(folder_id: int):
    return db.cursor.execute(
        "SELECT * FROM note_entries WHERE folder_id = ? ORDER BY created_at ASC",
        (folder_id,),
    ).fetchall()


def _shared_members(folder_id: int):
    return db.cursor.execute(
        "SELECT snf.user_id, snf.access_level, u.username FROM shared_note_folders snf "
        "LEFT JOIN users u ON u.user_id = snf.user_id "
        "WHERE snf.folder_id = ? ORDER BY snf.id ASC",
        (folder_id,),
    ).fetchall()


async def _send_shared_entries(update, folder_id: int, entries, title: str):
    settings = helpers.get_user_display_settings(db, update.effective_user.id)
    show_number = settings.get("show_number", True)
    show_date = settings.get("show_date", True)
    if not entries:
        await update.message.reply_text("📭 Папка порожня.")
        return True

    for i, e in enumerate(entries, start=1):
        footer = []
        if show_number:
            footer.append(f"📄 Запис #{i}")
        if show_date and e["created_at"]:
            try:
                d = datetime.strptime(e["created_at"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
            except Exception:
                d = str(e["created_at"])[:10]
            footer.append(f"📅 {d}")
        footer_text = " | ".join(footer) if footer else None

        photo_row = db.cursor.execute(
            "SELECT telegram_file_id FROM note_entry_photos WHERE entry_id = ? ORDER BY id DESC LIMIT 1",
            (e["entry_id"],),
        ).fetchone()
        text_out = e["content"]
        if footer_text:
            text_out = f"{text_out}\n\n{footer_text}"

        if photo_row:
            if len(text_out) > 1024:
                text_out = text_out[:1021] + "..."
            await update.message.reply_photo(photo=photo_row["telegram_file_id"], caption=text_out)
        else:
            await update.message.reply_text(text_out)
    return True


async def _send_shared_entry_for_deletion(update, entry_row, index: int):
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"🗑 Видалити запис #{index}", callback_data=f"snote_askdel_{entry_row['entry_id']}")]]
    )
    photo_row = db.cursor.execute(
        "SELECT telegram_file_id FROM note_entry_photos WHERE entry_id = ? ORDER BY id DESC LIMIT 1",
        (entry_row["entry_id"],),
    ).fetchone()
    content = entry_row["content"]
    if photo_row:
        if len(content) > 1024:
            content = content[:1021] + "..."
        await update.message.reply_photo(photo=photo_row["telegram_file_id"], caption=content, reply_markup=kb)
    else:
        await update.message.reply_text(content, reply_markup=kb)


async def handle_shared_note_buttons(update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("shared_note_active"):
        return False

    text = update.message.text
    folder_id = context.user_data.get("current_shared_note_folder")
    access = context.user_data.get("shared_note_access", "viewer")
    user_id = update.effective_user.id
    if not folder_id:
        return False

    if text == "◀️ Вийти з папки":
        context.user_data["shared_note_active"] = False
        context.user_data.pop("current_shared_note_folder", None)
        context.user_data.pop("shared_note_access", None)
        context.user_data.pop("shared_note_additional", None)
        context.user_data.pop("shared_note_in_delete_menu", None)
        context.user_data.pop("shared_note_in_members", None)
        await show_shared_notes(update, context)
        return True

    if context.user_data.get("awaiting_shared_note_folder_name_confirm"):
        context.user_data["awaiting_shared_note_folder_name_confirm"] = False
        deleting_id = context.user_data.pop("deleting_shared_note_folder", None)
        if not deleting_id:
            await update.message.reply_text("❌ Не знайдено папку для видалення.")
            return True
        row = db.cursor.execute(
            "SELECT name FROM note_folders WHERE folder_id = ?",
            (deleting_id,),
        ).fetchone()
        if not row:
            await update.message.reply_text("❌ Папку не знайдено.")
            return True
        if text.strip() != row["name"]:
            await update.message.reply_text("❌ Назва не співпадає. Видалення скасовано.")
            return True
        db.cursor.execute("DELETE FROM note_folders WHERE folder_id = ?", (deleting_id,))
        db.conn.commit()
        context.user_data["shared_note_active"] = False
        context.user_data.pop("current_shared_note_folder", None)
        context.user_data.pop("shared_note_access", None)
        context.user_data.pop("shared_note_additional", None)
        context.user_data.pop("shared_note_in_delete_menu", None)
        await update.message.reply_text("🔥 Папку видалено.")
        return True

    if text == "📤 Надіслати всю папку":
        rows = _shared_entries(folder_id)
        return await _send_shared_entries(update, folder_id, rows, "Вся спільна папка")

    if text == "⏳ Надіслати останні":
        context.user_data["shared_note_await_recent_count"] = True
        await update.message.reply_text("Введіть кількість останніх записів:")
        return True

    if context.user_data.get("shared_note_await_recent_count"):
        context.user_data["shared_note_await_recent_count"] = False
        try:
            n = max(1, int(text.strip()))
        except Exception:
            await update.message.reply_text("❌ Введіть число.")
            return True
        rows = _shared_entries(folder_id)
        return await _send_shared_entries(update, folder_id, rows[-n:], f"Останні {n}")

    if text == "⏮ Надіслати перші":
        context.user_data["shared_note_await_first_count"] = True
        await update.message.reply_text("Введіть кількість перших записів:")
        return True

    if context.user_data.get("shared_note_await_first_count"):
        context.user_data["shared_note_await_first_count"] = False
        try:
            n = max(1, int(text.strip()))
        except Exception:
            await update.message.reply_text("❌ Введіть число.")
            return True
        rows = _shared_entries(folder_id)
        return await _send_shared_entries(update, folder_id, rows[:n], f"Перші {n}")

    if text == "🔢 Надіслати проміжок":
        context.user_data["shared_note_await_range"] = True
        await update.message.reply_text("Введіть проміжок: 2-5")
        return True

    if context.user_data.get("shared_note_await_range"):
        context.user_data["shared_note_await_range"] = False
        try:
            a, b = [int(x.strip()) for x in text.split("-", 1)]
            if a < 1 or b < a:
                raise ValueError
        except Exception:
            await update.message.reply_text("❌ Формат X-Y (наприклад 2-5)")
            return True
        rows = _shared_entries(folder_id)
        return await _send_shared_entries(update, folder_id, rows[a - 1:b], f"Проміжок {a}-{b}")

    if text == "📅 Надіслати за датою":
        context.user_data["shared_note_await_date"] = True
        await update.message.reply_text("Введіть дату YYYY-MM-DD")
        return True

    if context.user_data.get("shared_note_await_date"):
        context.user_data["shared_note_await_date"] = False
        d = text.strip()
        rows = db.cursor.execute(
            "SELECT * FROM note_entries WHERE folder_id = ? AND date(created_at) = date(?) ORDER BY created_at ASC",
            (folder_id, d),
        ).fetchall()
        return await _send_shared_entries(update, folder_id, rows, f"Записи за {d}")

    if context.user_data.get("shared_note_in_delete_menu"):
        all_e = _shared_entries(folder_id)
        if text == "Надіслати: Весь альбом":
            await update.message.reply_text(f"📤 Надсилаю всі записи ({len(all_e)}) для видалення...")
            for idx, e in enumerate(all_e, 1):
                await _send_shared_entry_for_deletion(update, e, idx)
            return True
        if text == "Надіслати: Останні":
            context.user_data["shared_note_del_await_recent"] = True
            await update.message.reply_text("⏳ Скільки останніх записів надіслати для видалення?")
            return True
        if text == "Надіслати: Перші":
            context.user_data["shared_note_del_await_first"] = True
            await update.message.reply_text("⏮ Скільки перших записів надіслати для видалення?")
            return True
        if text == "Надіслати: Проміжок":
            context.user_data["shared_note_del_await_range"] = True
            await update.message.reply_text("🔢 Введіть проміжок X-Y (2-5)")
            return True
        if text == "Надіслати: За датою":
            context.user_data["shared_note_del_await_date"] = True
            await update.message.reply_text("📅 Введіть дату YYYY-MM-DD")
            return True

        if context.user_data.get("shared_note_del_await_recent"):
            context.user_data["shared_note_del_await_recent"] = False
            try:
                n = max(1, int(text.strip()))
            except Exception:
                await update.message.reply_text("❌ Введіть число.")
                return True
            chosen = all_e[-n:]
            for idx, e in enumerate(chosen, len(all_e) - len(chosen) + 1):
                await _send_shared_entry_for_deletion(update, e, idx)
            return True

        if context.user_data.get("shared_note_del_await_first"):
            context.user_data["shared_note_del_await_first"] = False
            try:
                n = max(1, int(text.strip()))
            except Exception:
                await update.message.reply_text("❌ Введіть число.")
                return True
            chosen = all_e[:n]
            for idx, e in enumerate(chosen, 1):
                await _send_shared_entry_for_deletion(update, e, idx)
            return True

        if context.user_data.get("shared_note_del_await_range"):
            context.user_data["shared_note_del_await_range"] = False
            try:
                a, b = [int(x.strip()) for x in text.split("-", 1)]
                if a < 1 or b < a:
                    raise ValueError
            except Exception:
                await update.message.reply_text("❌ Формат X-Y")
                return True
            b = min(b, len(all_e))
            chosen = all_e[a - 1:b]
            for idx, e in enumerate(chosen, a):
                await _send_shared_entry_for_deletion(update, e, idx)
            return True

        if context.user_data.get("shared_note_del_await_date"):
            context.user_data["shared_note_del_await_date"] = False
            d = text.strip()
            chosen = db.cursor.execute(
                "SELECT * FROM note_entries WHERE folder_id = ? AND date(created_at)=date(?) ORDER BY created_at ASC",
                (folder_id, d),
            ).fetchall()
            for idx, e in enumerate(chosen, 1):
                await _send_shared_entry_for_deletion(update, e, idx)
            return True

    if text == "⋯ Додаткові дії":
        context.user_data["shared_note_additional"] = True
        await update.message.reply_text("⚙️ Додаткові дії:", reply_markup=shared_notes_additional_keyboard())
        return True

    if text == "◀️ Назад до папки":
        context.user_data.pop("shared_note_additional", None)
        context.user_data.pop("shared_note_in_delete_menu", None)
        context.user_data.pop("shared_note_in_members", None)
        for k in (
            "shared_note_del_await_recent", "shared_note_del_await_first", "shared_note_del_await_range",
            "shared_note_del_await_date", "shared_note_member_add_wait_uid", "shared_note_member_add_wait_role",
            "shared_note_member_role_wait_uid", "shared_note_member_role_wait_role", "shared_note_member_del_wait_uid",
            "shared_note_member_role_flow", "shared_note_member_delete_flow", "shared_note_member_role_by_username_wait",
            "shared_note_member_delete_by_username_wait", "shared_note_member_delete_confirm_wait",
        ):
            context.user_data.pop(k, None)
        await update.message.reply_text("📁 Повернулись до папки.", reply_markup=shared_notes_keyboard())
        return True

    if context.user_data.get("shared_note_additional"):
        if text == "ℹ️ Інформація папки":
            folder = db.cursor.execute("SELECT * FROM note_folders WHERE folder_id = ?", (folder_id,)).fetchone()
            members_count = db.cursor.execute(
                "SELECT COUNT(*) FROM shared_note_folders WHERE folder_id = ?",
                (folder_id,),
            ).fetchone()[0]
            await update.message.reply_text(
                f"📁 {folder['name']}\nЗаписів: {folder['entries_count']}\nУчасників: {members_count}\n"
                f"Створено: {helpers.format_date(folder['created_at'])}"
            )
            return True

        if text == "👥 Учасники":
            context.user_data["shared_note_in_members"] = True
            can_manage = access in {"owner", "admin"}
            await update.message.reply_text("👥 Меню учасників:", reply_markup=shared_notes_members_keyboard(can_manage))
            return True

        if text == "🗂 Архівувати папку" and access in {"owner", "admin"}:
            db.cursor.execute("UPDATE note_folders SET is_archived = 1 WHERE folder_id = ?", (folder_id,))
            db.conn.commit()
            await update.message.reply_text("✅ Папку архівовано.")
            return True

        if text == "🔥 Видалити папку" and access == "owner":
            context.user_data["awaiting_shared_note_folder_name_confirm"] = True
            context.user_data["deleting_shared_note_folder"] = folder_id
            folder = db.cursor.execute("SELECT name FROM note_folders WHERE folder_id = ?", (folder_id,)).fetchone()
            await update.message.reply_text("🗑 Для видалення введіть точну назву папки:\n" + (folder["name"] if folder else ""))
            return True

        if text == "↩️ Перенести в Мої нотатки" and access == "owner":
            db.cursor.execute("UPDATE note_folders SET is_shared = 0 WHERE folder_id = ?", (folder_id,))
            db.cursor.execute("DELETE FROM shared_note_folders WHERE folder_id = ? AND user_id != ?", (folder_id, user_id))
            db.conn.commit()
            await update.message.reply_text("✅ Папку повернено в «Мої нотатки».", reply_markup=notes_folder_keyboard())
            return True

        if text == "🗑 Видалити запис" and access in {"owner", "admin", "editor", "contributor"}:
            context.user_data["shared_note_in_delete_menu"] = True
            for k in ("shared_note_del_await_recent", "shared_note_del_await_first", "shared_note_del_await_range", "shared_note_del_await_date"):
                context.user_data.pop(k, None)
            await update.message.reply_text("🗑 Оберіть спосіб надсилання записів для видалення:", reply_markup=shared_notes_delete_menu_keyboard())
            return True

    if context.user_data.get("shared_note_in_members"):
        members = _shared_members(folder_id)
        can_manage = access in {"owner", "admin"}
        member_menu_buttons = {
            "📋 Всі учасники",
            "➕ Додати учасника",
            "✏️ Змінити роль",
            "🗑 Видалити учасника",
            "◀️ Назад до учасників",
            "◀️ Назад до додаткових дій",
        }
        if text == "📋 Всі учасники":
            lines = ["👥 Учасники:"]
            for m in members:
                uname = f"@{m['username']}" if m['username'] else str(m['user_id'])
                lines.append(f"- {uname}: {helpers.get_role_name(m['access_level'])}")
            await update.message.reply_text("\n".join(lines))
            return True
        if text == "◀️ Назад до додаткових дій":
            context.user_data["shared_note_in_members"] = False
            await update.message.reply_text("⚙️ Додаткові дії:", reply_markup=shared_notes_additional_keyboard())
            return True
        if text == "◀️ Назад до учасників":
            context.user_data.pop("shared_note_member_role_flow", None)
            context.user_data.pop("shared_note_member_delete_flow", None)
            context.user_data.pop("shared_note_member_role_by_username_wait", None)
            context.user_data.pop("shared_note_member_delete_by_username_wait", None)
            context.user_data.pop("shared_note_member_add_wait_uid", None)
            context.user_data.pop("shared_note_member_add_wait_role", None)
            context.user_data.pop("shared_note_member_pending_uid", None)
            context.user_data.pop("shared_note_member_delete_pending_uid", None)
            context.user_data.pop("shared_note_member_delete_confirm_wait", None)
            await update.message.reply_text("👥 Меню учасників:", reply_markup=shared_notes_members_keyboard(can_manage))
            return True
        if can_manage and text == "➕ Додати учасника":
            context.user_data.pop("shared_note_member_role_flow", None)
            context.user_data.pop("shared_note_member_delete_flow", None)
            context.user_data.pop("shared_note_member_pending_uid", None)
            context.user_data.pop("shared_note_member_delete_confirm_wait", None)
            context.user_data.pop("shared_note_member_delete_confirm_uid", None)
            context.user_data["shared_note_member_add_wait_uid"] = True
            await update.message.reply_text("Введіть @username нового учасника:")
            return True
        if can_manage and text == "✏️ Змінити роль":
            context.user_data.pop("shared_note_member_add_wait_uid", None)
            context.user_data["shared_note_member_role_flow"] = True
            context.user_data.pop("shared_note_member_delete_flow", None)
            context.user_data.pop("shared_note_member_role_by_username_wait", None)
            context.user_data.pop("shared_note_member_pending_uid", None)
            context.user_data.pop("shared_note_member_delete_confirm_wait", None)
            context.user_data.pop("shared_note_member_delete_confirm_uid", None)
            await _send_members_for_role_change(update, members)
            return True
        if can_manage and text == "🗑 Видалити учасника":
            context.user_data.pop("shared_note_member_add_wait_uid", None)
            context.user_data["shared_note_member_delete_flow"] = True
            context.user_data.pop("shared_note_member_role_flow", None)
            context.user_data.pop("shared_note_member_pending_uid", None)
            context.user_data.pop("shared_note_member_delete_by_username_wait", None)
            context.user_data.pop("shared_note_member_delete_confirm_uid", None)
            context.user_data.pop("shared_note_member_delete_confirm_wait", None)
            await _send_members_for_delete(update, members)
            return True
        if context.user_data.get("shared_note_member_add_wait_uid"):
            if text in member_menu_buttons:
                context.user_data["shared_note_member_add_wait_uid"] = False
            elif text.strip().startswith("@"):
                context.user_data["shared_note_member_add_wait_uid"] = False
                uid = await _resolve_user_token(text.strip())
                if uid is None:
                    await update.message.reply_text("❌ Користувача не знайдено. Введіть саме @username.")
                    return True
                db.cursor.execute(
                    "INSERT OR REPLACE INTO shared_note_folders (folder_id, user_id, access_level, added_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (folder_id, uid, "viewer"),
                )
                db.conn.commit()
                await update.message.reply_text("✅ Учасника додано (Спостерігач).")
                return True
            else:
                await update.message.reply_text("❌ Введіть саме @username нового учасника.")
                return True
        if context.user_data.get("shared_note_member_delete_confirm_wait"):
            if text == "✅ Так":
                uid = context.user_data.pop("shared_note_member_delete_confirm_uid", None)
                context.user_data["shared_note_member_delete_confirm_wait"] = False
                context.user_data.pop("shared_note_member_pending_uid", None)
                if uid is not None:
                    db.cursor.execute(
                        "DELETE FROM shared_note_folders WHERE folder_id = ? AND user_id = ? AND access_level != 'owner'",
                        (folder_id, uid),
                    )
                    db.conn.commit()
                    await update.message.reply_text("✅ Учасника видалено.")
                await update.message.reply_text("👥 Меню учасників:", reply_markup=shared_notes_members_keyboard(can_manage))
                return True
            if text == "❌ Ні":
                context.user_data["shared_note_member_delete_confirm_wait"] = False
                context.user_data.pop("shared_note_member_delete_confirm_uid", None)
                context.user_data.pop("shared_note_member_pending_uid", None)
                context.user_data["shared_note_in_members"] = False
                context.user_data["shared_note_member_delete_flow"] = False
                await update.message.reply_text("Скасовано.", reply_markup=shared_notes_additional_keyboard())
                return True
        if context.user_data.get("shared_note_member_role_flow") and text.strip().startswith("@"):
            uid = await _resolve_user_token(text.strip())
            if uid is None:
                await update.message.reply_text("❌ Користувача не знайдено. Введіть @username.")
                return True
            context.user_data["shared_note_member_pending_uid"] = uid
            await _prompt_role_select(update, uid)
            return True
        if context.user_data.get("shared_note_member_pending_uid"):
            role_map = {
                "⚙️ Адмін": "admin",
                "✏️ Редактор": "editor",
                "📤 Автор": "contributor",
                "👁️ Спостерігач": "viewer",
            }
            role = role_map.get(text.strip())
            if role:
                uid = context.user_data.pop("shared_note_member_pending_uid", None)
                if uid is not None:
                    db.cursor.execute(
                        "UPDATE shared_note_folders SET access_level = ? WHERE folder_id = ? AND user_id = ? AND access_level != 'owner'",
                        (role, folder_id, uid),
                    )
                    db.conn.commit()
                    await update.message.reply_text("✅ Роль оновлено.")
                    await update.message.reply_text("👥 Меню учасників:", reply_markup=shared_notes_members_keyboard(can_manage))
                    return True
            await update.message.reply_text("Оберіть роль кнопкою нижче.", reply_markup=shared_notes_roles_keyboard())
            return True
        if context.user_data.get("shared_note_member_delete_flow") and text.strip().startswith("@"):
            uid = await _resolve_user_token(text.strip())
            if uid is None:
                await update.message.reply_text("❌ Користувача не знайдено. Введіть @username.")
                return True
            context.user_data["shared_note_member_delete_confirm_uid"] = uid
            context.user_data["shared_note_member_delete_confirm_wait"] = True
            await _prompt_delete_confirm(update, uid)
            return True
        await update.message.reply_text("Оберіть дію з меню учасників.", reply_markup=shared_notes_members_keyboard(can_manage))
        return True

    # ручний текст у спільній папці (тільки в основному екрані папки, не в підменю)
    if not context.user_data.get("shared_note_additional") and not context.user_data.get("shared_note_in_members") and _is_manual_note_text(text) and access in {"owner", "admin", "editor", "contributor"}:
        title = text.strip().split("\n", 1)[0][:60] or "Новий запис"
        db.cursor.execute(
            "INSERT INTO note_entries (folder_id, user_id, title, content, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (folder_id, user_id, title, text),
        )
        db.cursor.execute("UPDATE note_folders SET entries_count = entries_count + 1, last_entry_at = CURRENT_TIMESTAMP WHERE folder_id = ?", (folder_id,))
        db.conn.commit()
        await update.message.reply_text("✅ Запис додано у спільну папку.")
        return True

    return False


async def handle_shared_note_media(update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("shared_note_active"):
        return False
    folder_id = context.user_data.get("current_shared_note_folder")
    access = context.user_data.get("shared_note_access", "viewer")
    if not folder_id or access not in {"owner", "admin", "editor", "contributor"}:
        return False
    msg = update.message
    if not msg.photo:
        return False
    caption = (msg.caption or "").strip()
    if not _is_manual_note_text(caption):
        await msg.reply_text("⚠️ У спільних нотатках фото зберігається тільки разом із текстом у підписі.")
        return True
    title = caption.split("\n", 1)[0][:60] or "Новий запис"
    db.cursor.execute(
        "INSERT INTO note_entries (folder_id, user_id, title, content, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (folder_id, update.effective_user.id, title, caption),
    )
    entry_id = db.cursor.lastrowid
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
        (entry_id, msg.photo[-1].file_id),
    )
    db.cursor.execute("UPDATE note_folders SET entries_count = entries_count + 1, last_entry_at = CURRENT_TIMESTAMP WHERE folder_id = ?", (folder_id,))
    db.conn.commit()
    await msg.reply_text("✅ Фото з підписом збережено у спільну папку.")
    return True


async def handle_shared_note_delete_callback(update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    q = update.callback_query
    data = q.data
    await q.answer()
    if data.startswith("snote_askdel_"):
        entry_id = int(data.split("_")[-1])
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Так, видалити", callback_data=f"snote_confirmdel_{entry_id}"),
            InlineKeyboardButton("❌ Ні", callback_data=f"snote_canceldel_{entry_id}"),
        ]])
        try:
            await q.edit_message_caption("🗑 Видалити цей запис?", reply_markup=kb)
        except Exception:
            await q.edit_message_text("🗑 Видалити цей запис?", reply_markup=kb)
        return True
    if data.startswith("snote_confirmdel_"):
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
    if data.startswith("snote_canceldel_"):
        entry_id = int(data.split("_")[-1])
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Видалити запис", callback_data=f"snote_askdel_{entry_id}")]])
        try:
            await q.edit_message_reply_markup(reply_markup=kb)
        except Exception:
            pass
        return True
    if data.startswith("snotes_member_role_pick_"):
        uid = int(data.split("_")[-1])
        context.user_data["shared_note_member_role_flow"] = True
        context.user_data["shared_note_member_pending_uid"] = uid
        await _prompt_role_select(q, uid)
        return True
    if data.startswith("snotes_member_role_set_"):
        parts = data.split("_")
        uid = int(parts[4])
        role = parts[5]
        folder_id = context.user_data.get("current_shared_note_folder")
        if folder_id and role in {"viewer", "contributor", "editor", "admin"}:
            db.cursor.execute(
                "UPDATE shared_note_folders SET access_level = ? WHERE folder_id = ? AND user_id = ? AND access_level != 'owner'",
                (role, folder_id, uid),
            )
            db.conn.commit()
            await q.answer("Роль оновлено.")
            can_manage = context.user_data.get("shared_note_access") in {"owner", "admin"}
            await q.message.reply_text("✅ Роль учасника оновлено.", reply_markup=shared_notes_members_keyboard(can_manage))
        return True
    if data.startswith("snotes_member_del_"):
        uid = int(data.split("_")[-1])
        folder_id = context.user_data.get("current_shared_note_folder")
        if folder_id:
            context.user_data["shared_note_member_delete_confirm_uid"] = uid
            context.user_data["shared_note_member_delete_confirm_wait"] = True
            context.user_data["shared_note_member_delete_flow"] = True
            await _prompt_delete_confirm(q, uid)
            await q.answer()
        return True
    if data.startswith("snotes_member_del_confirm_"):
        uid = int(data.split("_")[-1])
        folder_id = context.user_data.get("current_shared_note_folder")
        if folder_id:
            db.cursor.execute(
                "DELETE FROM shared_note_folders WHERE folder_id = ? AND user_id = ? AND access_level != 'owner'",
                (folder_id, uid),
            )
            db.conn.commit()
        await q.answer("Учасника видалено.")
        return True
    if data == "snotes_member_del_cancel":
        await q.answer("Скасовано")
        return True
    return False


async def _resolve_user_token(token: str):
    t = (token or "").strip()
    if not t:
        return None
    if t.startswith("@"):
        row = db.cursor.execute("SELECT user_id FROM users WHERE username = ?", (t[1:],)).fetchone()
        return int(row["user_id"]) if row else None
    return None
