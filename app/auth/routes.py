from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .. import list_filters, services
from ..extensions import limiter
from ..forms import ChangeOwnPasswordForm, LoginForm, RegisterForm
from ..models import User

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("students.list_students"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user and user.check_password(form.password.data):
            if user.status == "pending":
                flash("帳號尚待管理者驗證，請耐心等候。", "warning")
            elif user.status == "disabled":
                flash("此帳號已被停用，請聯絡管理者。", "danger")
            else:
                login_user(user)
                if user.must_change_password:
                    flash("首次登入請先修改密碼。", "warning")
                    return redirect(url_for("auth.change_own_password"))
                flash("登入成功。", "success")
                next_url = request.args.get("next")
                if next_url and next_url.startswith("/"):
                    return redirect(next_url)
                return redirect(url_for("students.list_students"))
        else:
            flash("帳號或密碼錯誤。", "danger")

    return render_template("auth/login.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("students.list_students"))

    form = RegisterForm()
    if form.validate_on_submit():
        services.register_student_account(
            {
                "username": form.username.data,
                "password": form.password.data,
                "name": form.name.data,
                "email": form.email.data,
                "phone": form.phone.data,
                "phone_type": form.phone_type.data,
                "birthday": form.birthday.data,
                "gender": form.gender.data,
                "goal": form.goal.data,
            }
        )
        flash("註冊成功，請等候管理者驗證帳號後即可登入。", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_own_password():
    form = ChangeOwnPasswordForm()
    if form.validate_on_submit():
        try:
            services.change_own_password(current_user, form.current_password.data, form.new_password.data)
        except services.ValidationError as exc:
            getattr(form, exc.field).errors.append(exc.message)
        else:
            flash("密碼已更新。", "success")
            return redirect(url_for("students.list_students"))
    return render_template("auth/change_password.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    list_filters.clear_all()
    flash("已登出。", "success")
    return redirect(url_for("auth.login"))
