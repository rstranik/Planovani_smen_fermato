from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import get_user_by_username, update_last_login, update_user_password

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = get_user_by_username(username)

        if user is None or not user.check_password(password):
            flash('Neplatné uživatelské jméno nebo heslo.', 'error')
            return render_template('auth/login.html', username=username)

        if not user.is_active:
            flash('Účet je deaktivován. Kontaktujte administrátora.', 'error')
            return render_template('auth/login.html', username=username)

        login_user(user, remember=True)
        update_last_login(user.id)

        next_page = request.args.get('next')
        if next_page and next_page.startswith('/'):
            return redirect(next_page)
        return redirect(url_for('dashboard.index'))

    return render_template('auth/login.html')


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Byli jste odhlášeni.', 'success')
    return redirect(url_for('auth.login'))


@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not current_user.check_password(current_pw):
            flash('Současné heslo není správné.', 'error')
            return render_template('auth/change_password.html')

        if len(new_pw) < 6:
            flash('Nové heslo musí mít alespoň 6 znaků.', 'error')
            return render_template('auth/change_password.html')

        if new_pw != confirm_pw:
            flash('Hesla se neshodují.', 'error')
            return render_template('auth/change_password.html')

        update_user_password(current_user.id, new_pw)
        flash('Heslo bylo změněno.', 'success')
        return redirect(url_for('dashboard.index'))

    return render_template('auth/change_password.html')
