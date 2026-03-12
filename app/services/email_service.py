"""Email service using stdlib smtplib (no external dependencies).

Reads SMTP settings from DB (app_settings table) first,
falls back to Flask config (environment variables).
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from flask import current_app


def _get_smtp_config():
    """Get SMTP config: DB settings take priority, then env vars via Flask config."""
    from app.models.app_settings import get_smtp_settings
    db_smtp = get_smtp_settings()
    cfg = current_app.config

    # DB values take priority if set, otherwise fall back to config.py / env vars
    return {
        'server': db_smtp['server'] or cfg.get('MAIL_SERVER', 'smtp.gmail.com'),
        'port': int(db_smtp['port'] or cfg.get('MAIL_PORT', 587)),
        'use_tls': (db_smtp['use_tls'] != 'false') if db_smtp['username'] else cfg.get('MAIL_USE_TLS', True),
        'username': db_smtp['username'] or cfg.get('MAIL_USERNAME', ''),
        'password': db_smtp['password'] or cfg.get('MAIL_PASSWORD', ''),
        'sender': db_smtp['sender'] or cfg.get('MAIL_DEFAULT_SENDER', ''),
    }


def is_smtp_configured():
    """Check if SMTP credentials are set (in DB or env vars)."""
    smtp = _get_smtp_config()
    return bool(smtp['username'] and smtp['password'])


def send_schedule_email(to_email, employee_name, week_label, attachments):
    """Send weekly schedule as Excel attachment(s).

    Args:
        to_email: recipient email address
        employee_name: employee's display name (for greeting)
        week_label: e.g. "týdny 10–11/2026"
        attachments: list of (xlsx_bytes, filename) tuples

    Raises:
        ValueError: if SMTP is not configured
        smtplib.SMTPException: on email sending failure
    """
    smtp = _get_smtp_config()
    if not smtp['username'] or not smtp['password']:
        raise ValueError("SMTP není nakonfigurován (nastavte v Nastavení → Email)")

    sender = smtp['sender'] or smtp['username']

    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to_email
    msg['Subject'] = f'Rozpis směn \u2013 {week_label}'

    body = (
        f'Dobrý den {employee_name},\n\n'
        f'v příloze najdete rozpis směn na {week_label}.\n\n'
        f'S pozdravem,\n'
        f'Plánování směn FerMato'
    )
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    # Excel attachment(s)
    for xlsx_bytes, filename in attachments:
        part = MIMEBase(
            'application',
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        part.set_payload(xlsx_bytes)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
        msg.attach(part)

    # Send via SMTP
    port = int(smtp['port'])
    if port == 465:
        server = smtplib.SMTP_SSL(smtp['server'], port, timeout=15)
    else:
        server = smtplib.SMTP(smtp['server'], port, timeout=15)
    try:
        server.ehlo()
        if port != 465 and smtp['use_tls']:
            server.starttls()
            server.ehlo()
        server.login(smtp['username'], smtp['password'])
        server.sendmail(sender, [to_email], msg.as_string())
    finally:
        server.quit()
