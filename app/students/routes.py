from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload

from .. import list_filters, services
from ..auth.decorators import roles_required
from ..extensions import db
from ..forms import DeleteConfirmForm, StudentForm
from ..models import ClassRecord, PurchaseRecord, Student, User

bp = Blueprint("students", __name__, url_prefix="/students")


@bp.route("/")
@login_required
def list_students():
    if current_user.role == "student":
        if current_user.student_id is None:
            abort(404)
        return redirect(url_for("students.student_detail", student_id=current_user.student_id))

    restored = list_filters.restore_or_remember(("search", "status", "class_type", "page"))
    if restored:
        return restored

    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()
    class_type = request.args.get("class_type", "").strip()
    page = request.args.get("page", 1, type=int)

    # 列表每張卡片都會顯示帳號與堂數統計，一次批次載入，避免每位學生各查 3 次資料庫
    query = services.visible_students_query(current_user).options(
        selectinload(Student.accounts),
        selectinload(Student.purchase_records),
        selectinload(Student.class_records),
    )
    if search:
        query = query.filter(Student.name.ilike(f"%{search}%"))
    if status in ("active", "inactive"):
        query = query.filter(Student.status == status)
    if class_type in services.CLASS_TYPE_LABELS:
        query = query.filter(Student.class_type == class_type)
    # 剩餘堂數不足 5 堂(含超上)的學生優先呈現，依剩餘堂數由少到多；其餘依建立時間新到舊。
    # 在 SQL 計算剩餘堂數(與 Student.remaining 相同邏輯)，分頁後各頁排序才會一致。
    purchased = (
        db.select(
            db.func.coalesce(
                db.func.sum(PurchaseRecord.quantity - PurchaseRecord.opening_deduction), 0
            )
        )
        .where(PurchaseRecord.student_id == Student.id)
        .correlate(Student)
        .scalar_subquery()
    )
    attended = (
        db.select(db.func.count(ClassRecord.id))
        .where(ClassRecord.student_id == Student.id, ClassRecord.is_opening.is_(False))
        .correlate(Student)
        .scalar_subquery()
    )
    remaining = purchased - attended
    is_low = remaining < 5
    query = query.order_by(
        db.case((is_low, 0), else_=1),
        db.case((is_low, remaining), else_=0),
        Student.created_at.desc(),
        Student.id.desc(),
    )

    pagination = query.paginate(page=page, per_page=12, error_out=False)

    return render_template(
        "students/list.html",
        students=pagination.items,
        pagination=pagination,
        search=search,
        status=status,
        class_type=class_type,
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
                    "status": form.status.data,
                    "notes": form.notes.data,
                }
            )
            flash(f"學生「{student.name}」已建立。", "success")
            return redirect(url_for("students.student_detail", student_id=student.id))
        except services.ValidationError as exc:
            flash(exc.message, "danger")
    return render_template("students/form.html", form=form, mode="new", today=date.today())


@bp.route("/<int:student_id>")
@login_required
def student_detail(student_id):
    if current_user.role == "student" and student_id != current_user.student_id:
        abort(403)
    # 每筆上課紀錄都會顯示教練與訓練菜單，一次批次載入，避免每筆紀錄各查一次資料庫
    student = services.get_student_or_404(
        student_id,
        current_user,
        options=(
            selectinload(Student.accounts),
            selectinload(Student.purchase_records),
            selectinload(Student.class_records).selectinload(ClassRecord.exercises),
            selectinload(Student.class_records).joinedload(ClassRecord.coach),
        ),
    )
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
    student = services.get_student_or_404(student_id, current_user)
    if student.is_pair:
        return _edit_pair_member(student)
    form = StudentForm(obj=student)
    if form.validate_on_submit():
        data = {
            "name": form.name.data,
            "phone": form.phone.data,
            "phone_type": form.phone_type.data,
            "email": form.email.data,
            "birthday": form.birthday.data,
            "gender": form.gender.data,
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


def _edit_pair_member(student):
    """一對二卡片的個人資料存在各自的帳號上：學生只能改自己，管理者/教練以 ?member= 指定要改哪一位。"""
    if current_user.role == "student":
        member = current_user
    else:
        member = services.get_pair_member_or_404(student, request.args.get("member", type=int))
    form = StudentForm(
        name=member.name,
        phone=member.phone,
        phone_type=member.phone_type,
        email=member.email,
        birthday=member.birthday,
        gender=member.gender,
        status=student.status,
        notes=member.goal,
    )
    if form.validate_on_submit():
        try:
            services.update_pair_member(
                student,
                member,
                {
                    "name": form.name.data,
                    "phone": form.phone.data,
                    "phone_type": form.phone_type.data,
                    "email": form.email.data,
                    "birthday": form.birthday.data,
                    "gender": form.gender.data,
                    "notes": form.notes.data,
                },
            )
            flash("學生資料已更新。", "success")
            return redirect(url_for("students.student_detail", student_id=student.id))
        except services.ValidationError as exc:
            flash(exc.message, "danger")
    return render_template(
        "students/form.html", form=form, mode="edit", student=student, member=member, can_edit_status=False
    )


@bp.route("/<int:student_id>/pair", methods=["GET", "POST"])
@roles_required("admin", "coach")
def pair_student(student_id):
    student = services.get_student_or_404(student_id, current_user)
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        partner = db.session.get(User, request.form.get("partner_id", type=int) or 0)
        if partner is not None and not services.can_access_account(current_user, partner):
            abort(403)
        try:
            pair = services.pair_students(student, partner)
            flash(f"已建立一對二「{pair.name}」，兩位學員登入後會看到共同的堂數與訓練菜單。", "success")
            return redirect(url_for("students.student_detail", student_id=pair.id))
        except services.ValidationError as exc:
            flash(exc.message, "danger")
    return render_template(
        "students/pair.html",
        student=student,
        summary=services.summary_dict(student),
        candidates=services.list_pair_candidates(current_user, student),
        form=form,
    )


@bp.route("/<int:student_id>/split", methods=["POST"])
@roles_required("admin", "coach")
def split_student(student_id):
    student = services.get_student_or_404(student_id, current_user)
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        name = student.name
        try:
            services.split_pair(student)
        except services.ValidationError as exc:
            flash(exc.message, "danger")
            return redirect(url_for("students.student_detail", student_id=student_id))
        flash(f"已將「{name}」拆分為一對一，兩位學員已回到各自的一對一學生卡片。", "success")
        return redirect(url_for("students.list_students"))
    return redirect(url_for("students.student_detail", student_id=student_id))


@bp.route("/<int:student_id>/status", methods=["POST"])
@roles_required("admin", "coach")
def change_status(student_id):
    student = services.get_student_or_404(student_id, current_user)
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        new_status = "inactive" if student.status == "active" else "active"
        services.set_student_status(student, new_status)
        label = "停用" if new_status == "inactive" else "重新啟用"
        flash(f"已{label}學生「{student.name}」。", "success")
    return redirect(url_for("students.student_detail", student_id=student.id))
