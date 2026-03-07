import logging
from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models.plan import (
    get_plan, get_all_plans, update_plan_status, delete_plan,
    upsert_assignment, clear_assignment, clear_day
)
from app.models.employee import get_employee
from app.models.department import get_all_departments, get_tasks_for_department
from app.models.shift import get_all_shifts
from app.services.planner_service import (
    create_or_get_plan, build_plan_grid, get_staffing_summary,
    get_monday, get_week_dates, ABSENCE_TYPES,
    copy_from_previous_week, refill_from_patterns
)
from app.services.export_service import generate_week_excel
from app.services.email_service import send_schedule_email, is_smtp_configured

logger = logging.getLogger(__name__)

bp = Blueprint('planner', __name__, url_prefix='/planner')

DAY_NAMES = ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne']
DAY_NAMES_FULL = ['Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Neděle']


@bp.route('/')
def index():
    """Show current week or redirect to specific week."""
    week = request.args.get('week')
    if not week:
        monday = get_monday()
        return redirect(url_for('planner.week_view', week_start=monday.isoformat()))
    return redirect(url_for('planner.week_view', week_start=week))


@bp.route('/week/<week_start>')
def week_view(week_start):
    """Main weekly planner view."""
    plan_id, is_new = create_or_get_plan(week_start)
    if is_new:
        flash('Nový plán vytvořen a předvyplněn z výchozích vzorů.', 'success')

    plan = get_plan(plan_id)
    grid, dates = build_plan_grid(plan_id, week_start)
    summary, task_summary = get_staffing_summary(plan_id, dates)
    departments = get_all_departments()
    shifts = get_all_shifts()

    # Prev/next week navigation
    parts = week_start.split('-')
    ws = date(int(parts[0]), int(parts[1]), int(parts[2]))
    prev_week = (ws - timedelta(weeks=1)).isoformat()
    next_week = (ws + timedelta(weeks=1)).isoformat()
    today_week = get_monday().isoformat()

    return render_template('planner/week.html',
                           plan=plan, grid=grid, dates=dates,
                           summary=summary, task_summary=task_summary,
                           departments=departments,
                           shifts=shifts, day_names=DAY_NAMES,
                           day_names_full=DAY_NAMES_FULL,
                           week_start=week_start,
                           prev_week=prev_week, next_week=next_week,
                           today_week=today_week,
                           absence_types=ABSENCE_TYPES)


@bp.route('/cell/<int:plan_id>/<int:emp_id>/<cell_date>', methods=['GET'])
def edit_cell(plan_id, emp_id, cell_date):
    """HTMX: return edit form for a single cell."""
    departments = get_all_departments()
    shifts = get_all_shifts()
    from app.db import get_db
    db = get_db()
    assignment = db.execute(
        """SELECT a.*, d.name as dept_name, t.name as task_name, st.name as shift_name
           FROM assignments a
           LEFT JOIN departments d ON a.department_id = d.id
           LEFT JOIN tasks t ON a.task_id = t.id
           LEFT JOIN shift_templates st ON a.shift_template_id = st.id
           WHERE a.plan_id = ? AND a.employee_id = ? AND a.date = ?""",
        (plan_id, emp_id, cell_date)
    ).fetchone()
    return render_template('planner/_cell_edit.html',
                           plan_id=plan_id, emp_id=emp_id, cell_date=cell_date,
                           assignment=assignment, departments=departments,
                           shifts=shifts, absence_types=ABSENCE_TYPES)


@bp.route('/cell/<int:plan_id>/<int:emp_id>/<cell_date>', methods=['POST'])
def save_cell(plan_id, emp_id, cell_date):
    """HTMX: save cell and return updated display."""
    action = request.form.get('action', 'save')

    if action == 'cancel':
        pass  # Just re-render the display without changes
    elif action == 'clear':
        clear_assignment(plan_id, emp_id, cell_date)
    elif action == 'absence':
        absence_type = request.form.get('absence_type', 'jine')
        note = request.form.get('note', '')
        upsert_assignment(plan_id, emp_id, cell_date,
                          is_absence=1, absence_type=absence_type, note=note)
    else:
        shift_id = request.form.get('shift_template_id') or None
        dept_id = request.form.get('department_id') or None
        task_id = request.form.get('task_id') or None
        note = request.form.get('note', '')
        # If nothing selected, treat as clear instead of creating empty record
        if not shift_id and not dept_id and not task_id and not note:
            clear_assignment(plan_id, emp_id, cell_date)
        else:
            upsert_assignment(plan_id, emp_id, cell_date,
                              shift_template_id=shift_id, department_id=dept_id,
                              task_id=task_id, note=note)

    # Return updated cell display
    from app.db import get_db
    db = get_db()
    assignment = db.execute(
        """SELECT a.*, d.name as dept_name, d.color as dept_color,
                  t.name as task_name, st.name as shift_name
           FROM assignments a
           LEFT JOIN departments d ON a.department_id = d.id
           LEFT JOIN tasks t ON a.task_id = t.id
           LEFT JOIN shift_templates st ON a.shift_template_id = st.id
           WHERE a.plan_id = ? AND a.employee_id = ? AND a.date = ?""",
        (plan_id, emp_id, cell_date)
    ).fetchone()
    html = render_template('planner/_cell_display.html',
                           plan_id=plan_id, emp_id=emp_id, cell_date=cell_date,
                           a=assignment)
    # Trigger summary refresh via HTMX (except on cancel)
    if action != 'cancel':
        return html, 200, {'HX-Trigger': 'cellSaved'}
    return html


