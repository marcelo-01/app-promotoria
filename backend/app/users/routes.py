from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.infrastructure.persistence.session import get_db_session
from app.users.schemas import SetPasswordRequest, UserCreate, UserResponse
from app.users.service import UsersService

router = APIRouter(prefix="/users", tags=["users"])

_ADMIN = ("admin", "supervisor")


@router.get("", response_model=list[UserResponse])
async def list_users(
    role: Optional[str] = Query(None, description="Filtrar por papel: promoter | admin"),
    search: Optional[str] = None,
    active_only: bool = Query(False),
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    return await UsersService.list(
        session, context["tenant_id"], role=role, search=search, active_only=active_only
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    return await UsersService.create(session, context["tenant_id"], payload)


@router.put("/{user_id}/password", status_code=204)
async def set_user_password(
    user_id: UUID,
    payload: SetPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
    context: dict = Depends(require_roles(*_ADMIN)),
):
    await UsersService.set_password(
        session, context["tenant_id"], user_id, payload.new_password
    )
