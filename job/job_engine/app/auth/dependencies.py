# app/auth/dependencies.py
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User, UserRole
from app.auth.utils import decode_token

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


class RoleRequired:
    """Dependency that enforces minimum role level."""

    _role_hierarchy = {
        UserRole.VIEWER: 0,
        UserRole.OPERATOR: 1,
        UserRole.ADMIN: 2,
    }

    def __init__(self, minimum_role: UserRole):
        self.minimum_role = minimum_role

    def __call__(self, user: User = Depends(get_current_user)) -> User:
        user_level = self._role_hierarchy.get(user.role, 0)
        required_level = self._role_hierarchy.get(self.minimum_role, 0)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{self.minimum_role.value}' or higher required",
            )
        return user
