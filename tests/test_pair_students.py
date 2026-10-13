"""REQ-053：一對二學生卡片——兩個帳號共用同一張卡片的堂數、購課與上課紀錄。"""

from datetime import date, time

import pytest

from app import services
from app.models import ClassRecord, PurchaseRecord, Student, User
from tests.conftest import COACH_PASSWORD, COACH_USERNAME, get_csrf_token, login

STUDENT_PASSWORD = "StudentPass123"


def _make_student(db, name, username, purchased=0, attended=0, coach=None):
    student = Student(name=name, status="active", phone="0911111111", phone_type="mobile")
    if purchased:
        student.purchase_records.append(PurchaseRecord(purchase_date=date(2026, 1, 1), quantity=purchased))
    for _ in range(attended):
        student.class_records.append(
            ClassRecord(
                class_date=date(2026, 2, 1), class_time=time(10, 0), coach_id=coach.id if coach else None
            )
        )
    account = User(username=username, role="student", status="active", name=name, student=student)
    account.set_password(STUDENT_PASSWORD)
    db.session.add_all([student, account])
    db.session.commit()
    return account


@pytest.fixture()
def alice(db):
    """堂數已用完(買 2 上 2)的一對一學生。"""
    return _make_student(db, "王小明", "alice", purchased=2, attended=2)


@pytest.fixture()
def bob(db):
    """剛註冊、沒有任何紀錄的一對一學生。"""
    return _make_student(db, "陳大華", "bob")


@pytest.fixture()
def pair(db, alice, bob):
    return services.pair_students(alice.student, bob)


def _csrf(client, path):
    return get_csrf_token(client.get(path).get_data(as_text=True))


def _logout(client):
    client.post("/logout", data={"csrf_token": _csrf(client, "/change-password")})


# ---------- 配對 ----------

def test_pair_creates_shared_card_and_retires_old_cards(db, alice, bob):
    alice_old_id, bob_old_id = alice.student_id, bob.student_id

    pair = services.pair_students(alice.student, bob)

    assert pair.class_type == "one_on_two" and pair.status == "active"
    assert pair.name == "王小明、陳大華"
    assert alice.student_id == pair.id and bob.student_id == pair.id
    assert pair.remaining == 0 and pair.total_purchased == 0
    # 兩張原卡片都停用保留(不論有沒有紀錄)，並記下原本的帳號(REQ-054)
    for old_id, account in ((alice_old_id, alice), (bob_old_id, bob)):
        old = db.session.get(Student, old_id)
        assert old.status == "inactive" and old.accounts == []
        assert old.former_account_id == account.id
    assert len(db.session.get(Student, alice_old_id).class_records) == 2
    # 舊卡片停用不會連帶停用帳號
    assert alice.status == "active" and bob.status == "active"


@pytest.mark.parametrize("purchased, attended, message", [(5, 2, "尚有 3 堂未上完"), (1, 3, "已超上 2 堂")])
def test_pair_requires_classes_used_up(db, bob, purchased, attended, message):
    carol = _make_student(db, "林小美", "carol", purchased=purchased, attended=attended)
    for student, partner in ((carol.student, bob), (bob.student, carol)):
        with pytest.raises(services.ValidationError) as exc:
            services.pair_students(student, partner)
        assert message in exc.value.message
    assert Student.query.filter_by(class_type="one_on_two").count() == 0
    assert carol.student.status == "active"


def test_pair_rejects_invalid_partner(db, alice, bob, pair, coach_user):
    carol = _make_student(db, "林小美", "carol")
    with pytest.raises(services.ValidationError, match="已經是一對二"):
        services.pair_students(carol.student, alice)
    with pytest.raises(services.ValidationError, match="已經是一對二"):
        services.pair_students(pair, carol)
    with pytest.raises(services.ValidationError, match="不能和自己配對"):
        services.pair_students(carol.student, carol)
    with pytest.raises(services.ValidationError, match="請選擇"):
        services.pair_students(carol.student, coach_user)
    with pytest.raises(services.ValidationError, match="請選擇"):
        services.pair_students(carol.student, None)


def test_pair_page_lists_only_eligible_candidates(logged_in_client, db, alice, bob):
    _make_student(db, "林小美", "carol", purchased=3)
    html = logged_in_client.get(f"/students/{alice.student_id}/pair").get_data(as_text=True)
    assert "陳大華（bob）" in html
    assert "carol" not in html


