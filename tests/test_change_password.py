from app import services
from app.models import User
from tests.conftest import (
    ACTIVE_STUDENT_PASSWORD,
    ACTIVE_STUDENT_USERNAME,
    get_csrf_token,
    login,
)


def _flag(db, username):
    user = User.query.filter_by(username=username).one()
    user.must_change_password = True
    db.session.commit()
    return user


def _change(client, current, new, confirm=None):
    resp = client.get("/change-password")
    token = get_csrf_token(resp.get_data(as_text=True))
    return client.post(
        "/change-password",
        data={
            "current_password": current,
            "new_password": new,
            "confirm_password": confirm if confirm is not None else new,
            "csrf_token": token,
        },
        follow_redirects=True,
    )


def test_flagged_user_is_sent_to_change_password_after_login(client, db, active_student_user):
    _flag(db, ACTIVE_STUDENT_USERNAME)
    resp = login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD)
    html = resp.get_data(as_text=True)
    assert "首次登入請先修改密碼" in html
    assert 'name="current_password"' in html


def test_flagged_user_cannot_reach_other_pages_or_api(client, db, active_student_user):
    _flag(db, ACTIVE_STUDENT_USERNAME)
    login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD)

    resp = client.get(f"/students/{active_student_user.student_id}")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/change-password")
    resp = client.get(f"/api/students/{active_student_user.student_id}")
    assert resp.status_code == 403 and resp.get_json()["error"] == "請先修改密碼"


def test_changing_password_clears_flag_and_unlocks_pages(client, db, active_student_user):
    _flag(db, ACTIVE_STUDENT_USERNAME)
    login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD)

    resp = _change(client, ACTIVE_STUDENT_PASSWORD, "BrandNew456")
    assert "密碼已更新" in resp.get_data(as_text=True)
    user = db.session.get(User, active_student_user.id)
    assert user.must_change_password is False
    assert user.check_password("BrandNew456")
    assert client.get(f"/students/{active_student_user.student_id}").status_code == 200


def test_change_password_rejects_bad_input(client, db, active_student_user):
    _flag(db, ACTIVE_STUDENT_USERNAME)
    login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD)

    assert "目前密碼不正確" in _change(client, "wrong-password", "BrandNew456").get_data(as_text=True)
    assert "不可與目前密碼相同" in _change(
        client, ACTIVE_STUDENT_PASSWORD, ACTIVE_STUDENT_PASSWORD
    ).get_data(as_text=True)
    assert "至少需 8 碼" in _change(client, ACTIVE_STUDENT_PASSWORD, "short").get_data(as_text=True)
    assert "不一致" in _change(client, ACTIVE_STUDENT_PASSWORD, "BrandNew456", "Other456789").get_data(
        as_text=True
    )
    user = db.session.get(User, active_student_user.id)
    assert user.must_change_password is True
    assert user.check_password(ACTIVE_STUDENT_PASSWORD)


def test_unflagged_user_logs_in_normally_and_can_change_voluntarily(client, db, active_student_user):
    resp = login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD)
    assert "登入成功" in resp.get_data(as_text=True)
    assert "修改密碼" in resp.get_data(as_text=True)
    _change(client, ACTIVE_STUDENT_PASSWORD, "BrandNew456")
    assert db.session.get(User, active_student_user.id).check_password("BrandNew456")


def test_admin_reset_and_new_coach_require_change(app, db, active_student_user):
    services.set_account_password(active_student_user, "ResetPass123")
    assert active_student_user.must_change_password is True

    coach = services.create_coach_account(
        {"username": "coach_new", "password": "CoachPass123", "name": "新教練", "phone": None, "phone_type": None}
    )
    assert coach.must_change_password is True


def test_self_registration_does_not_require_change(app, db):
    user = services.register_student_account(
        {
            "username": "selfreg",
            "password": "MyOwnPass123",
            "name": "自己註冊",
            "phone": "0912345678",
            "phone_type": "mobile",
        }
    )
    assert user.must_change_password is False
