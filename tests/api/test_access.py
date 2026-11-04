import pytest
from flask import g

from app.api.http import success
from app.services.access import Identity, ResourceScope, require_resource


@pytest.fixture
def protected(make_app):
    state = {
        "identity": Identity("a", "class-a", frozenset({"sample"})),
        "broken": False,
        "writes": 0,
    }
    scopes = {
        "owned": ResourceScope("class-a", "a"),
        "private": ResourceScope("class-a", "b"),
        "cross": ResourceScope("class-b"),
    }

    def resolve():
        if state["broken"]:
            raise RuntimeError("synthetic dependency fault")
        return state["identity"]

    app = make_app(
        resolve_identity=resolve,
        policies={("sample", method): "sample" for method in ("GET", "POST")},
    )

    @app.route("/api/v1/samples/<sample_id>", methods=["GET", "POST"])
    def sample(sample_id):
        require_resource(g.identity, scopes.get(sample_id))
        from flask import request

        if request.method == "POST":
            state["writes"] += 1
        return success({"id": sample_id})

    @app.get("/unregistered")
    def unregistered():
        pytest.fail("默认拒绝入口的处理器被执行")

    return app.test_client(), state


def assert_refused(response, status, code):
    assert response.status_code == status
    payload = response.get_json()
    assert payload["code"] == code
    assert payload["data"] is None
    assert payload["request_id"] == response.headers["X-Request-ID"]
    return payload["message"]


def test_AC_N01_only_probes_are_public(make_app):
    app = make_app()
    assert {rule.rule: rule.methods for rule in app.url_map.iter_rules()} == {
        "/health": {"GET", "HEAD"},
        "/live": {"GET", "HEAD"},
    }
    client = app.test_client()
    assert client.get("/health").status_code == client.get("/live").status_code == 200


def test_AC_N02_current_identity_can_read_and_write(protected):
    client, state = protected
    response = client.get("/api/v1/samples/owned")
    assert response.json["code"] == 0
    assert response.json["data"] == {"id": "owned"}
    assert client.post("/api/v1/samples/owned").json["code"] == 0
    assert state["writes"] == 1


def test_AC_F01_unregistered_denied_even_with_valid_identity(protected):
    client, state = protected
    assert_refused(client.get("/unregistered"), 403, 1200)
    assert state["writes"] == 0


def test_AC_F01_alias_cannot_inherit_probe_public_access(make_app):
    app = make_app()
    app.add_url_rule("/alias", endpoint="live")
    assert_refused(app.test_client().get("/alias"), 403, 1200)


@pytest.mark.parametrize(
    "headers", [{}, {"role": "admin", "class_id": "class-a", "X-Identity": "a"}]
)
def test_AC_F02_missing_identity_and_forged_role(protected, headers):
    client, state = protected
    state["identity"] = None
    assert_refused(client.post("/api/v1/samples/owned", headers=headers), 401, 1100)
    assert state["writes"] == 0


def test_AC_F03_unknown_path_and_invalid_probe_methods(make_app):
    def probe():
        pytest.fail("错误请求进入健康探测")

    client = make_app(mysql=probe).test_client()
    assert_refused(client.get("/missing"), 404, 1300)
    for method in ("POST", "OPTIONS"):
        response = client.open("/health", method=method)
        assert response.status_code == 405
        assert set(response.headers["Allow"].split(", ")) == {"GET", "HEAD"}
        assert response.json["status"] == "method_not_allowed"
        assert response.json["request_id"] == response.headers["X-Request-ID"]


def test_AC_F04_revocation_uses_current_identity(protected):
    client, state = protected
    assert client.get("/api/v1/samples/owned").json["code"] == 0
    state["identity"] = Identity("a", "class-a", frozenset())
    assert_refused(
        client.post("/api/v1/samples/owned", headers={"role": "admin"}), 403, 1200
    )
    assert state["writes"] == 0


def test_AC_F05_out_of_scope_equals_missing(protected):
    client, state = protected
    for method in ("GET", "POST"):
        messages = [
            assert_refused(
                client.open(f"/api/v1/samples/{key}", method=method), 404, 1300
            )
            for key in ("private", "cross", "missing")
        ]
        assert len(set(messages)) == 1
    assert state["writes"] == 0


def test_AC_F06_identity_dependency_failure_closes_access(protected):
    client, state = protected
    state["broken"] = True
    response = client.post("/api/v1/samples/owned")
    assert_refused(response, 503, 1500)
    assert "synthetic dependency fault" not in response.get_data(as_text=True)
    assert state["writes"] == 0


def test_AC_B01_public_head_does_not_grant_protected_access(protected):
    client, state = protected
    state["identity"] = None
    for path in ("/health", "/live"):
        assert client.head(path).status_code == 200
        assert_refused(client.get("/api/v1/samples/owned"), 401, 1100)
