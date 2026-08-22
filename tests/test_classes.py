from tests.conftest import get_csrf_token
from tests.test_purchases import add_purchase
from tests.test_students import create_student


def _student(db, name="王小明"):
    from app.models import Student

    return Student.query.filter_by(name=name).first()


def _student_with_quota(client, db, quantity=10, name="王小明"):
    """建立學生並購買足夠堂數，供需要新增上課紀錄的測試使用(新增時會檢查剩餘堂數)。"""
    create_student(client, name=name)
    student = _student(db, name=name)
    add_purchase(client, student.id, quantity=str(quantity))
    return student


def add_class(client, student_id, **overrides):
    resp = client.get(f"/students/{student_id}/classes/new")
    token = get_csrf_token(resp.get_data(as_text=True))
    data = {
        "class_date": "2026-01-05",
        "class_time": "10:00",
        "duration_minutes": "",
        "notes": "",
        "csrf_token": token,
    }
    data.update(overrides)
    return client.post(f"/students/{student_id}/classes/new", data=data, follow_redirects=True)


def test_date_and_time_required(logged_in_client, db):
    student = _student_with_quota(logged_in_client, db)

    resp = add_class(logged_in_client, student.id, class_date="")
    assert "到課日期為必填" in resp.get_data(as_text=True)

    resp = add_class(logged_in_client, student.id, class_time="")
    assert "到課時間為必填" in resp.get_data(as_text=True)


def test_create_class_record_updates_attended_count(logged_in_client, db):
    student = _student_with_quota(logged_in_client, db)

    add_class(logged_in_client, student.id, class_date="2026-01-05")
    add_class(logged_in_client, student.id, class_date="2026-01-12")
    db.session.refresh(student)
    assert student.total_attended == 2


