"""共用業務邏輯層:HTML 路由(表單已驗證過)與 JSON API 路由都呼叫這裡的函式，
確保新增/編輯/刪除與堂數統計規則只實作一份，不會兩邊邏輯兜不起來。
"""

import re
import secrets
import zlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import abort

from .extensions import db
from .models import (
    Announcement,
    ClassExercise,
    ClassRecord,
    ExerciseCatalogItem,
    LoginSession,
    PageView,
    PurchaseRecord,
    Student,
    User,
)


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


# ---------- 教練可見範圍(REQ-051) ----------

def _coach_student_filter(coach):
    """教練可見的學生：自己上過課的，或尚未有任何教練上過課(未分配)的學生。"""
    return db.or_(
        Student.class_records.any(ClassRecord.coach_id == coach.id),
        ~Student.class_records.any(ClassRecord.coach_id.isnot(None)),
    )


def visible_students_query(user):
    query = Student.query
    if user.role == "coach":
        query = query.filter(_coach_student_filter(user))
    return query


def can_access_student(user, student):
    if user.role == "admin":
        return True
    if user.role == "student":
        return user.student_id == student.id
    coach_ids = {c.coach_id for c in student.class_records if c.coach_id is not None}
    return not coach_ids or user.id in coach_ids


def ensure_student_access(user, student):
    if not can_access_student(user, student):
        abort(403)


def visible_accounts_query(user):
    """教練只看得到學生帳號：尚未連結學生名冊的(例如待驗證)，或連結到自己可見學生的。"""
    query = User.query
    if user.role == "coach":
        query = query.filter(
            User.role == "student",
            db.or_(User.student_id.is_(None), User.student.has(_coach_student_filter(user))),
        )
    return query


def can_access_account(user, account):
    if user.role == "admin":
        return True
    if account.role != "student":
        return False
    return account.student is None or can_access_student(user, account.student)


# ---------- Student ----------

def list_students(search=None, status=None, user=None, class_type=None):
    query = visible_students_query(user) if user is not None else Student.query
    if search:
        query = query.filter(Student.name.ilike(f"%{search.strip()}%"))
    if status in ("active", "inactive"):
        query = query.filter(Student.status == status)
    if class_type in ("one_on_one", "one_on_two"):
        query = query.filter(Student.class_type == class_type)
    return query.order_by(Student.created_at.desc()).all()


def get_student_or_404(student_id, user=None):
    """有帶 user 時一併檢查該使用者能否存取這位學生，不能則 403。"""
    student = db.session.get(Student, student_id)
    if not student:
        abort(404)
    if user is not None:
        ensure_student_access(user, student)
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
        enrollment_date=date.today(),
        status=data.get("status") or "active",
        notes=_blank_to_none(data.get("notes")),
    )
    db.session.add(student)
    db.session.commit()
    return student


def update_student(student, data):
    # 一對二卡片的姓名／電話／信箱屬於各自的帳號(update_pair_member)，不由卡片回寫。
    account = None if student.is_pair else student.account
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise ValidationError("姓名為必填", field="name")
        validate_student_name(name)
        student.name = name
        if account is not None:
            account.name = name
    if "phone" in data or "phone_type" in data:
        phone = _blank_to_none(data["phone"]) if "phone" in data else student.phone
        phone_type = (data["phone_type"] if "phone_type" in data else student.phone_type) or None
        validate_phone_by_type(phone, phone_type)
        student.phone = phone
        student.phone_type = phone_type
        if account is not None:
            account.phone = phone
            account.phone_type = phone_type
    if "email" in data:
        student.email = _blank_to_none(data["email"])
        if account is not None:
            account.email = student.email
    if "notes" in data:
        student.notes = _blank_to_none(data["notes"])
    # 入班/建檔日期不可編輯：一律沿用建立當下寫入的值，即使呼叫端帶了 enrollment_date 也忽略。
    for key in ("birthday", "gender"):
        if key in data:
            setattr(student, key, data[key] or None)
    if "status" in data and data["status"] in ("active", "inactive"):
        student.status = data["status"]
        if student.status == "active":
            _activate_linked_account(student)
        else:
            _deactivate_linked_account(student)
    db.session.commit()
    return student


