"""REQ-055：帳號管理可替學生帳號設定所屬教練(可複選)，驗證待審核帳號時可一併設定。"""

from datetime import date, time

import pytest
from flask import g

from app import services
from app.extensions import db as _db
from app.models import ClassRecord, Student, User, account_coaches
from tests.conftest import (
    COACH_PASSWORD,
    COACH_USERNAME,
    get_csrf_token,
    login,
)


@pytest.fixture()
def coach_b(app, db):
    coach = User(username="coach2", role="coach", status="active", name="教練B")
    coach.set_password(COACH_PASSWORD)
    db.session.add(coach)
    db.session.commit()
    return coach


def _token(client):
    return get_csrf_token(client.get("/accounts/").get_data(as_text=True))


def _verify(client, user, coach_ids):
    return client.post(
        f"/accounts/{user.id}/verify",
        data={"csrf_token": _token(client), "assign_coaches": "1", "coach_ids": [str(i) for i in coach_ids]},
    )


def _set_coaches(client, user, coach_ids):
    return client.post(
        f"/accounts/{user.id}/coaches",
        data={"csrf_token": _token(client), "coach_ids": [str(i) for i in coach_ids]},
    )


def _switch(client, username, password):
    """以另一位使用者登入，回傳新的 client(登出路由只接受 POST，直接換一個乾淨的 client 比較單純)。
    測試全程共用同一個 app context，Flask-Login 的登入者與 Flask-WTF 的 CSRF token 都快取在 g，換人前要清掉。"""
    g.pop("_login_user", None)
    g.pop("csrf_token", None)
    other = client.application.test_client()
    login(other, username, password)
    return other


def test_verify_dialog_lists_coaches_and_preselects_current_coach(
    client, coach_user, coach_b, pending_student_user
):
    login(client, COACH_USERNAME, COACH_PASSWORD)
    html = client.get("/accounts/").get_data(as_text=True)
    assert f'id="verify-dialog-{pending_student_user.id}"' in html
    assert "教練B" in html
    assert f'value="{coach_user.id}" checked' in html
    assert f'value="{coach_b.id}" checked' not in html


def test_coach_verifies_with_own_coach_only_hides_from_other_coaches(
    client, coach_user, coach_b, pending_student_user
):
    login(client, COACH_USERNAME, COACH_PASSWORD)
    resp = _verify(client, pending_student_user, [coach_user.id])
    assert resp.status_code == 302
    assert pending_student_user.status == "active"
    assert pending_student_user.student is not None
    assert [c.id for c in pending_student_user.assigned_coaches] == [coach_user.id]
    student_id = pending_student_user.student_id
    assert client.get(f"/students/{student_id}").status_code == 200

    client = _switch(client, "coach2", COACH_PASSWORD)
    assert pending_student_user.name not in client.get("/students/").get_data(as_text=True)
    assert client.get(f"/students/{student_id}").status_code == 403
    assert pending_student_user.username not in client.get("/accounts/").get_data(as_text=True)
    assert client.get(f"/accounts/{pending_student_user.id}").status_code == 403


def test_verify_with_multiple_coaches_visible_to_each(client, admin_user, coach_user, coach_b, pending_student_user):
    login(client)
    _verify(client, pending_student_user, [coach_user.id, coach_b.id])
    assert {c.id for c in pending_student_user.assigned_coaches} == {coach_user.id, coach_b.id}
    student_id = pending_student_user.student_id
    for username in (COACH_USERNAME, "coach2"):
        client = _switch(client, username, COACH_PASSWORD)
        assert client.get(f"/students/{student_id}").status_code == 200, username


def test_verify_without_any_coach_stays_unassigned(client, coach_user, coach_b, pending_student_user):
    login(client, COACH_USERNAME, COACH_PASSWORD)
    _verify(client, pending_student_user, [])
    assert pending_student_user.status == "active" and pending_student_user.assigned_coaches == []
    client = _switch(client, "coach2", COACH_PASSWORD)
    assert client.get(f"/students/{pending_student_user.student_id}").status_code == 200


def test_plain_verify_keeps_existing_coaches(client, admin_user, coach_user, pending_student_user):
    services.set_account_coaches(pending_student_user, [coach_user.id])
    login(client)
    client.post(f"/accounts/{pending_student_user.id}/verify", data={"csrf_token": _token(client)})
    assert pending_student_user.status == "active"
    assert [c.id for c in pending_student_user.assigned_coaches] == [coach_user.id]


def test_verify_rejects_invalid_coach(client, admin_user, coach_user, pending_student_user):
    login(client)
    resp = _verify(client, pending_student_user, [admin_user.id])
    assert resp.status_code == 302
    assert pending_student_user.status == "pending"
    assert pending_student_user.student is None
    assert "所屬教練不正確" in client.get("/accounts/").get_data(as_text=True)


def test_pending_account_assigned_to_other_coach_is_hidden(client, coach_user, coach_b, pending_student_user):
    services.set_account_coaches(pending_student_user, [coach_b.id])
    login(client, COACH_USERNAME, COACH_PASSWORD)
    assert pending_student_user.username not in client.get("/accounts/").get_data(as_text=True)
    assert client.get(f"/accounts/{pending_student_user.id}").status_code == 403
    client = _switch(client, "coach2", COACH_PASSWORD)
    assert pending_student_user.username in client.get("/accounts/").get_data(as_text=True)