@bp.route('/summary/<int:plan_id>/<week_start>')
def summary_row(plan_id, week_start):
    """HTMX: return updated staffing summary row."""
    dates = get_week_dates(week_start)
    summary, task_summary = get_staffing_summary(plan_id, dates)
    return render_template('planner/_summary_row.html',
                           dates=dates, summary=summary,
                           task_summary=task_summary)


@bp.route('/tasks/<int:dept_id>')
def api_tasks(dept_id):
    """HTMX: return task options for department select."""
    tasks = get_tasks_for_department(dept_id)
    html = '<option value="">—</option>'
    for t in tasks:
        html += f'<option value="{t["id"]}">{t["name"]}</option>'
    return html


@bp.route('/status/<int:plan_id>', methods=['POST'])
def change_status(plan_id):
    """Change plan status (draft/published)."""
    new_status = request.form.get('status', 'draft')
    update_plan_status(plan_id, new_status)
    label = 'publikován' if new_status == 'published' else 'vrácen do konceptu'
    flash(f'Plán {label}.', 'success')
    plan = get_plan(plan_id)
    return redirect(url_for('planner.week_view', week_start=plan['week_start']))


@bp.route('/copy-week/<int:plan_id>', methods=['POST'])
def copy_week(plan_id):
    """Copy assignments from previous week into current plan."""
    plan = get_plan(plan_id)
    if not plan:
        flash('Plán nenalezen.', 'error')
        return redirect(url_for('planner.index'))
    success, msg = copy_from_previous_week(plan_id, plan['week_start'])
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('planner.week_view', week_start=plan['week_start']))


@bp.route('/clear-day/<int:plan_id>/<day_date>', methods=['POST'])
def clear_day_route(plan_id, day_date):
    """Clear all assignments for a specific day."""
    plan = get_plan(plan_id)
    if not plan:
        flash('Plán nenalezen.', 'error')
        return redirect(url_for('planner.index'))
    clear_day(plan_id, day_date)
    flash('Den vymazán.', 'success')
    return redirect(url_for('planner.week_view', week_start=plan['week_start']))


@bp.route('/refill/<int:plan_id>', methods=['POST'])
def refill(plan_id):
    """Clear plan and refill from default patterns + constraints."""
    plan = get_plan(plan_id)
    if not plan:
        flash('Plán nenalezen.', 'error')
        return redirect(url_for('planner.index'))
    refill_from_patterns(plan_id, plan['week_start'])
    flash('Plán přeplněn z výchozích vzorů a omezení.', 'success')
    return redirect(url_for('planner.week_view', week_start=plan['week_start']))


@bp.route('/send-email/<int:plan_id>', methods=['POST'])
def send_email(plan_id):
    """Send weekly schedule via email to selected employees."""
    plan = get_plan(plan_id)
    if not plan:
        flash('Plán nenalezen.', 'error')
        return redirect(url_for('planner.index'))

    if not is_smtp_configured():
        flash('SMTP není nakonfigurován. Nastavte MAIL_USERNAME a MAIL_PASSWORD v prostředí.', 'error')
        return redirect(url_for('planner.week_view', week_start=plan['week_start']))

    emp_ids = request.form.getlist('emp_ids')
    if not emp_ids:
        flash('Nebyli vybráni žádní zaměstnanci.', 'warning')
        return redirect(url_for('planner.week_view', week_start=plan['week_start']))

    # Generate Excel once (shared attachment for all recipients)
    grid, dates = build_plan_grid(plan_id, plan['week_start'])
    summary, task_summary = get_staffing_summary(plan_id, dates)
    xlsx_bytes = generate_week_excel(plan, grid, dates, summary, task_summary)

    week_label = f"týden {plan['week_number']}/{plan['year']}"
    filename = f"Plan_smen_{dates[0].strftime('%d.%m.')}-{dates[6].strftime('%d.%m.%Y')}.xlsx"

    sent = 0
    errors = []
    for eid in emp_ids:
        emp = get_employee(int(eid))
        if emp and emp['email']:
            try:
                send_schedule_email(emp['email'], emp['name'], week_label, xlsx_bytes, filename)
                sent += 1
            except Exception as e:
                logger.error(f"Email failed for {emp['name']} ({emp['email']}): {e}")
                errors.append(emp['name'])

    if errors:
        flash(f'Odesláno: {sent}. Chyba u: {", ".join(errors)}', 'error')
    else:
        flash(f'Rozpis odeslán {sent} zaměstnanc{"i" if sent == 1 else "ům"}.', 'success')

    return redirect(url_for('planner.week_view', week_start=plan['week_start']))
