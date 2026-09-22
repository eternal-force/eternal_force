from datetime import date

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


def test_accounts_list_filter_bar_is_collapsible_and_collapsed_by_default(logged_in_client):
    resp = logged_in_client.get("/accounts/")
    body = resp.get_data(as_text=True)
    assert '<details class="card">' in body
    assert '<details class="card" open>' not in body
    assert 'name="search"' in body


def test_accounts_list_search_by_username_or_name(logged_in_client, pending_student_user, coach_user):
    resp = logged_in_client.get("/accounts/", query_string={"search": pending_student_user.name})
    body = resp.get_data(as_text=True)
    assert pending_student_user.username in body
    assert coach_user.username not in body

    resp = logged_in_client.get("/accounts/", query_string={"search": coach_user.username})
    body = resp.get_data(as_text=True)
    assert coach_user.username in body
    assert pending_student_user.username not in body


def test_accounts_list_role_filter(logged_in_client, pending_student_user, coach_user):
    resp = logged_in_client.get("/accounts/")
    body = resp.get_data(as_text=True)
    assert pending_student_user.username in body
    assert coach_user.username in body

    resp = logged_in_client.get("/accounts/", query_string={"role": "coach"})
    body = resp.get_data(as_text=True)
    assert coach_user.username in body
    assert pending_student_user.username not in body

    resp = logged_in_client.get("/accounts/", query_string={"role": "student"})
    body = resp.get_data(as_text=True)
    assert pending_student_user.username in body
    assert coach_user.username not in body


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
    assert student.enrollment_date == date.today()


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
    assert student.enrollment_date == date.today()


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


def test_reactivating_account_reactivates_linked_student(logged_in_client, active_student_user, db):
    student = db.session.get(Student, active_student_user.student_id)

    resp = logged_in_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))

    logged_in_client.post(
        f"/accounts/{active_student_user.id}/status",
        data={"target_status": "disabled", "csrf_token": token},
    )
    db.session.refresh(student)
    assert student.status == "inactive"

    logged_in_client.post(
        f"/accounts/{active_student_user.id}/status",
        data={"target_status": "active", "csrf_token": token},
    )
    db.session.refresh(student)
    assert student.status == "active"


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


def test_switching_coach_to_student_creates_missing_student_roster(logged_in_client, coach_user, db):
    assert coach_user.student_id is None

    resp = logged_in_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        f"/accounts/{coach_user.id}/role",
        data={"target_role": "student", "csrf_token": token},
    )

    db.session.refresh(coach_user)
    assert coach_user.role == "student"
    assert coach_user.student_id is not None
    assert coach_user.student.name == coach_user.name
    assert coach_user.student.status == "active"


def test_switching_coach_to_student_keeps_existing_student_roster(
    logged_in_client, active_student_user, db
):
    existing_student_id = active_student_user.student_id
    active_student_user.role = "coach"
    db.session.commit()

    resp = logged_in_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        f"/accounts/{active_student_user.id}/role",
        data={"target_role": "student", "csrf_token": token},
    )

    db.session.refresh(active_student_user)
    assert active_student_user.role == "student"
    assert active_student_user.student_id == existing_student_id


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


def test_coach_sees_deactivate_button_for_student_in_accounts_list(coach_client, active_student_user):
    body = coach_client.get("/accounts/").get_data(as_text=True)
    assert ">停用<" in body


def test_coach_does_not_see_deactivate_button_for_coach_in_accounts_list(coach_client, db):
    other_coach = User(username="coach2", role="coach", status="active", name="教練B")
    other_coach.set_password("OtherCoach123")
    db.session.add(other_coach)
    db.session.commit()

    body = coach_client.get("/accounts/").get_data(as_text=True)
    assert ">停用<" not in body


def test_admin_sees_deactivate_button_in_accounts_list(logged_in_client, active_student_user):
    body = logged_in_client.get("/accounts/").get_data(as_text=True)
    assert ">停用<" in body


def test_coach_can_change_student_account_status(coach_client, active_student_user, db):
    resp = coach_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))

    coach_client.post(
        f"/accounts/{active_student_user.id}/status",
        data={"target_status": "disabled", "csrf_token": token},
    )
    db.session.refresh(active_student_user)
    assert active_student_user.status == "disabled"

    coach_client.post(
        f"/accounts/{active_student_user.id}/status",
        data={"target_status": "active", "csrf_token": token},
    )
    db.session.refresh(active_student_user)
    assert active_student_user.status == "active"


def test_coach_cannot_change_coach_account_status(coach_client, db):
    other_coach = User(username="coach2", role="coach", status="active", name="教練B")
    other_coach.set_password("OtherCoach123")
    db.session.add(other_coach)
    db.session.commit()

    resp = coach_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))
    resp = coach_client.post(
        f"/accounts/{other_coach.id}/status",
        data={"target_status": "disabled", "csrf_token": token},
    )
    assert resp.status_code == 403

    db.session.refresh(other_coach)
    assert other_coach.status == "active"


def test_coach_cannot_change_admin_account_status(coach_client, admin_user, db):
    resp = coach_client.get("/accounts/")
    token = get_csrf_token(resp.get_data(as_text=True))
    resp = coach_client.post(
        f"/accounts/{admin_user.id}/status",
        data={"target_status": "disabled", "csrf_token": token},
    )
    assert resp.status_code == 403

    db.session.refresh(admin_user)
    assert admin_user.status == "active"


def test_new_coach_stores_email_and_shown_on_detail_page(logged_in_client, db):
    resp = logged_in_client.get("/accounts/new-coach")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        "/accounts/new-coach",
        data={
            "username": "coach_with_email",
            "password": "NewCoach123",
            "name": "新教練",
            "email": "coach@example.com",
            "phone_type": "mobile",
            "phone": "0955555555",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    coach = User.query.filter_by(username="coach_with_email").first()
    assert coach.email == "coach@example.com"

    detail = logged_in_client.get(f"/accounts/{coach.id}")
    assert "coach@example.com" in detail.get_data(as_text=True)


def test_new_coach_duplicate_username_case_insensitive_rejected(logged_in_client, active_student_user):
    resp = logged_in_client.get("/accounts/new-coach")
    token = get_csrf_token(resp.get_data(as_text=True))
    resp = logged_in_client.post(
        "/accounts/new-coach",
        data={
            "username": active_student_user.username.upper(),
            "password": "NewCoach123",
            "name": "新教練",
            "csrf_token": token,
        },
    )
    assert "此帳號已被使用" in resp.get_data(as_text=True)


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
