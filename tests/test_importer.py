from datetime import date

from openpyxl import load_workbook

from app import importer
from app.models import ClassRecord, PurchaseRecord, Student, User


def _fill(path, rows, keep_example=False):
    importer.build_template(path)
    wb = load_workbook(path)
    ws = wb[importer.DATA_SHEET]
    keys = [key for key, *_rest in importer.COLUMNS]
    start = 3 if keep_example else 2
    if not keep_example:
        for col in range(1, len(keys) + 1):
            ws.cell(row=2, column=col).value = None
    for offset, row in enumerate(rows):
        for col, key in enumerate(keys, start=1):
            ws.cell(row=start + offset, column=col).value = row.get(key)
    wb.save(path)


def _row(**overrides):
    row = {
        "name": "陳大文",
        "phone_type": "手機",
        "phone": "0912345678",
        "gender": "男",
        "purchase_date": date(2026, 1, 1),
        "quantity": 10,
        "used": 3,
        "last_class_date": date(2026, 9, 1),
        "coach": "教練A",
    }
    row.update(overrides)
    return row


def test_template_example_row_is_valid(app, coach_user, tmp_path):
    path = tmp_path / "t.xlsx"
    importer.build_template(path)
    rows, errors = importer.read_rows(path)
    assert errors == []
    assert [d["name"] for _n, d in rows] == ["範例 王小明"]
    assert rows[0][1]["coach_id"] == coach_user.id


def test_import_records_used_as_opening_deduction(app, coach_user, db, tmp_path):
    path = tmp_path / "t.xlsx"
    _fill(path, [_row(price=12000), _row(name="林小美", phone_type=None, phone=None, used=0, quantity=5)])
    rows, errors = importer.read_rows(path)
    assert errors == []
    importer.import_rows(rows)

    chen = Student.query.filter_by(name="陳大文").one()
    assert (chen.total_purchased, chen.total_attended, chen.remaining) == (7, 0, 7)
    assert chen.gender == "male" and chen.phone_type == "mobile"
    (purchase,) = chen.purchase_records
    assert (purchase.quantity, purchase.opening_deduction, purchase.price) == (10, 3, 12000)
    lin = Student.query.filter_by(name="林小美").one()
    assert (lin.total_purchased, lin.remaining) == (5, 5)
    assert lin.class_records == []

    (opening,) = chen.class_records
    assert (opening.class_date, opening.coach_id) == (date(2026, 9, 1), coach_user.id)
    assert opening.is_opening and opening.notes == "初始匯入" and opening.exercises == []
    assert ClassRecord.query.count() == 1


def test_fully_used_row_imports_with_zero_remaining(app, coach_user, db, tmp_path):
    path = tmp_path / "t.xlsx"
    _fill(path, [_row(quantity=10, used=10)])
    rows, errors = importer.read_rows(path)
    assert errors == []
    importer.import_rows(rows)
    student = Student.query.one()
    assert (student.total_purchased, student.remaining) == (0, 0)
    assert PurchaseRecord.query.one().quantity == 10


def test_validation_errors_are_reported_per_row(app, coach_user, db, tmp_path):
    db.session.add(Student(name="舊學生", status="active"))
    db.session.commit()
    path = tmp_path / "t.xlsx"
    _fill(
        path,
        [
            _row(used=11),
            _row(name="舊學生"),
            _row(name="甲", quantity=None),
            _row(name="乙", phone="12345", phone_type="手機"),
            _row(name="丙", purchase_date="2026/13/40"),
            _row(name="丁"),
            _row(name="丁"),
        ],
    )
    rows, errors = importer.read_rows(path)
    assert [n for n, _m in errors] == [2, 3, 4, 5, 6, 8]
    assert "不能大於購買堂數" in errors[0][1]
    assert [d["name"] for _n, d in rows] == ["丁"]


