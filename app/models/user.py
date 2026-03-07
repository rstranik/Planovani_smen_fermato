from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import get_db


class User(UserMixin):
    """User objekt pro Flask-Login."""

    def __init__(self, id, username, password_hash, display_name='',
                 active=1, created_at=None, last_login=None):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.display_name = display_name
        self.active = active
        self.created_at = created_at
        self.last_login = last_login

    @property
    def is_active(self):
        return bool(self.active)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def from_row(row):
        if row is None:
            return None
        return User(
            id=row['id'],
            username=row['username'],
            password_hash=row['password_hash'],
            display_name=row['display_name'],
            active=row['active'],
            created_at=row['created_at'],
            last_login=row['last_login'],
        )


def get_user_by_id(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User.from_row(row)


def get_user_by_username(username):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return User.from_row(row)


def create_user(username, password, display_name=''):
    db = get_db()
    pw_hash = generate_password_hash(password)
    if not display_name:
        display_name = username
    cursor = db.execute(
        "INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)",
        (username, pw_hash, display_name)
    )
    db.commit()
    return cursor.lastrowid


def update_user_password(user_id, new_password):
    db = get_db()
    pw_hash = generate_password_hash(new_password)
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
    db.commit()


def update_last_login(user_id):
    db = get_db()
    db.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
    db.commit()
