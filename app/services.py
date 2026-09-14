"""共用業務邏輯層:HTML 路由(表單已驗證過)與 JSON API 路由都呼叫這裡的函式，
確保新增/編輯/刪除與堂數統計規則只實作一份，不會兩邊邏輯兜不起來。
"""

import re
from decimal import Decimal, InvalidOperation

from flask import abort

from .extensions import db
from .models import ClassExercise, ClassRecord, ExerciseCatalogItem, PurchaseRecord, Student, User


class ValidationError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def _blank_to_none(value):
    if value is None:
        return None
    value = value.strip() if isinstance(value, str) else value
    return value or None


def username_exists(username):
    """大小寫不敏感比對，避免「Alice」與「alice」被當成不同帳號重複註冊/新增。"""
    return (
        User.query.filter(db.func.lower(User.username) == (username or "").strip().lower()).first()
        is not None
    )


# ---------- 學生姓名格式限制 ----------

_STUDENT_NAME_MAX_LENGTH = 20
_STUDENT_NAME_RE = re.compile(r"^[A-Za-z0-9一-鿿\s]+$")


def validate_student_name(name):
    if len(name) > _STUDENT_NAME_MAX_LENGTH:
        raise ValidationError(f"姓名不能超過 {_STUDENT_NAME_MAX_LENGTH} 個字", field="name")
    if not _STUDENT_NAME_RE.match(name):
        raise ValidationError("姓名不能包含特殊符號", field="name")


# ---------- 帳號聯絡電話格式(REQ-006) ----------

PHONE_TYPE_LABELS = {"mobile": "手機", "landline": "市話"}

# 手機：09 開頭的 10 碼數字（台灣門號格式，例如 0912345678）。
_MOBILE_PHONE_RE = re.compile(r"^09\d{8}$")
# 市話：0 開頭的區碼（1~2 碼，但排除手機開頭的 09）加上 6~8 碼電話號碼，允許中間以「-」分隔（例如 02-12345678、049-123456）。
_LANDLINE_PHONE_RE = re.compile(r"^(?!09)0\d{1,2}-?\d{6,8}$")


def validate_phone_by_type(phone, phone_type):
    """依 phone_type 驗證電話格式；phone 為空白時不驗證(留給呼叫端自行判斷是否必填)。"""
    if not phone:
        return
    if phone_type == "mobile":
        if not _MOBILE_PHONE_RE.match(phone):
            raise ValidationError("手機格式不正確，需為 09 開頭的 10 碼數字，例如 0912345678", field="phone")
    elif phone_type == "landline":
        if not _LANDLINE_PHONE_RE.match(phone):
            raise ValidationError("市話格式不正確，需為區碼加電話號碼，例如 02-12345678", field="phone")
    else:
        raise ValidationError("請選擇聯絡電話類型（手機或市話）", field="phone_type")


def _validate_positive_int(value, label, max_value=None):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label}必須是正整數", field="quantity")
    if value <= 0:
        raise ValidationError(f"{label}必須是正整數", field="quantity")
    if max_value is not None and value > max_value:
        raise ValidationError(f"{label}不能大於 {max_value}", field="quantity")
    return value


def _validate_purchase_price(value):
    if value in (None, ""):
        return None
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("購買金額必須是數字", field="price")
    if price > Decimal("1000000"):
        raise ValidationError("購買金額不能大於 1,000,000", field="price")
    return price


# ---------- Student ----------

def list_students(search=None, status=None):
    query = Student.query
    if search:
        query = query.filter(Student.name.ilike(f"%{search.strip()}%"))
    if status in ("active", "inactive"):
        query = query.filter(Student.status == status)
    return query.order_by(Student.created_at.desc()).all()


