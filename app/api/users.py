"""Gerenciamento de usuários/operadores do painel Escuta.

CRUD para a tabela `users`:
  GET    /api/users            — lista membros da org (+ operador ENV como owner virtual)
  POST   /api/users            — cria usuário (com senha) ou convite (sem senha)
  PATCH  /api/users/{id}       — edita nome/papel/status
  DELETE /api/users/{id}       — remove (não o operador ENV)
  POST   /api/users/{id}/set-password — define/troca senha (convite → ativo)

Requer require_operator em todas as rotas (injeta o panel key em main.py).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import _get_org
from app.api.auth import require_operator
from app.config import settings
from app.db import get_session
from app.models.core import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["users"])

_ROLES = {"owner", "admin", "member"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateUserIn(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=100)
    role: str = "member"
    password: str | None = Field(default=None, min_length=6, max_length=128)


class UpdateUserIn(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    role: str | None = None
    is_active: bool | None = None


class SetPasswordIn(BaseModel):
    password: str = Field(min_length=6, max_length=128)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_dict(u: User) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "is_active": u.is_active,
        "has_password": u.password_hash is not None,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "invited_by": u.invited_by,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _parse_uuid(user_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="id de usuário inválido")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(
    session: AsyncSession = Depends(get_session),
    operator: str = Depends(require_operator),
) -> list[dict[str, Any]]:
    """Lista todos os usuários da org + o operador ENV como entrada virtual."""
    org = await _get_org(session)
    rows = (
        await session.execute(
            select(User)
            .where(User.organization_id == org.id)
            .order_by(User.created_at)
        )
    ).scalars().all()

    result: list[dict[str, Any]] = []

    # Operador ENV aparece sempre como "owner" virtual (sem id no banco).
    env_user = settings.operator_user
    if env_user:
        result.append({
            "id": "env",
            "email": env_user,
            "name": env_user,
            "role": "owner",
            "is_active": True,
            "has_password": True,
            "last_login_at": None,
            "invited_by": None,
            "created_at": None,
            "_env_operator": True,
        })

    result.extend(_user_dict(u) for u in rows)
    return result


@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserIn,
    session: AsyncSession = Depends(get_session),
    operator: str = Depends(require_operator),
) -> dict[str, Any]:
    """Cria um novo usuário (com senha imediata) ou convite (sem senha).

    Se `password` vier no body, o usuário já pode logar. Sem senha, fica como
    convite pendente (has_password=false) até `POST /users/{id}/set-password`.
    """
    if body.role not in _ROLES:
        raise HTTPException(status_code=422, detail=f"papel inválido: {body.role!r} — use owner/admin/member")

    org = await _get_org(session)

    # Dedup por email dentro da org
    existing = (
        await session.execute(
            select(User).where(
                User.organization_id == org.id,
                User.email == str(body.email),
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="e-mail já cadastrado nesta organização")

    # Também impede conflito com o operador ENV
    if settings.operator_user and str(body.email) == settings.operator_user:
        raise HTTPException(status_code=409, detail="e-mail reservado pelo operador principal")

    pw_hash = _hash_password(body.password) if body.password else None
    user = User(
        organization_id=org.id,
        email=str(body.email),
        name=body.name,
        password_hash=pw_hash,
        role=body.role,
        is_active=True,
        invited_by=operator,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("audit user_create por=%s email=%s role=%s", operator, user.email, user.role)
    return _user_dict(user)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserIn,
    session: AsyncSession = Depends(get_session),
    operator: str = Depends(require_operator),
) -> dict[str, Any]:
    """Edita nome, papel ou status ativo/inativo de um usuário."""
    if user_id == "env":
        raise HTTPException(status_code=403, detail="operador principal não pode ser editado aqui — use as variáveis de ambiente")

    org = await _get_org(session)
    user = (
        await session.execute(
            select(User).where(
                User.organization_id == org.id,
                User.id == _parse_uuid(user_id),
            )
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="usuário não encontrado")

    if body.role is not None:
        if body.role not in _ROLES:
            raise HTTPException(status_code=422, detail=f"papel inválido: {body.role!r}")
        user.role = body.role
    if body.name is not None:
        user.name = body.name
    if body.is_active is not None:
        user.is_active = body.is_active

    await session.commit()
    await session.refresh(user)
    logger.info("audit user_update por=%s id=%s", operator, user_id)
    return _user_dict(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    operator: str = Depends(require_operator),
) -> None:
    """Remove um usuário da org."""
    if user_id == "env":
        raise HTTPException(status_code=403, detail="operador principal não pode ser removido aqui")

    org = await _get_org(session)
    user = (
        await session.execute(
            select(User).where(
                User.organization_id == org.id,
                User.id == _parse_uuid(user_id),
            )
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="usuário não encontrado")

    await session.delete(user)
    await session.commit()
    logger.info("audit user_delete por=%s id=%s email=%s", operator, user_id, user.email)


@router.post("/users/{user_id}/set-password")
async def set_password(
    user_id: str,
    body: SetPasswordIn,
    session: AsyncSession = Depends(get_session),
    operator: str = Depends(require_operator),
) -> dict[str, Any]:
    """Define ou troca a senha de um usuário (ativa um convite pendente)."""
    if user_id == "env":
        raise HTTPException(status_code=403, detail="use as variáveis de ambiente para trocar a senha do operador principal")

    org = await _get_org(session)
    user = (
        await session.execute(
            select(User).where(
                User.organization_id == org.id,
                User.id == _parse_uuid(user_id),
            )
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="usuário não encontrado")

    user.password_hash = _hash_password(body.password)
    user.is_active = True
    await session.commit()
    await session.refresh(user)
    logger.info("audit user_set_password por=%s id=%s", operator, user_id)
    return _user_dict(user)
