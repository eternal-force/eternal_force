import re
from datetime import date

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import Student, User

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "SuperSecret123"

COACH_USERNAME = "coach1"
COACH_PASSWORD = "CoachPass123"

PENDING_STUDENT_USERNAME = "student_pending"
PENDING_STUDENT_PASSWORD = "StudentPass123"

ACTIVE_STUDENT_USERNAME = "student_active"
ACTIVE_STUDENT_PASSWORD = "StudentPass123"

CSRF_RE = re.compile(r'name="csrf_token" type="hidden" value="([^"]+)"')


@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def admin_user(app, db):
    user = User(username=ADMIN_USERNAME, role="admin", status="active")
    user.set_password(ADMIN_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def coach_user(app, db):
    user = User(
        username=COACH_USERNAME,
        role="coach",
        status="active",
        name="教練A",
        phone="0900000000",
    )
    user.set_password(COACH_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def pending_student_user(app, db):
    user = User(
        username=PENDING_STUDENT_USERNAME,
        role="student",
        status="pending",
        name="王小明",
        phone="0912345678",
        birthday=date(2000, 1, 1),
        gender="male",
        goal="增肌",
    )
    user.set_password(PENDING_STUDENT_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def active_student_user(app, db):
    student = Student(
        name="李小華",
        phone="0922222222",
        birthday=date(1999, 5, 5),
        gender="female",
        status="active",
    )
    db.session.add(student)
    db.session.flush()

    user = User(
        username=ACTIVE_STUDENT_USERNAME,
        role="student",
        status="active",
        name=student.name,
        phone=student.phone,
        birthday=student.birthday,
        gender=student.gender,
        student_id=student.id,
    )
    user.set_password(ACTIVE_STUDENT_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def client(app):
    return app.test_client()


def get_csrf_token(html):
    match = CSRF_RE.search(html)
    assert match, "找不到 csrf_token，頁面可能沒有正確渲染表單"
    return match.group(1)


def login(client, username=ADMIN_USERNAME, password=ADMIN_PASSWORD):
    resp = client.get("/login")
    token = get_csrf_token(resp.get_data(as_text=True))
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=True,
    )


@pytest.fixture()
def logged_in_client(client, admin_user):
    login(client)
    return client


@pytest.fixture()
def coach_client(client, coach_user):
    login(client, COACH_USERNAME, COACH_PASSWORD)
    return client


@pytest.fixture()
def student_client(client, active_student_user):
    login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD)
    return client
