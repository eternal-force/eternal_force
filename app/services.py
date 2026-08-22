"""共用業務邏輯層:HTML 路由(表單已驗證過)與 JSON API 路由都呼叫這裡的函式，
確保新增/編輯/刪除與堂數統計規則只實作一份，不會兩邊邏輯兜不起來。
"""

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


def _validate_positive_int(value, label):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label}必須是正整數", field="quantity")
    if value <= 0:
        raise ValidationError(f"{label}必須是正整數", field="quantity")
    return value


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

    student = Student(
        name=name,
        phone=_blank_to_none(data.get("phone")),
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
        student.name = name
    for key in ("phone", "email", "notes"):
        if key in data:
            setattr(student, key, _blank_to_none(data[key]))
    for key in ("birthday", "enrollment_date", "gender"):
        if key in data:
            setattr(student, key, data[key] or None)
    if "status" in data and data["status"] in ("active", "inactive"):
        student.status = data["status"]
    db.session.commit()
    return student


def set_student_status(student, status):
    if status not in ("active", "inactive"):
        raise ValidationError("狀態值不正確，需為 active 或 inactive", field="status")
    student.status = status
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
    quantity = _validate_positive_int(data.get("quantity"), "購買堂數")

    record = PurchaseRecord(
        student_id=student.id,
        purchase_date=data["purchase_date"],
        quantity=quantity,
        price=data.get("price") or None,
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
        record.quantity = _validate_positive_int(data["quantity"], "購買堂數")
    if "price" in data:
        record.price = data["price"] or None
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


def _build_class_exercises(entries):
    """entries: [{'category', 'name'}, ...]。名稱空白的列視為未填寫的空白列，直接略過；
    有名稱就必須有分類(可從訓練項目清單選，也可以是自訂、清單裡沒有的名稱)。
    名稱與清單項目吻合時記錄關聯，方便日後統計使用哪些訓練項目。"""
    cleaned = []
    for entry in entries:
        category = (entry.get("category") or "").strip()
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        if not category:
            raise ValidationError("有訓練項目未選擇分類", field="exercises")
        cleaned.append((category, name))

    catalog_by_name = {}
    if cleaned:
        names = [name for _, name in cleaned]
        catalog_by_name = {
            item.name: item.id
            for item in ExerciseCatalogItem.query.filter(ExerciseCatalogItem.name.in_(names)).all()
        }

    return [
        ClassExercise(
            category=category,
            name=name,
            exercise_catalog_item_id=catalog_by_name.get(name),
            sort_order=index,
        )
        for index, (category, name) in enumerate(cleaned)
    ]


def create_class_record(student, data):
    if student.remaining <= 0:
        raise ValidationError("已無上課堂數，請確認", field="remaining")
    if not data.get("class_date"):
        raise ValidationError("到課日期為必填", field="class_date")
    if not data.get("class_time"):
        raise ValidationError("到課時間為必填", field="class_time")
    exercises = _build_class_exercises(data.get("exercises") or [])

    record = ClassRecord(
        student_id=student.id,
        class_date=data["class_date"],
        class_time=data["class_time"],
        duration_minutes=data.get("duration_minutes") or None,
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
    if "duration_minutes" in data:
        record.duration_minutes = data["duration_minutes"] or None
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
    _check_exercise_name_unique(name, exclude_id=item.id)
    item.category = category
    item.name = name
    db.session.commit()
    return item


def delete_exercise_catalog_item(item):
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
    if User.query.filter_by(username=username).first():
        raise ValidationError("此帳號已被使用", field="username")

    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("姓名為必填", field="name")

    user = User(
        username=username,
        role="student",
        status="pending",
        name=name,
        phone=_blank_to_none(data.get("phone")),
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
    if User.query.filter_by(username=username).first():
        raise ValidationError("此帳號已被使用", field="username")

    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("姓名為必填", field="name")

    user = User(
        username=username,
        role="coach",
        status="active",
        name=name,
        phone=_blank_to_none(data.get("phone")),
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()
    return user


def create_student_from_registration(user):
    student = Student(
        name=user.name,
        phone=user.phone,
        birthday=user.birthday,
        gender=user.gender,
        status="active",
        notes=f"期望運動達成效益：{user.goal}" if user.goal else None,
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
    db.session.commit()
    return user


def set_account_role(user, target_role):
    if target_role not in ("coach", "student"):
        raise ValidationError("角色不正確，需為 coach 或 student", field="role")
    if user.role == "admin":
        raise ValidationError("管理者帳號的角色無法在此變更", field="role")
    user.role = target_role
    db.session.commit()
    return user
