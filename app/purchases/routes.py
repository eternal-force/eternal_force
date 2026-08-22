from flask import Blueprint, flash, redirect, render_template, url_for

from .. import services
from ..auth.decorators import roles_required
from ..forms import DeleteConfirmForm, PurchaseForm

bp = Blueprint("purchases", __name__)


@bp.route("/students/<int:student_id>/purchases/new", methods=["GET", "POST"])
@roles_required("admin", "coach")
def new_purchase(student_id):
    student = services.get_student_or_404(student_id)
    form = PurchaseForm()
    if form.validate_on_submit():
        services.create_purchase(
            student,
            {
                "purchase_date": form.purchase_date.data,
                "quantity": form.quantity.data,
                "price": form.price.data,
                "notes": form.notes.data,
            },
        )
        flash("購買紀錄已新增，堂數統計已更新。", "success")
        return redirect(url_for("students.student_detail", student_id=student.id))
    return render_template("purchases/form.html", form=form, mode="new", student=student)


@bp.route("/purchases/<int:purchase_id>/edit", methods=["GET", "POST"])
@roles_required("admin", "coach")
def edit_purchase(purchase_id):
    record = services.get_purchase_or_404(purchase_id)
    student = record.student
    form = PurchaseForm(obj=record)
    if form.validate_on_submit():
        services.update_purchase(
            record,
            {
                "purchase_date": form.purchase_date.data,
                "quantity": form.quantity.data,
                "price": form.price.data,
                "notes": form.notes.data,
            },
        )
        flash("購買紀錄已更新，堂數統計已重新計算。", "success")
        return redirect(url_for("students.student_detail", student_id=student.id))
    return render_template("purchases/form.html", form=form, mode="edit", student=student, record=record)


@bp.route("/purchases/<int:purchase_id>/delete", methods=["POST"])
@roles_required("admin", "coach")
def delete_purchase(purchase_id):
    record = services.get_purchase_or_404(purchase_id)
    student_id = record.student_id
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        services.delete_purchase(record)
        flash("購買紀錄已刪除，堂數統計已重新計算。", "success")
    return redirect(url_for("students.student_detail", student_id=student_id))