def test_edit_class_record_does_not_change_attended_count(logged_in_client, db):
    student = _student_with_quota(logged_in_client, db)
    add_class(logged_in_client, student.id, class_date="2026-01-05")

    from app.models import ClassRecord

    record = ClassRecord.query.filter_by(student_id=student.id).first()

    resp = logged_in_client.get(f"/classes/{record.id}/edit")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        f"/classes/{record.id}/edit",
        data={
            "class_date": "2026-01-06",
            "class_time": "11:00",
            "duration_minutes": "",
            "notes": "更正日期時間",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    db.session.refresh(student)
    assert student.total_attended == 1


def test_delete_class_record_decreases_attended_count(logged_in_client, db):
    student = _student_with_quota(logged_in_client, db)
    add_class(logged_in_client, student.id, class_date="2026-01-05")
    add_class(logged_in_client, student.id, class_date="2026-01-12")

    from app.models import ClassRecord

    record = ClassRecord.query.filter_by(student_id=student.id).first()

    detail = logged_in_client.get(f"/students/{student.id}")
    token = get_csrf_token(detail.get_data(as_text=True))
    logged_in_client.post(
        f"/classes/{record.id}/delete", data={"csrf_token": token}, follow_redirects=True
    )

    db.session.refresh(student)
    assert student.total_attended == 1


def test_cannot_add_class_when_no_remaining_quota(logged_in_client, db):
    from app.models import ClassRecord

    create_student(logged_in_client, name="王小明")
    student = _student(db)
    assert student.remaining == 0

    resp = add_class(logged_in_client, student.id)
    assert "已無上課堂數，請確認" in resp.get_data(as_text=True)
    assert ClassRecord.query.filter_by(student_id=student.id).count() == 0


def test_cannot_add_class_when_quota_exactly_used_up(logged_in_client, db):
    from app.models import ClassRecord

    student = _student_with_quota(logged_in_client, db, quantity=1)
    add_class(logged_in_client, student.id, class_date="2026-01-05")
    db.session.refresh(student)
    assert student.remaining == 0

    resp = add_class(logged_in_client, student.id, class_date="2026-01-06")
    assert "已無上課堂數，請確認" in resp.get_data(as_text=True)
    assert ClassRecord.query.filter_by(student_id=student.id).count() == 1


def test_new_class_page_shows_warning_when_no_remaining_quota(logged_in_client, db):
    create_student(logged_in_client, name="王小明")
    student = _student(db)

    resp = logged_in_client.get(f"/students/{student.id}/classes/new")
    assert "已無上課堂數，請確認" in resp.get_data(as_text=True)


def test_new_class_page_has_no_warning_when_quota_available(logged_in_client, db):
    student = _student_with_quota(logged_in_client, db)

    resp = logged_in_client.get(f"/students/{student.id}/classes/new")
    assert "已無上課堂數，請確認" not in resp.get_data(as_text=True)


def test_edit_class_still_allowed_when_quota_used_up(logged_in_client, db):
    from app.models import ClassRecord

    student = _student_with_quota(logged_in_client, db, quantity=1)
    add_class(logged_in_client, student.id, class_date="2026-01-05")
    db.session.refresh(student)
    assert student.remaining == 0

    record = ClassRecord.query.filter_by(student_id=student.id).first()
    resp = logged_in_client.get(f"/classes/{record.id}/edit")
    token = get_csrf_token(resp.get_data(as_text=True))
    resp = logged_in_client.post(
        f"/classes/{record.id}/edit",
        data={
            "class_date": "2026-01-06",
            "class_time": "11:00",
            "duration_minutes": "",
            "notes": "",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    db.session.refresh(record)
    assert record.class_date.isoformat() == "2026-01-06"


def test_add_class_with_catalog_exercise_links_catalog_item(logged_in_client, db):
    from app.models import ClassExercise, ExerciseCatalogItem

    student = _student_with_quota(logged_in_client, db)

    catalog_item = ExerciseCatalogItem(category="下肢(蹲類)訓練", name="壺鈴深蹲", sort_order=0)
    db.session.add(catalog_item)
    db.session.commit()

    add_class(
        logged_in_client,
        student.id,
        **{"exercise_category": "下肢(蹲類)訓練", "exercise_name": "壺鈴深蹲"},
    )

    exercise = ClassExercise.query.filter_by(name="壺鈴深蹲").first()
    assert exercise is not None
    assert exercise.category == "下肢(蹲類)訓練"
    assert exercise.exercise_catalog_item_id == catalog_item.id


def test_add_class_with_custom_exercise_not_in_catalog(logged_in_client, db):
    from app.models import ClassExercise

    student = _student_with_quota(logged_in_client, db)

    add_class(
        logged_in_client,
        student.id,
        **{"exercise_category": "自訂分類", "exercise_name": "教練自訂項目"},
    )

    exercise = ClassExercise.query.filter_by(name="教練自訂項目").first()
    assert exercise is not None
    assert exercise.exercise_catalog_item_id is None


def test_add_class_with_multiple_exercises_preserves_order(logged_in_client, db):
    from app.models import ClassRecord

    student = _student_with_quota(logged_in_client, db)

    resp = logged_in_client.get(f"/students/{student.id}/classes/new")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        f"/students/{student.id}/classes/new",
        data={
            "class_date": "2026-01-05",
            "class_time": "10:00",
            "duration_minutes": "",
            "notes": "",
            "exercise_category": ["核心 / 旋轉", "下肢(蹲類)訓練"],
            "exercise_name": ["捲腹", "壺鈴深蹲"],
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    record = ClassRecord.query.filter_by(student_id=student.id).first()
    assert [e.name for e in record.exercises] == ["捲腹", "壺鈴深蹲"]


def test_add_class_with_exercise_name_but_no_category_shows_error(logged_in_client, db):
    from app.models import ClassExercise

    student = _student_with_quota(logged_in_client, db)

    resp = add_class(
        logged_in_client,
        student.id,
        **{"exercise_category": "", "exercise_name": "捲腹"},
    )
    assert "有訓練項目未選擇分類" in resp.get_data(as_text=True)
    assert ClassExercise.query.count() == 0


def test_edit_class_replaces_exercise_list(logged_in_client, db):
    from app.models import ClassRecord

    student = _student_with_quota(logged_in_client, db)
    add_class(
        logged_in_client,
        student.id,
        **{"exercise_category": "核心 / 旋轉", "exercise_name": "捲腹"},
    )

    record = ClassRecord.query.filter_by(student_id=student.id).first()

    resp = logged_in_client.get(f"/classes/{record.id}/edit")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        f"/classes/{record.id}/edit",
        data={
            "class_date": "2026-01-05",
            "class_time": "10:00",
            "duration_minutes": "",
            "notes": "",
            "exercise_category": "下肢(蹲類)訓練",
            "exercise_name": "壺鈴深蹲",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    db.session.refresh(record)
    assert [e.name for e in record.exercises] == ["壺鈴深蹲"]


def test_delete_class_record_removes_its_exercises(logged_in_client, db):
    from app.models import ClassExercise, ClassRecord

    student = _student_with_quota(logged_in_client, db)
    add_class(
        logged_in_client,
        student.id,
        **{"exercise_category": "核心 / 旋轉", "exercise_name": "捲腹"},
    )
    record = ClassRecord.query.filter_by(student_id=student.id).first()

    detail = logged_in_client.get(f"/students/{student.id}")
    token = get_csrf_token(detail.get_data(as_text=True))
    logged_in_client.post(
        f"/classes/{record.id}/delete", data={"csrf_token": token}, follow_redirects=True
    )

    assert ClassExercise.query.count() == 0


def test_student_role_gets_403_on_class_routes(student_client, active_student_user):
    sid = active_student_user.student_id
    own_page = student_client.get(f"/students/{sid}")
    token = get_csrf_token(own_page.get_data(as_text=True))

    assert student_client.get(f"/students/{sid}/classes/new").status_code == 403
    assert (
        student_client.post(f"/students/{sid}/classes/new", data={"csrf_token": token}).status_code
        == 403
    )
    assert student_client.get("/classes/1/edit").status_code == 403
    assert student_client.post("/classes/1/delete", data={"csrf_token": token}).status_code == 403
