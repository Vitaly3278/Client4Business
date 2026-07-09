from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Path, status
from pydantic import BaseModel


class AuthContext(BaseModel):
    workspace_id: str
    user_id: str
    actions: set[str]


def _parse_auth_context(
    x_auth_workspace_id: str | None,
    x_auth_user_id: str | None,
    x_auth_actions: str | None,
) -> AuthContext:
    if not x_auth_workspace_id or not x_auth_user_id or not x_auth_actions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing auth headers",
        )
    actions = {action.strip() for action in x_auth_actions.split(",") if action.strip()}
    return AuthContext(
        workspace_id=x_auth_workspace_id,
        user_id=x_auth_user_id,
        actions=actions,
    )


def require_action(action: str) -> Callable[..., AuthContext]:
    def _dependency(
        workspace_id: str = Path(...),
        x_auth_workspace_id: str | None = Header(default=None, alias="X-Auth-Workspace-Id"),
        x_auth_user_id: str | None = Header(default=None, alias="X-Auth-User-Id"),
        x_auth_actions: str | None = Header(default=None, alias="X-Auth-Actions"),
    ) -> AuthContext:
        ctx = _parse_auth_context(x_auth_workspace_id, x_auth_user_id, x_auth_actions)
        if ctx.workspace_id != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Workspace access denied",
            )
        if action not in ctx.actions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing action '{action}'",
            )
        return ctx

    return _dependency


def parse_general_auth(
    x_auth_workspace_id: str | None = Header(default=None, alias="X-Auth-Workspace-Id"),
    x_auth_user_id: str | None = Header(default=None, alias="X-Auth-User-Id"),
    x_auth_actions: str | None = Header(default=None, alias="X-Auth-Actions"),
) -> AuthContext:
    return _parse_auth_context(x_auth_workspace_id, x_auth_user_id, x_auth_actions)
