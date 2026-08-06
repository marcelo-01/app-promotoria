from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import (
    LoginRequest, TokenResponse, UserResponse,
    RefreshRequest, AccessTokenResponse, ChangePasswordRequest,
)
from app.auth.service import AuthService
from app.core.dependencies import get_current_user
from app.core.security import hash_password, verify_password
from app.infrastructure.persistence.session import get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, session: AsyncSession = Depends(get_db_session)):
    user = await AuthService.authenticate_user(session, request.email, request.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Email ou senha inválidos")
    access_token, refresh_token = AuthService.create_tokens_for_user(user)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_token(body: RefreshRequest, session: AsyncSession = Depends(get_db_session)):
    access_token = await AuthService.refresh_access_token(session, body.refresh_token)
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Refresh token inválido ou expirado")
    return AccessTokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user=Depends(get_current_user)):
    return current_user


# PUT e POST no mesmo handler: o plano especifica PUT, mas o `stores/user.js`
# copiado verbatim do ERP chama POST. Aceitar os dois evita divergir de nenhum.
@router.api_route("/change-password", methods=["PUT", "POST"], status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    current_user.password_hash = hash_password(body.new_password)
    session.add(current_user)
    await session.commit()
