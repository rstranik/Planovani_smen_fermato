"""Import employees from HR system Excel export (DJR/Zaměstnanec.xlsx)."""
import os
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, current_app
)
from werkzeug.utils import secure_filename
from app.db import get_db
from app.models.employee import find_employee_by_name, create_employee, update_employee

bp = Blueprint('import_csv', __name__, url_prefix='/import')

# Mapping: HR "Středisko" → our department name
STREDISKO_MAP = {
    'Výroba': 'VÝR',
    'Expedice': 'EXP',
    'VINACZ': 'VÝR',      # VINACZ is a task under VÝR
    'Management': None,     # Management = no production dept
}


def _parse_xlsx(filepath):
    """Parse HR Excel export. Returns list of dicts with employee data."""
    import openpyxl
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    # Find header row (contains 'Příjmení')
    header_idx = None
    for i, row in enumerate(rows):
        if row and any(str(c).strip() == 'Příjmení' for c in row if c):
            header_idx = i
            break
    if header_idx is None:
        return []

    headers = [str(c).strip() if c else '' for c in rows[header_idx]]

    # Parse data rows
    employees = []
    for row in rows[header_idx + 1:]:
        if not row or not any(row):
            continue
        data = {}
        for j, val in enumerate(row):
            if j < len(headers) and headers[j]:
                data[headers[j]] = val
        # Skip rows without name
        prijmeni = (data.get('Příjmení') or '').strip()
        jmeno = (data.get('Jméno') or '').strip()
        if not prijmeni:
            continue

        full_name = f"{prijmeni} {jmeno}".strip()
        stredisko = (data.get('Středisko') or '').strip()
        pozice = (data.get('Pozice') or '').strip()
        typ = (data.get('Typ pracovního poměru') or '').strip()
        hodiny = data.get('Týdenní pracovní doba')
        konec = str(data.get('Konec prac. poměru') or '')
        znacky = (data.get('Značky') or '').strip()
        email_prac = (data.get('Email pracovní') or '').strip()
        email_osob = (data.get('Email osobní') or '').strip()
        email = email_prac or email_osob  # work email has priority

        # Build note from position + type + hours
        note_parts = []
        if pozice:
            note_parts.append(pozice)
        if typ:
            note_parts.append(typ)
        if hodiny:
            note_parts.append(f"{int(hodiny)}h/týd")

        employees.append({
            'name': full_name,
            'stredisko': stredisko,
            'dept_mapped': STREDISKO_MAP.get(stredisko),
            'pozice': pozice,
            'typ': typ,
            'hodiny': int(hodiny) if hodiny else None,
            'note': ', '.join(note_parts),
            'active': '2222' in konec or '9999' in konec,
            'znacky': znacky,
            'email': email,
        })

    wb.close()
    return employees


def _get_dept_id_by_name(dept_short_name):
    """Lookup department ID by short name (e.g. 'VÝR')."""
    db = get_db()
    row = db.execute(
        "SELECT id FROM departments WHERE name = ? AND active = 1",
        (dept_short_name,)
    ).fetchone()
    return row['id'] if row else None


@bp.route('/')
def index():
    return render_template('import/index.html')


