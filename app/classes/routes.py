from itertools import zip_longest

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import services
from ..auth.decorators import roles_required
from ..forms import ClassRecordForm, DeleteConfirmForm

bp = Blueprint("classes", __name__)

_EMPTY_EXERCISE_ROW = {
    "category": "",
    "name": "",
    "weight_kg": "",
    "sets": "",
    "reps": "",
    "note": "",
}


def _exercise_rows_from_form():
    categories = request.form.getlist("exercise_category")
    names = request.form.getlist("exercise_name")
    weights = request.form.getlist("exercise_weight_kg")
    sets = request.form.getlist("exercise_sets")
    reps = request.form.getlist("exercise_reps")
    notes = request.form.getlist("exercise_note")
    return [
        {"category": c, "name": n, "weight_kg": w, "sets": s, "reps": r, "note": note}
        for c, n, w, s, r, note in zip_longest(
            categories, names, weights, sets, reps, notes, fillvalue=""
        )
    ]


def _exercise_rows_from_record(record):
    return [
        {
            "category": e.category,
            "name": e.name,
            "weight_kg": e.weight_kg if e.weight_kg is not None else "",
            "sets": e.sets if e.sets is not None else "",
            "reps": e.reps if e.reps is not None else "",
            "note": e.note or "",
        }
        for e in record.exercises
    ] or [dict(_EMPTY_EXERCISE_ROW)]


def _coach_choices():
    return [("", "請選擇教練")] + [
        (str(coach.id), coach.name) for coach in services.list_active_coaches()
    ]


@bp.route("/students/<int:student_id>/classes/new", methods=["GET", "POST"])
@roles_required("admin", "coach")
def new_class_record(student_id):
    student = services.get_student_or_404(student_id)
    form = ClassRecordForm()
    form.coach_id.choices = _coach_choices()
    if request.method == "GET" and student.remaining <= 0:
        flash("已無上課堂數，請確認。", "warning")
    exercise_rows = (
        _exercise_rows_from_form() if request.method == "POST" else [dict(_EMPTY_EXERCISE_ROW)]
    )
    if form.validate_on_submit():
        try:
            services.create_class_record(
                student,
                {
                    "class_date": form.class_date.data,
                    "class_time": form.class_time.data,
                    "coach_id": int(form.coach_id.data) if form.coach_id.data else None,
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
    form.coach_id.choices = _coach_choices()
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
                    "coach_id": int(form.coach_id.data) if form.coach_id.data else None,
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
