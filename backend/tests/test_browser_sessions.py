from app.core.security import COOKIE_NAME
from tests.test_identity import API, BROWSER, bearer, signed_in


def test_old_tab_cannot_refresh_or_remove_new_tabs_cookie(client, app):
    a = signed_in(client, "tab_alice")
    b = signed_in(client, "tab_bob")
    cookie_b = client.cookies.get(COOKIE_NAME)
    # A holds its original in-memory token while the browser now holds B's cookie.
    assert client.get(API + "/users/me", headers=bearer(a)).json()["username"] == "tab_alice"
    old_refresh = client.post(API + "/auth/refresh", headers={**BROWSER, **bearer(a)})
    old_logout = client.post(API + "/auth/logout", headers={**BROWSER, **bearer(a)})
    assert old_refresh.status_code == 401
    assert old_logout.status_code == 204
    assert "set-cookie" not in old_refresh.headers
    assert "set-cookie" not in old_logout.headers
    assert client.cookies.get(COOKIE_NAME) == cookie_b
    assert client.get(API + "/users/me", headers=bearer(a)).status_code == 401
    assert client.get(API + "/users/me", headers=bearer(b)).json()["username"] == "tab_bob"
    assert client.post(API + "/auth/refresh", headers={**BROWSER, **bearer(b)}).json()["user"]["username"] == "tab_bob"
