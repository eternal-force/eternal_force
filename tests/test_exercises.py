from app import services
from app.exercise_catalog_seed import EXERCISE_CATALOG_SEED
from app.models import ExerciseCatalogItem
from tests.conftest import get_csrf_token
from tests.test_classes import _student_with_quota, add_class


def test_student_role_gets_403_on_exercises_routes(student_client, active_student_user):
    assert student_client.get("/exercises/").status_code == 403
    assert student_client.get("/exercises/new").status_code == 403


def test_new_exercise_creates_item_with_incrementing_sort_order(logged_in_client, db):
    resp = logged_in_client.get("/exercises/new")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        "/exercises/new",
        data={"category": "下肢(蹲類)訓練", "name": "壺鈴深蹲", "csrf_token": token},
        follow_redirects=True,
    )

    resp = logged_in_client.get("/exercises/new")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        "/exercises/new",
        data={"category": "下肢(蹲類)訓練", "name": "壺鈴側深蹲", "csrf_token": token},
        follow_redirects=True,
    )

    items = ExerciseCatalogItem.query.order_by(ExerciseCatalogItem.sort_order.asc()).all()
    assert [i.name for i in items] == ["壺鈴深蹲", "壺鈴側深蹲"]
    assert items[0].sort_order < items[1].sort_order


def test_new_exercise_rejects_duplicate_name(logged_in_client, db):
    resp = logged_in_client.get("/exercises/new")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        "/exercises/new",
        data={"category": "核心 / 旋轉", "name": "捲腹", "csrf_token": token},
        follow_redirects=True,
    )

    resp = logged_in_client.get("/exercises/new")
    token = get_csrf_token(resp.get_data(as_text=True))
    resp = logged_in_client.post(
        "/exercises/new",
        data={"category": "核心 / 旋轉", "name": "捲腹", "csrf_token": token},
    )
    assert resp.status_code == 200
    assert "已經有相同名稱的項目" in resp.get_data(as_text=True)
    assert ExerciseCatalogItem.query.count() == 1


def test_list_groups_by_category_and_supports_search_and_filter(logged_in_client, db):
    db.session.add_all(
        [
            ExerciseCatalogItem(category="暖身 / 伸展", name="鴿式伸展", sort_order=0),
            ExerciseCatalogItem(category="下肢(蹲類)訓練", name="壺鈴深蹲", sort_order=1),
        ]
    )
    db.session.commit()

    resp = logged_in_client.get("/exercises/")
    body = resp.get_data(as_text=True)
    assert "鴿式伸展" in body
    assert "壺鈴深蹲" in body

    resp = logged_in_client.get("/exercises/", query_string={"search": "深蹲"})
    body = resp.get_data(as_text=True)
    assert "壺鈴深蹲" in body
    assert "鴿式伸展" not in body

    resp = logged_in_client.get("/exercises/", query_string={"category": "暖身 / 伸展"})
    body = resp.get_data(as_text=True)
    assert "鴿式伸展" in body
    assert "壺鈴深蹲" not in body


def test_category_badge_class_is_deterministic_and_not_always_muted():
    assert services.category_badge_class("暖身 / 伸展") == services.category_badge_class("暖身 / 伸展")
    assert services.category_badge_class("下肢(蹲類)訓練") == services.category_badge_class("下肢(蹲類)訓練")
    assert services.category_badge_class("") == "badge-muted"
    assert services.category_badge_class(None) == "badge-muted"
    assert services.category_badge_class("暖身 / 伸展") != "badge-muted"


def test_list_shows_category_with_color_badge(logged_in_client, db):
    db.session.add(ExerciseCatalogItem(category="暖身 / 伸展", name="鴿式伸展", sort_order=0))
    db.session.commit()

    resp = logged_in_client.get("/exercises/")
    body = resp.get_data(as_text=True)
    badge_class = services.category_badge_class("暖身 / 伸展")
    assert f'class="badge {badge_class}"' in body
    assert 'class="badge badge-muted">暖身 / 伸展' not in body


def test_list_search_bar_and_category_groups_are_collapsed_by_default(logged_in_client, db):
    db.session.add(ExerciseCatalogItem(category="暖身 / 伸展", name="鴿式伸展", sort_order=0))
    db.session.commit()

    resp = logged_in_client.get("/exercises/")
    body = resp.get_data(as_text=True)
    assert '<details class="card">' in body
    assert '<details class="card" open>' not in body
    assert "鴿式伸展" in body


