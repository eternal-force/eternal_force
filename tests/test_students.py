from datetime import date, timedelta

from tests.conftest import get_csrf_token


def create_student(client, **overrides):
    resp = client.get("/students/new")
    token = get_csrf_token(resp.get_data(as_text=True))
    data = {
        "name": "王小明",
        "phone_type": "",
        "phone": "",
        "email": "",
        "birthday": "",
        "gender": "",
        "status": "active",
        "notes": "",
        "csrf_token": token,
    }
    data.update(overrides)
    return client.post("/students/new", data=data, follow_redirects=True)


def test_logo_links_to_student_list(logged_in_client):
    resp = logged_in_client.get("/students/")
    body = resp.get_data(as_text=True)
    assert 'class="app-title" href="/students/"' in body


def test_create_student_requires_name(logged_in_client):
    resp = create_student(logged_in_client, name="")
    assert resp.status_code == 200
    assert "姓名為必填" in resp.get_data(as_text=True)


def test_create_student_success_redirects_to_detail(logged_in_client):
    resp = create_student(logged_in_client, name="王小明")
    body = resp.get_data(as_text=True)
    assert "已建立" in body
    assert "王小明" in body


def test_create_student_rejects_special_characters_in_name(logged_in_client):
    resp = create_student(logged_in_client, name="王小明@!")
    assert resp.status_code == 200
    assert "姓名不能包含特殊符號" in resp.get_data(as_text=True)


def test_new_student_enrollment_date_defaults_to_today_and_is_not_editable(logged_in_client):
    from app.models import Student

    resp = logged_in_client.get("/students/new")
    body = resp.get_data(as_text=True)
    assert "入班/建檔日期" in body
    assert date.today().isoformat() in body
    assert 'name="enrollment_date"' not in body

    forged_date = (date.today() - timedelta(days=30)).isoformat()
    create_student(logged_in_client, name="王小明", enrollment_date=forged_date)
    student = Student.query.filter_by(name="王小明").first()
    assert student.enrollment_date == date.today()