@bp.route('/upload', methods=['POST'])
def upload():
    """Upload and parse Excel file, show preview."""
    if 'file' not in request.files:
        flash('Nebyl vybrán žádný soubor.', 'error')
        return redirect(url_for('import_csv.index'))

    f = request.files['file']
    if not f.filename:
        flash('Nebyl vybrán žádný soubor.', 'error')
        return redirect(url_for('import_csv.index'))

    if not f.filename.lower().endswith(('.xlsx', '.xls')):
        flash('Podporovaný formát je .xlsx', 'error')
        return redirect(url_for('import_csv.index'))

    # Save to temp
    upload_dir = current_app.config.get('UPLOAD_DIR', 'instance/uploads')
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(f.filename)
    filepath = os.path.join(upload_dir, filename)
    f.save(filepath)

    try:
        employees = _parse_xlsx(filepath)
    except Exception as e:
        flash(f'Chyba při čtení souboru: {e}', 'error')
        return redirect(url_for('import_csv.index'))

    if not employees:
        flash('Soubor neobsahuje žádné zaměstnance.', 'error')
        return redirect(url_for('import_csv.index'))

    # Check which employees already exist
    for emp in employees:
        existing = find_employee_by_name(emp['name'])
        emp['exists'] = existing is not None
        emp['existing_id'] = existing['id'] if existing else None

    # Get available departments
    db = get_db()
    departments = db.execute(
        "SELECT id, name, full_name FROM departments WHERE active = 1 ORDER BY sort_order"
    ).fetchall()

    return render_template('import/preview.html',
                           employees=employees,
                           departments=departments,
                           filename=filename,
                           total=len(employees),
                           new_count=sum(1 for e in employees if not e['exists']),
                           existing_count=sum(1 for e in employees if e['exists']))


@bp.route('/confirm', methods=['POST'])
def confirm():
    """Execute the actual import based on user selections."""
    filename = request.form.get('filename')
    if not filename:
        flash('Chybí soubor.', 'error')
        return redirect(url_for('import_csv.index'))

    filepath = os.path.join(
        current_app.config.get('UPLOAD_DIR', 'instance/uploads'),
        secure_filename(filename)
    )
    if not os.path.exists(filepath):
        flash('Soubor vypršel. Nahrajte znovu.', 'error')
        return redirect(url_for('import_csv.index'))

    employees = _parse_xlsx(filepath)
    db = get_db()

    created = 0
    updated = 0
    skipped = 0
    qualified = 0

    for i, emp in enumerate(employees):
        # Check user checkbox (import this row?)
        if not request.form.get(f'import_{i}'):
            skipped += 1
            continue

        existing = find_employee_by_name(emp['name'])

        if existing:
            # Update note and email
            update_kwargs = {}
            if emp['note']:
                update_kwargs['note'] = emp['note']
            if emp.get('email'):
                update_kwargs['email'] = emp['email']
            if update_kwargs:
                update_employee(existing['id'], **update_kwargs)
            emp_id = existing['id']
            updated += 1
        else:
            # Create new employee
            emp_id = create_employee(
                name=emp['name'],
                note=emp['note'],
                email=emp.get('email', '')
            )
            created += 1

        # Set department qualification if mapped
        dept_name = emp.get('dept_mapped')
        if dept_name:
            dept_id = _get_dept_id_by_name(dept_name)
            if dept_id:
                # Check if qualification already exists
                existing_qual = db.execute(
                    """SELECT 1 FROM employee_qualifications
                       WHERE employee_id = ? AND department_id = ? AND task_id IS NULL""",
                    (emp_id, dept_id)
                ).fetchone()
                if not existing_qual:
                    db.execute(
                        """INSERT OR IGNORE INTO employee_qualifications
                           (employee_id, department_id, task_id)
                           VALUES (?, ?, NULL)""",
                        (emp_id, dept_id)
                    )
                    qualified += 1

        # Handle VINACZ special case: also add VINACZ task qualification
        if emp['stredisko'] == 'VINACZ':
            dept_id = _get_dept_id_by_name('VÝR')
            if dept_id:
                vinacz_task = db.execute(
                    "SELECT id FROM tasks WHERE department_id = ? AND name = 'VINACZ'",
                    (dept_id,)
                ).fetchone()
                if vinacz_task:
                    db.execute(
                        """INSERT OR IGNORE INTO employee_qualifications
                           (employee_id, department_id, task_id)
                           VALUES (?, ?, ?)""",
                        (emp_id, dept_id, vinacz_task['id'])
                    )

    db.commit()

    # Clean up uploaded file
    try:
        os.remove(filepath)
    except OSError:
        pass

    flash(
        f'Import dokončen: {created} nových, {updated} aktualizováno, '
        f'{skipped} přeskočeno, {qualified} kvalifikací přidáno.',
        'success'
    )
    return redirect(url_for('employees.index'))