def get_student_or_404(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        abort(404)
    return student


def create_student(data):
    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("姓名為必填", field="name")
    validate_student_name(name)

    phone = _blank_to_none(data.get("phone"))
    phone_type = data.get("phone_type") or None
    validate_phone_by_type(phone, phone_type)

    student = Student(
        name=name,
        phone=phone,
        phone_type=phone_type,
        email=_blank_to_none(data.get("email")),
        birthday=data.get("birthday"),
        gender=data.get("gender") or None,
        enrollment_date=data.get("enrollment_date"),
        status=data.get("status") or "active",
        notes=_blank_to_none(data.get("notes")),
    )
    db.session.add(student)
    db.session.commit()
    return student


def update_student(student, data):
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise ValidationError("姓名為必填", field="name")
        validate_student_name(name)
        student.name = name
        if student.account is not None:
            student.account.name = name
    if "phone" in data or "phone_type" in data:
        phone = _blank_to_none(data["phone"]) if "phone" in data else student.phone
        phone_type = (data["phone_type"] if "phone_type" in data else student.phone_type) or None
        validate_phone_by_type(phone, phone_type)
        student.phone = phone
        student.phone_type = phone_type
    for key in ("email", "notes"):
        if key in data:
            setattr(student, key, _blank_to_none(data[key]))
    for key in ("birthday", "enrollment_date", "gender"):
        if key in data:
            setattr(student, key, data[key] or None)
    if "status" in data and data["status"] in ("active", "inactive"):
        student.status = data["status"]
    db.session.commit()
    return student


def _activate_linked_account(student):
    """學生重新啟用時，若有對應的登入帳號且尚未啟用，一併改為啟用(呼應帳號停用時會同步停用學生名冊的既有規則)。"""
    linked_user = User.query.filter_by(student_id=student.id).first()
    if linked_user is not None and linked_user.role != "admin" and linked_user.status != "active":
        linked_user.status = "active"


def set_student_status(student, status):
    if status not in ("active", "inactive"):
        raise ValidationError("狀態值不正確，需為 active 或 inactive", field="status")
    student.status = status
    if status == "active":
        _activate_linked_account(student)
    db.session.commit()
    return student


def delete_student_hard(student):
    """硬刪除(含所有購買/上課紀錄)。UI 預設走軟刪除(set_student_status)，
    此函式僅供 API DELETE /api/students/{id} 在明確需要徹底移除時使用。"""
    linked_user = User.query.filter_by(student_id=student.id).first()
    if linked_user:
        linked_user.student_id = None
    db.session.delete(student)
    db.session.commit()


def summary_dict(student):
    return {
        "total_purchased": student.total_purchased,
        "total_attended": student.total_attended,
        "remaining": student.remaining,
    }


# ---------- Purchase records ----------

def get_purchase_or_404(purchase_id):
    record = db.session.get(PurchaseRecord, purchase_id)
    if not record:
        abort(404)
    return record


def create_purchase(student, data):
    if not data.get("purchase_date"):
        raise ValidationError("購買日期為必填", field="purchase_date")
    quantity = _validate_positive_int(data.get("quantity"), "購買堂數", max_value=999)
    price = _validate_purchase_price(data.get("price"))

    record = PurchaseRecord(
        student_id=student.id,
        purchase_date=data["purchase_date"],
        quantity=quantity,
        price=price,
        notes=_blank_to_none(data.get("notes")),
    )
    db.session.add(record)
    db.session.commit()
    return record


def update_purchase(record, data):
    if "purchase_date" in data:
        if not data["purchase_date"]:
            raise ValidationError("購買日期為必填", field="purchase_date")
        record.purchase_date = data["purchase_date"]
    if "quantity" in data:
        record.quantity = _validate_positive_int(data["quantity"], "購買堂數", max_value=999)
    if "price" in data:
        record.price = _validate_purchase_price(data["price"])
    if "notes" in data:
        record.notes = _blank_to_none(data["notes"])
    db.session.commit()
    return record


def delete_purchase(record):
    db.session.delete(record)
    db.session.commit()


# ---------- Class records ----------

def get_class_record_or_404(record_id):
    record = db.session.get(ClassRecord, record_id)
    if not record:
        abort(404)
    return record


def _parse_optional_int(value, label, max_value=None):
    if isinstance(value, str):
        value = value.strip()
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label}必須是整數", field="exercises")
    if parsed < 0:
        raise ValidationError(f"{label}不能是負數", field="exercises")
    if max_value is not None and parsed > max_value:
        raise ValidationError(f"{label}不能大於 {max_value}", field="exercises")
    return parsed