def test_admin_sets_coaches_on_detail_page(client, admin_user, coach_user, coach_b, active_student_user):
    login(client)
    html = client.get(f"/accounts/{active_student_user.id}").get_data(as_text=True)
    assert "所屬教練" in html and "未指定" in html and "設定所屬教練" in html

    resp = _set_coaches(client, active_student_user, [coach_b.id])
    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/accounts/{active_student_user.id}")
    assert [c.id for c in active_student_user.assigned_coaches] == [coach_b.id]
    html = client.get(f"/accounts/{active_student_user.id}").get_data(as_text=True)
    assert f'value="{coach_b.id}" checked' in html
    assert "教練：教練B" in client.get("/accounts/").get_data(as_text=True)

    client = _switch(client, COACH_USERNAME, COACH_PASSWORD)
    assert client.get(f"/students/{active_student_user.student_id}").status_code == 403


def test_coach_removing_self_redirects_to_list(client, coach_user, coach_b, active_student_user):
    services.set_account_coaches(active_student_user, [coach_user.id])
    login(client, COACH_USERNAME, COACH_PASSWORD)
    resp = _set_coaches(client, active_student_user, [coach_b.id])
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/accounts/")
    assert client.get(f"/accounts/{active_student_user.id}").status_code == 403


def test_coach_cannot_set_coaches_on_hidden_or_non_student_accounts(client, coach_user, coach_b, active_student_user):
    services.set_account_coaches(active_student_user, [coach_b.id])
    login(client, COACH_USERNAME, COACH_PASSWORD)
    assert _set_coaches(client, active_student_user, [coach_user.id]).status_code == 403
    assert _set_coaches(client, coach_b, [coach_user.id]).status_code == 403
    assert [c.id for c in active_student_user.assigned_coaches] == [coach_b.id]


def test_class_record_coach_still_sees_assigned_student(client, coach_user, coach_b, active_student_user):
    services.set_account_coaches(active_student_user, [coach_b.id])
    active_student_user.student.class_records.append(
        ClassRecord(class_date=date(2026, 2, 1), class_time=time(10, 0), coach_id=coach_user.id)
    )
    _db.session.commit()
    login(client, COACH_USERNAME, COACH_PASSWORD)
    assert client.get(f"/students/{active_student_user.student_id}").status_code == 200


def test_disabled_coach_kept_but_cannot_be_newly_added(app, db, coach_user, coach_b, active_student_user, pending_student_user):
    services.set_account_coaches(active_student_user, [coach_b.id])
    coach_b.status = "disabled"
    db.session.commit()
    services.set_account_coaches(active_student_user, [coach_b.id, coach_user.id])
    assert {c.id for c in active_student_user.assigned_coaches} == {coach_b.id, coach_user.id}
    assert coach_b in services.coach_choices_for(active_student_user)
    with pytest.raises(services.ValidationError):
        services.set_account_coaches(pending_student_user, [coach_b.id])


def test_role_change_to_coach_clears_assignments(app, db, coach_user, active_student_user):
    services.set_account_coaches(active_student_user, [coach_user.id])
    services.set_account_role(active_student_user, "coach")
    assert active_student_user.assigned_coaches == []
    assert db.session.query(account_coaches).count() == 0


def test_deleting_coach_removes_assignment(app, db, coach_user, active_student_user):
    services.set_account_coaches(active_student_user, [coach_user.id])
    coach_user.status = "disabled"
    db.session.commit()
    services.delete_account(coach_user)
    assert db.session.query(account_coaches).count() == 0
    assert active_student_user.assigned_coaches == []


def test_pair_card_visible_when_either_account_is_assigned(app, db, coach_user, coach_b):
    student = Student(name="甲、乙", status="active", class_type="one_on_two")
    first = User(username="pair_a", role="student", status="active", name="甲", student=student)
    second = User(username="pair_b", role="student", status="active", name="乙", student=student)
    for u in (first, second):
        u.set_password("StudentPass123")
    db.session.add_all([student, first, second])
    db.session.commit()
    services.set_account_coaches(second, [coach_b.id])
    assert services.can_access_student(coach_b, student)
    assert not services.can_access_student(coach_user, student)
    assert services.visible_students_query(coach_user).filter(Student.id == student.id).count() == 0
    assert services.visible_students_query(coach_b).filter(Student.id == student.id).count() == 1


def test_backfill_sets_coaches_from_class_records(app, db, coach_user, coach_b, active_student_user):
    """REQ-057：依上課紀錄的教練補設所屬教練；只新增不移除、略過停用教練、先檢查再寫入。"""
    retired = User(username="retired", role="coach", status="disabled", name="離職教練")
    retired.set_password(COACH_PASSWORD)
    db.session.add(retired)
    db.session.flush()
    student = active_student_user.student
    for coach in (coach_user, coach_user, retired):
        student.class_records.append(ClassRecord(class_date=date(2026, 2, 1), class_time=time(10, 0), coach_id=coach.id))
    no_class = Student(name="沒上過課", status="active")
    no_class_account = User(username="no_class", role="student", status="active", name="沒上過課", student=no_class)
    no_class_account.set_password("StudentPass123")
    db.session.add_all([no_class, no_class_account])
    db.session.commit()
    services.set_account_coaches(active_student_user, [coach_b.id])

    runner = app.test_cli_runner()
    result = runner.invoke(args=["backfill-account-coaches"])
    assert result.exit_code == 0, result.output
    assert "新增所屬教練 教練A" in result.output
    assert "略過已停用教練 離職教練" in result.output
    assert "共 1 個學生帳號" in result.output
    assert [c.id for c in active_student_user.assigned_coaches] == [coach_b.id]

    result = runner.invoke(args=["backfill-account-coaches", "--commit"])
    assert result.exit_code == 0 and "已寫入" in result.output
    db.session.expire_all()
    account = db.session.get(User, active_student_user.id)
    assert {c.id for c in account.assigned_coaches} == {coach_user.id, coach_b.id}
    assert db.session.get(User, no_class_account.id).assigned_coaches == []

    result = runner.invoke(args=["backfill-account-coaches", "--commit"])
    assert "沒有需要補設的帳號" in result.output
