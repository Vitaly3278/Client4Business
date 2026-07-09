from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import app


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_session() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def auth_headers(workspace: str, actions: str, user: str = "usr_admin") -> dict[str, str]:
    return {
        "X-Auth-Workspace-Id": workspace,
        "X-Auth-User-Id": user,
        "X-Auth-Actions": actions,
    }


def create_payload() -> dict[str, object]:
    return {
        "sourceType": "publication",
        "sourceId": "pub_123",
        "title": "Instagram reel draft",
        "description": "Needs final approval",
        "reviewerUserIds": ["usr_1", "usr_2"],
    }


def test_create_and_get_request(client: TestClient) -> None:
    create_res = client.post(
        "/api/v1/workspaces/ws_1/approval-requests",
        json=create_payload(),
        headers=auth_headers("ws_1", "approval:create,approval:read"),
    )
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["status"] == "pending"

    get_res = client.get(
        f"/api/v1/workspaces/ws_1/approval-requests/{created['id']}",
        headers=auth_headers("ws_1", "approval:read"),
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == created["id"]


def test_workspace_isolation(client: TestClient) -> None:
    create_res = client.post(
        "/api/v1/workspaces/ws_1/approval-requests",
        json=create_payload(),
        headers=auth_headers("ws_1", "approval:create"),
    )
    request_id = create_res.json()["id"]

    get_res = client.get(
        f"/api/v1/workspaces/ws_2/approval-requests/{request_id}",
        headers=auth_headers("ws_2", "approval:read"),
    )
    assert get_res.status_code == 404


def test_idempotency_prevents_duplicates(client: TestClient) -> None:
    headers = auth_headers("ws_1", "approval:create")
    headers["X-Idempotency-Key"] = "idem-1"

    first = client.post(
        "/api/v1/workspaces/ws_1/approval-requests",
        json=create_payload(),
        headers=headers,
    )
    second = client.post(
        "/api/v1/workspaces/ws_1/approval-requests",
        json=create_payload(),
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


def test_final_state_cannot_change(client: TestClient) -> None:
    create_res = client.post(
        "/api/v1/workspaces/ws_1/approval-requests",
        json=create_payload(),
        headers=auth_headers("ws_1", "approval:create"),
    )
    request_id = create_res.json()["id"]

    approve_res = client.post(
        f"/api/v1/workspaces/ws_1/approval-requests/{request_id}/approve",
        json={"comment": "Approved"},
        headers=auth_headers("ws_1", "approval:decide"),
    )
    assert approve_res.status_code == 200

    reject_res = client.post(
        f"/api/v1/workspaces/ws_1/approval-requests/{request_id}/reject",
        json={"reason": "Too late"},
        headers=auth_headers("ws_1", "approval:decide"),
    )
    assert reject_res.status_code == 409
