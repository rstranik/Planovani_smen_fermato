"""Email service using Resend API (HTTPS-based, no SMTP needed).

Falls back to SMTP if Resend is not configured.
"""
import os
import base64
import logging
import requests

logger = logging.getLogger(__name__)

RESEND_API_URL = 'https://api.resend.com/emails'


def _get_resend_key():
    """Get Resend API key from env or DB settings."""
    key = os.environ.get('RESEND_API_KEY', '')
    if not key:
        try:
            from app.models.app_settings import get_setting
            key = get_setting('resend_api_key', '')
        except Exception:
            pass
    return key


def _get_sender():
    """Get sender email from DB settings or default."""
    try:
        from app.models.app_settings import get_smtp_settings
        smtp = get_smtp_settings()
        return smtp.get('sender') or smtp.get('username') or 'onboarding@resend.dev'
    except Exception:
        return 'onboarding@resend.dev'


def is_smtp_configured():
    """Check if email sending is configured (Resend API key exists)."""
    return bool(_get_resend_key())


def send_schedule_email(to_email, employee_name, week_label, attachments):
    """Send weekly schedule as Excel attachment(s) via Resend API.

    Args:
        to_email: recipient email address
        employee_name: employee's display name (for greeting)
        week_label: e.g. "týdny 10–11/2026"
        attachments: list of (xlsx_bytes, filename) tuples

    Raises:
        ValueError: if Resend is not configured
        Exception: on email sending failure
    """
    api_key = _get_resend_key()
    if not api_key:
        raise ValueError("Email není nakonfigurován (nastavte RESEND_API_KEY)")

    sender = _get_sender()

    html_body = (
        f'<p>Dobrý den {employee_name},</p>'
        f'<p>v příloze najdete rozpis směn na <strong>{week_label}</strong>.</p>'
        f'<p>S pozdravem,<br>Plánování směn FerMato</p>'
    )

    # Build attachments list for Resend API
    resend_attachments = []
    for xlsx_bytes, filename in attachments:
        resend_attachments.append({
            'filename': filename,
            'content': base64.b64encode(xlsx_bytes).decode('utf-8'),
        })

    payload = {
        'from': sender,
        'to': [to_email],
        'subject': f'Rozpis směn – {week_label}',
        'html': html_body,
        'attachments': resend_attachments,
    }

    resp = requests.post(
        RESEND_API_URL,
        json=payload,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        error_msg = resp.text
        logger.error(f"Resend API error ({resp.status_code}): {error_msg}")
        raise Exception(f"Resend API error: {resp.status_code} - {error_msg}")

    logger.info(f"Email sent to {to_email} via Resend: {resp.json()}")


def test_connection():
    """Test Resend API key validity by sending a test email."""
    api_key = _get_resend_key()
    if not api_key:
        raise ValueError("RESEND_API_KEY není nastavený")

    sender = _get_sender()

    payload = {
        'from': sender,
        'to': [sender],  # send test to self
        'subject': 'Test – Plánování směn FerMato',
        'html': '<p>Testovací email z aplikace Plánování směn. ✓</p>',
    }

    resp = requests.post(
        RESEND_API_URL,
        json=payload,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        timeout=15,
    )

    if resp.status_code not in (200, 201):
        raise Exception(f"Resend API: {resp.status_code} - {resp.text}")

    return resp.json()
