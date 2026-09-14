from app.models import User
from tests.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    PENDING_STUDENT_PASSWORD,
    PENDING_STUDENT_USERNAME,
    get_csrf_token,
    login,
)


def test_unauthenticated_request_redirects_to_login(client):
    resp = client.get("/students/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_with_wrong_password_fails(client, admin_user):
    resp = client.get("/login")
    token = get_csrf_token(resp.get_data(as_text=True))
    resp = client.post(
        "/login",
        data={"username": ADMIN_USERNAME, "password": "wrong-password", "csrf_token": token},
        follow_redirects=True,
    )
    assert "帳號或密碼錯誤" in resp.get_data(as_text=True)


def test_login_success_then_logout(client, admin_user):
    resp = login(client)
    assert resp.status_code == 200
    assert "登入成功" in resp.get_data(as_text=True)

    students_page = client.get("/students/")
    assert students_page.status_code == 200

    home = client.get("/students/")
    token = get_csrf_token(home.get_data(as_text=True))
    resp = client.post("/logout", data={"csrf_token": token}, follow_redirects=True)
    assert "已登出" in resp.get_data(as_text=True)

    resp = client.get("/students/", follow_redirects=False)
    assert resp.status_code == 302


def test_api_unauthenticated_returns_json_401(client):
    resp = client.get("/api/students")
    assert resp.status_code == 401
    assert resp.get_json()["error"]


def _register(client, **overrides):
    resp = client.get("/register")
    token = get_csrf_token(resp.get_data(as_text=True))
    data = {
        "username": "new_student",
        "password": "NewStudent123",
        "confirm_password": "NewStudent123",
        "name": "新學生",
        "phone_type": "mobile",
        "phone": "0933333333",
        "birthday": "2001-01-01",
        "gender": "female",
        "goal": "減脂",
        "csrf_token": token,
    }
    data.update(overrides)
    return client.post("/register", data=data, follow_redirects=True)


def test_register_creates_pending_student_account(client, db):
    resp = _register(client)
    assert "請等候管理者驗證" in resp.get_data(as_text=True)

    user = User.query.filter_by(username="new_student").first()
    assert user is not None
    assert user.role == "student"
    assert user.status == "pending"


def test_register_duplicate_username_rejected(client, admin_user):
    resp = _register(client, username=ADMIN_USERNAME)
    assert "此帳號已被使用" in resp.get_data(as_text=True)


def test_register_duplicate_username_case_insensitive_rejected(client, admin_user):
    resp = _register(client, username=ADMIN_USERNAME.upper())
    assert "此帳號已被使用" in resp.get_data(as_text=True)
    assert User.query.filter_by(username=ADMIN_USERNAME.upper()).first() is None


def test_register_stores_email(client, db):
    _register(client, email="student@example.com")
    user = User.query.filter_by(username="new_student").first()
    assert user.email == "student@example.com"


def test_login_with_pending_account_is_refused(client, pending_student_user):
    resp = login(client, PENDING_STUDENT_USERNAME, PENDING_STUDENT_PASSWORD)
    assert "尚待管理者驗證" in resp.get_data(as_text=True)

    resp = client.get("/students/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_with_disabled_account_is_refused(client, db, pending_student_user):
    pending_student_user.status = "disabled"
    db.session.commit()
    resp = login(client, PENDING_STUDENT_USERNAME, PENDING_STUDENT_PASSWORD)
    assert "已被停用" in resp.get_data(as_text=True)