def _parse_optional_decimal(value, label, max_value=None):
    if isinstance(value, str):
        value = value.strip()
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f"{label}必須是數字", field="exercises")
    if parsed < 0:
        raise ValidationError(f"{label}不能是負數", field="exercises")
    if max_value is not None and parsed > max_value:
        raise ValidationError(f"{label}不能大於 {max_value}", field="exercises")
    return parsed


def _build_class_exercises(entries):
    """entries: [{'category', 'name', 'weight_kg', 'sets', 'reps', 'note'}, ...]。
    名稱空白的列視為未填寫的空白列，直接略過；有名稱就必須有分類(可從訓練項目清單選，
    也可以是自訂、清單裡沒有的名稱)。公斤數/組數/次數為選填，但填了就必須是非負數字。
    名稱與清單項目吻合時記錄關聯，方便日後統計使用哪些訓練項目。"""
    cleaned = []
    for entry in entries:
        category = (entry.get("category") or "").strip()
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        if not category:
            raise ValidationError("有訓練項目未選擇分類", field="exercises")
        cleaned.append(
            {
                "category": category,
                "name": name,
                "weight_kg": _parse_optional_decimal(entry.get("weight_kg"), "公斤數", max_value=200),
                "sets": _parse_optional_int(entry.get("sets"), "組數", max_value=100),
                "reps": _parse_optional_int(entry.get("reps"), "次數", max_value=100),
                "note": _blank_to_none(entry.get("note")),
            }
        )

    catalog_by_name = {}
    if cleaned:
        names = [item["name"] for item in cleaned]
        catalog_by_name = {
            item.name: item.id
            for item in ExerciseCatalogItem.query.filter(ExerciseCatalogItem.name.in_(names)).all()
        }

    return [
        ClassExercise(
            category=item["category"],
            name=item["name"],
            weight_kg=item["weight_kg"],
            sets=item["sets"],
            reps=item["reps"],
            note=item["note"],
            exercise_catalog_item_id=catalog_by_name.get(item["name"]),
            sort_order=index,
        )
        for index, item in enumerate(cleaned)
    ]


def list_active_coaches():
    return User.query.filter_by(role="coach", status="active").order_by(User.name.asc()).all()


def _validate_coach(coach_id):
    if not coach_id:
        raise ValidationError("請選擇上課教練", field="coach_id")
    coach = db.session.get(User, coach_id)
    if not coach or coach.role != "coach" or coach.status != "active":
        raise ValidationError("上課教練不正確", field="coach_id")
    return coach


def create_class_record(student, data):
    if student.remaining <= 0:
        raise ValidationError("已無上課堂數，請確認", field="remaining")
    if not data.get("class_date"):
        raise ValidationError("到課日期為必填", field="class_date")
    if not data.get("class_time"):
        raise ValidationError("到課時間為必填", field="class_time")
    coach = _validate_coach(data.get("coach_id"))
    exercises = _build_class_exercises(data.get("exercises") or [])

    record = ClassRecord(
        student_id=student.id,
        class_date=data["class_date"],
        class_time=data["class_time"],
        coach_id=coach.id,
        notes=_blank_to_none(data.get("notes")),
        exercises=exercises,
    )
    db.session.add(record)
    db.session.commit()
    return record