def _activate_linked_account(student):
    """學生重新啟用時，若有對應的登入帳號且尚未啟用，一併改為啟用(呼應帳號停用時會同步停用學生名冊的既有規則)。"""
    for linked_user in student.accounts:
        if linked_user.role != "admin" and linked_user.status != "active":
            linked_user.status = "active"


def _deactivate_linked_account(student):
    """學生停用時，若有對應的登入帳號且尚未停用，一併改為停用，方向對稱於帳號管理停用帳號時連動停用學生名冊。"""
    for linked_user in student.accounts:
        if linked_user.role != "admin" and linked_user.status != "disabled":
            linked_user.status = "disabled"


def set_student_status(student, status):
    if status not in ("active", "inactive"):
        raise ValidationError("狀態值不正確，需為 active 或 inactive", field="status")
    student.status = status
    if status == "active":
        _activate_linked_account(student)
    else:
        _deactivate_linked_account(student)
    db.session.commit()
    return student


def delete_student_hard(student):
    """硬刪除(含所有購買/上課紀錄)。UI 預設走軟刪除(set_student_status)，
    此函式僅供 API DELETE /api/students/{id} 在明確需要徹底移除時使用。"""
    for linked_user in list(student.accounts):
        linked_user.student = None
    db.session.delete(student)
    db.session.commit()


# ---------- 一對二(REQ-053) ----------

CLASS_TYPE_LABELS = {"one_on_one": "一對一", "one_on_two": "一對二"}
PAIR_NAME_SEPARATOR = "、"


def _ensure_classes_used_up(student):
    """轉換課程類型前，原卡片的堂數必須剛好用完。"""
    remaining = student.remaining
    if remaining > 0:
        raise ValidationError(f"「{student.name}」尚有 {remaining} 堂未上完，需全部用完才能轉換", field="student")
    if remaining < 0:
        raise ValidationError(f"「{student.name}」已超上 {-remaining} 堂，請先補購後再轉換", field="student")


def _retire_card(student):
    """拆分後的一對二卡片：有紀錄的停用保留當歷史，完全沒有紀錄的直接刪除。呼叫前帳號須已改連到其他卡片。"""
    if student.purchase_records or student.class_records:
        student.status = "inactive"
    else:
        db.session.delete(student)


def _find_former_card(member):
    """學員轉為一對二前的一對一卡片(REQ-054)。REQ-054 之前配對的卡片沒有記下原帳號，
    改找同名、已停用、沒有帳號的一對一卡片，剛好只有一張才採用，避免認錯人。"""
    unlinked = Student.query.filter(Student.class_type == "one_on_one", ~Student.accounts.any())
    card = (
        unlinked.filter(Student.former_account_id == member.id).order_by(Student.updated_at.desc()).first()
    )
    if card is not None:
        return card
    same_name = unlinked.filter(
        Student.former_account_id.is_(None), Student.status == "inactive", Student.name == member.name
    ).all()
    return same_name[0] if len(same_name) == 1 else None


def _restore_former_card(member, card):
    card.former_account_id = None
    member.student = card
    # 一對二期間學員可能改過自己的資料，帶回卡片，維持卡片與帳號一致。
    card.name = member.name or card.name
    card.phone, card.phone_type, card.email = member.phone, member.phone_type, member.email
    if member.status == "active":
        card.status = "active"
    return card


def _sync_pair_name(student):
    """一對二卡片的名稱由兩位學員的姓名組成，學生列表才能用任一人的姓名搜尋。"""
    if student.is_pair and student.accounts:
        student.name = PAIR_NAME_SEPARATOR.join(a.name or a.username for a in student.accounts)


def _check_pair_partner(student, partner):
    if partner is None or partner.role != "student":
        raise ValidationError("請選擇要一起上課的學生帳號", field="partner_id")
    if partner.status != "active":
        raise ValidationError("只能選擇啟用中的學生帳號", field="partner_id")
    if partner.student is None:
        raise ValidationError("該帳號尚未建立學生名冊，無法配對", field="partner_id")
    if partner.student_id == student.id:
        raise ValidationError("不能和自己配對", field="partner_id")
    if partner.student.is_pair:
        raise ValidationError("該學生已經是一對二，請先拆分後再配對", field="partner_id")


