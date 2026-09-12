from tests.conftest import get_csrf_token


def create_student(client, **overrides):
    resp = client.get("/students/new")
    token = get_csrf_token(resp.get_data(as_text=True))
    data = {
        "name": "王小明",
        "phone": "",
        "email": "",
        "birthday": "",
        "gender": "",
        "enrollment_date": "",
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


def test_toggle_status_deactivate_and_reactivate(logged_in_client, db):
    create_student(logged_in_client, name="王小明")
    from app.models import Student

    student = Student.query.filter_by(name="王小明").first()
    assert student.status == "active"

    detail = logged_in_client.get(f"/students/{student.id}")
    token = get_csrf_token(detail.get_data(as_text=True))

    resp = logged_in_client.post(
        f"/students/{student.id}/status", data={"csrf_token": token}, follow_redirects=True
    )
    db.session.refresh(student)
    assert student.status == "inactive"
    assert "已停用" in resp.get_data(as_text=True)

    # 軟刪除保留歷史紀錄:學生本身仍然存在,只是狀態變成 inactive
    assert db.session.get(Student, student.id) is not None

    detail = logged_in_client.get(f"/students/{student.id}")
    token = get_csrf_token(detail.get_data(as_text=True))
    resp = logged_in_client.post(
        f"/students/{student.id}/status", data={"csrf_token": token}, follow_redirects=True
    )
    db.session.refresh(student)
    assert student.status == "active"
    assert "已重新啟用" in resp.get_data(as_text=True)


def test_student_role_list_redirects_to_own_detail(student_client, active_student_user):
    resp = student_client.get("/students/", follow_redirects=False)
    assert resp.status_code == 302
    assert f"/students/{active_student_user.student_id}" in resp.headers["Location"]


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
