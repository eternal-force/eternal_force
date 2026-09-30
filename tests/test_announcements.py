import io
from datetime import timedelta

from app import services
from app.models import Announcement

from tests.conftest import (
    ACTIVE_STUDENT_PASSWORD,
    ACTIVE_STUDENT_USERNAME,
    COACH_PASSWORD,
    COACH_USERNAME,
    get_csrf_token,
    login,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
DT_FORMAT = "%Y-%m-%dT%H:%M"


def _now():
    return services.taipei_now().replace(second=0, microsecond=0)


def _make_announcement(db, title="停課公告", publish_offset=-1, unpublish_offset=24, **overrides):
    now = _now()
    data = {
        "announce_date": (now + timedelta(hours=publish_offset)).date(),
        "publish_at": now + timedelta(hours=publish_offset),
        "unpublish_at": now + timedelta(hours=unpublish_offset),
        "title": title,
        "content": "第一行\n第二行",
        "show_to_student": True,
        "show_to_coach": True,
        "show_to_admin": True,
    }
    data.update(overrides)
    return services.create_announcement(data)


def _form(client, url, **overrides):
    token = get_csrf_token(client.get(url).get_data(as_text=True))
    now = _now()
    data = {
        "csrf_token": token,
        "announce_date": now.date().isoformat(),
        "publish_at": now.strftime(DT_FORMAT),
        "unpublish_at": (now + timedelta(days=3)).strftime(DT_FORMAT),
        "title": "新公告",
        "content": "公告內容",
        "show_to_student": "y",
        "show_to_coach": "y",
        "show_to_admin": "y",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


def _post(client, url, data):
    return client.post(url, data=data, content_type="multipart/form-data", follow_redirects=True)


# ---------- 後台權限 ----------


def test_admin_can_open_management(logged_in_client):
    assert logged_in_client.get("/announcements/").status_code == 200
    assert "公告管理" in logged_in_client.get("/students/").get_data(as_text=True)


def test_coach_can_manage_announcements(coach_client):
    resp = coach_client.get("/announcements/")
    assert resp.status_code == 200
    data = _form(coach_client, "/announcements/new")
    resp = _post(coach_client, "/announcements/new", data)
    assert "公告「新公告」已新增" in resp.get_data(as_text=True)


def test_student_cannot_manage_announcements(student_client):
    assert student_client.get("/announcements/").status_code == 403
    assert student_client.get("/announcements/new").status_code == 403
    assert "公告管理" not in student_client.get("/students/").get_data(as_text=True)


# ---------- 新增 / 驗證 ----------


def test_create_announcement_with_image(logged_in_client, db):
    data = _form(logged_in_client, "/announcements/new", image=(io.BytesIO(PNG_BYTES), "a.png"))
    resp = _post(logged_in_client, "/announcements/new", data)
    body = resp.get_data(as_text=True)
    assert "公告「新公告」已新增" in body
    assert "上架中" in body
    item = Announcement.query.one()
    assert item.image_mime == "image/png"
    assert item.image_data == PNG_BYTES


def test_publish_date_cannot_be_before_announce_date(logged_in_client, db):
    now = _now()
    data = _form(
        logged_in_client,
        "/announcements/new",
        announce_date=(now + timedelta(days=1)).date().isoformat(),
    )
    body = _post(logged_in_client, "/announcements/new", data).get_data(as_text=True)
    assert "上架日期不得早於公告日期" in body
    assert Announcement.query.count() == 0


def test_publish_on_announce_date_is_allowed(app, db):
    now = _now()
    item = _make_announcement(db, announce_date=now.date(), publish_offset=0)
    assert item.publish_at.date() == item.announce_date


def test_unpublish_must_be_after_publish(logged_in_client, db):
    now = _now()
    data = _form(logged_in_client, "/announcements/new", unpublish_at=now.strftime(DT_FORMAT))
    body = _post(logged_in_client, "/announcements/new", data).get_data(as_text=True)
    assert "下架日期時間必須晚於上架日期時間" in body
    assert Announcement.query.count() == 0


def test_at_least_one_audience_required(logged_in_client, db):
    data = _form(
        logged_in_client,
        "/announcements/new",
        show_to_student=None,
        show_to_coach=None,
        show_to_admin=None,
    )
    body = _post(logged_in_client, "/announcements/new", data).get_data(as_text=True)
    assert "請至少選擇一個顯示對象" in body
    assert Announcement.query.count() == 0


def test_required_fields(logged_in_client, db):
    data = _form(logged_in_client, "/announcements/new", title="", content="")
    body = _post(logged_in_client, "/announcements/new", data).get_data(as_text=True)
    assert "公告標題為必填" in body
    assert "公告內容為必填" in body


def test_rejects_non_image_upload(logged_in_client, db):
    data = _form(
        logged_in_client,
        "/announcements/new",
        image=(io.BytesIO(b"<svg onload=alert(1)>"), "evil.png"),
    )
    body = _post(logged_in_client, "/announcements/new", data).get_data(as_text=True)
    assert "圖片格式需為 JPG、PNG 或 WebP" in body
    assert Announcement.query.count() == 0


def test_rejects_image_over_2mb(logged_in_client, db):
    big = PNG_BYTES + b"\x00" * (2 * 1024 * 1024)
    data = _form(logged_in_client, "/announcements/new", image=(io.BytesIO(big), "big.png"))
    body = _post(logged_in_client, "/announcements/new", data).get_data(as_text=True)
    assert "圖片大小不能超過 2MB" in body
    assert Announcement.query.count() == 0


# ---------- 編輯 / 刪除 ----------


def test_edit_replaces_and_removes_image(logged_in_client, db):
    item = _make_announcement(db, image_data=PNG_BYTES)
    url = f"/announcements/{item.id}/edit"

    data = _form(logged_in_client, url, title="改過的標題", image=(io.BytesIO(JPEG_BYTES), "b.jpg"))
    assert "公告已更新" in _post(logged_in_client, url, data).get_data(as_text=True)
    db.session.refresh(item)
    assert item.title == "改過的標題"
    assert item.image_mime == "image/jpeg"

    data = _form(logged_in_client, url, remove_image="y")
    _post(logged_in_client, url, data)
    db.session.refresh(item)
    assert item.image_mime is None
    assert item.image_data is None


def test_edit_without_new_image_keeps_existing(logged_in_client, db):
    item = _make_announcement(db, image_data=PNG_BYTES)
    url = f"/announcements/{item.id}/edit"
    _post(logged_in_client, url, _form(logged_in_client, url))
    db.session.refresh(item)
    assert item.image_mime == "image/png"


def test_delete_announcement(logged_in_client, db):
    item = _make_announcement(db)
    token = get_csrf_token(logged_in_client.get("/announcements/").get_data(as_text=True))
    resp = logged_in_client.post(
        f"/announcements/{item.id}/delete", data={"csrf_token": token}, follow_redirects=True
    )
    assert "已刪除" in resp.get_data(as_text=True)
    assert Announcement.query.count() == 0


def test_list_status_filter(logged_in_client, db):
    _make_announcement(db, title="上架中公告")
    _make_announcement(db, title="未上架公告", publish_offset=24, unpublish_offset=48)
    _make_announcement(db, title="已下架公告", publish_offset=-48, unpublish_offset=-1)

    body = logged_in_client.get("/announcements/?status=live").get_data(as_text=True)
    assert "上架中公告" in body
    assert "未上架公告" not in body
    assert "已下架公告" not in body

    body = logged_in_client.get("/announcements/?status=expired").get_data(as_text=True)
    assert "已下架公告" in body
    assert "上架中公告" not in body


# ---------- 登入後彈跳 ----------


def test_live_announcement_pops_up_once_after_login(client, db, active_student_user):
    _make_announcement(db, title="上架中公告")
    _make_announcement(db, title="未上架公告", publish_offset=24, unpublish_offset=48)
    _make_announcement(db, title="已下架公告", publish_offset=-48, unpublish_offset=-1)

    body = login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD).get_data(as_text=True)
    assert 'id="announcement-popup"' in body
    assert "上架中公告" in body
    assert "未上架公告" not in body
    assert "已下架公告" not in body

    body = client.get("/students/").get_data(as_text=True)
    assert 'id="announcement-popup"' not in body


def test_multiple_announcements_newest_first(client, db, active_student_user):
    _make_announcement(db, title="較早公告", publish_offset=-5)
    _make_announcement(db, title="較新公告", publish_offset=-1)
    body = login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD).get_data(as_text=True)
    assert body.count('class="announcement-slide"') == 2
    assert body.index("較新公告") < body.index("較早公告")