def test_edit_exercise_updates_category_and_name(logged_in_client, db):
    item = ExerciseCatalogItem(category="核心 / 旋轉", name="捲腹", sort_order=0)
    db.session.add(item)
    db.session.commit()

    resp = logged_in_client.get(f"/exercises/{item.id}/edit")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        f"/exercises/{item.id}/edit",
        data={"category": "核心 / 旋轉", "name": "捲腹+俄羅斯轉體", "csrf_token": token},
        follow_redirects=True,
    )

    db.session.refresh(item)
    assert item.name == "捲腹+俄羅斯轉體"


def test_edit_exercise_blocked_when_referenced_by_class_record(logged_in_client, db):
    item = ExerciseCatalogItem(category="下肢(蹲類)訓練", name="壺鈴深蹲", sort_order=0)
    db.session.add(item)
    db.session.commit()

    student = _student_with_quota(logged_in_client, db)
    add_class(
        logged_in_client,
        db,
        student.id,
        **{"exercise_category": "下肢(蹲類)訓練", "exercise_name": "壺鈴深蹲"},
    )

    resp = logged_in_client.get(f"/exercises/{item.id}/edit")
    token = get_csrf_token(resp.get_data(as_text=True))
    resp = logged_in_client.post(
        f"/exercises/{item.id}/edit",
        data={"category": "下肢(蹲類)訓練", "name": "壺鈴深蹲2", "csrf_token": token},
    )
    assert "已被學生的訓練菜單引用" in resp.get_data(as_text=True)
    db.session.refresh(item)
    assert item.name == "壺鈴深蹲"


def test_delete_exercise_blocked_when_referenced_by_class_record(logged_in_client, db):
    item = ExerciseCatalogItem(category="下肢(蹲類)訓練", name="壺鈴深蹲", sort_order=0)
    db.session.add(item)
    db.session.commit()
    item_id = item.id

    student = _student_with_quota(logged_in_client, db)
    add_class(
        logged_in_client,
        db,
        student.id,
        **{"exercise_category": "下肢(蹲類)訓練", "exercise_name": "壺鈴深蹲"},
    )

    resp = logged_in_client.get("/exercises/")
    token = get_csrf_token(resp.get_data(as_text=True))
    resp = logged_in_client.post(
        f"/exercises/{item_id}/delete", data={"csrf_token": token}, follow_redirects=True
    )
    assert "已被學生的訓練菜單引用" in resp.get_data(as_text=True)
    assert db.session.get(ExerciseCatalogItem, item_id) is not None


def test_delete_exercise_removes_item(logged_in_client, db):
    item = ExerciseCatalogItem(category="核心 / 旋轉", name="捲腹", sort_order=0)
    db.session.add(item)
    db.session.commit()
    item_id = item.id

    resp = logged_in_client.get("/exercises/")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post(
        f"/exercises/{item_id}/delete",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert db.session.get(ExerciseCatalogItem, item_id) is None


def test_seed_exercise_catalog_imports_all_items_without_duplicates(app, db):
    services.seed_exercise_catalog(EXERCISE_CATALOG_SEED)

    assert ExerciseCatalogItem.query.count() == len(EXERCISE_CATALOG_SEED)
    names = {name for _, name in EXERCISE_CATALOG_SEED}
    assert {i.name for i in ExerciseCatalogItem.query.all()} == names


def test_seed_exercise_catalog_is_idempotent_and_preserves_manual_edits(app, db):
    services.seed_exercise_catalog(EXERCISE_CATALOG_SEED)

    item = ExerciseCatalogItem.query.filter_by(name="壺鈴深蹲").first()
    item.category = "自訂分類"
    db.session.commit()

    services.seed_exercise_catalog(EXERCISE_CATALOG_SEED)

    assert ExerciseCatalogItem.query.count() == len(EXERCISE_CATALOG_SEED)
    db.session.refresh(item)
    assert item.category == "下肢(蹲類)訓練"  # 重新匯入以種子資料為準


def test_seed_exercise_catalog_does_not_remove_extra_manual_items(app, db):
    db.session.add(ExerciseCatalogItem(category="自訂分類", name="教練自訂項目", sort_order=999))
    db.session.commit()

    services.seed_exercise_catalog(EXERCISE_CATALOG_SEED)

    assert ExerciseCatalogItem.query.filter_by(name="教練自訂項目").count() == 1
    assert ExerciseCatalogItem.query.count() == len(EXERCISE_CATALOG_SEED) + 1


def test_coach_can_manage_exercise_catalog(coach_client, db):
    resp = coach_client.get("/exercises/new")
    assert resp.status_code == 200
    token = get_csrf_token(resp.get_data(as_text=True))
    resp = coach_client.post(
        "/exercises/new",
        data={"category": "核心 / 旋轉", "name": "捲腹", "csrf_token": token},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert ExerciseCatalogItem.query.filter_by(name="捲腹").count() == 1