def list_pair_candidates(user, student):
    """可與這位學生配對的帳號：登入者看得到、啟用中、目前是一對一且堂數已用完的學生帳號。"""
    accounts = (
        visible_accounts_query(user)
        .filter(User.role == "student", User.status == "active", User.student_id.isnot(None))
        .filter(User.student_id != student.id)
        .filter(User.student.has(Student.class_type == "one_on_one"))
        .order_by(User.name)
        .all()
    )
    return [a for a in accounts if a.student.remaining == 0]


def pair_students(student, partner):
    """把一對一學生與另一位學生帳號配成一對二：建立新的共用卡片，兩張原卡片都停用保留，拆分時再啟用。"""
    if student.is_pair:
        raise ValidationError("這位學生已經是一對二", field="student")
    if student.status != "active":
        raise ValidationError("已停用的學生無法轉為一對二，請先重新啟用", field="student")
    owner = student.account
    if owner is None:
        raise ValidationError("這位學生沒有登入帳號，無法轉為一對二", field="student")
    _check_pair_partner(student, partner)
    old_cards = [(student, owner), (partner.student, partner)]
    for card, _ in old_cards:
        _ensure_classes_used_up(card)

    pair = Student(name="", class_type="one_on_two", status="active", enrollment_date=date.today())
    pair.accounts = [owner, partner]
    _sync_pair_name(pair)
    db.session.add(pair)
    for card, account in old_cards:
        card.status = "inactive"
        card.former_account_id = account.id
    db.session.commit()
    return pair


def split_pair(student):
    """把一對二拆回一對一：每位學員回到原本停用的一對一卡片並重新啟用，找不到原卡片才新建；
    原一對二卡片停用保留(沒有紀錄的刪除)。"""
    if not student.is_pair:
        raise ValidationError("這位學生不是一對二", field="student")
    _ensure_classes_used_up(student)
    cards = []
    for member in list(student.accounts):
        former = _find_former_card(member)
        if former is not None:
            card = _restore_former_card(member, former)
        else:
            card = create_student_from_registration(member)
            if member.status != "active":
                card.status = "inactive"
        cards.append(card)
    _retire_card(student)
    db.session.commit()
    return cards


def get_pair_member_or_404(student, user_id):
    for member in student.accounts:
        if member.id == user_id:
            return member
    abort(404)


def update_pair_member(student, member, data):
    """一對二卡片的個人資料存在各自的帳號上，編輯其中一位不影響另一位。"""
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise ValidationError("姓名為必填", field="name")
        validate_student_name(name)
        member.name = name
    if "phone" in data or "phone_type" in data:
        phone = _blank_to_none(data["phone"]) if "phone" in data else member.phone
        phone_type = (data["phone_type"] if "phone_type" in data else member.phone_type) or None
        validate_phone_by_type(phone, phone_type)
        member.phone = phone
        member.phone_type = phone_type
    if "email" in data:
        member.email = _blank_to_none(data["email"])
    if "notes" in data:
        member.goal = _blank_to_none(data["notes"])
    for key in ("birthday", "gender"):
        if key in data:
            setattr(member, key, data[key] or None)
    _sync_pair_name(student)
    db.session.commit()
    return member


def summary_dict(student):
    return {
        "total_purchased": student.total_purchased,
        "total_attended": student.total_attended,
        "remaining": student.remaining,
    }


# ---------- Purchase records ----------

def get_purchase_or_404(purchase_id, user=None):
    record = db.session.get(PurchaseRecord, purchase_id)
    if not record:
        abort(404)
    if user is not None:
        ensure_student_access(user, record.student)
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
        quantity = _validate_positive_int(data["quantity"], "購買堂數", max_value=999)
        if quantity < (record.opening_deduction or 0):
            raise ValidationError(
                f"購買堂數不能小於期初已扣抵的 {record.opening_deduction} 堂", field="quantity"
            )
        record.quantity = quantity
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

