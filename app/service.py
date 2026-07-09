import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    ApprovalEvent,
    ApprovalRequest,
    ApprovalStatus,
    IdempotencyRecord,
    OutboxEvent,
)
from app.schemas import CreateApprovalRequestBody


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def build_create_payload_hash(payload: CreateApprovalRequestBody) -> str:
    payload_dict = {
        "sourceType": payload.source_type,
        "sourceId": payload.source_id,
        "title": payload.title,
        "description": payload.description,
        "reviewerUserIds": payload.reviewer_user_ids,
    }
    raw = json.dumps(payload_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def to_response_model(entity: ApprovalRequest) -> dict[str, object]:
    return {
        "id": entity.id,
        "workspaceId": entity.workspace_id,
        "sourceType": entity.source_type,
        "sourceId": entity.source_id,
        "title": entity.title,
        "description": entity.description,
        "reviewerUserIds": json.loads(entity.reviewer_user_ids_json),
        "status": entity.status,
        "createdByUserId": entity.created_by_user_id,
        "createdAt": entity.created_at,
        "updatedAt": entity.updated_at,
        "decidedAt": entity.decided_at,
    }


def _record_event_and_outbox(
    session: Session,
    *,
    request: ApprovalRequest,
    actor_user_id: str,
    action: str,
    event_type: str,
    comment: str | None = None,
    reason: str | None = None,
) -> None:
    session.add(
        ApprovalEvent(
            request_id=request.id,
            workspace_id=request.workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            comment=comment,
            reason=reason,
        )
    )

    payload = {
        "requestId": request.id,
        "workspaceId": request.workspace_id,
        "sourceType": request.source_type,
        "sourceId": request.source_id,
        "status": request.status,
        "actorUserId": actor_user_id,
        "action": action,
        "comment": comment,
        "reason": reason,
        "updatedAt": request.updated_at.isoformat() if request.updated_at else None,
    }
    session.add(
        OutboxEvent(
            workspace_id=request.workspace_id,
            aggregate_type="approval_request",
            aggregate_id=request.id,
            event_type=event_type,
            payload_json=json.dumps(payload, separators=(",", ":"), ensure_ascii=True),
        )
    )


def create_request(
    session: Session,
    *,
    workspace_id: str,
    payload: CreateApprovalRequestBody,
    actor_user_id: str,
    idempotency_key: str | None,
) -> tuple[ApprovalRequest, bool]:
    payload_hash = build_create_payload_hash(payload)

    if idempotency_key:
        existing = (
            session.query(IdempotencyRecord)
            .filter(
                IdempotencyRecord.workspace_id == workspace_id,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
            .one_or_none()
        )
        if existing:
            if existing.payload_hash != payload_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key is already used with different payload",
                )
            existing_request = (
                session.query(ApprovalRequest)
                .filter(
                    ApprovalRequest.id == existing.request_id,
                    ApprovalRequest.workspace_id == workspace_id,
                )
                .one()
            )
            return existing_request, False

    request = ApprovalRequest(
        workspace_id=workspace_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        title=payload.title,
        description=payload.description,
        reviewer_user_ids_json=json.dumps(payload.reviewer_user_ids, ensure_ascii=True),
        status=ApprovalStatus.PENDING.value,
        created_by_user_id=actor_user_id,
    )
    session.add(request)
    session.flush()
    session.refresh(request)

    _record_event_and_outbox(
        session,
        request=request,
        actor_user_id=actor_user_id,
        action="created",
        event_type="ApprovalRequestCreated",
    )

    if idempotency_key:
        session.add(
            IdempotencyRecord(
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                request_id=request.id,
                payload_hash=payload_hash,
            )
        )

    session.commit()
    session.refresh(request)
    return request, True


def get_request_or_404(session: Session, *, workspace_id: str, request_id: str) -> ApprovalRequest:
    request = (
        session.query(ApprovalRequest)
        .filter(
            ApprovalRequest.workspace_id == workspace_id,
            ApprovalRequest.id == request_id,
        )
        .one_or_none()
    )
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    return request


def decide_request(
    session: Session,
    *,
    request: ApprovalRequest,
    actor_user_id: str,
    new_status: ApprovalStatus,
    action: str,
    event_type: str,
    comment: str | None = None,
    reason: str | None = None,
) -> ApprovalRequest:
    if request.status != ApprovalStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Final decision already exists",
        )

    request.status = new_status.value
    request.decided_at = utcnow()
    request.updated_at = utcnow()

    _record_event_and_outbox(
        session,
        request=request,
        actor_user_id=actor_user_id,
        action=action,
        event_type=event_type,
        comment=comment,
        reason=reason,
    )
    session.commit()
    session.refresh(request)
    return request
