from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SourceType = Literal["publication", "scenario", "edit", "external"]
StatusType = Literal["pending", "approved", "rejected", "canceled"]


class CreateApprovalRequestBody(BaseModel):
    source_type: SourceType = Field(alias="sourceType")
    source_id: str = Field(min_length=1, max_length=128, alias="sourceId")
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    reviewer_user_ids: list[str] = Field(min_length=1, alias="reviewerUserIds")

    model_config = ConfigDict(populate_by_name=True)


class ApproveBody(BaseModel):
    comment: str | None = Field(default=None, max_length=5000)


class RejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=5000)


class CancelBody(BaseModel):
    reason: str = Field(min_length=1, max_length=5000)


class ApprovalRequestResponse(BaseModel):
    id: str
    workspace_id: str = Field(alias="workspaceId")
    source_type: SourceType = Field(alias="sourceType")
    source_id: str = Field(alias="sourceId")
    title: str
    description: str | None = None
    reviewer_user_ids: list[str] = Field(alias="reviewerUserIds")
    status: StatusType
    created_by_user_id: str = Field(alias="createdByUserId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    decided_at: datetime | None = Field(default=None, alias="decidedAt")

    model_config = ConfigDict(populate_by_name=True)
