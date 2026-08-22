from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import services
from ..auth.decorators import roles_required
from ..forms import ClassRecordForm, DeleteConfirmForm

bp = Blueprint("classes", __name__)


def _exercise_rows_from_form():
    categories = request.form.getlist("exercise_category")
    names = request.form.getlist("exercise_name")
    return [{"category": c, "name": n} for c, n in zip(categories, names)]


def _exercise_rows_from_record(record):
    return [{"category": e.category, "name": e.name} for e in record.exercises] or [
        {"category": "", "name": ""}
    ]


@bp.route("/students/<int:student_id>/classes/new", methods=["GET", "POST"])
@roles_required("admin", "coach")
def new_class_record(student_id):
    student = services.get_student_or_404(student_id)
    form = ClassRecordForm()
    if request.method == "GET" and student.remaining <= 0:
        flash("已無上課堂數，請確認。", "warning")
    exercise_rows = (
        _exercise_rows_from_form() if request.method == "POST" else [{"category": "", "name": ""}]
    )
    if form.validate_on_submit():
        try:
            services.create_class_record(
                student,
                {
                    "class_date": form.class_date.data,
                    "class_time": form.class_time.data,
                    "duration_minutes": form.duration_minutes.data,
                    "notes": form.notes.data,
                    "exercises": exercise_rows,
                },
            )
            flash("上課紀錄已新增，堂數統計已更新。", "success")
            return redirect(url_for("students.student_detail", student_id=student.id))
        except services.ValidationError as exc:
            flash(exc.message, "danger")
    return render_template(
        "classes/form.html",
        form=form,
        mode="new",
        student=student,
        exercise_rows=exercise_rows,
        categories=services.list_exercise_categories(),
        catalog_map=services.exercise_catalog_name_map(),
    )


@bp.route("/classes/<int:record_id>/edit", methods=["GET", "POST"])
@roles_required("admin", "coach")
def edit_class_record(record_id):
    record = services.get_class_record_or_404(record_id)
    student = record.student
    form = ClassRecordForm(obj=record)
    exercise_rows = (
        _exercise_rows_from_form() if request.method == "POST" else _exercise_rows_from_record(record)
    )
    if form.validate_on_submit():
        try:
            services.update_class_record(
                record,
                {
                    "class_date": form.class_date.data,
                    "class_time": form.class_time.data,
                    "duration_minutes": form.duration_minutes.data,
                    "notes": form.notes.data,
                    "exercises": exercise_rows,
                },
            )
            flash("上課紀錄已更新（已上堂數不受影響）。", "success")
            return redirect(url_for("students.student_detail", student_id=student.id))
        except services.ValidationError as exc:
            flash(exc.message, "danger")
    return render_template(
        "classes/form.html",
        form=form,
        mode="edit",
        student=student,
        record=record,
        exercise_rows=exercise_rows,
        categories=services.list_exercise_categories(),
        catalog_map=services.exercise_catalog_name_map(),
    )


@bp.route("/classes/<int:record_id>/delete", methods=["POST"])
@roles_required("admin", "coach")
def delete_class_record(record_id):
    record = services.get_class_record_or_404(record_id)
    student_id = record.student_id
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        services.delete_class_record(record)
        flash("上課紀錄已刪除，堂數統計已重新計算。", "success")
    return redirect(url_for("students.student_detail", student_id=student_id))