def test_used_lessons_require_valid_coach_and_last_class_date(app, coach_user, db, tmp_path):
    twin = [User(username=f"twin{i}", role="coach", status="active", name="雙胞胎") for i in (1, 2)]
    retired = User(username="retired", role="coach", status="disabled", name="離職教練")
    for user in twin + [retired]:
        user.set_password("password123")
    db.session.add_all(twin + [retired])
    db.session.commit()
    path = tmp_path / "t.xlsx"
    _fill(
        path,
        [
            _row(name="甲", coach=None),
            _row(name="乙", last_class_date=None),
            _row(name="丙", coach="不存在"),
            _row(name="丁", coach="雙胞胎"),
            _row(name="戊", coach="離職教練"),
            _row(name="己", last_class_date=date(2025, 12, 31)),
            _row(name="庚", last_class_date=date(2999, 1, 1)),
            _row(name="辛", phone=None, phone_type=None, used=0, coach=None, last_class_date=None),
        ],
    )
    rows, errors = importer.read_rows(path)
    messages = dict(errors)
    assert sorted(messages) == [2, 3, 4, 5, 6, 7, 8]
    assert "目前教練為必填" in messages[2]
    assert "最後上課日期為必填" in messages[3]
    assert "找不到啟用中的教練" in messages[4]
    assert "多位教練同名" in messages[5]
    assert "找不到啟用中的教練" in messages[6]
    assert "不能早於購買日期" in messages[7]
    assert "不能晚於今天" in messages[8]
    assert [(d["name"], d["coach_id"]) for _n, d in rows] == [("辛", None)]


def test_template_lists_active_coaches(app, coach_user, tmp_path):
    path = tmp_path / "t.xlsx"
    importer.build_template(path)
    ws = load_workbook(path)[importer.DATA_SHEET]
    formulas = [dv.formula1 for dv in ws.data_validations.dataValidation]
    assert '"教練A"' in formulas


def test_phone_losing_leading_zero_is_restored(app, coach_user, tmp_path):
    path = tmp_path / "t.xlsx"
    _fill(path, [_row(phone=912345678)])
    rows, errors = importer.read_rows(path)
    assert errors == []
    assert rows[0][1]["phone"] == "0912345678"


def test_import_creates_account_for_mobile_phone(app, coach_user, db, tmp_path):
    path = tmp_path / "t.xlsx"
    _fill(
        path,
        [
            _row(email="chen@mail.com", birthday=date(1990, 2, 3)),
            _row(name="林小美", phone_type=None, phone=None),
            _row(name="王市話", phone_type="市話", phone="02-12345678"),
        ],
    )
    rows, errors = importer.read_rows(path)
    assert errors == []
    importer.import_rows(rows)

    user = User.query.filter_by(role="student").one()
    chen = Student.query.filter_by(name="陳大文").one()
    assert (user.username, user.role, user.status) == ("0912345678", "student", "active")
    assert user.check_password("0912345678") and user.must_change_password
    assert user.student_id == chen.id and chen.account is user
    assert (user.name, user.email, user.phone, user.phone_type) == ("陳大文", "chen@mail.com", "0912345678", "mobile")
    assert (user.birthday, user.gender) == (date(1990, 2, 3), "male")
    assert Student.query.filter_by(name="林小美").one().account is None
    assert Student.query.filter_by(name="王市話").one().account is None


def test_phone_clashing_with_account_is_rejected(app, coach_user, db, tmp_path):
    existing = User(username="0911111111", role="coach", status="active")
    existing.set_password("password123")
    db.session.add(existing)
    db.session.commit()
    path = tmp_path / "t.xlsx"
    _fill(path, [_row(phone="0911111111"), _row(name="甲"), _row(name="乙")])
    rows, errors = importer.read_rows(path)
    assert [n for n, _m in errors] == [2, 4]
    assert "系統內已有帳號" in errors[0][1]
    assert "與第 3 列手機號碼重複" in errors[1][1]
    assert [d["name"] for _n, d in rows] == ["甲"]


def test_cli_dry_run_does_not_write(app, coach_user, db, tmp_path):
    path = tmp_path / "t.xlsx"
    _fill(path, [_row()])
    runner = app.test_cli_runner()
    result = runner.invoke(args=["import-students", str(path)])
    assert result.exit_code == 0, result.output
    assert "將建立 1 個學生帳號" in result.output
    assert "教練「教練A」：1 位學生" in result.output
    assert Student.query.count() == 0
    assert User.query.filter_by(role="student").count() == 0

    result = runner.invoke(args=["import-students", str(path), "--commit"])
    assert result.exit_code == 0, result.output
    assert Student.query.count() == 1
    assert User.query.filter_by(role="student").count() == 1


def test_cli_rejects_whole_batch_on_error(app, coach_user, db, tmp_path):
    path = tmp_path / "t.xlsx"
    _fill(path, [_row(), _row(name="壞資料", used=99)])
    result = app.test_cli_runner().invoke(args=["import-students", str(path), "--commit"])
    assert result.exit_code != 0
    assert Student.query.count() == 0
