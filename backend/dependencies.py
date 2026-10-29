from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from backend.database import db
from backend.models import TABLE_USERS


def get_current_user(request: Request) -> dict:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação necessária.")
    response = db.client.table(TABLE_USERS).select("*").eq("id", user_id).execute()
    if not response.data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão inválida.")
    user = response.data[0]
    if not user.get("is_active"):
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão inválida.")
    return user


def require_roles(*roles: str) -> Callable:
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seu perfil não permite esta operação.")
        return user
    return dependency