def update_class_record(record, data):
    if "class_date" in data:
        if not data["class_date"]:
            raise ValidationError("到課日期為必填", field="class_date")
        record.class_date = data["class_date"]
    if "class_time" in data:
        if not data["class_time"]:
            raise ValidationError("到課時間為必填", field="class_time")
        record.class_time = data["class_time"]
    if "coach_id" in data:
        record.coach_id = _validate_coach(data["coach_id"]).id
    if "notes" in data:
        record.notes = _blank_to_none(data["notes"])
    if "exercises" in data:
        record.exercises = _build_class_exercises(data["exercises"] or [])
    db.session.commit()
    return record


def delete_class_record(record):
    db.session.delete(record)
    db.session.commit()


# ---------- Exercise catalog(訓練項目清單) ----------

def list_exercise_catalog(search=None, category=None):
    query = ExerciseCatalogItem.query
    if category:
        query = query.filter(ExerciseCatalogItem.category == category)
    if search:
        query = query.filter(ExerciseCatalogItem.name.ilike(f"%{search.strip()}%"))
    return query.order_by(ExerciseCatalogItem.sort_order.asc(), ExerciseCatalogItem.id.asc()).all()


def list_exercise_categories():
    rows = (
        db.session.query(ExerciseCatalogItem.category)
        .distinct()
        .order_by(ExerciseCatalogItem.category.asc())
        .all()
    )
    return [row[0] for row in rows]


def exercise_catalog_name_map():
    """回傳 {分類: [項目名稱, ...]}，提供上課紀錄表單挑選訓練菜單時的分類/自動完成清單使用。"""
    mapping = {}
    for item in list_exercise_catalog():
        mapping.setdefault(item.category, []).append(item.name)
    return mapping


def get_exercise_catalog_item_or_404(item_id):
    item = db.session.get(ExerciseCatalogItem, item_id)
    if not item:
        abort(404)
    return item


def _check_exercise_name_unique(name, exclude_id=None):
    query = ExerciseCatalogItem.query.filter(ExerciseCatalogItem.name == name)
    if exclude_id is not None:
        query = query.filter(ExerciseCatalogItem.id != exclude_id)
    if query.first():
        raise ValidationError("已經有相同名稱的項目", field="name")


def _check_exercise_catalog_item_not_in_use(item, action_label):
    in_use = ClassExercise.query.filter_by(exercise_catalog_item_id=item.id).first() is not None
    if in_use:
        raise ValidationError(f"此訓練項目已被學生的訓練菜單引用，無法{action_label}", field="name")


def create_exercise_catalog_item(data):
    category = (data.get("category") or "").strip()
    name = (data.get("name") or "").strip()
    if not category:
        raise ValidationError("分類為必填", field="category")
    if not name:
        raise ValidationError("項目名稱為必填", field="name")
    _check_exercise_name_unique(name)

    max_sort = db.session.query(
        db.func.coalesce(db.func.max(ExerciseCatalogItem.sort_order), -1)
    ).scalar()
    item = ExerciseCatalogItem(category=category, name=name, sort_order=max_sort + 1)
    db.session.add(item)
    db.session.commit()
    return item


def update_exercise_catalog_item(item, data):
    category = (data.get("category") or "").strip()
    name = (data.get("name") or "").strip()
    if not category:
        raise ValidationError("分類為必填", field="category")
    if not name:
        raise ValidationError("項目名稱為必填", field="name")
    _check_exercise_catalog_item_not_in_use(item, "編輯")
    _check_exercise_name_unique(name, exclude_id=item.id)
    item.category = category
    item.name = name
    db.session.commit()
    return item


def delete_exercise_catalog_item(item):
    _check_exercise_catalog_item_not_in_use(item, "刪除")
    db.session.delete(item)
    db.session.commit()


def seed_exercise_catalog(seed_items):
    """依 (category, name) 序列匯入訓練項目種子資料；名稱已存在時更新分類與排序，
    不存在則新增。不會刪除清單中未包含的既有項目。"""
    for index, (category, name) in enumerate(seed_items):
        item = ExerciseCatalogItem.query.filter_by(name=name).first()
        if item:
            item.category = category
            item.sort_order = index
        else:
            db.session.add(ExerciseCatalogItem(category=category, name=name, sort_order=index))
    db.session.commit()


