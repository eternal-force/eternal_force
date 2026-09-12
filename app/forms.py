from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    DecimalField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
    TimeField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError as WTFValidationError,
)

from .models import User
from .services import ValidationError as ServiceValidationError
from .services import validate_phone_by_type

PHONE_TYPE_CHOICES = [("", "請選擇"), ("mobile", "手機"), ("landline", "家電")]


def _validate_phone_field(form, field):
    """依 phone_type 下拉選單驗證 phone 欄位格式；服務層與表單共用同一組正則，避免規則兜不起來。"""
    try:
        validate_phone_by_type(field.data, form.phone_type.data or None)
    except ServiceValidationError as exc:
        raise WTFValidationError(exc.message)


class LoginForm(FlaskForm):
    username = StringField("帳號", validators=[DataRequired(), Length(max=80)])
    password = PasswordField("密碼", validators=[DataRequired()])


def _validate_username_unique(form, field):
    if User.query.filter_by(username=field.data.strip()).first():
        raise WTFValidationError("此帳號已被使用")


class RegisterForm(FlaskForm):
    username = StringField(
        "帳號", validators=[DataRequired(message="帳號為必填"), Length(max=80), _validate_username_unique]
    )
    password = PasswordField(
        "密碼", validators=[DataRequired(message="密碼為必填"), Length(min=8, message="密碼長度至少需 8 碼")]
    )
    confirm_password = PasswordField(
        "確認密碼",
        validators=[DataRequired(message="請再次輸入密碼"), EqualTo("password", message="兩次輸入的密碼不一致")],
    )
    name = StringField("姓名", validators=[DataRequired(message="姓名為必填"), Length(max=120)])
    phone_type = SelectField(
        "電話類型", choices=PHONE_TYPE_CHOICES, validators=[DataRequired(message="請選擇電話類型")]
    )
    phone = StringField(
        "連絡電話", validators=[DataRequired(message="連絡電話為必填"), Length(max=40), _validate_phone_field]
    )
    birthday = DateField("生日", validators=[DataRequired(message="生日為必填")])
    gender = SelectField(
        "性別",
        choices=[("", "請選擇"), ("male", "男"), ("female", "女"), ("other", "其他")],
        validators=[DataRequired(message="請選擇性別")],
    )
    goal = TextAreaField("期望運動達成的效益", validators=[Optional(), Length(max=2000)])


class SetPasswordForm(FlaskForm):
    new_password = PasswordField(
        "新密碼", validators=[DataRequired(message="密碼為必填"), Length(min=8, message="密碼長度至少需 8 碼")]
    )
    confirm_password = PasswordField(
        "確認新密碼",
        validators=[DataRequired(message="請再次輸入密碼"), EqualTo("new_password", message="兩次輸入的密碼不一致")],
    )


class CoachForm(FlaskForm):
    username = StringField(
        "帳號", validators=[DataRequired(message="帳號為必填"), Length(max=80), _validate_username_unique]
    )
    password = PasswordField(
        "密碼", validators=[DataRequired(message="密碼為必填"), Length(min=8, message="密碼長度至少需 8 碼")]
    )
    name = StringField("姓名", validators=[DataRequired(message="姓名為必填"), Length(max=120)])
    phone_type = SelectField("電話類型", choices=PHONE_TYPE_CHOICES, validators=[Optional()])
    phone = StringField("連絡電話", validators=[Optional(), Length(max=40), _validate_phone_field])


class StudentForm(FlaskForm):
    name = StringField("姓名", validators=[DataRequired(message="姓名為必填"), Length(max=120)])
    phone = StringField("聯絡電話", validators=[Optional(), Length(max=40)])
    email = StringField("聯絡信箱", validators=[Optional(), Email(message="Email 格式不正確"), Length(max=255)])
    birthday = DateField("生日", validators=[Optional()])
    gender = SelectField(
        "性別",
        choices=[("", "未填寫"), ("male", "男"), ("female", "女"), ("other", "其他")],
        validators=[Optional()],
    )
    enrollment_date = DateField("入班/建檔日期", validators=[Optional()])
    status = SelectField(
        "在籍狀態", choices=[("active", "在籍"), ("inactive", "停用")], validators=[DataRequired()]
    )
    notes = TextAreaField("備註", validators=[Optional(), Length(max=2000)])

    def validate_gender(self, field):
        if field.data == "":
            field.data = None


class PurchaseForm(FlaskForm):
    purchase_date = DateField("購買日期", validators=[DataRequired(message="購買日期為必填")])
    quantity = IntegerField(
        "購買堂數",
        validators=[
            InputRequired(message="購買堂數為必填"),
            NumberRange(min=1, max=9999, message="購買堂數必須是正整數，且不能大於 9999"),
        ],
    )
    price = DecimalField(
        "購買金額",
        places=2,
        validators=[Optional(), NumberRange(max=1000000, message="購買金額不能大於 1,000,000")],
    )
    notes = TextAreaField("備註", validators=[Optional(), Length(max=2000)])


class ClassRecordForm(FlaskForm):
    class_date = DateField("到課日期", validators=[DataRequired(message="到課日期為必填")])
    class_time = TimeField("到課時間", validators=[DataRequired(message="到課時間為必填")])
    coach_id = SelectField("上課教練", validators=[DataRequired(message="請選擇上課教練")])
    notes = TextAreaField("備註", validators=[Optional(), Length(max=2000)])


class ExerciseCatalogForm(FlaskForm):
    category = StringField("分類", validators=[DataRequired(message="分類為必填"), Length(max=120)])
    name = StringField("項目名稱", validators=[DataRequired(message="項目名稱為必填"), Length(max=200)])


class DeleteConfirmForm(FlaskForm):
    """僅用來攜帶 CSRF token 的空表單,搭配確認刪除頁使用。"""

    pass
