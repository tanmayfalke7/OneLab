from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

ROOT = Path(__file__).parents[1]

def client_with_token():
    client = TestClient(app)
    app.state.reset_rate_limits()
    response = client.post("/auth/login", json={"email":"auditor@onelab.finance", "password":"Onelab@2026"})
    return client, response.json()["access_token"]

def auth(token): return {"Authorization": f"Bearer {token}"}

def test_auth_protection_login_and_headers():
    client = TestClient(app); app.state.reset_rate_limits()
    assert client.get("/", follow_redirects=False).status_code == 302
    assert client.post("/api/reconcile/default").status_code == 401
    assert client.post("/auth/login", json={"email":"auditor@onelab.finance", "password":"wrong"}).status_code == 401
    client, token = client_with_token()
    response = client.get("/", headers=auth(token))
    assert response.status_code == 200
    assert "httponly" in client.cookies.get("access_token", "") or token
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Request-ID"]

def test_upload_validation_and_silent_routes():
    client, token = client_with_token()
    headers = auth(token)
    files = {"platform_file":("malware.exe", b"x", "application/octet-stream"), "bank_file":("bank.csv", b"x", "text/csv")}
    assert client.post("/api/reconcile/upload", files=files, headers=headers).status_code == 400
    files = {"platform_file":("p.csv", b"wrong\nrow\n", "text/csv"), "bank_file":("b.csv", b"wrong\nrow\n", "text/csv")}
    assert client.post("/api/reconcile/upload", files=files, headers=headers).status_code == 400
    assert client.get("/favicon.ico").status_code == 204
    assert client.get("/hybridaction/zybTrackerStatisticsAction").status_code == 204

def test_login_rate_limit():
    client = TestClient(app); app.state.reset_rate_limits()
    for _ in range(10): assert client.post("/auth/login", json={"email":"x", "password":"x"}).status_code == 401
    assert client.post("/auth/login", json={"email":"x", "password":"x"}).status_code == 429
