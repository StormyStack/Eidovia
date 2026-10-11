from dataclasses import dataclass
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from db import db
from security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False, description="JWT Bearer token")

@dataclass(frozen=True)
class CurrentAdmin:
    user_id: str
    username: str
    is_admin: bool

async def get_current_admin(
    request: Request,
    _credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> CurrentAdmin:
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication token missing")

    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    user_id = decode_access_token(token)

    async with db.get_session() as session:
        result = await session.execute(
            text("SELECT username, is_admin FROM users WHERE user_id = :uid"),
            {"uid": user_id}
        )
        row = result.first()
        if not row:
            raise HTTPException(status_code=401, detail="User account does not exist")
        if not row.is_admin:
            raise HTTPException(status_code=403, detail="Forbidden: Administrative privileges required")

    return CurrentAdmin(user_id=user_id, username=row.username, is_admin=bool(row.is_admin))

def require_admin(admin: CurrentAdmin = Depends(get_current_admin)) -> CurrentAdmin:
    return admin