def test_popup_respects_audience(client, db, active_student_user, coach_user):
    _make_announcement(db, title="只給教練", show_to_student=False, show_to_admin=False)

    body = login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD).get_data(as_text=True)
    assert "只給教練" not in body

    client.post("/logout", data={"csrf_token": get_csrf_token(body)})
    body = login(client, COACH_USERNAME, COACH_PASSWORD).get_data(as_text=True)
    assert "只給教練" in body


def test_no_popup_without_live_announcements(client, db, active_student_user):
    body = login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD).get_data(as_text=True)
    assert 'id="announcement-popup"' not in body


def test_popup_waits_until_password_changed(client, db, active_student_user):
    active_student_user.must_change_password = True
    db.session.commit()
    _make_announcement(db, title="上架中公告")

    body = login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD).get_data(as_text=True)
    assert "首次登入請先修改密碼" in body
    assert 'id="announcement-popup"' not in body

    token = get_csrf_token(body)
    resp = client.post(
        "/change-password",
        data={
            "csrf_token": token,
            "current_password": ACTIVE_STUDENT_PASSWORD,
            "new_password": "BrandNew12345",
            "confirm_password": "BrandNew12345",
        },
        follow_redirects=True,
    )
    body = resp.get_data(as_text=True)
    assert "密碼已更新" in body
    assert "上架中公告" in body


def test_content_is_escaped(client, db, active_student_user):
    _make_announcement(db, title="<b>標題</b>", content="<script>alert(1)</script>")
    body = login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


# ---------- 圖片存取 ----------


def test_student_can_view_image_of_visible_live_announcement(student_client, db):
    item = _make_announcement(db, image_data=PNG_BYTES)
    resp = student_client.get(f"/announcements/{item.id}/image")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"
    assert resp.data == PNG_BYTES


def test_student_cannot_view_image_of_hidden_announcements(student_client, db):
    not_for_students = _make_announcement(db, image_data=PNG_BYTES, show_to_student=False)
    expired = _make_announcement(db, image_data=PNG_BYTES, publish_offset=-48, unpublish_offset=-1)
    assert student_client.get(f"/announcements/{not_for_students.id}/image").status_code == 404
    assert student_client.get(f"/announcements/{expired.id}/image").status_code == 404


def test_manager_can_preview_any_image(logged_in_client, db):
    item = _make_announcement(db, image_data=PNG_BYTES, publish_offset=24, unpublish_offset=48)
    assert logged_in_client.get(f"/announcements/{item.id}/image").status_code == 200


def test_image_requires_login(client, db):
    item = _make_announcement(db, image_data=PNG_BYTES)
    resp = client.get(f"/announcements/{item.id}/image")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
