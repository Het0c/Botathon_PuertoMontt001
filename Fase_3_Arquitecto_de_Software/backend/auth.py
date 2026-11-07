import secrets
from collections.abc import Callable

import jwt
from fastapi import Depends, Header, HTTPException, status

from .config import get_settings
from .schemas import Principal, Role


def rpa_principal(authorization: str | None = Header(default=None)) -> Principal:
    settings = get_settings()
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if not token or not secrets.compare_digest(token, settings.rpa_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial RPA inválida")
    return Principal(actor_id="blue-prism", role=Role.RPA, origin="blue_prism")


def user_principal(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_role: Role | None = Header(default=None),
) -> Principal:
    settings = get_settings()
    bearer = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if settings.supabase_jwt_secret and bearer:
        try:
            claims = jwt.decode(
                bearer,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
            metadata = claims.get("app_metadata") or {}
            role = Role(metadata.get("app_role"))
            return Principal(actor_id=str(claims["sub"]), role=role, origin="user")
        except (jwt.PyJWTError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT de Supabase inválido") from exc
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticación Supabase JWT no configurada",
        )
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.user_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial de usuario inválida")
    if not x_user_id or not x_role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identidad y rol requeridos")
    return Principal(actor_id=x_user_id, role=x_role, origin="user")


def require_roles(*roles: Role) -> Callable:
    def dependency(principal: Principal = Depends(user_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permisos insuficientes")
        return principal

    return dependency
