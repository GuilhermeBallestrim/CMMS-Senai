"""Authentication routes (web interface)."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from hmac import compare_digest
import secrets

from backend.database import db
from backend.security import verify_password
from web.common import U, check_rate_limit, render_template, validate_csrf

router = APIRouter()


@router.get("/login")
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dashboard", status_code=303)
    return render_template(request, "login.html")


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    expected = request.session.get("csrf_token", "")
    if not expected or not compare_digest(expected, csrf_token):
        return render_template(request, "login.html", notice="Sessão expirada. Tente novamente.", status_code=403)
    if not check_rate_limit(f"login:{email.strip().lower()}"):
        return render_template(request, "login.html", notice="Muitas tentativas. Tente novamente em instantes.", status_code=429)
    resp = db.client.table(U).select("*").eq("email", email.strip().lower()).execute()
    user = resp.data[0] if resp.data else None
    if not user or not user.get("is_active") or not verify_password(password, user["password_hash"]):
        return render_template(request, "login.html", notice="E-mail ou senha inválidos.", status_code=401)
    request.session.clear()
    request.session.update({
        "user_id": user["id"],
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
        "csrf_token": secrets.token_urlsafe(32),
    })
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout")
async def logout(request: Request, csrf_token: str = Form(...)):
    expected = request.session.get("csrf_token", "")
    if not expected or not compare_digest(expected, csrf_token):
        return RedirectResponse("/dashboard?notice=Sessão%20expirada.", status_code=303)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/recuperar-senha")
async def password_recovery(request: Request):
    return render_template(request, "login.html", notice="Solicite ao administrador a redefinição da sua senha.")