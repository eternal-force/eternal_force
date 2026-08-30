from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum("admin", "coach", "student", name="user_role_enum", native_enum=False),
        default="student",
        nullable=False,
    )
    status = db.Column(
        db.Enum("pending", "active", "disabled", name="user_status_enum", native_enum=False),
        default="active",
        nullable=False,
    )
    name = db.Column(db.String(120))
    phone = db.Column(db.String(40))
    birthday = db.Column(db.Date)
    gender = db.Column(
        db.Enum("male", "female", "other", name="user_gender_enum", native_enum=False)
    )
    goal = db.Column(db.Text)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="SET NULL"), unique=True
    )
    student = db.relationship("Student", foreign_keys=[student_id])
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password, method="pbkdf2:sha256")

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_active(self):
        return self.status == "active"


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(40))
    email = db.Column(db.String(255))
    birthday = db.Column(db.Date)
    gender = db.Column(
        db.Enum("male", "female", "other", name="gender_enum", native_enum=False)
    )
    enrollment_date = db.Column(db.Date)
    status = db.Column(
        db.Enum("active", "inactive", name="student_status_enum", native_enum=False),
        default="active",
        nullable=False,
    )
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    purchase_records = db.relationship(
        "PurchaseRecord",
        backref="student",
        cascade="all, delete-orphan",
        order_by="PurchaseRecord.purchase_date.desc()",
    )
    class_records = db.relationship(
        "ClassRecord",
        backref="student",
        cascade="all, delete-orphan",
        order_by="ClassRecord.class_date.desc()",
    )

    @property
    def total_purchased(self):
        return sum((p.quantity for p in self.purchase_records), 0)

    @property
    def total_attended(self):
        return len(self.class_records)

    @property
    def remaining(self):
        return self.total_purchased - self.total_attended

    def to_dict(self, include_summary=True):
        data = {
            "student_id": self.id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "birthday": self.birthday.isoformat() if self.birthday else None,
            "gender": self.gender,
            "enrollment_date": self.enrollment_date.isoformat() if self.enrollment_date else None,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_summary:
            data.update(
                {
                    "total_purchased": self.total_purchased,
                    "total_attended": self.total_attended,
                    "remaining": self.remaining,
                }
            )
        return data


class PurchaseRecord(db.Model):
    __tablename__ = "purchase_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (db.CheckConstraint("quantity > 0", name="ck_purchase_quantity_positive"),)

    def to_dict(self):
        return {
            "purchase_id": self.id,
            "student_id": self.student_id,
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "quantity": self.quantity,
            "price": float(self.price) if self.price is not None else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ClassRecord(db.Model):
    __tablename__ = "class_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_date = db.Column(db.Date, nullable=False)
    class_time = db.Column(db.Time, nullable=False)
    coach_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    coach = db.relationship("User", foreign_keys=[coach_id])
    exercises = db.relationship(
        "ClassExercise",
        backref="class_record",
        cascade="all, delete-orphan",
        order_by="ClassExercise.sort_order",
    )

    def to_dict(self):
        return {
            "record_id": self.id,
            "student_id": self.student_id,
            "class_date": self.class_date.isoformat() if self.class_date else None,
            "class_time": self.class_time.isoformat() if self.class_time else None,
            "coach_id": self.coach_id,
            "coach_name": self.coach.name if self.coach else None,
            "notes": self.notes,
            "exercises": [e.to_dict() for e in self.exercises],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ExerciseCatalogItem(db.Model):
    __tablename__ = "exercise_catalog_items"

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(200), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "name": self.name,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ClassExercise(db.Model):
    """某次上課紀錄選用的訓練項目(訓練菜單)；項目可來自訓練項目清單，也可自行輸入未建檔的項目名稱。"""

    __tablename__ = "class_exercises"

    id = db.Column(db.Integer, primary_key=True)
    class_record_id = db.Column(
        db.Integer, db.ForeignKey("class_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exercise_catalog_item_id = db.Column(
        db.Integer, db.ForeignKey("exercise_catalog_items.id", ondelete="SET NULL")
    )
    category = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    weight_kg = db.Column(db.Numeric(6, 2))
    sets = db.Column(db.Integer)
    reps = db.Column(db.Integer)
    note = db.Column(db.Text)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "class_record_id": self.class_record_id,
            "exercise_catalog_item_id": self.exercise_catalog_item_id,
            "category": self.category,
            "name": self.name,
            "weight_kg": float(self.weight_kg) if self.weight_kg is not None else None,
            "sets": self.sets,
            "reps": self.reps,
            "note": self.note,
            "sort_order": self.sort_order,
        }
