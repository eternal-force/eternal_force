from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import list_filters, services
from ..auth.decorators import roles_required
from ..forms import AnnouncementForm, DeleteConfirmForm

bp = Blueprint("announcements", __name__, url_prefix="/announcements")

MANAGER_ROLES = ("admin", "coach")


def _apply_form_error(form, exc):
    field = getattr(form, exc.field, None) if exc.field else None
    if field is not None:
        field.errors.append(exc.message)
    else:
        flash(exc.message, "danger")


def _form_data(form):
    upload = form.image.data
    image_data = upload.read() if upload and getattr(upload, "filename", "") else None
    return {
        "announce_date": form.announce_date.data,
        "publish_at": form.publish_at.data,
        "unpublish_at": form.unpublish_at.data,
        "title": form.title.data,
        "content": form.content.data,
        "show_to_student": form.show_to_student.data,
        "show_to_coach": form.show_to_coach.data,
        "show_to_admin": form.show_to_admin.data,
        "image_data": image_data,
        "remove_image": form.remove_image.data,
    }


@bp.route("/")
@roles_required(*MANAGER_ROLES)
def list_announcements():
    restored = list_filters.restore_or_remember(("status",))
    if restored:
        return restored

    status = request.args.get("status", "").strip()
    if status not in services.ANNOUNCEMENT_STATUS_LABELS:
        status = ""
    now = services.taipei_now()
    announcements = services.list_announcements(status=status or None)
    return render_template(
        "announcements/list.html",
        announcements=[(a, services.announcement_status(a, now)) for a in announcements],
        status=status,
        status_labels=services.ANNOUNCEMENT_STATUS_LABELS,
        delete_form=DeleteConfirmForm(),
    )


@bp.route("/new", methods=["GET", "POST"])
@roles_required(*MANAGER_ROLES)
def new_announcement():
    form = AnnouncementForm()
    if form.validate_on_submit():
        try:
            item = services.create_announcement(_form_data(form), created_by=current_user)
            flash(f"公告「{item.title}」已新增。", "success")
            return redirect(url_for("announcements.list_announcements"))
        except services.ValidationError as exc:
            _apply_form_error(form, exc)
    return render_template("announcements/form.html", form=form, mode="new")


@bp.route("/<int:announcement_id>/edit", methods=["GET", "POST"])
@roles_required(*MANAGER_ROLES)
def edit_announcement(announcement_id):
    item = services.get_announcement_or_404(announcement_id)
    form = AnnouncementForm(obj=item)
    if form.validate_on_submit():
        try:
            services.update_announcement(item, _form_data(form))
            flash("公告已更新。", "success")
            return redirect(url_for("announcements.list_announcements"))
        except services.ValidationError as exc:
            _apply_form_error(form, exc)
    return render_template("announcements/form.html", form=form, mode="edit", item=item)


@bp.route("/<int:announcement_id>/delete", methods=["POST"])
@roles_required(*MANAGER_ROLES)
def delete_announcement(announcement_id):
    item = services.get_announcement_or_404(announcement_id)
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        title = item.title
        services.delete_announcement(item)
        flash(f"公告「{title}」已刪除。", "success")
    return redirect(url_for("announcements.list_announcements"))


@bp.route("/<int:announcement_id>/image")
@login_required
def announcement_image(announcement_id):
    item = services.get_announcement_or_404(announcement_id)
    # 管理者/教練可看所有公告圖片(後台預覽)；其他人只能看目前上架且對象包含自己的公告圖片。
    if current_user.role not in MANAGER_ROLES and not (
        item.visible_to(current_user.role) and services.announcement_status(item) == "live"
    ):
        abort(404)
    if not item.has_image:
        abort(404)
    response = make_response(item.image_data)
    response.headers["Content-Type"] = item.image_mime
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response
