from fastapi import Depends, FastAPI, Header, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import AuthContext, require_action
from app.database import get_session
from app.models import ApprovalStatus
from app.schemas import (
    ApprovalRequestResponse,
    ApproveBody,
    CancelBody,
    CreateApprovalRequestBody,
    RejectBody,
)
from app.service import create_request, decide_request, get_request_or_404, to_response_model

app = FastAPI(title="approval-service", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready(session: Session = Depends(get_session)) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_approval_request(
    workspace_id: str,
    payload: CreateApprovalRequestBody,
    response: Response,
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_action("approval:create")),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> ApprovalRequestResponse:
    request, created = create_request(
        session,
        workspace_id=workspace_id,
        payload=payload,
        actor_user_id=auth.user_id,
        idempotency_key=x_idempotency_key,
    )
    if not created:
        # The client retried the same create request, so we return the existing record.
        response.status_code = status.HTTP_200_OK
        return ApprovalRequestResponse(**to_response_model(request))
    return ApprovalRequestResponse(**to_response_model(request))


@app.get(
    "/api/v1/workspaces/{workspace_id}/approval-requests",
    response_model=list[ApprovalRequestResponse],
)
def list_approval_requests(
    workspace_id: str,
    session: Session = Depends(get_session),
    _: AuthContext = Depends(require_action("approval:read")),
) -> list[ApprovalRequestResponse]:
    from app.models import ApprovalRequest

    items = (
        session.query(ApprovalRequest)
        .filter(ApprovalRequest.workspace_id == workspace_id)
        .order_by(ApprovalRequest.created_at.desc())
        .all()
    )
    return [ApprovalRequestResponse(**to_response_model(item)) for item in items]


@app.get(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}",
    response_model=ApprovalRequestResponse,
)
def get_approval_request(
    workspace_id: str,
    request_id: str,
    session: Session = Depends(get_session),
    _: AuthContext = Depends(require_action("approval:read")),
) -> ApprovalRequestResponse:
    request = get_request_or_404(session, workspace_id=workspace_id, request_id=request_id)
    return ApprovalRequestResponse(**to_response_model(request))


@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/approve",
    response_model=ApprovalRequestResponse,
)
def approve_request(
    workspace_id: str,
    request_id: str,
    payload: ApproveBody,
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_action("approval:decide")),
) -> ApprovalRequestResponse:
    request = get_request_or_404(session, workspace_id=workspace_id, request_id=request_id)
    updated = decide_request(
        session,
        request=request,
        actor_user_id=auth.user_id,
        new_status=ApprovalStatus.APPROVED,
        action="approved",
        event_type="ApprovalRequestApproved",
        comment=payload.comment,
    )
    return ApprovalRequestResponse(**to_response_model(updated))


@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/reject",
    response_model=ApprovalRequestResponse,
)
def reject_request(
    workspace_id: str,
    request_id: str,
    payload: RejectBody,
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_action("approval:decide")),
) -> ApprovalRequestResponse:
    request = get_request_or_404(session, workspace_id=workspace_id, request_id=request_id)
    updated = decide_request(
        session,
        request=request,
        actor_user_id=auth.user_id,
        new_status=ApprovalStatus.REJECTED,
        action="rejected",
        event_type="ApprovalRequestRejected",
        reason=payload.reason,
    )
    return ApprovalRequestResponse(**to_response_model(updated))


@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/cancel",
    response_model=ApprovalRequestResponse,
)
def cancel_request(
    workspace_id: str,
    request_id: str,
    payload: CancelBody,
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(require_action("approval:cancel")),
) -> ApprovalRequestResponse:
    request = get_request_or_404(session, workspace_id=workspace_id, request_id=request_id)
    updated = decide_request(
        session,
        request=request,
        actor_user_id=auth.user_id,
        new_status=ApprovalStatus.CANCELED,
        action="canceled",
        event_type="ApprovalRequestCanceled",
        reason=payload.reason,
    )
    return ApprovalRequestResponse(**to_response_model(updated))