def test_edit_student_cannot_change_enrollment_date(logged_in_client, db):
    from app.models import Student

    create_student(logged_in_client, name="王小明")
    student = Student.query.filter_by(name="王小明").first()
    original_enrollment_date = student.enrollment_date

    resp = logged_in_client.get(f"/students/{student.id}/edit")
    body = resp.get_data(as_text=True)
    assert 'name="enrollment_date"' not in body
    assert original_enrollment_date.isoformat() in body

    token = get_csrf_token(body)
    forged_date = (date.today() - timedelta(days=30)).isoformat()
    logged_in_client.post(
        f"/students/{student.id}/edit",
        data={
            "name": "王小明",
            "phone_type": "",
            "phone": "",
            "email": "",
            "birthday": "",
            "gender": "",
            "status": "active",
            "notes": "",
            "enrollment_date": forged_date,
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    db.session.refresh(student)
    assert student.enrollment_date == original_enrollment_date


def test_create_student_rejects_name_over_20_chars(logged_in_client):
    resp = create_student(logged_in_client, name="a" * 21)
    assert resp.status_code == 200
    assert "姓名不能超過 20 個字" in resp.get_data(as_text=True)


def test_create_student_allows_exactly_20_chars(logged_in_client):
    resp = create_student(logged_in_client, name="a" * 20)
    assert "已建立" in resp.get_data(as_text=True)


def test_create_student_with_landline_shows_landline_label(logged_in_client, db):
    from app.models import Student

    create_student(logged_in_client, phone_type="landline", phone="02-12345678")
    student = Student.query.filter_by(name="王小明").first()
    assert student.phone_type == "landline"

    body = logged_in_client.get(f"/students/{student.id}").get_data(as_text=True)
    assert "市話：02-12345678" in body
    assert "手機：02-12345678" not in body


def test_create_student_with_mobile_shows_mobile_label(logged_in_client, db):
    from app.models import Student

    create_student(logged_in_client, phone_type="mobile", phone="0912345678")
    student = Student.query.filter_by(name="王小明").first()
    assert student.phone_type == "mobile"

    body = logged_in_client.get(f"/students/{student.id}").get_data(as_text=True)
    assert "手機：0912345678" in body


def test_create_student_phone_requires_matching_format(logged_in_client):
    resp = create_student(logged_in_client, phone_type="mobile", phone="02-12345678")
    assert "手機格式不正確" in resp.get_data(as_text=True)


def test_edit_student_phone_type_updates_detail_label(logged_in_client, db):
    from app.models import Student

    create_student(logged_in_client, phone_type="mobile", phone="0912345678")
    student = Student.query.filter_by(name="王小明").first()

    edit_page = logged_in_client.get(f"/students/{student.id}/edit")
    token = get_csrf_token(edit_page.get_data(as_text=True))
    logged_in_client.post(
        f"/students/{student.id}/edit",
        data={
            "name": "王小明",
            "phone_type": "landline",
            "phone": "02-12345678",
            "email": "",
            "birthday": "",
            "gender": "",
            "enrollment_date": "",
            "status": "active",
            "notes": "",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    db.session.refresh(student)
    assert student.phone_type == "landline"
    body = logged_in_client.get(f"/students/{student.id}").get_data(as_text=True)
    assert "市話：02-12345678" in body


def test_student_list_heading_is_hidden(logged_in_client):
    resp = logged_in_client.get("/students/")
    body = resp.get_data(as_text=True)
    assert "<h2" not in body


def test_student_list_hides_add_student_button(logged_in_client):
    create_student(logged_in_client, name="王小明")
    resp = logged_in_client.get("/students/")
    body = resp.get_data(as_text=True)
    assert "+ 新增學生" not in body
    assert "王小明" in body


def test_student_list_filter_bar_is_collapsible_and_collapsed_by_default(logged_in_client):
    resp = logged_in_client.get("/students/")
    body = resp.get_data(as_text=True)
    assert '<details class="card">' in body
    assert '<details class="card" open>' not in body
    assert 'name="search"' in body
    assert 'name="status"' in body


def test_student_detail_shows_goal_label_without_duplicate_prefix(logged_in_client, db):
    from app.models import Student

    create_student(logged_in_client, notes="增肌減脂")
    student = Student.query.filter_by(name="王小明").first()

    body = logged_in_client.get(f"/students/{student.id}").get_data(as_text=True)
    assert "期望運動達成的效益：增肌減脂" in body
    assert "備註" not in body
    assert body.count("期望運動達成") == 1


def test_registration_goal_becomes_student_notes_without_prefix(client, db, admin_user):
    from app.models import Student, User
    from tests.conftest import login

    resp = client.get("/register")
    token = get_csrf_token(resp.get_data(as_text=True))
    client.post(
        "/register",
        data={
            "username": "goal_student",
            "password": "GoalStudent123",
            "confirm_password": "GoalStudent123",
            "name": "目標學生",
            "email": "goal_student@example.com",
            "phone_type": "landline",
            "phone": "02-12345678",
            "birthday": "2001-01-01",
            "gender": "female",
            "goal": "增肌",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    login(client)
    user = User.query.filter_by(username="goal_student").first()
    token = get_csrf_token(client.get("/accounts/").get_data(as_text=True))
    client.post(f"/accounts/{user.id}/verify", data={"csrf_token": token}, follow_redirects=True)

    student = db.session.get(Student, user.student_id)
    assert student.notes == "增肌"
    assert student.phone_type == "landline"
    assert student.email == "goal_student@example.com"

    body = client.get(f"/students/{student.id}").get_data(as_text=True)
    assert "期望運動達成的效益：增肌" in body
    assert "市話：02-12345678" in body

    edit_page = client.get(f"/students/{student.id}/edit").get_data(as_text=True)
    assert "goal_student@example.com" in edit_page
    assert "信箱" in edit_page


def test_student_list_search_and_status_filter(logged_in_client):
    create_student(logged_in_client, name="王小明")
    create_student(logged_in_client, name="陳小華")

    resp = logged_in_client.get("/students/?search=小明")
    body = resp.get_data(as_text=True)
    assert "王小明" in body
    assert "陳小華" not in body

    resp = logged_in_client.get("/students/?status=inactive")
    body = resp.get_data(as_text=True)
    assert "王小明" not in body
    assert "陳小華" not in body


def test_student_detail_shows_summary_and_record_links(logged_in_client):
    create_student(logged_in_client, name="王小明")
    from app.models import Student

    student = Student.query.filter_by(name="王小明").first()

    resp = logged_in_client.get(f"/students/{student.id}")
    body = resp.get_data(as_text=True)
    assert "剩餘堂數" in body
    assert "新增購買紀錄" in body
    assert "新增上課紀錄" in body


def test_student_card_shows_low_remaining_warning_when_below_five(logged_in_client, db):
    create_student(logged_in_client, name="王小明")
    from app.models import Student

    student = Student.query.filter_by(name="王小明").first()

    resp = logged_in_client.get("/students/")
    body = resp.get_data(as_text=True)
    assert student.remaining < 5
    assert "剩餘堂數不足 5 堂，請提醒教練安排續購" in body


def test_student_card_hides_low_remaining_warning_when_enough_remaining(logged_in_client, db):
    from datetime import date

    from app.models import PurchaseRecord, Student

    create_student(logged_in_client, name="王小明")
    student = Student.query.filter_by(name="王小明").first()
    db.session.add(
        PurchaseRecord(student_id=student.id, purchase_date=date(2026, 1, 1), quantity=10)
    )
    db.session.commit()

    resp = logged_in_client.get("/students/")
    body = resp.get_data(as_text=True)
    assert "剩餘堂數不足 5 堂" not in body


def _toggle_status(client, student_id):
    detail = client.get(f"/students/{student_id}")
    token = get_csrf_token(detail.get_data(as_text=True))
    return client.post(f"/students/{student_id}/status", data={"csrf_token": token}, follow_redirects=True)


def test_toggle_status_deactivate_and_reactivate(logged_in_client, db):
    create_student(logged_in_client, name="王小明")
    from app.models import Student

    student = Student.query.filter_by(name="王小明").first()
    assert student.status == "active"

    resp = _toggle_status(logged_in_client, student.id)
    db.session.refresh(student)
    assert student.status == "inactive"
    assert "已停用" in resp.get_data(as_text=True)

    # 軟刪除保留歷史紀錄:學生本身仍然存在,只是狀態變成 inactive
    assert db.session.get(Student, student.id) is not None

    resp = _toggle_status(logged_in_client, student.id)
    db.session.refresh(student)
    assert student.status == "active"
    assert "已重新啟用" in resp.get_data(as_text=True)


def test_reactivating_student_reactivates_linked_account(logged_in_client, active_student_user, db):
    from app import services
    from app.models import Student

    student = db.session.get(Student, active_student_user.student_id)

    # 模擬帳號管理頁停用帳號：依既有規則(REQ-004)連動把學生名冊改為停用
    services.set_account_status(active_student_user, "disabled")
    db.session.refresh(student)
    assert student.status == "inactive"
    assert active_student_user.status == "disabled"

    _toggle_status(logged_in_client, student.id)
    db.session.refresh(student)
    db.session.refresh(active_student_user)
    assert student.status == "active"
    assert active_student_user.status == "active"


def test_deactivating_student_deactivates_linked_account(logged_in_client, active_student_user, db):
    from app.models import Student

    student = db.session.get(Student, active_student_user.student_id)
    assert student.status == "active"
    assert active_student_user.status == "active"

    _toggle_status(logged_in_client, student.id)
    db.session.refresh(student)
    db.session.refresh(active_student_user)
    assert student.status == "inactive"
    assert active_student_user.status == "disabled"


def test_student_role_list_redirects_to_own_detail(student_client, active_student_user):
    resp = student_client.get("/students/", follow_redirects=False)
    assert resp.status_code == 302
    assert f"/students/{active_student_user.student_id}" in resp.headers["Location"]


def test_student_role_does_not_see_back_to_list_link(student_client, active_student_user):
    resp = student_client.get(f"/students/{active_student_user.student_id}")
    body = resp.get_data(as_text=True)
    assert "回學生列表" not in body


def test_admin_sees_back_to_list_link(logged_in_client, db):
    create_student(logged_in_client, name="王小明")
    from app.models import Student

    student = Student.query.filter_by(name="王小明").first()
    assert "回學生列表" in logged_in_client.get(f"/students/{student.id}").get_data(as_text=True)


def test_coach_sees_back_to_list_link(coach_client, db):
    from app import services

    student = services.create_student({"name": "王小明", "status": "active"})
    assert "回學生列表" in coach_client.get(f"/students/{student.id}").get_data(as_text=True)


def test_admin_sees_deactivate_and_reactivate_button_on_student_detail(logged_in_client, db):
    from app import services

    student = services.create_student({"name": "王小明", "status": "active"})

    body = logged_in_client.get(f"/students/{student.id}").get_data(as_text=True)
    assert ">停用<" in body

    services.set_student_status(student, "inactive")
    db.session.refresh(student)

    body = logged_in_client.get(f"/students/{student.id}").get_data(as_text=True)
    assert ">重新啟用<" in body


def test_coach_does_not_see_deactivate_button_but_sees_reactivate(coach_client, db):
    from app import services

    student = services.create_student({"name": "王小明", "status": "active"})

    body = coach_client.get(f"/students/{student.id}").get_data(as_text=True)
    assert ">停用<" not in body

    services.set_student_status(student, "inactive")
    db.session.refresh(student)
    assert student.status == "inactive"

    body = coach_client.get(f"/students/{student.id}").get_data(as_text=True)
    assert ">重新啟用<" in body


def test_student_card_shows_linked_account_username(logged_in_client, active_student_user, db):
    resp = logged_in_client.get("/students/")
    body = resp.get_data(as_text=True)
    assert active_student_user.username in body


def test_student_detail_shows_labeled_phone_and_account(logged_in_client, active_student_user, db):
    resp = logged_in_client.get(f"/students/{active_student_user.student_id}")
    body = resp.get_data(as_text=True)
    assert f"手機：{active_student_user.phone}" in body
    assert f"帳號：{active_student_user.username}" in body


def test_student_detail_shows_account_email_phone_in_order(logged_in_client, active_student_user, db):
    from app.models import Student

    student = db.session.get(Student, active_student_user.student_id)
    student.email = "student@example.com"
    db.session.commit()

    body = logged_in_client.get(f"/students/{student.id}").get_data(as_text=True)
    assert f"信箱：{student.email}" in body

    account_pos = body.find(f"帳號：{active_student_user.username}")
    email_pos = body.find(f"信箱：{student.email}")
    phone_pos = body.find(f"手機：{student.phone}")
    assert -1 < account_pos < email_pos < phone_pos


def test_update_student_name_syncs_linked_account_name(logged_in_client, active_student_user, db):
    from app.models import Student

    student = db.session.get(Student, active_student_user.student_id)

    edit_page = logged_in_client.get(f"/students/{student.id}/edit")
    token = get_csrf_token(edit_page.get_data(as_text=True))
    logged_in_client.post(
        f"/students/{student.id}/edit",
        data={
            "name": "李小華新名字",
            "phone_type": "mobile",
            "phone": student.phone or "",
            "email": "",
            "birthday": "",
            "gender": "",
            "enrollment_date": "",
            "status": "active",
            "notes": "",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    db.session.refresh(student)
    db.session.refresh(active_student_user)
    assert student.name == "李小華新名字"
    assert active_student_user.name == "李小華新名字"

    account_page = logged_in_client.get(f"/accounts/{active_student_user.id}")
    assert "李小華新名字" in account_page.get_data(as_text=True)


def test_update_student_email_and_phone_sync_linked_account(logged_in_client, active_student_user, db):
    from app.models import Student

    student = db.session.get(Student, active_student_user.student_id)

    edit_page = logged_in_client.get(f"/students/{student.id}/edit")
    token = get_csrf_token(edit_page.get_data(as_text=True))
    logged_in_client.post(
        f"/students/{student.id}/edit",
        data={
            "name": student.name,
            "phone_type": "landline",
            "phone": "02-12345678",
            "email": "new-mail@example.com",
            "birthday": "",
            "gender": "",
            "enrollment_date": "",
            "status": "active",
            "notes": "",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    db.session.refresh(student)
    db.session.refresh(active_student_user)
    assert student.email == "new-mail@example.com"
    assert active_student_user.email == "new-mail@example.com"
    assert student.phone == active_student_user.phone == "02-12345678"
    assert student.phone_type == active_student_user.phone_type == "landline"

    account_body = logged_in_client.get(f"/accounts/{active_student_user.id}").get_data(as_text=True)
    assert "new-mail@example.com" in account_body
    assert "02-12345678" in account_body


def test_student_role_cannot_view_other_students_detail(student_client, db):
    from app.models import Student

    other = Student(name="其他學生", status="active")
    db.session.add(other)
    db.session.commit()

    resp = student_client.get(f"/students/{other.id}")
    assert resp.status_code == 403


def test_student_role_gets_403_on_admin_routes(student_client, active_student_user):
    assert student_client.get("/students/new").status_code == 403

    own_page = student_client.get(f"/students/{active_student_user.student_id}")
    token = get_csrf_token(own_page.get_data(as_text=True))
    resp = student_client.post(
        f"/students/{active_student_user.student_id}/status", data={"csrf_token": token}
    )
    assert resp.status_code == 403


def test_student_role_can_edit_own_student_data_but_not_status(student_client, active_student_user, db):
    from app.models import Student

    edit_page = student_client.get(f"/students/{active_student_user.student_id}/edit")
    assert edit_page.status_code == 200
    body = edit_page.get_data(as_text=True)
    # 在籍狀態不應以可編輯的下拉選單呈現給學生本人，但仍需以隱藏欄位帶出現值供表單驗證
    assert 'id="status"' not in body
    assert 'name="status" value="active"' in body

    token = get_csrf_token(body)
    resp = student_client.post(
        f"/students/{active_student_user.student_id}/edit",
        data={
            "name": "李小華",
            "phone_type": "mobile",
            "phone": "0955555555",
            "email": "changed@example.com",
            "status": "inactive",  # 竄改嘗試：學生不應能透過此欄位變更在籍狀態
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    student = db.session.get(Student, active_student_user.student_id)
    assert student.phone == "0955555555"
    assert student.email == "changed@example.com"
    assert student.status == "active"


def test_student_role_cannot_edit_other_students_data(student_client, db):
    from app.models import Student

    other = Student(name="其他學生", status="active")
    db.session.add(other)
    db.session.commit()

    assert student_client.get(f"/students/{other.id}/edit").status_code == 403


def test_coach_has_same_access_as_admin(coach_client):
    resp = create_student(coach_client, name="教練建立的學生")
    assert "已建立" in resp.get_data(as_text=True)
