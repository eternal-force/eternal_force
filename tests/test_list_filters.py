from tests.conftest import get_csrf_token


def test_students_list_restores_last_filters(logged_in_client):
    logged_in_client.get("/students/?search=王&status=inactive")
    resp = logged_in_client.get("/students/")
    assert resp.status_code == 302
    location = resp.headers["Location"]
    assert "status=inactive" in location
    assert "search=" in location and "search=&" not in location


def test_students_list_restores_page(logged_in_client):
    logged_in_client.get("/students/?search=&status=&page=2")
    resp = logged_in_client.get("/students/")
    assert resp.status_code == 302
    assert "page=2" in resp.headers["Location"]


def test_submitting_empty_filters_clears_remembered_state(logged_in_client):
    logged_in_client.get("/students/?search=王&status=inactive")
    logged_in_client.get("/students/?search=&status=")
    resp = logged_in_client.get("/students/")
    assert resp.status_code == 200


def test_accounts_list_restores_last_filters(logged_in_client):
    logged_in_client.get("/accounts/?search=coach&role=coach")
    resp = logged_in_client.get("/accounts/", follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert 'value="coach"' in body
    assert '<option value="coach" selected' in body


def test_exercises_list_restores_last_filters(logged_in_client):
    logged_in_client.get("/exercises/?search=深蹲&category=")
    resp = logged_in_client.get("/exercises/", follow_redirects=True)
    assert 'value="深蹲"' in resp.get_data(as_text=True)


def test_filters_are_remembered_per_page(logged_in_client):
    logged_in_client.get("/students/?search=王&status=")
    assert logged_in_client.get("/accounts/").status_code == 200
    assert logged_in_client.get("/exercises/").status_code == 200


def test_logout_clears_remembered_filters(logged_in_client):
    resp = logged_in_client.get("/students/?search=王&status=")
    token = get_csrf_token(resp.get_data(as_text=True))
    logged_in_client.post("/logout", data={"csrf_token": token})
    with logged_in_client.session_transaction() as sess:
        assert not any(k.startswith("list_filters:") for k in sess)
