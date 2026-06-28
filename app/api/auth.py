"""Login de operador (JWT HS256) — emitido e validado SÓ no FastAPI.

Contrato (ver blueprint §a):
- POST /api/auth/login  {user,password} -> 200 {token,user,expires_in} | 401 | 503
- GET  /api/auth/me     (require_operator) -> 200 {user,exp} | 401
- POST /api/auth/logout -> 200 {ok:true}  (stateless; o logout REAL = apagar o cookie no BFF)

O JWT viaja num cookie httpOnly setado pelo BFF Next (o JS nunca vê o token). Cada
chamada do BFF às rotas protegidas reinjeta `Authorization: Bearer <jwt>` + `X-Panel-Key`.
`require_operator` lê o Bearer, valida HS256/exp/typ e devolve o `sub` (operador) para a
auditoria do "quem editou".

Segurança:
- Sem JWT_SECRET / ESCUTA_OPERATOR_USER / ESCUTA_OPERATOR_PASSWORD_HASH => login NÃO
  funciona (503). NÃO há fail-open de login (diferente do painel/webhook).
- bcrypt.checkpw com hash dummy quando o user não existe (mitiga user-enumeration/timing).
- Mensagem de erro IDÊNTICA para user errado e senha errada ("credenciais inválidas").
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._rate_limit import limiter
from app.config import settings
from app.db import get_session
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# TTL do token = 12h (pedido). Constante p/ login devolver `expires_in` e p/ o cookie
# usar o mesmo Max-Age.
JWT_TTL_SECONDS = 12 * 3600
_JWT_ALG = "HS256"
_TOKEN_TYP = "operator"  # literal `typ` — defende contra reuso do segredo p/ outro fim.

# Hash bcrypt dummy (de senha aleatória), gerado uma vez no import. Usado p/ executar um
# checkpw mesmo quando o user é desconhecido — o caminho de erro custa o mesmo do sucesso.
_DUMMY_HASH = bcrypt.hashpw(b"x" * 16, bcrypt.gensalt())


class LoginIn(BaseModel):
    user: str
    password: str


def _create_token(user: str) -> str:
    """Assina um JWT HS256 com os claims do contrato (A.1)."""
    secret = settings.jwt_secret
    if not secret:  # nunca deveria chegar aqui (login já barra antes), mas é defensivo.
        raise HTTPException(status_code=503, detail="login não configurado")
    now = datetime.now(timezone.utc)
    iat = int(now.timestamp())
    payload = {
        "sub": user,
        "iat": iat,
        "exp": iat + JWT_TTL_SECONDS,
        "typ": _TOKEN_TYP,
    }
    return jwt.encode(payload, secret, algorithm=_JWT_ALG)


def _decode_token(token: str) -> dict:
    """Decodifica/valida o JWT (exp obrigatório, typ=operator). Levanta HTTPException(401).

    Sem `jwt_secret` não há como validar o token: numa ROTA PROTEGIDA isso é "não
    autenticado" (401), nunca um 503 que vaze o estado da config. Fail-CLOSED: sempre
    nega. O 503 "login não configurado" é contrato EXCLUSIVO do POST /auth/login (lá o
    cliente PRECISA saber que o login não está configurado), via `_login_configured()`.
    """
    secret = settings.jwt_secret
    if not secret:
        raise HTTPException(status_code=401, detail="não autenticado")
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[_JWT_ALG],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="não autenticado")
    if claims.get("typ") != _TOKEN_TYP:
        raise HTTPException(status_code=401, detail="não autenticado")
    if not claims.get("sub"):
        raise HTTPException(status_code=401, detail="não autenticado")
    return claims


async def require_operator(authorization: str | None = Header(default=None)) -> str:
    """Dependency de IDENTIDADE: extrai e valida o JWT do header `Authorization: Bearer`.

    Retorna o `sub` (string do operador) para reuso na auditoria do "quem editou". Coexiste
    com require_panel_key (panel_key = "veio do nosso BFF"; operator = "tem operador logado").
    Erros: header ausente/sem `Bearer `/JWT inválido/expirado/typ!=operator -> 401.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="não autenticado")
    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="não autenticado")
    claims = _decode_token(token)
    return str(claims["sub"])


def _login_configured() -> bool:
    return bool(settings.jwt_secret)


@router.post("/auth/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Valida user+senha (bcrypt) e devolve o JWT.

    Tenta o operador ENV primeiro (backward-compat); se não bater, busca na tabela
    `users` pelo e-mail (suporte a múltiplos operadores). 401 mesma msg para user/senha
    errados (mitiga enumeração); 503 se JWT_SECRET não estiver configurado.
    """
    if not _login_configured():
        raise HTTPException(status_code=503, detail="login não configurado")

    pw_bytes = body.password.encode("utf-8")

    # --- Passo 1: operador ENV (mantém backward-compat) ---
    env_user = settings.operator_user or ""
    env_hash = (settings.operator_password_hash or "").encode("utf-8")
    env_match = bool(env_user) and (body.user == env_user)

    try:
        if env_match and env_hash:
            if bcrypt.checkpw(pw_bytes, env_hash):
                token = _create_token(env_user)
                return {"token": token, "user": env_user, "expires_in": JWT_TTL_SECONDS}
    except ValueError:
        logger.error("ESCUTA_OPERATOR_PASSWORD_HASH malformado")

    # --- Passo 2: usuário na tabela `users` ---
    db_user: User | None = None
    try:
        from app.api.admin import _get_org  # evita circular import no nível de módulo
        org = await _get_org(session)
        result = await session.execute(
            select(User).where(
                User.organization_id == org.id,
                User.email == body.user,
                User.is_active.is_(True),
            )
        )
        db_user = result.scalar_one_or_none()
    except Exception:  # noqa: BLE001
        # DB indisponível não deve vazar stack; ainda tentamos o dummy abaixo.
        pass

    if db_user and db_user.password_hash:
        try:
            if bcrypt.checkpw(pw_bytes, db_user.password_hash.encode("utf-8")):
                # Atualiza last_login_at de forma best-effort
                try:
                    db_user.last_login_at = datetime.now(timezone.utc)
                    await session.commit()
                except Exception:  # noqa: BLE001
                    pass
                token = _create_token(db_user.email)
                return {"token": token, "user": db_user.email, "expires_in": JWT_TTL_SECONDS}
        except (ValueError, Exception):  # noqa: BLE001
            pass

    # Dummy checkpw para timing consistente quando user é desconhecido.
    bcrypt.checkpw(pw_bytes, _DUMMY_HASH)
    raise HTTPException(status_code=401, detail="credenciais inválidas")


@router.get("/auth/me")
async def me(authorization: str | None = Header(default=None)) -> dict:
    """Identidade do token corrente. 401 sem/invalid token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="não autenticado")
    token = authorization[len("Bearer ") :].strip()
    claims = _decode_token(token)
    return {"user": str(claims["sub"]), "exp": int(claims["exp"])}


@router.post("/auth/logout")
async def logout() -> dict:
    """Stateless: o backend não mantém blacklist. O cookie é apagado pelo BFF. 200 sempre."""
    return {"ok": True}