# ---------- User accounts ----------

def list_accounts(search=None):
    query = User.query
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(db.or_(User.username.ilike(like), User.name.ilike(like)))
    return query.order_by(
        db.case((User.status == "pending", 0), else_=1), User.created_at.desc()
    ).all()


def register_student_account(data):
    username = (data.get("username") or "").strip()
    if not username:
        raise ValidationError("帳號為必填", field="username")
    if username_exists(username):
        raise ValidationError("此帳號已被使用", field="username")

    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("姓名為必填", field="name")

    phone = _blank_to_none(data.get("phone"))
    phone_type = data.get("phone_type") or None
    validate_phone_by_type(phone, phone_type)

    user = User(
        username=username,
        role="student",
        status="pending",
        name=name,
        email=_blank_to_none(data.get("email")),
        phone=phone,
        phone_type=phone_type,
        birthday=data.get("birthday"),
        gender=data.get("gender") or None,
        goal=_blank_to_none(data.get("goal")),
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()
    return user


def create_coach_account(data):
    username = (data.get("username") or "").strip()
    if not username:
        raise ValidationError("帳號為必填", field="username")
    if username_exists(username):
        raise ValidationError("此帳號已被使用", field="username")

    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("姓名為必填", field="name")

    phone = _blank_to_none(data.get("phone"))
    phone_type = data.get("phone_type") or None
    validate_phone_by_type(phone, phone_type)

    user = User(
        username=username,
        role="coach",
        status="active",
        name=name,
        email=_blank_to_none(data.get("email")),
        phone=phone,
        phone_type=phone_type,
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()
    return user


def create_student_from_registration(user):
    student = Student(
        name=user.name,
        email=user.email,
        phone=user.phone,
        phone_type=user.phone_type,
        birthday=user.birthday,
        gender=user.gender,
        status="active",
        notes=user.goal or None,
    )
    db.session.add(student)
    db.session.flush()
    user.student_id = student.id
    return student


def verify_account(user):
    user.status = "active"
    if user.role == "student" and user.student_id is None:
        create_student_from_registration(user)
    db.session.commit()
    return user


def set_account_status(user, target_status):
    if target_status not in ("active", "disabled"):
        raise ValidationError("狀態值不正確，需為 active 或 disabled", field="status")
    if user.role == "admin":
        raise ValidationError("管理者帳號無法在此變更狀態", field="status")
    user.status = target_status
    if target_status == "disabled" and user.student is not None:
        user.student.status = "inactive"
    if target_status == "active":
        if user.role == "student" and user.student_id is None:
            create_student_from_registration(user)
        if user.student is not None:
            user.student.status = "active"
    db.session.commit()
    return user


def delete_account(user):
    """僅能刪除已停用、非管理者的帳號；若對應學生名冊仍有剩餘課程則擋下，避免誤刪尚在使用中的學生資料。"""
    if user.role == "admin":
        raise ValidationError("管理者帳號無法刪除", field="role")
    if user.status != "disabled":
        raise ValidationError("僅能刪除已停用的帳號", field="status")
    student = user.student
    if student is not None and student.remaining > 0:
        raise ValidationError("該學生尚有課程未完成，請勿刪除", field="student")
    if student is not None:
        db.session.delete(student)
    db.session.delete(user)
    db.session.commit()


def set_account_role(user, target_role):
    if target_role not in ("coach", "student"):
        raise ValidationError("角色不正確，需為 coach 或 student", field="role")
    if user.role == "admin":
        raise ValidationError("管理者帳號的角色無法在此變更", field="role")
    user.role = target_role
    db.session.commit()
    return user


def set_account_password(user, new_password):
    user.set_password(new_password)
    db.session.commit()
    return user
