import re

from app.models import LoginSession, PageView

from .conftest import ACTIVE_STUDENT_PASSWORD, ACTIVE_STUDENT_USERNAME, get_csrf_token, login

FINISH_URL_RE = re.compile(r'data-page-view-url="(/page-views/[0-9a-f]{32}/finish)"')


def _open(client, url):
    """開頁面並關閉回應：頁面瀏覽紀錄在回應送完(關閉)後才寫入，正式環境由 gunicorn 關閉。"""
    resp = client.get(url)
    resp.close()
    return resp


def _finish_url(html):
    match = FINISH_URL_RE.search(html)
    assert match, "頁面上找不到頁面瀏覽回報網址"
    return match.group(1)


def test_login_creates_login_session(client, db, admin_user):
    login(client)
    sessions = LoginSession.query.filter_by(user_id=admin_user.id).all()
    assert len(sessions) == 1
    assert sessions[0].logout_at is None
    assert sessions[0].duration_seconds is not None


def test_failed_login_creates_no_login_session(client, db, admin_user):
    login(client, password="wrong-password")
    assert LoginSession.query.count() == 0


def test_logout_records_logout_time(logged_in_client, db, admin_user):
    resp = logged_in_client.get("/students/")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post("/logout", data={"csrf_token": token})
    db.session.expire_all()
    assert LoginSession.query.filter_by(user_id=admin_user.id).one().logout_at is not None


def test_page_view_recorded_with_url_and_login_session(logged_in_client, db, admin_user):
    _open(logged_in_client, "/students/?page=1")
    login_session = LoginSession.query.filter_by(user_id=admin_user.id).one()
    view = PageView.query.filter_by(url="/students/?page=1").one()
    assert view.user_id == admin_user.id
    assert view.login_session_id == login_session.id
    assert view.endpoint == "students.list_students"
    assert view.load_ms is None and view.duration_ms is None


def test_page_view_is_written_only_after_response_closes(logged_in_client, db):
    before = PageView.query.count()
    resp = logged_in_client.get("/students/")
    assert PageView.query.count() == before
    resp.close()
    assert PageView.query.count() == before + 1


def test_not_logged_in_pages_and_errors_are_not_recorded(client, db, admin_user):
    _open(client, "/login")
    assert PageView.query.count() == 0
    login(client)
    before = PageView.query.count()
    _open(client, "/no-such-page")
    _open(client, "/healthz")
    _open(client, "/")  # 導向，不記
    assert PageView.query.count() == before


def test_finish_page_view_records_load_and_duration(logged_in_client, db):
    url = _finish_url(_open(logged_in_client, "/students/").get_data(as_text=True))
    resp = logged_in_client.post(url, json={"load_ms": 350, "duration_ms": 12000})
    assert resp.status_code == 204
    # 再回報一次較小的停留時間不會倒退
    logged_in_client.post(url, json={"load_ms": 350, "duration_ms": 5000})
    db.session.expire_all()
    view = PageView.query.filter(PageView.url == "/students/").order_by(PageView.id.desc()).first()
    assert view.load_ms == 350
    assert view.duration_ms == 12000


def test_finish_page_view_ignores_invalid_values(logged_in_client, db):
    url = _finish_url(_open(logged_in_client, "/students/").get_data(as_text=True))
    logged_in_client.post(url, json={"load_ms": -1, "duration_ms": "abc"})
    db.session.expire_all()
    view = PageView.query.filter(PageView.url == "/students/").order_by(PageView.id.desc()).first()
    assert view.load_ms is None and view.duration_ms is None


def _logout(client):
    token = get_csrf_token(client.get("/students/").get_data(as_text=True))
    client.post("/logout", data={"csrf_token": token})


def test_cannot_finish_another_users_page_view(logged_in_client, db, active_student_user):
    client = logged_in_client
    url = _finish_url(_open(client, "/students/").get_data(as_text=True))
    _logout(client)
    assert client.post(url, json={"duration_ms": 999}).status_code == 401
    login(client, ACTIVE_STUDENT_USERNAME, ACTIVE_STUDENT_PASSWORD)
    assert client.post(url, json={"duration_ms": 999}).status_code == 404
    db.session.expire_all()
    view = PageView.query.filter(PageView.url == "/students/").order_by(PageView.id.asc()).first()
    assert view.duration_ms is None
