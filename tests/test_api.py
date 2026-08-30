def test_api_create_and_get_student(logged_in_client):
    resp = logged_in_client.post("/api/students", json={"name": "王小明", "phone": "0900000000"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["name"] == "王小明"
    assert body["remaining"] == 0

    student_id = body["student_id"]
    resp = logged_in_client.get(f"/api/students/{student_id}")
    assert resp.status_code == 200
    assert resp.get_json()["student_id"] == student_id


def test_api_create_student_requires_name(logged_in_client):
    resp = logged_in_client.post("/api/students", json={"name": "  "})
    assert resp.status_code == 400
    assert resp.get_json()["error"]


def test_api_list_students_supports_search_and_status(logged_in_client):
    logged_in_client.post("/api/students", json={"name": "王小明"})
    logged_in_client.post("/api/students", json={"name": "陳小華"})

    resp = logged_in_client.get("/api/students?search=小明")
    names = [s["name"] for s in resp.get_json()]
    assert names == ["王小明"]

    resp = logged_in_client.get("/api/students?status=inactive")
    assert resp.get_json() == []


def test_api_summary_shape_matches_spec(logged_in_client, coach_user):
    student_id = logged_in_client.post("/api/students", json={"name": "王小明"}).get_json()["student_id"]

    logged_in_client.post(
        f"/api/students/{student_id}/purchases",
        json={"purchase_date": "2026-01-01", "quantity": 10},
    )
    logged_in_client.post(
        f"/api/students/{student_id}/classes",
        json={"class_date": "2026-01-05", "class_time": "10:00", "coach_id": coach_user.id},
    )

    resp = logged_in_client.get(f"/api/students/{student_id}/summary")
    assert resp.status_code == 200
    assert resp.get_json() == {"total_purchased": 10, "total_attended": 1, "remaining": 9}


def test_api_purchase_quantity_validation(logged_in_client):
    student_id = logged_in_client.post("/api/students", json={"name": "王小明"}).get_json()["student_id"]
    resp = logged_in_client.post(
        f"/api/students/{student_id}/purchases",
        json={"purchase_date": "2026-01-01", "quantity": 0},
    )
    assert resp.status_code == 400


def test_api_delete_student_is_soft_delete(logged_in_client):
    student_id = logged_in_client.post("/api/students", json={"name": "王小明"}).get_json()["student_id"]
    resp = logged_in_client.delete(f"/api/students/{student_id}")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "inactive"

    # 歷史紀錄保留:仍可查得到這位學生
    resp = logged_in_client.get(f"/api/students/{student_id}")
    assert resp.status_code == 200


def test_api_delete_purchase_is_hard_delete(logged_in_client):
    student_id = logged_in_client.post("/api/students", json={"name": "王小明"}).get_json()["student_id"]
    purchase = logged_in_client.post(
        f"/api/students/{student_id}/purchases",
        json={"purchase_date": "2026-01-01", "quantity": 5},
    ).get_json()

    resp = logged_in_client.delete(f"/api/purchases/{purchase['purchase_id']}")
    assert resp.status_code == 204

    resp = logged_in_client.get(f"/api/students/{student_id}/purchases")
    assert resp.get_json() == []


def test_api_student_role_gets_403_not_401(student_client):
    resp = student_client.get("/api/students")
    assert resp.status_code == 403


def test_api_coach_role_has_same_access_as_admin(coach_client):
    resp = coach_client.post("/api/students", json={"name": "教練建立"})
    assert resp.status_code == 201


def test_api_exercise_catalog_crud(logged_in_client):
    resp = logged_in_client.post(
        "/api/exercise-catalog", json={"category": "下肢(蹲類)訓練", "name": "壺鈴深蹲"}
    )
    assert resp.status_code == 201
    item = resp.get_json()
    assert item["category"] == "下肢(蹲類)訓練"
    assert item["sort_order"] == 0

    resp = logged_in_client.get("/api/exercise-catalog")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1

    resp = logged_in_client.put(
        f"/api/exercise-catalog/{item['id']}",
        json={"category": "下肢(蹲類)訓練", "name": "壺鈴側深蹲"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "壺鈴側深蹲"

    resp = logged_in_client.delete(f"/api/exercise-catalog/{item['id']}")
    assert resp.status_code == 204
    assert logged_in_client.get("/api/exercise-catalog").get_json() == []


def test_api_exercise_catalog_rejects_duplicate_name(logged_in_client):
    logged_in_client.post("/api/exercise-catalog", json={"category": "核心 / 旋轉", "name": "捲腹"})
    resp = logged_in_client.post("/api/exercise-catalog", json={"category": "核心 / 旋轉", "name": "捲腹"})
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "name"


def test_api_exercise_catalog_requires_category_and_name(logged_in_client):
    resp = logged_in_client.post("/api/exercise-catalog", json={"category": "", "name": "捲腹"})
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "category"

    resp = logged_in_client.post("/api/exercise-catalog", json={"category": "核心 / 旋轉", "name": ""})
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "name"


def test_api_exercise_catalog_student_role_gets_403(student_client):
    resp = student_client.get("/api/exercise-catalog")
    assert resp.status_code == 403


def test_api_create_class_blocked_when_no_remaining_quota(logged_in_client):
    student_id = logged_in_client.post("/api/students", json={"name": "王小明"}).get_json()["student_id"]

    resp = logged_in_client.post(
        f"/api/students/{student_id}/classes",
        json={"class_date": "2026-01-05", "class_time": "10:00"},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["field"] == "remaining"
    assert "已無上課堂數，請確認" in body["error"]


def test_api_create_class_with_exercises(logged_in_client, coach_user):
    student_id = logged_in_client.post("/api/students", json={"name": "王小明"}).get_json()["student_id"]
    logged_in_client.post(
        f"/api/students/{student_id}/purchases",
        json={"purchase_date": "2026-01-01", "quantity": 10},
    )
    logged_in_client.post("/api/exercise-catalog", json={"category": "核心 / 旋轉", "name": "捲腹"})

    resp = logged_in_client.post(
        f"/api/students/{student_id}/classes",
        json={
            "class_date": "2026-01-05",
            "class_time": "10:00",
            "coach_id": coach_user.id,
            "exercises": [{"category": "核心 / 旋轉", "name": "捲腹", "sets": 3, "reps": 12}],
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["coach_id"] == coach_user.id
    assert body["exercises"] == [
        {
            "id": body["exercises"][0]["id"],
            "class_record_id": body["record_id"],
            "exercise_catalog_item_id": body["exercises"][0]["exercise_catalog_item_id"],
            "category": "核心 / 旋轉",
            "name": "捲腹",
            "weight_kg": None,
            "sets": 3,
            "reps": 12,
            "note": None,
            "sort_order": 0,
        }
    ]
    assert body["exercises"][0]["exercise_catalog_item_id"] is not None


def test_api_create_class_without_coach_returns_400(logged_in_client):
    student_id = logged_in_client.post("/api/students", json={"name": "王小明"}).get_json()["student_id"]
    logged_in_client.post(
        f"/api/students/{student_id}/purchases",
        json={"purchase_date": "2026-01-01", "quantity": 10},
    )
    resp = logged_in_client.post(
        f"/api/students/{student_id}/classes",
        json={"class_date": "2026-01-05", "class_time": "10:00"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "coach_id"


def test_api_create_class_with_exercise_missing_category_returns_400(logged_in_client, coach_user):
    student_id = logged_in_client.post("/api/students", json={"name": "王小明"}).get_json()["student_id"]
    logged_in_client.post(
        f"/api/students/{student_id}/purchases",
        json={"purchase_date": "2026-01-01", "quantity": 10},
    )
    resp = logged_in_client.post(
        f"/api/students/{student_id}/classes",
        json={
            "class_date": "2026-01-05",
            "class_time": "10:00",
            "coach_id": coach_user.id,
            "exercises": [{"category": "", "name": "捲腹"}],
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "exercises"


def test_api_update_class_replaces_exercises(logged_in_client, coach_user):
    student_id = logged_in_client.post("/api/students", json={"name": "王小明"}).get_json()["student_id"]
    logged_in_client.post(
        f"/api/students/{student_id}/purchases",
        json={"purchase_date": "2026-01-01", "quantity": 10},
    )
    record = logged_in_client.post(
        f"/api/students/{student_id}/classes",
        json={
            "class_date": "2026-01-05",
            "class_time": "10:00",
            "coach_id": coach_user.id,
            "exercises": [{"category": "核心 / 旋轉", "name": "捲腹"}],
        },
    ).get_json()

    resp = logged_in_client.put(
        f"/api/classes/{record['record_id']}",
        json={"exercises": [{"category": "下肢(蹲類)訓練", "name": "壺鈴深蹲"}]},
    )
    assert resp.status_code == 200
    assert [e["name"] for e in resp.get_json()["exercises"]] == ["壺鈴深蹲"]

    # 沒有帶 exercises 欄位時不應清空既有菜單
    resp = logged_in_client.put(f"/api/classes/{record['record_id']}", json={"notes": "更新備註"})
    assert [e["name"] for e in resp.get_json()["exercises"]] == ["壺鈴深蹲"]
