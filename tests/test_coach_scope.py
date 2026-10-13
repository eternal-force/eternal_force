"""REQ-051：教練只能看到自己上過課的學生(與尚未分配教練的學生)，以及這些學生的帳號。"""

from datetime import date, time

import pytest

from app.models import ClassRecord, PurchaseRecord, Student, User
from tests.conftest import COACH_PASSWORD, COACH_USERNAME, get_csrf_token, login


@pytest.fixture()
def scope(app, db, coach_user, admin_user):
    """教練A(coach_user)與教練B，以及 mine / theirs / shared / unassigned 四位學生(各有帳號)。"""
    coach_b = User(username="coach2", role="coach", status="active", name="教練B")
    coach_b.set_password(COACH_PASSWORD)
    db.session.add(coach_b)
    db.session.flush()

    def make(name, coaches):
        student = Student(name=name, status="active")
        student.purchase_records.append(PurchaseRecord(purchase_date=date(2026, 1, 1), quantity=10))
        for coach in coaches:
            student.class_records.append(
                ClassRecord(class_date=date(2026, 2, 1), class_time=time(10, 0), coach_id=coach.id)
            )
        account = User(username=f"acct_{name}", role="student", status="active", name=name, student=student)
        account.set_password("StudentPass123")
        db.session.add_all([student, account])
        return student

    students = {
        "mine": make("我的學生", [coach_user]),
        "theirs": make("別人的學生", [coach_b]),
        "shared": make("共用學生", [coach_user, coach_b]),
        "unassigned": make("未分配學生", []),
    }
    db.session.commit()
    return {"coach_b": coach_b, **students}


@pytest.fixture()
def coach_a_client(client, scope):
    login(client, COACH_USERNAME, COACH_PASSWORD)
    return client


def _csrf(client, scope):
    return get_csrf_token(client.get(f"/students/{scope['mine'].id}").get_data(as_text=True))


def test_coach_list_only_shows_own_shared_and_unassigned(coach_a_client, scope):
    html = coach_a_client.get("/students/").get_data(as_text=True)
    assert "我的學生" in html and "共用學生" in html and "未分配學生" in html
    assert "別人的學生" not in html


def test_admin_list_shows_everyone(logged_in_client, scope):
    html = logged_in_client.get("/students/").get_data(as_text=True)
    for name in ("我的學生", "別人的學生", "共用學生", "未分配學生"):
        assert name in html


def test_coach_blocked_from_other_coach_student_pages(coach_a_client, scope):
    theirs = scope["theirs"]
    record_id = theirs.class_records[0].id
    purchase_id = theirs.purchase_records[0].id
    for url in (
        f"/students/{theirs.id}",
        f"/students/{theirs.id}/edit",
        f"/students/{theirs.id}/purchases/new",
        f"/purchases/{purchase_id}/edit",
        f"/students/{theirs.id}/classes/new",
        f"/classes/{record_id}/edit",
    ):
        assert coach_a_client.get(url).status_code == 403, url
    token = _csrf(coach_a_client, scope)
    for url in (
        f"/students/{theirs.id}/status",
        f"/purchases/{purchase_id}/delete",
        f"/classes/{record_id}/delete",
    ):
        assert coach_a_client.post(url, data={"csrf_token": token}).status_code == 403, url
    assert ClassRecord.query.filter_by(student_id=theirs.id).count() == 1


def test_both_coaches_can_open_shared_student(client, scope):
    shared_id = scope["shared"].id
    login(client, "coach2", COACH_PASSWORD)
    resp = client.get(f"/students/{shared_id}")
    assert resp.status_code == 200
    # 共用學生的兩位教練都看得到對方的上課紀錄
    assert "教練A" in resp.get_data(as_text=True)
    assert client.get(f"/students/{scope['mine'].id}").status_code == 403


def test_coach_api_is_scoped(coach_a_client, scope):
    names = {s["name"] for s in coach_a_client.get("/api/students").get_json()}
    assert names == {"我的學生", "共用學生", "未分配學生"}
    theirs = scope["theirs"]
    assert coach_a_client.get(f"/api/students/{theirs.id}").status_code == 403
    assert coach_a_client.get(f"/api/students/{theirs.id}/summary").status_code == 403
    assert coach_a_client.get(f"/api/students/{theirs.id}/classes").status_code == 403
    assert coach_a_client.get(f"/api/students/{theirs.id}/purchases").status_code == 403
    assert coach_a_client.delete(f"/api/classes/{theirs.class_records[0].id}").status_code == 403
    assert coach_a_client.delete(f"/api/purchases/{theirs.purchase_records[0].id}").status_code == 403
    assert coach_a_client.get(f"/api/students/{scope['mine'].id}").status_code == 200


def test_coach_accounts_are_scoped(coach_a_client, scope, pending_student_user):
    html = coach_a_client.get("/accounts/").get_data(as_text=True)
    assert "acct_我的學生" in html and "acct_共用學生" in html and "acct_未分配學生" in html
    assert pending_student_user.username in html
    assert "acct_別人的學生" not in html
    assert "coach2" not in html and "新增教練帳號" not in html

    their_account = User.query.filter_by(username="acct_別人的學生").one()
    assert coach_a_client.get(f"/accounts/{their_account.id}").status_code == 403
    resp = coach_a_client.post(
        f"/accounts/{their_account.id}/status",
        data={"csrf_token": _csrf(coach_a_client, scope), "target_status": "disabled"},
    )
    assert resp.status_code == 403 and their_account.status == "active"
    assert coach_a_client.get(f"/accounts/{scope['coach_b'].id}").status_code == 403
    assert coach_a_client.get("/accounts/new-coach").status_code == 403
    my_account = User.query.filter_by(username="acct_我的學生").one()
    assert coach_a_client.get(f"/accounts/{my_account.id}").status_code == 200
    assert coach_a_client.get(f"/accounts/{pending_student_user.id}").status_code == 200


def test_admin_accounts_show_everyone(logged_in_client, scope):
    html = logged_in_client.get("/accounts/").get_data(as_text=True)
    assert "acct_別人的學生" in html and "coach2" in html and "新增教練帳號" in html


def test_new_class_form_defaults_to_current_coach(coach_a_client, scope, coach_user):
    html = coach_a_client.get(f"/students/{scope['unassigned'].id}/classes/new").get_data(as_text=True)
    assert f'<option selected value="{coach_user.id}">' in html


def test_assigning_unassigned_student_to_other_coach_hides_it(coach_a_client, scope):
    student_id = scope["unassigned"].id
    url = f"/students/{student_id}/classes/new"
    token = get_csrf_token(coach_a_client.get(url).get_data(as_text=True))
    resp = coach_a_client.post(
        url,
        data={
            "class_date": "2026-03-01",
            "class_time": "10:00",
            "coach_id": str(scope["coach_b"].id),
            "csrf_token": token,
        },
    )
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/students/")
    assert coach_a_client.get(f"/students/{student_id}").status_code == 403


def test_opening_record_is_not_counted_as_attended(app, db, coach_user):
    student = Student(name="期初學生", status="active")
    student.purchase_records.append(
        PurchaseRecord(purchase_date=date(2026, 1, 1), quantity=10, opening_deduction=3)
    )
    student.class_records.append(
        ClassRecord(
            class_date=date(2026, 9, 1), class_time=time(0, 0), coach_id=coach_user.id, is_opening=True
        )
    )
    db.session.add(student)
    db.session.commit()
    assert (student.total_purchased, student.total_attended, student.remaining) == (7, 0, 7)