def get_class_record_or_404(record_id, user=None):
    record = db.session.get(ClassRecord, record_id)
    if not record:
        abort(404)
    if user is not None:
        ensure_student_access(user, record.student)
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


CATEGORY_BADGE_COLOR_COUNT = 10


def category_badge_class(category):
    """依分類名稱固定分配一種顏色樣式(badge-cat-0 ~ badge-cat-9)，同一分類無論在哪個頁面顯示都會是同一個顏色。
    用 crc32 而非內建 hash()，避免字串 hash 隨機化(PYTHONHASHSEED)導致每次啟動服務顏色跳動。"""
    if not category:
        return "badge-muted"
    index = zlib.crc32(category.encode("utf-8")) % CATEGORY_BADGE_COLOR_COUNT
    return f"badge-cat-{index}"


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

def list_accounts(search=None, role=None, user=None):
    query = visible_accounts_query(user) if user is not None else User.query
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(db.or_(User.username.ilike(like), User.name.ilike(like)))
    if role in ("admin", "coach", "student"):
        query = query.filter(User.role == role)
    return query.order_by(
        db.case((User.status == "pending", 0), else_=1), User.created_at.desc()
    ).all()


def register_student_account(data):
    username = (data.get("username") or "").strip()
    if not username:
        raise ValidationError("帳號為必填", field="username")
    if len(username) > 30:
        raise ValidationError("帳號長度不得超過 30 個字元", field="username")
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
        must_change_password=True,
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()
    return user


def create_student_from_registration(user):
    """帳號經教練/管理者審核通過（驗證或重新啟用）才會建立學生名冊，入班/建檔日期預設為審核當天。"""
    student = Student(
        name=user.name,
        email=user.email,
        phone=user.phone,
        phone_type=user.phone_type,
        birthday=user.birthday,
        gender=user.gender,
        status="active",
        enrollment_date=date.today(),
        notes=user.goal or None,
    )
    db.session.add(student)
    user.student = student
    db.session.flush()
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
    # 一對二卡片要兩個帳號都停用才跟著停用，另一位還在上課時卡片維持在籍(REQ-053)。
    if target_status == "disabled" and user.student is not None:
        if all(a.status == "disabled" for a in user.student.accounts):
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
    if student is not None and len(student.accounts) > 1:
        # 一對二還有另一位學員：只移除這個帳號，共用卡片與紀錄留給另一位(REQ-053)。
        user.student = None
        _sync_pair_name(student)
    elif student is not None:
        if student.remaining > 0:
            raise ValidationError("該學生尚有課程未完成，請勿刪除", field="student")
        db.session.delete(student)
    db.session.delete(user)
    db.session.commit()


def set_account_role(user, target_role):
    if target_role not in ("coach", "student"):
        raise ValidationError("角色不正確，需為 coach 或 student", field="role")
    if user.role == "admin":
        raise ValidationError("管理者帳號的角色無法在此變更", field="role")
    user.role = target_role
    if target_role == "student" and user.student_id is None:
        create_student_from_registration(user)
    db.session.commit()
    return user


def set_account_password(user, new_password):
    """管理者替他人設定密碼：對方下次登入須自行修改。"""
    user.set_password(new_password)
    user.must_change_password = True
    db.session.commit()
    return user


def change_own_password(user, current_password, new_password):
    if not user.check_password(current_password):
        raise ValidationError("目前密碼不正確", field="current_password")
    if current_password == new_password:
        raise ValidationError("新密碼不可與目前密碼相同", field="new_password")
    user.set_password(new_password)
    user.must_change_password = False
    db.session.commit()
    return user


# ---------- 公告(REQ-044) ----------

# 台灣沒有日光節約時間，固定 UTC+8；不依賴 tzdata(Windows 預設沒有)。
TAIPEI_TZ = timezone(timedelta(hours=8), "Asia/Taipei")

