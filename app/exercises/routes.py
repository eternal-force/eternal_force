from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import services
from ..auth.decorators import roles_required
from ..forms import DeleteConfirmForm, ExerciseCatalogForm

bp = Blueprint("exercises", __name__, url_prefix="/exercises")


def _apply_form_error(form, exc):
    field = getattr(form, exc.field, None) if exc.field else None
    if field is not None:
        field.errors.append(exc.message)
    else:
        flash(exc.message, "danger")


def _grouped_by_category(items):
    groups = {}
    for item in items:
        groups.setdefault(item.category, []).append(item)
    return list(groups.items())


@bp.route("/")
@roles_required("admin", "coach")
def list_exercises():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    items = services.list_exercise_catalog(search=search, category=category)

    return render_template(
        "exercises/list.html",
        groups=_grouped_by_category(items),
        categories=services.list_exercise_categories(),
        search=search,
        category=category,
        delete_form=DeleteConfirmForm(),
    )


@bp.route("/new", methods=["GET", "POST"])
@roles_required("admin", "coach")
def new_exercise():
    form = ExerciseCatalogForm()
    if form.validate_on_submit():
        try:
            item = services.create_exercise_catalog_item(
                {"category": form.category.data, "name": form.name.data}
            )
            flash(f"訓練項目「{item.name}」已新增。", "success")
            return redirect(url_for("exercises.list_exercises"))
        except services.ValidationError as exc:
            _apply_form_error(form, exc)
    return render_template(
        "exercises/form.html", form=form, mode="new", categories=services.list_exercise_categories()
    )


@bp.route("/<int:item_id>/edit", methods=["GET", "POST"])
@roles_required("admin", "coach")
def edit_exercise(item_id):
    item = services.get_exercise_catalog_item_or_404(item_id)
    form = ExerciseCatalogForm(obj=item)
    if form.validate_on_submit():
        try:
            services.update_exercise_catalog_item(
                item, {"category": form.category.data, "name": form.name.data}
            )
            flash("訓練項目已更新。", "success")
            return redirect(url_for("exercises.list_exercises"))
        except services.ValidationError as exc:
            _apply_form_error(form, exc)
    return render_template(
        "exercises/form.html",
        form=form,
        mode="edit",
        item=item,
        categories=services.list_exercise_categories(),
    )


@bp.route("/<int:item_id>/delete", methods=["POST"])
@roles_required("admin", "coach")
def delete_exercise(item_id):
    item = services.get_exercise_catalog_item_or_404(item_id)
    form = DeleteConfirmForm()
    if form.validate_on_submit():
        name = item.name
        services.delete_exercise_catalog_item(item)
        flash(f"訓練項目「{name}」已刪除。", "success")
    return redirect(url_for("exercises.list_exercises"))
