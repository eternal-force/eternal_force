from tests.conftest import get_csrf_token
from tests.test_students import create_student


def _student(db, name="王小明"):
    from app.models import Student

    return Student.query.filter_by(name=name).first()


def add_purchase(client, student_id, **overrides):
    resp = client.get(f"/students/{student_id}/purchases/new")
    token = get_csrf_token(resp.get_data(as_text=True))
    data = {
        "purchase_date": "2026-01-01",
        "quantity": "10",
        "price": "",
        "notes": "",
        "csrf_token": token,
    }
    data.update(overrides)
    return client.post(f"/students/{student_id}/purchases/new", data=data, follow_redirects=True)


def test_quantity_must_be_positive_integer(logged_in_client, db):
    create_student(logged_in_client, name="王小明")
    student = _student(db)

    resp = add_purchase(logged_in_client, student.id, quantity="0")
    assert "購買堂數必須是正整數" in resp.get_data(as_text=True)

    resp = add_purchase(logged_in_client, student.id, quantity="-3")
    assert "購買堂數必須是正整數" in resp.get_data(as_text=True)


def test_create_purchase_updates_summary_immediately(logged_in_client, db):
    create_student(logged_in_client, name="王小明")
    student = _student(db)

    add_purchase(logged_in_client, student.id, quantity="10")
    db.session.refresh(student)
    assert student.total_purchased == 10
    assert student.remaining == 10


def test_edit_purchase_recalculates_summary(logged_in_client, db):
    create_student(logged_in_client, name="王小明")
    student = _student(db)
    add_purchase(logged_in_client, student.id, quantity="10")

    from app.models import PurchaseRecord

    record = PurchaseRecord.query.filter_by(student_id=student.id).first()

    resp = logged_in_client.get(f"/purchases/{record.id}/edit")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        f"/purchases/{record.id}/edit",
        data={
            "purchase_date": "2026-01-01",
            "quantity": "20",
            "price": "",
            "notes": "更正堂數",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    db.session.refresh(student)
    assert student.total_purchased == 20


def test_delete_purchase_recalculates_summary(logged_in_client, db):
    create_student(logged_in_client, name="王小明")
    student = _student(db)
    add_purchase(logged_in_client, student.id, quantity="10")

    from app.models import PurchaseRecord

    record = PurchaseRecord.query.filter_by(student_id=student.id).first()

    detail = logged_in_client.get(f"/students/{student.id}")
    token = get_csrf_token(detail.get_data(as_text=True))
    logged_in_client.post(
        f"/purchases/{record.id}/delete", data={"csrf_token": token}, follow_redirects=True
    )

    db.session.refresh(student)
    assert student.total_purchased == 0
    assert PurchaseRecord.query.filter_by(student_id=student.id).count() == 0


def test_student_role_gets_403_on_purchase_routes(student_client, active_student_user):
    sid = active_student_user.student_id
    own_page = student_client.get(f"/students/{sid}")
    token = get_csrf_token(own_page.get_data(as_text=True))

    assert student_client.get(f"/students/{sid}/purchases/new").status_code == 403
    assert (
        student_client.post(f"/students/{sid}/purchases/new", data={"csrf_token": token}).status_code
        == 403
    )
    assert student_client.get("/purchases/1/edit").status_code == 403
    assert student_client.post("/purchases/1/delete", data={"csrf_token": token}).status_code == 403