ANNOUNCEMENT_TITLE_MAX_LENGTH = 100
ANNOUNCEMENT_CONTENT_MAX_LENGTH = 2000
ANNOUNCEMENT_IMAGE_MAX_BYTES = 2 * 1024 * 1024
ANNOUNCEMENT_STATUS_LABELS = {"scheduled": "未上架", "live": "上架中", "expired": "已下架"}
_AUDIENCE_FIELDS = ("show_to_student", "show_to_coach", "show_to_admin")


def to_taipei(value):
    """把 UTC 時間(帶或不帶時區；SQLite 讀回來會是不帶時區)轉成台灣時間，None 原樣回傳。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TAIPEI_TZ)


def record_login(user, ip_address=None, user_agent=None):
    """登入成功：更新最後登入時間，並新增一筆登入紀錄(回傳它，id 存進 session 供之後的頁面紀錄連結)。"""
    now = datetime.now(timezone.utc)
    user.last_login_at = now
    login_session = LoginSession(
        user=user,
        login_at=now,
        last_seen_at=now,
        ip_address=(ip_address or "")[:45] or None,
        user_agent=(user_agent or "")[:500] or None,
    )
    db.session.add(login_session)
    db.session.commit()
    return login_session


def record_logout(login_session_id, user_id):
    login_session = db.session.get(LoginSession, login_session_id) if login_session_id else None
    if login_session is None or login_session.user_id != user_id:
        return
    now = datetime.now(timezone.utc)
    login_session.logout_at = now
    login_session.last_seen_at = now
    db.session.commit()


def new_page_view_key():
    return secrets.token_hex(16)


def _touch_login_session(login_session_id, user_id, now):
    login_session = db.session.get(LoginSession, login_session_id) if login_session_id else None
    if login_session is None or login_session.user_id != user_id or login_session.logout_at is not None:
        return None
    login_session.last_seen_at = now
    return login_session


def record_page_view(user, view_key, url, endpoint=None, login_session_id=None):
    now = datetime.now(timezone.utc)
    login_session = _touch_login_session(login_session_id, user.id, now)
    db.session.add(
        PageView(
            view_key=view_key,
            user_id=user.id,
            login_session_id=login_session.id if login_session else None,
            url=url[:2048],
            endpoint=(endpoint or "")[:120] or None,
            visited_at=now,
        )
    )
    db.session.commit()


# 瀏覽器回報值的合理上限，超出的視為異常資料不採用。
_MAX_LOAD_MS = 10 * 60 * 1000
_MAX_DURATION_MS = 7 * 24 * 60 * 60 * 1000


def _bounded_ms(value, upper):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = int(value)
    return value if 0 <= value <= upper else None


def finish_page_view(user, view_key, load_ms=None, duration_ms=None):
    """瀏覽器離開(或切走)頁面時回報載入與停留時間；只能更新自己的紀錄。回傳是否有找到紀錄。"""
    page_view = PageView.query.filter_by(view_key=view_key, user_id=user.id).first()
    if page_view is None:
        return False
    load_ms = _bounded_ms(load_ms, _MAX_LOAD_MS)
    duration_ms = _bounded_ms(duration_ms, _MAX_DURATION_MS)
    if load_ms is not None:
        page_view.load_ms = load_ms
    # 同一頁可能回報多次(切走又切回來)，停留時間是累計值，只往上更新。
    if duration_ms is not None and (page_view.duration_ms is None or duration_ms > page_view.duration_ms):
        page_view.duration_ms = duration_ms
    _touch_login_session(page_view.login_session_id, user.id, datetime.now(timezone.utc))
    db.session.commit()
    return True


def taipei_now():
    """目前的台灣時間(不帶時區)，與 Announcement 上/下架欄位的存法一致。"""
    return datetime.now(TAIPEI_TZ).replace(tzinfo=None)


def announcement_status(announcement, now=None):
    now = now or taipei_now()
    if now < announcement.publish_at:
        return "scheduled"
    if now >= announcement.unpublish_at:
        return "expired"
    return "live"


def _detect_image_mime(data):
    """以檔案開頭的魔術數字判斷圖片類型，不信任副檔名與瀏覽器送來的 Content-Type。"""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _validate_announcement_image(data):
    if len(data) > ANNOUNCEMENT_IMAGE_MAX_BYTES:
        raise ValidationError("圖片大小不能超過 2MB", field="image")
    mime = _detect_image_mime(data)
    if mime is None:
        raise ValidationError("圖片格式需為 JPG、PNG 或 WebP", field="image")
    return mime


def _apply_announcement_data(announcement, data):
    announce_date = data.get("announce_date")
    publish_at = data.get("publish_at")
    unpublish_at = data.get("unpublish_at")
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()

    if not announce_date:
        raise ValidationError("公告日期為必填", field="announce_date")
    if not publish_at:
        raise ValidationError("上架日期時間為必填", field="publish_at")
    if not unpublish_at:
        raise ValidationError("下架日期時間為必填", field="unpublish_at")
    if publish_at.date() < announce_date:
        raise ValidationError("上架日期不得早於公告日期", field="publish_at")
    if unpublish_at <= publish_at:
        raise ValidationError("下架日期時間必須晚於上架日期時間", field="unpublish_at")
    if not title:
        raise ValidationError("公告標題為必填", field="title")
    if len(title) > ANNOUNCEMENT_TITLE_MAX_LENGTH:
        raise ValidationError(f"公告標題不能超過 {ANNOUNCEMENT_TITLE_MAX_LENGTH} 個字", field="title")
    if not content:
        raise ValidationError("公告內容為必填", field="content")
    if len(content) > ANNOUNCEMENT_CONTENT_MAX_LENGTH:
        raise ValidationError(f"公告內容不能超過 {ANNOUNCEMENT_CONTENT_MAX_LENGTH} 個字", field="content")
    audience = {f: bool(data.get(f)) for f in _AUDIENCE_FIELDS}
    if not any(audience.values()):
        raise ValidationError("請至少選擇一個顯示對象", field="show_to_student")

    image_data = data.get("image_data")
    image_mime = _validate_announcement_image(image_data) if image_data else None

    announcement.announce_date = announce_date
    announcement.publish_at = publish_at.replace(second=0, microsecond=0)
    announcement.unpublish_at = unpublish_at.replace(second=0, microsecond=0)
    announcement.title = title
    announcement.content = content
    for field, value in audience.items():
        setattr(announcement, field, value)
    if image_data:
        announcement.image_data = image_data
        announcement.image_mime = image_mime
    elif data.get("remove_image"):
        announcement.image_data = None
        announcement.image_mime = None


def create_announcement(data, created_by=None):
    announcement = Announcement(created_by_id=created_by.id if created_by else None)
    _apply_announcement_data(announcement, data)
    db.session.add(announcement)
    db.session.commit()
    return announcement


def update_announcement(announcement, data):
    _apply_announcement_data(announcement, data)
    db.session.commit()
    return announcement


def delete_announcement(announcement):
    db.session.delete(announcement)
    db.session.commit()


def get_announcement_or_404(announcement_id):
    announcement = db.session.get(Announcement, announcement_id)
    if not announcement:
        abort(404)
    return announcement


def list_announcements(status=None):
    now = taipei_now()
    query = Announcement.query
    if status == "scheduled":
        query = query.filter(Announcement.publish_at > now)
    elif status == "live":
        query = query.filter(Announcement.publish_at <= now, Announcement.unpublish_at > now)
    elif status == "expired":
        query = query.filter(Announcement.unpublish_at <= now)
    return query.order_by(Announcement.publish_at.desc(), Announcement.id.desc()).all()


def list_live_announcements_for(role):
    """目前上架中、且顯示對象包含該角色的公告，最新上架的在前。"""
    column = {
        "student": Announcement.show_to_student,
        "coach": Announcement.show_to_coach,
        "admin": Announcement.show_to_admin,
    }.get(role)
    if column is None:
        return []
    now = taipei_now()
    return (
        Announcement.query.filter(
            column.is_(True), Announcement.publish_at <= now, Announcement.unpublish_at > now
        )
        .order_by(Announcement.publish_at.desc(), Announcement.id.desc())
        .all()
    )
