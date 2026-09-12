from app.models import Student, User
from tests.conftest import get_csrf_token, login


def test_student_role_gets_403_on_accounts_routes(student_client, active_student_user):
    assert student_client.get("/accounts/").status_code == 403
    assert student_client.get("/accounts/new-coach").status_code == 403

    own_page = student_client.get(f"/students/{active_student_user.student_id}")
    token = get_csrf_token(own_page.get_data(as_text=True))
    resp = student_client.post(f"/accounts/{active_student_user.id}/verify", data={"csrf_token": token})
    assert resp.status_code == 403


def test_admin_sees_pending_account_in_list(logged_in_client, pending_student_user):
    resp = logged_in_client.get("/accounts/")
    assert resp.status_code == 200
    assert pending_student_user.username in resp.get_data(as_text=True)


def test_accounts_list_search_by_username_or_name(logged_in_client, pending_student_user, coach_user):
    resp = logged_in_client.get("/accounts/", query_string={"search": pending_student_user.name})
    body = resp.get_data(as_text=True)
    assert pending_student_user.username in body
    assert coach_user.username not in body

    resp = logged_in_client.get("/accounts/", query_string={"search": coach_user.username})
    body = resp.get_data(as_text=True)
    assert coach_user.username in body
    assert pending_student_user.username not in body


def test_view_account_shows_profile_details(logged_in_client, pending_student_user):
    resp = logged_in_client.get(f"/accounts/{pending_student_user.id}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert pending_student_user.username in body
    assert pending_student_user.phone in body
    assert "增肌" in body


def test_nav_shows_pending_badge_for_admin(logged_in_client, pending_student_user):
    resp = logged_in_client.get("/students/")
    body = resp.get_data(as_text=True)
    assert "nav-badge" in body
    assert ">1<" in body


def test_nav_hides_pending_badge_when_no_pending_accounts(logged_in_client):
    resp = logged_in_client.get("/students/")
    assert "nav-badge" not in resp.get_data(as_text=True)


def test_verify_activates_account_and_creates_linked_student(logged_in_client, pending_student_user, db):
    resp = logged_in_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))
    resp = logged_in_client.post(
        f"/accounts/{pending_student_user.id}/verify",
        data={"csrf_token": token},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    db.session.refresh(pending_student_user)
    assert pending_student_user.status == "active"
    assert pending_student_user.student_id is not None

    student = db.session.get(Student, pending_student_user.student_id)
    assert student.name == pending_student_user.name
    assert student.phone == pending_student_user.phone
    assert "增肌" in (student.notes or "")


def test_verify_is_idempotent(logged_in_client, pending_student_user, db):
    resp = logged_in_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))

    logged_in_client.post(f"/accounts/{pending_student_user.id}/verify", data={"csrf_token": token})
    logged_in_client.post(f"/accounts/{pending_student_user.id}/verify", data={"csrf_token": token})

    assert Student.query.count() == 1


def test_reject_then_reactivate_rebinds_student(logged_in_client, pending_student_user, db):
    resp = logged_in_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))

    logged_in_client.post(
        f"/accounts/{pending_student_user.id}/status",
        data={"target_status": "disabled", "csrf_token": token},
    )
    db.session.refresh(pending_student_user)
    assert pending_student_user.status == "disabled"
    assert pending_student_user.student_id is None

    logged_in_client.post(
        f"/accounts/{pending_student_user.id}/status",
        data={"target_status": "active", "csrf_token": token},
    )
    db.session.refresh(pending_student_user)
    assert pending_student_user.status == "active"
    assert pending_student_user.student_id is not None

    student = db.session.get(Student, pending_student_user.student_id)
    assert student.name == pending_student_user.name
    assert student.status == "active"


def test_status_toggle_both_directions(logged_in_client, active_student_user, db):
    resp = logged_in_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))

    logged_in_client.post(
        f"/accounts/{active_student_user.id}/status",
        data={"target_status": "disabled", "csrf_token": token},
    )
    db.session.refresh(active_student_user)
    assert active_student_user.status == "disabled"

    logged_in_client.post(
        f"/accounts/{active_student_user.id}/status",
        data={"target_status": "active", "csrf_token": token},
    )
    db.session.refresh(active_student_user)
    assert active_student_user.status == "active"


def test_admin_account_cannot_have_status_changed(logged_in_client, db):
    other_admin = User(username="admin2", role="admin", status="active")
    other_admin.set_password("OtherAdmin123")
    db.session.add(other_admin)
    db.session.commit()

    resp = logged_in_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        f"/accounts/{other_admin.id}/status",
        data={"target_status": "disabled", "csrf_token": token},
    )

    db.session.refresh(other_admin)
    assert other_admin.status == "active"


def test_admin_can_promote_student_to_coach_and_back(logged_in_client, active_student_user, db):
    resp = logged_in_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))

    logged_in_client.post(
        f"/accounts/{active_student_user.id}/role",
        data={"target_role": "coach", "csrf_token": token},
    )
    db.session.refresh(active_student_user)
    assert active_student_user.role == "coach"

    logged_in_client.post(
        f"/accounts/{active_student_user.id}/role",
        data={"target_role": "student", "csrf_token": token},
    )
    db.session.refresh(active_student_user)
    assert active_student_user.role == "student"


def test_admin_account_role_cannot_be_changed(logged_in_client, db):
    other_admin = User(username="admin2", role="admin", status="active")
    other_admin.set_password("OtherAdmin123")
    db.session.add(other_admin)
    db.session.commit()

    resp = logged_in_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        f"/accounts/{other_admin.id}/role",
        data={"target_role": "coach", "csrf_token": token},
    )

    db.session.refresh(other_admin)
    assert other_admin.role == "admin"


def test_invalid_role_value_is_rejected(logged_in_client, active_student_user, db):
    resp = logged_in_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        f"/accounts/{active_student_user.id}/role",
        data={"target_role": "admin", "csrf_token": token},
    )

    db.session.refresh(active_student_user)
    assert active_student_user.role == "student"


def test_coach_cannot_change_account_role(coach_client, active_student_user):
    own_page = coach_client.get(f"/students/{active_student_user.student_id}")
    token = get_csrf_token(own_page.get_data(as_text=True))
    resp = coach_client.post(
        f"/accounts/{active_student_user.id}/role",
        data={"target_role": "coach", "csrf_token": token},
    )
    assert resp.status_code == 403


def test_new_coach_is_active_immediately_without_verification(logged_in_client, db):
    resp = logged_in_client.get("/accounts/new-coach")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        "/accounts/new-coach",
        data={
            "username": "new_coach",
            "password": "NewCoach123",
            "name": "新教練",
            "phone_type": "mobile",
            "phone": "0955555555",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    coach = User.query.filter_by(username="new_coach").first()
    assert coach is not None
    assert coach.role == "coach"
    assert coach.status == "active"

    # 同一個 client 先登出管理者，再直接以新教練帳號登入（不需驗證）
    home = logged_in_client.get("/students/")
    token = get_csrf_token(home.get_data(as_text=True))
    logged_in_client.post("/logout", data={"csrf_token": token}, follow_redirects=True)

    resp = login(logged_in_client, "new_coach", "NewCoach123")
    assert "登入成功" in resp.get_data(as_text=True)
