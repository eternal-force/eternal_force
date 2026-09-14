from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import services
from ..auth.decorators import roles_required
from ..forms import DeleteConfirmForm, StudentForm
from ..models import Student

bp = Blueprint("students", __name__, url_prefix="/students")


@bp.route("/")
@login_required
def list_students():
    if current_user.role == "student":
        if current_user.student_id is None:
            abort(404)
        return redirect(url_for("students.student_detail", student_id=current_user.student_id))

    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Student.query
    if search:
        query = query.filter(Student.name.ilike(f"%{search}%"))
    if status in ("active", "inactive"):
        query = query.filter(Student.status == status)
    query = query.order_by(Student.created_at.desc())

    pagination = query.paginate(page=page, per_page=12, error_out=False)

    return render_template(
        "students/list.html",
        students=pagination.items,
        pagination=pagination,
        search=search,
        status=status,
    )


@bp.route("/new", methods=["GET", "POST"])
@roles_required("admin", "coach")
def new_student():
    form = StudentForm(status="active")
    if form.validate_on_submit():
        try:
            student = services.create_student(
                {
                    "name": form.name.data,
                    "phone": form.phone.data,
                    "phone_type": form.phone_type.data,
                    "email": form.email.data,
                    "birthday": form.birthday.data,
                    "gender": form.gender.data,
                    "enrollment_date": form.enrollment_date.data,
                    "status": form.status.data,
                    "notes": form.notes.data,
                }
            )
            flash(f"學生「{student.name}」已建立。", "success")
            return redirect(url_for("students.student_detail", student_id=student.id))
        except services.ValidationError as exc:
            flash(exc.message, "danger")
    return render_template("students/form.html", form=form, mode="new")


@bp.route("/<int:student_id>")
@login_required
def student_detail(student_id):
    if current_user.role == "student" and student_id != current_user.student_id:
        abort(403)
    student = services.get_student_or_404(student_id)
    return render_template(
        "students/detail.html",
        student=student,
        summary=services.summary_dict(student),
        delete_form=DeleteConfirmForm(),
    )


@bp.route("/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
def edit_student(student_id):
    if current_user.role == "student" and student_id != current_user.student_id:
        abort(403)
    can_edit_status = current_user.role != "student"
    student = services.get_student_or_404(student_id)
    form = StudentForm(obj=student)
    if form.validate_on_submit():
        data = {
            "name": form.name.data,
            "phone": form.phone.data,
            "phone_type": form.phone_type.data,
            "email": form.email.data,
            "birthday": form.birthday.data,
            "gender": form.gender.data,
            "enrollment_date": form.enrollment_date.data,
            "notes": form.notes.data,
        }
        if can_edit_status:
            data["status"] = form.status.data
        try:
            services.update_student(student, data)
            flash("學生資料已更新。", "success")
            return redirect(url_for("students.student_detail", student_id=student.id))
        except services.ValidationError as exc:
            flash(exc.message, "danger")
    return render_template(
        "students/form.html", form=form, mode="edit", student=student, can_edit_status=can_edit_status
    )


@bp.route("/<int:student_id>/status", methods=["POST"])
@roles_required("admin", "coach")
def change_status(student_id):
    student = services.get_student_or_404(student_id)
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        new_status = "inactive" if student.status == "active" else "active"
        services.set_student_status(student, new_status)
        label = "停用" if new_status == "inactive" else "重新啟用"
        flash(f"已{label}學生「{student.name}」。", "success")
    return redirect(url_for("students.student_detail", student_id=student.id))
