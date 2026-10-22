"""Bearer-token auth shared by every endpoint except /api/health."""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def require_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    tokens: list[str] = request.app.state.settings.app_tokens
    supplied = credentials.credentials if credentials else ""
    # compare_digest against every token so timing doesn't reveal which one matched.
    valid = False
    for token in tokens:
        valid |= hmac.compare_digest(supplied.encode(), token.encode())
    if not supplied or not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return supplied
