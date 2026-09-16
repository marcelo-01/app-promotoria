from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, Sequence
from app.core.security import verify_token
from app.infrastructure.persistence.session import get_db_session
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.tenant import Tenant, TenantStatus

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_db_session)
) -> User:
    token = credentials.credentials
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sem user_id",
        )
    
    try:
        user_id = UUID(user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    query = select(User).where(User.id == user_id)
    result = await session.execute(query)
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo",
        )
    
    return user


async def get_current_user_and_tenant(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get current user and their tenant ID"""
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário não possui tenant associado",
        )
    
    # Verify tenant exists
    query = select(Tenant).where(Tenant.id == user.tenant_id)
    result = await session.execute(query)
    tenant = result.scalars().first()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant não encontrado",
        )
    
    if tenant.status != TenantStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant inativo",
        )
    
    return {"user": user, "tenant_id": user.tenant_id}


def require_roles(*roles: str):
    """Factory de dependência que exige que o usuário tenha um dos papéis informados."""
    async def _check(
        context: Dict[str, Any] = Depends(get_current_user_and_tenant),
    ) -> Dict[str, Any]:
        user: User = context["user"]
        # Conjunto, e não `user.role`: quem acumula promotor e vendedor entra
        # nas rotas dos dois.
        if not (user.roles & set(roles)):
            allowed = ", ".join(roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso restrito. Papéis permitidos: {allowed}",
            )
        return context

    return _check

