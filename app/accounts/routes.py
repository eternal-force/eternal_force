from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .. import list_filters, services
from ..auth.decorators import roles_required
from ..extensions import db
from ..forms import CoachForm, DeleteConfirmForm, SetPasswordForm
from ..models import User

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


def _get_user_or_404(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    return user


@bp.route("/")
@roles_required("admin", "coach")
def list_accounts():
    restored = list_filters.restore_or_remember(("search", "role"))
    if restored:
        return restored

    search = request.args.get("search", "").strip()
    role = request.args.get("role", "").strip()
    accounts = services.list_accounts(search=search, role=role)
    return render_template(
        "accounts/list.html",
        accounts=accounts,
        search=search,
        role=role,
        delete_form=DeleteConfirmForm(),
    )


@bp.route("/<int:user_id>")
@roles_required("admin", "coach")
def view_account(user_id):
    user = _get_user_or_404(user_id)
    return render_template(
        "accounts/detail.html",
        account=user,
        delete_form=DeleteConfirmForm(),
        password_form=SetPasswordForm(),
    )


@bp.route("/<int:user_id>/verify", methods=["POST"])
@roles_required("admin", "coach")
def verify(user_id):
    user = _get_user_or_404(user_id)
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        services.verify_account(user)
        flash(f"帳號「{user.username}」已驗證啟用。", "success")
    return redirect(url_for("accounts.list_accounts"))


@bp.route("/<int:user_id>/status", methods=["POST"])
@roles_required("admin", "coach")
def change_status(user_id):
    user = _get_user_or_404(user_id)
    if current_user.role == "coach" and user.role != "student":
        abort(403)
    target_status = request.form.get("target_status")
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        try:
            services.set_account_status(user, target_status)
            label = "停用" if target_status == "disabled" else "啟用"
            flash(f"已{label}帳號「{user.username}」。", "success")
        except services.ValidationError as exc:
            flash(exc.message, "danger")
    return redirect(url_for("accounts.list_accounts"))


@bp.route("/<int:user_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_account(user_id):
    user = _get_user_or_404(user_id)
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        try:
            username = user.username
            services.delete_account(user)
            flash(f"帳號「{username}」已刪除。", "success")
            return redirect(url_for("accounts.list_accounts"))
        except services.ValidationError as exc:
            flash(exc.message, "danger")
    return redirect(url_for("accounts.view_account", user_id=user_id))


@bp.route("/<int:user_id>/role", methods=["POST"])
@roles_required("admin")
def change_role(user_id):
    user = _get_user_or_404(user_id)
    target_role = request.form.get("target_role")
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        try:
            services.set_account_role(user, target_role)
            label = {"coach": "教練", "student": "學生"}.get(target_role, target_role)
            flash(f"已將帳號「{user.username}」的角色調整為{label}。", "success")
        except services.ValidationError as exc:
            flash(exc.message, "danger")
    return redirect(url_for("accounts.list_accounts"))


@bp.route("/<int:user_id>/password", methods=["POST"])
@roles_required("admin")
def change_password(user_id):
    user = _get_user_or_404(user_id)
    form = SetPasswordForm()
    if form.validate_on_submit():
        services.set_account_password(user, form.new_password.data)
        flash(f"已變更帳號「{user.username}」的密碼。", "success")
    else:
        for field_errors in form.errors.values():
            for message in field_errors:
                flash(message, "danger")
    return redirect(url_for("accounts.view_account", user_id=user_id))


@bp.route("/new-coach", methods=["GET", "POST"])
@roles_required("admin", "coach")
def new_coach():
    form = CoachForm()
    if form.validate_on_submit():
        user = services.create_coach_account(
            {
                "username": form.username.data,
                "password": form.password.data,
                "name": form.name.data,
                "email": form.email.data,
                "phone": form.phone.data,
                "phone_type": form.phone_type.data,
            }
        )
        flash(f"教練帳號「{user.username}」已建立並啟用。", "success")
        return redirect(url_for("accounts.list_accounts"))
    return render_template("accounts/new_coach.html", form=form)