def test_pair_via_page_then_both_accounts_see_shared_card(logged_in_client, db, alice, bob, coach_user):
    path = f"/students/{alice.student_id}/pair"
    resp = logged_in_client.post(
        path, data={"csrf_token": _csrf(logged_in_client, path), "partner_id": bob.id}, follow_redirects=True
    )
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200 and "已建立一對二" in html
    pair = Student.query.filter_by(class_type="one_on_two").one()

    # 共同的堂數與訓練菜單：買 10 堂、上 1 堂，兩人都看到剩 9 堂與同一份菜單
    services.create_purchase(pair, {"purchase_date": date(2026, 3, 1), "quantity": 10})
    services.create_class_record(
        pair,
        {
            "class_date": date(2026, 3, 2),
            "class_time": time(9, 0),
            "coach_id": coach_user.id,
            "exercises": [{"category": "腿", "name": "共同深蹲", "sets": 3, "reps": 10}],
        },
    )
    client = logged_in_client
    for username in ("alice", "bob"):
        _logout(client)
        login(client, username, STUDENT_PASSWORD)
        resp = client.get("/students/", follow_redirects=True)
        html = resp.get_data(as_text=True)
        assert resp.request.path == f"/students/{pair.id}"
        assert "一對二" in html and "王小明" in html and "陳大華" in html
        assert '<div class="stat-num ">9</div>' in html
        assert "共同深蹲" in html
        assert "拆分為一對一" not in html


def test_other_student_cannot_see_pair_card(client, db, pair):
    _make_student(db, "林小美", "carol")
    login(client, "carol", STUDENT_PASSWORD)
    assert client.get(f"/students/{pair.id}").status_code == 403


def test_coach_can_pair_and_sees_new_card(client, db, coach_user, alice, bob):
    login(client, COACH_USERNAME, COACH_PASSWORD)
    path = f"/students/{alice.student_id}/pair"
    resp = client.post(path, data={"csrf_token": _csrf(client, path), "partner_id": bob.id}, follow_redirects=True)
    assert "已建立一對二" in resp.get_data(as_text=True)
    html = client.get("/students/?class_type=one_on_two").get_data(as_text=True)
    assert "王小明、陳大華" in html and "alice、bob" in html


def test_student_cannot_pair_or_split(client, db, alice, bob):
    login(client, "alice", STUDENT_PASSWORD)
    assert client.get(f"/students/{alice.student_id}/pair").status_code == 403
    token = _csrf(client, f"/students/{alice.student_id}")
    assert client.post(f"/students/{alice.student_id}/split", data={"csrf_token": token}).status_code == 403


# ---------- 列表 ----------

def test_list_filters_by_class_type_and_searches_either_name(logged_in_client, db, pair):
    _make_student(db, "林小美", "carol")
    html = logged_in_client.get("/students/?class_type=one_on_two").get_data(as_text=True)
    assert "王小明、陳大華" in html and "林小美" not in html
    html = logged_in_client.get("/students/?class_type=one_on_one&status=active").get_data(as_text=True)
    assert "林小美" in html and "陳大華" not in html
    html = logged_in_client.get("/students/?search=陳大華&status=active").get_data(as_text=True)
    assert "王小明、陳大華" in html


# ---------- 拆分 ----------

@pytest.fixture()
def original_cards(alice, bob):
    """配對前兩人各自的一對一卡片 id；需排在 pair 之前。"""
    return {"alice": alice.student_id, "bob": bob.student_id}


def test_split_reactivates_original_cards(db, alice, bob, original_cards, pair):
    pair_id = pair.id
    pair.purchase_records.append(PurchaseRecord(purchase_date=date(2026, 3, 1), quantity=1))
    pair.class_records.append(ClassRecord(class_date=date(2026, 3, 2), class_time=time(9, 0)))
    db.session.commit()
    services.update_pair_member(pair, bob, {"name": "陳大華改", "phone": "0933333333", "phone_type": "mobile"})

    services.split_pair(pair)

    # 回到原本的卡片並重新啟用，不多出新卡片
    assert alice.student_id == original_cards["alice"] and bob.student_id == original_cards["bob"]
    assert Student.query.count() == 3
    for account in (alice, bob):
        card = account.student
        assert card.class_type == "one_on_one" and card.status == "active"
        assert card.former_account_id is None and card.remaining == 0
    assert len(alice.student.class_records) == 2
    # 一對二期間改過的個人資料帶回卡片
    assert (bob.student.name, bob.student.phone) == ("陳大華改", "0933333333")
    old = db.session.get(Student, pair_id)
    assert old.status == "inactive" and old.accounts == []


def test_split_creates_card_when_original_is_gone(db, alice, bob, original_cards, pair):
    db.session.delete(db.session.get(Student, original_cards["bob"]))
    db.session.commit()

    services.split_pair(pair)

    assert alice.student_id == original_cards["alice"]
    assert bob.student_id not in original_cards.values()
    assert bob.student.class_type == "one_on_one" and bob.student.status == "active"


def test_split_falls_back_to_same_name_card_for_older_pairs(db, alice, bob, original_cards, pair):
    """REQ-054 之前配對的卡片沒有記下原帳號：同名、已停用、沒有帳號的一對一卡片剛好一張才採用。"""
    for old_id in original_cards.values():
        db.session.get(Student, old_id).former_account_id = None
    # 另一張同名的停用卡片讓「陳大華」無法判斷是哪一張
    db.session.add(Student(name="陳大華", status="inactive"))
    db.session.commit()

    services.split_pair(pair)

    assert alice.student_id == original_cards["alice"] and alice.student.status == "active"
    assert bob.student_id != original_cards["bob"]
    assert Student.query.filter_by(name="陳大華").count() == 3


