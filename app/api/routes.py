"""JSON REST API，對應規格書「四、建議 API 清單」。

僅供已登入的管理者或教練(同一瀏覽器 session)呼叫，作為系統內部工具/測試用途；學生角色一律回傳 403；
因此不強制要求呼叫端額外帶 CSRF token(已在 create_app() 中對此 blueprint 執行 csrf.exempt)，
但仍要求登入 session 才可存取，未登入一律回傳 401 JSON 而非導向登入頁。
"""

from datetime import datetime

from flask import Blueprint, jsonify, request

from .. import services
from ..auth.decorators import roles_required

bp = Blueprint("api", __name__, url_prefix="/api")


def _parse_date(value, field):
    if value in (None, ""):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise services.ValidationError(f"{field} 格式需為 YYYY-MM-DD", field=field)


def _parse_time(value, field):
    if value in (None, ""):
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except (TypeError, ValueError):
            continue
    raise services.ValidationError(f"{field} 格式需為 HH:MM", field=field)


def _json_body():
    return request.get_json(silent=True) or {}


@bp.route("/students", methods=["GET"])
@roles_required("admin", "coach")
def api_list_students():
    search = request.args.get("search")
    status = request.args.get("status")
    students = services.list_students(search=search, status=status)
    return jsonify([s.to_dict() for s in students])


@bp.route("/students", methods=["POST"])
@roles_required("admin", "coach")
def api_create_student():
    data = _json_body()
    try:
        payload = dict(data)
        payload["birthday"] = _parse_date(data.get("birthday"), "birthday")
        student = services.create_student(payload)
    except services.ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    return jsonify(student.to_dict()), 201


@bp.route("/students/<int:student_id>", methods=["GET"])
@roles_required("admin", "coach")
def api_get_student(student_id):
    student = services.get_student_or_404(student_id)
    return jsonify(student.to_dict())


@bp.route("/students/<int:student_id>", methods=["PUT", "PATCH"])
@roles_required("admin", "coach")
def api_update_student(student_id):
    student = services.get_student_or_404(student_id)
    data = _json_body()
    try:
        payload = dict(data)
        if "birthday" in data:
            payload["birthday"] = _parse_date(data.get("birthday"), "birthday")
        student = services.update_student(student, payload)
    except services.ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    return jsonify(student.to_dict())


@bp.route("/students/<int:student_id>", methods=["DELETE"])
@roles_required("admin", "coach")
def api_delete_student(student_id):
    """依規格書決策採軟刪除：狀態改為 inactive，保留歷史購買/上課紀錄。"""
    student = services.get_student_or_404(student_id)
    services.set_student_status(student, "inactive")
    return jsonify(student.to_dict())


@bp.route("/students/<int:student_id>/summary", methods=["GET"])
@roles_required("admin", "coach")
def api_student_summary(student_id):
    student = services.get_student_or_404(student_id)
    return jsonify(services.summary_dict(student))


# ---------- Purchases ----------

@bp.route("/students/<int:student_id>/purchases", methods=["GET"])
@roles_required("admin", "coach")
def api_list_purchases(student_id):
    student = services.get_student_or_404(student_id)
    return jsonify([p.to_dict() for p in student.purchase_records])


@bp.route("/students/<int:student_id>/purchases", methods=["POST"])
@roles_required("admin", "coach")
def api_create_purchase(student_id):
    student = services.get_student_or_404(student_id)
    data = _json_body()
    try:
        payload = dict(data)
        payload["purchase_date"] = _parse_date(data.get("purchase_date"), "purchase_date")
        record = services.create_purchase(student, payload)
    except services.ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    return jsonify(record.to_dict()), 201


@bp.route("/purchases/<int:purchase_id>", methods=["PUT", "PATCH"])
@roles_required("admin", "coach")
def api_update_purchase(purchase_id):
    record = services.get_purchase_or_404(purchase_id)
    data = _json_body()
    try:
        payload = dict(data)
        if "purchase_date" in data:
            payload["purchase_date"] = _parse_date(data.get("purchase_date"), "purchase_date")
        record = services.update_purchase(record, payload)
    except services.ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    return jsonify(record.to_dict())


@bp.route("/purchases/<int:purchase_id>", methods=["DELETE"])
@roles_required("admin", "coach")
def api_delete_purchase(purchase_id):
    record = services.get_purchase_or_404(purchase_id)
    services.delete_purchase(record)
    return "", 204


# ---------- Class records ----------

@bp.route("/students/<int:student_id>/classes", methods=["GET"])
@roles_required("admin", "coach")
def api_list_classes(student_id):
    student = services.get_student_or_404(student_id)
    return jsonify([c.to_dict() for c in student.class_records])


@bp.route("/students/<int:student_id>/classes", methods=["POST"])
@roles_required("admin", "coach")
def api_create_class(student_id):
    student = services.get_student_or_404(student_id)
    data = _json_body()
    try:
        payload = dict(data)
        payload["class_date"] = _parse_date(data.get("class_date"), "class_date")
        payload["class_time"] = _parse_time(data.get("class_time"), "class_time")
        record = services.create_class_record(student, payload)
    except services.ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    return jsonify(record.to_dict()), 201


@bp.route("/classes/<int:class_id>", methods=["PUT", "PATCH"])
@roles_required("admin", "coach")
def api_update_class(class_id):
    record = services.get_class_record_or_404(class_id)
    data = _json_body()
    try:
        payload = dict(data)
        if "class_date" in data:
            payload["class_date"] = _parse_date(data.get("class_date"), "class_date")
        if "class_time" in data:
            payload["class_time"] = _parse_time(data.get("class_time"), "class_time")
        record = services.update_class_record(record, payload)
    except services.ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    return jsonify(record.to_dict())


@bp.route("/classes/<int:class_id>", methods=["DELETE"])
@roles_required("admin", "coach")
def api_delete_class(class_id):
    record = services.get_class_record_or_404(class_id)
    services.delete_class_record(record)
    return "", 204


# ---------- Exercise catalog(訓練項目清單) ----------

@bp.route("/exercise-catalog", methods=["GET"])
@roles_required("admin", "coach")
def api_list_exercise_catalog():
    search = request.args.get("search")
    category = request.args.get("category")
    items = services.list_exercise_catalog(search=search, category=category)
    return jsonify([i.to_dict() for i in items])


@bp.route("/exercise-catalog", methods=["POST"])
@roles_required("admin", "coach")
def api_create_exercise_catalog_item():
    data = _json_body()
    try:
        item = services.create_exercise_catalog_item(data)
    except services.ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    return jsonify(item.to_dict()), 201


@bp.route("/exercise-catalog/<int:item_id>", methods=["PUT", "PATCH"])
@roles_required("admin", "coach")
def api_update_exercise_catalog_item(item_id):
    item = services.get_exercise_catalog_item_or_404(item_id)
    data = _json_body()
    try:
        item = services.update_exercise_catalog_item(item, data)
    except services.ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    return jsonify(item.to_dict())


@bp.route("/exercise-catalog/<int:item_id>", methods=["DELETE"])
@roles_required("admin", "coach")
def api_delete_exercise_catalog_item(item_id):
    item = services.get_exercise_catalog_item_or_404(item_id)
    try:
        services.delete_exercise_catalog_item(item)
    except services.ValidationError as exc:
        return jsonify({"error": exc.message, "field": exc.field}), 400
    return "", 204
