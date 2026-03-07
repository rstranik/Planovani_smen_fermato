from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models.constraint import (
    get_all_constraints, get_constraint, create_constraint,
    update_constraint, delete_constraint
)
from app.models.employee import get_all_employees
from app.services.planner_service import ABSENCE_TYPES

bp = Blueprint('constraints', __name__, url_prefix='/constraints')


@bp.route('/')
def index():
    employee_id = request.args.get('employee_id', type=int)
    constraints = get_all_constraints(employee_id=employee_id)
    employees = get_all_employees(active_only=True)
    return render_template('constraints/index.html',
                           constraints=constraints,
                           employees=employees,
                           absence_types=ABSENCE_TYPES,
                           selected_employee=employee_id)


@bp.route('/add', methods=['POST'])
def add():
    employee_id = request.form.get('employee_id', type=int)
    date_from = request.form.get('date_from', '').strip()
    date_to = request.form.get('date_to', '').strip()
    type_ = request.form.get('type', '').strip()
    note = request.form.get('note', '').strip()

    if not employee_id or not date_from or not date_to or not type_:
        flash('Vyplňte všechny povinné údaje.', 'error')
        return redirect(url_for('constraints.index'))

    if date_to < date_from:
        flash('Datum "do" nesmí být před datem "od".', 'error')
        return redirect(url_for('constraints.index'))

    try:
        create_constraint(employee_id, date_from, date_to, type_, note=note)
        flash('Omezení přidáno.', 'success')
    except Exception as e:
        flash(f'Chyba: {e}', 'error')

    return redirect(url_for('constraints.index'))


@bp.route('/<int:constraint_id>/edit', methods=['POST'])
def edit(constraint_id):
    employee_id = request.form.get('employee_id', type=int)
    date_from = request.form.get('date_from', '').strip()
    date_to = request.form.get('date_to', '').strip()
    type_ = request.form.get('type', '').strip()
    note = request.form.get('note', '').strip()

    if date_to < date_from:
        flash('Datum "do" nesmí být před datem "od".', 'error')
        return redirect(url_for('constraints.index'))

    update_constraint(constraint_id,
                      employee_id=employee_id,
                      date_from=date_from,
                      date_to=date_to,
                      type=type_,
                      note=note)
    flash('Omezení aktualizováno.', 'success')
    return redirect(url_for('constraints.index'))


@bp.route('/<int:constraint_id>/delete', methods=['POST'])
def delete(constraint_id):
    try:
        delete_constraint(constraint_id)
        flash('Omezení smazáno.', 'success')
    except Exception as e:
        flash(f'Chyba: {e}', 'error')
    return redirect(url_for('constraints.index'))