def test_split_keeps_card_inactive_for_disabled_account(db, alice, bob, original_cards, pair):
    services.set_account_status(bob, "disabled")
    services.split_pair(pair)
    assert bob.student_id == original_cards["bob"] and bob.student.status == "inactive"
    assert alice.student.status == "active"


def test_pair_again_after_split_reuses_original_cards(db, alice, bob, original_cards, pair):
    services.split_pair(pair)
    again = services.pair_students(alice.student, bob)
    assert again.is_pair and alice.student_id == again.id
    services.split_pair(again)
    assert alice.student_id == original_cards["alice"] and bob.student_id == original_cards["bob"]


def test_split_requires_classes_used_up(logged_in_client, db, alice, bob, pair):
    pair.purchase_records.append(PurchaseRecord(purchase_date=date(2026, 3, 1), quantity=4))
    db.session.commit()
    path = f"/students/{pair.id}"
    resp = logged_in_client.post(
        f"{path}/split", data={"csrf_token": _csrf(logged_in_client, path)}, follow_redirects=True
    )
    assert "尚有 4 堂未上完" in resp.get_data(as_text=True)
    assert alice.student_id == pair.id and bob.student_id == pair.id


def test_split_empty_pair_card_is_deleted(db, alice, bob, pair):
    pair_id = pair.id
    services.split_pair(pair)
    assert db.session.get(Student, pair_id) is None
    assert alice.student.status == "active" and bob.student.status == "active"


# ---------- 編輯個人資料 ----------

def test_student_edits_only_own_data_on_pair_card(client, db, alice, bob, pair):
    login(client, "bob", STUDENT_PASSWORD)
    # 即使網址指定另一位學員，學生也只會改到自己
    path = f"/students/{pair.id}/edit?member={alice.id}"
    html = client.get(path).get_data(as_text=True)
    assert 'value="陳大華"' in html
    resp = client.post(
        path,
        data={
            "csrf_token": get_csrf_token(html),
            "name": "陳大華改",
            "phone_type": "mobile",
            "phone": "0933333333",
            "email": "bob@example.com",
            "gender": "",
            "status": "inactive",
            "notes": "減脂",
        },
        follow_redirects=True,
    )
    assert "學生資料已更新" in resp.get_data(as_text=True)
    assert (bob.name, bob.phone, bob.email, bob.goal) == ("陳大華改", "0933333333", "bob@example.com", "減脂")
    assert alice.name == "王小明" and alice.phone is None
    assert pair.name == "王小明、陳大華改" and pair.status == "active"


def test_admin_edits_chosen_member(logged_in_client, db, alice, bob, pair):
    path = f"/students/{pair.id}/edit?member={alice.id}"
    html = logged_in_client.get(path).get_data(as_text=True)
    assert 'value="王小明"' in html
    assert logged_in_client.get(f"/students/{pair.id}/edit").status_code == 404
    assert logged_in_client.get(f"/students/{pair.id}/edit?member=99999").status_code == 404


# ---------- 帳號停用／刪除連動 ----------

def test_pair_card_stays_active_until_both_accounts_disabled(db, alice, bob, pair):
    services.set_account_status(alice, "disabled")
    assert pair.status == "active"
    services.set_account_status(bob, "disabled")
    assert pair.status == "inactive"
    services.set_account_status(alice, "active")
    assert pair.status == "active" and bob.status == "disabled"


def test_card_status_change_applies_to_both_accounts(db, alice, bob, pair):
    services.set_student_status(pair, "inactive")
    assert alice.status == "disabled" and bob.status == "disabled"
    services.set_student_status(pair, "active")
    assert alice.status == "active" and bob.status == "active"


def test_deleting_one_account_keeps_shared_card(db, alice, bob, pair):
    pair_id, bob_id = pair.id, bob.id
    pair.purchase_records.append(PurchaseRecord(purchase_date=date(2026, 3, 1), quantity=5))
    db.session.commit()
    services.set_account_status(alice, "disabled")

    services.delete_account(alice)

    card = db.session.get(Student, pair_id)
    assert card is not None and card.status == "active" and card.remaining == 5
    assert [a.id for a in card.accounts] == [bob_id] and card.name == "陳大華"
    # 最後一位學員沿用原規則：尚有剩餘堂數不可刪
    services.set_account_status(bob, "disabled")
    with pytest.raises(services.ValidationError, match="尚有課程未完成"):
        services.delete_account(bob)


# ---------- 一對一行為不變 ----------

def test_one_on_one_name_still_syncs_to_account(db, alice):
    services.update_student(alice.student, {"name": "王大明"})
    assert alice.name == "王大明" and alice.student.class_type == "one_on_one"


def test_api_student_includes_class_type_and_accounts(logged_in_client, db, pair):
    data = logged_in_client.get(f"/api/students/{pair.id}").get_json()
    assert data["class_type"] == "one_on_two"
    assert [a["username"] for a in data["accounts"]] == ["alice", "bob"]
