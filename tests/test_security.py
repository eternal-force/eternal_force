from tests.test_students import create_student


def test_post_without_csrf_token_is_rejected(logged_in_client):
    resp = logged_in_client.post(
        "/students/new",
        data={
            "name": "王小明",
            "phone": "",
            "email": "",
            "birthday": "",
            "gender": "",
            "enrollment_date": "",
            "status": "active",
            "notes": "",
        },
    )
    assert resp.status_code == 400


def test_student_name_with_script_tag_is_rejected(logged_in_client):
    from app.models import Student

    payload = "<script>alert('xss')</script>"
    resp = create_student(logged_in_client, name=payload)

    assert resp.status_code == 200
    assert Student.query.filter_by(name=payload).first() is None


def test_student_notes_is_escaped_in_rendered_html(logged_in_client):
    from app.models import Student

    payload = "<script>alert('xss')</script>"
    create_student(logged_in_client, name="王小明", notes=payload)
    student = Student.query.filter_by(name="王小明").first()

    resp = logged_in_client.get(f"/students/{student.id}")
    body = resp.get_data(as_text=True)

    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_search_with_sql_special_characters_does_not_error(logged_in_client):
    create_student(logged_in_client, name="王小明")

    resp = logged_in_client.get("/students/", query_string={"search": "' OR '1'='1"})
    assert resp.status_code == 200
    assert "王小明" not in resp.get_data(as_text=True)

    resp = logged_in_client.get("/students/", query_string={"search": "%; DROP TABLE students; --"})
    assert resp.status_code == 200


def test_api_json_endpoints_reject_anonymous_access(client):
    resp = client.post("/api/students", json={"name": "王小明"})
    assert resp.status_code == 401


def test_register_without_csrf_token_is_rejected(client):
    resp = client.post(
        "/register",
        data={
            "username": "no_csrf",
            "password": "NoCsrf1234",
            "confirm_password": "NoCsrf1234",
            "name": "無token",
            "phone": "0900000001",
            "birthday": "2000-01-01",
            "gender": "male",
            "goal": "",
        },
    )
    assert resp.status_code == 400


def test_accounts_verify_without_csrf_token_is_rejected(logged_in_client, pending_student_user):
    resp = logged_in_client.post(f"/accounts/{pending_student_user.id}/verify", data={})
    assert resp.status_code == 400


def test_accounts_status_without_csrf_token_is_rejected(logged_in_client, pending_student_user):
    resp = logged_in_client.post(
        f"/accounts/{pending_student_user.id}/status", data={"target_status": "disabled"}
    )
    assert resp.status_code == 400
