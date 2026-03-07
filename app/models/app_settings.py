"""Application settings stored in DB (key-value)."""
from app.db import get_db


def get_setting(key, default=''):
    """Get a single setting value."""
    db = get_db()
    row = db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row['value'] if row else default


def set_setting(key, value):
    """Set a single setting value (upsert)."""
    db = get_db()
    db.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value)
    )
    db.commit()


def get_settings_by_prefix(prefix):
    """Get all settings matching a prefix as dict."""
    db = get_db()
    rows = db.execute(
        "SELECT key, value FROM app_settings WHERE key LIKE ?",
        (prefix + '%',)
    ).fetchall()
    return {r['key']: r['value'] for r in rows}


def get_smtp_settings():
    """Get all SMTP settings as a dict with short keys."""
    settings = get_settings_by_prefix('smtp_')
    return {
        'server': settings.get('smtp_server', ''),
        'port': settings.get('smtp_port', '587'),
        'use_tls': settings.get('smtp_use_tls', 'true'),
        'username': settings.get('smtp_username', ''),
        'password': settings.get('smtp_password', ''),
        'sender': settings.get('smtp_sender', ''),
    }


def save_smtp_settings(server, port, use_tls, username, password, sender):
    """Save all SMTP settings at once."""
    db = get_db()
    pairs = [
        ('smtp_server', server),
        ('smtp_port', str(port)),
        ('smtp_use_tls', use_tls),
        ('smtp_username', username),
        ('smtp_sender', sender),
    ]
    # Only update password if provided (non-empty) — allows keeping existing
    if password:
        pairs.append(('smtp_password', password))

    for key, value in pairs:
        db.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )
    db.commit()
