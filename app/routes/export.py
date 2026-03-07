from flask import Blueprint, make_response, abort
from app.models.plan import get_plan_by_week
from app.services.planner_service import build_plan_grid, get_staffing_summary, get_week_dates
from app.services.export_service import generate_week_excel

bp = Blueprint('export', __name__, url_prefix='/export')


@bp.route('/week/<week_start>')
def export_week(week_start):
    """Download weekly plan as Excel file."""
    plan = get_plan_by_week(week_start)
    if not plan:
        abort(404)

    grid, dates = build_plan_grid(plan['id'], week_start)
    summary, task_summary = get_staffing_summary(plan['id'], dates)

    xlsx_bytes = generate_week_excel(plan, grid, dates, summary, task_summary)

    # Build filename: Plan_smen_02.03.-08.03.2026.xlsx
    date_from = dates[0].strftime('%d.%m.')
    date_to = dates[6].strftime('%d.%m.%Y')
    filename = f'Plan_smen_{date_from}-{date_to}.xlsx'

    response = make_response(xlsx_bytes)
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
