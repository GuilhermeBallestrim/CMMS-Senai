"""SENAI CMMS web application and HTML interface."""

from contextlib import asynccontextmanager
from pathlib import Path
import secrets

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from backend import models
from backend.api import router as api_router
from backend.config import settings
from backend.database import Base, SessionLocal, engine, get_db
from backend.security import verify_password


ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for name in ("Usinagem", "Plástico", "Utilidades", "Marcenaria"):
            if not db.scalar(select(models.Sector).where(models.Sector.name == name)):
                db.add(models.Sector(name=name))
        db.commit()
    yield


app = FastAPI(title="SENAI CMMS", description="Sistema de gestão de manutenção", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=settings.session_https_only,
    session_cookie="cmms_session",
    max_age=60 * 60 * 8,
)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
templates = Jinja2Templates(directory=FRONTEND_DIR / "templates")
app.include_router(api_router)


def render(request: Request, template: str, *, notice: str | None = None, status_code: int = 200):
    csrf_token = request.session.get("csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = csrf_token
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={
            "notice": notice or request.query_params.get("notice", ""),
            "csrf_token": csrf_token,
            "current_user": request.session.get("user"),
        },
        status_code=status_code,
    )


def page(request: Request, template: str, *, role: str | None = None):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    with SessionLocal() as db:
        account = db.get(models.User, user_id)
        if not account or not account.is_active:
            request.session.clear()
            return RedirectResponse("/login", status_code=303)
        user = {"id": account.id, "name": account.name, "email": account.email, "role": account.role}
        request.session["user"] = user
    if role == "administrator" and user["role"] != "administrator":
        return RedirectResponse("/dashboard?notice=Acesso%20restrito%20ao%20administrador.", status_code=303)
    return render(request, template)


@app.get("/", include_in_schema=False)
async def home():
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/login", name="login")
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "login.html")


@app.post("/login", name="login_submit")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    from hmac import compare_digest

    expected = request.session.get("csrf_token", "")
    if not expected or not compare_digest(expected, csrf_token):
        return render(request, "login.html", notice="Sessão expirada. Tente novamente.", status_code=403)
    user = db.scalar(select(models.User).where(models.User.email == email.strip().lower()))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return render(request, "login.html", notice="E-mail ou senha inválidos.", status_code=401)
    request.session.clear()
    request.session.update({
        "user_id": user.id,
        "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role},
        "csrf_token": secrets.token_urlsafe(32),
    })
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/logout", name="logout")
async def logout(request: Request, csrf_token: str = Form(...)):
    from hmac import compare_digest

    expected = request.session.get("csrf_token", "")
    if not expected or not compare_digest(expected, csrf_token):
        return RedirectResponse("/dashboard?notice=Sessão%20expirada.", status_code=303)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/recuperar-senha", include_in_schema=False)
async def password_recovery(request: Request):
    return render(request, "login.html", notice="Solicite ao administrador a redefinição da sua senha.")


@app.get("/dashboard")
async def dashboard(request: Request): return page(request, "dashboard.html")


@app.get("/chamados")
async def chamados(request: Request): return page(request, "chamados/lista.html")


@app.get("/chamados/novo")
async def novo_chamado(request: Request): return page(request, "chamados/novo.html")


@app.get("/chamados/detalhe")
async def detalhe_chamado(request: Request): return page(request, "chamados/detalhe.html")


@app.get("/equipamentos")
async def equipamentos(request: Request): return page(request, "equipamentos/lista.html")


@app.get("/equipamentos/novo")
async def novo_equipamento(request: Request): return page(request, "equipamentos/novo.html", role="administrator")


@app.get("/equipamentos/detalhe")
async def detalhe_equipamento(request: Request): return page(request, "equipamentos/detalhe.html")


@app.get("/ordens-servico")
async def ordens_servico(request: Request): return page(request, "ordens_servico/lista.html", role="administrator")


@app.get("/ordens-servico/detalhe")
async def detalhe_ordem_servico(request: Request): return page(request, "ordens_servico/detalhe.html", role="administrator")


@app.get("/historico")
async def historico(request: Request): return page(request, "historico/lista.html", role="administrator")


@app.get("/solicitacoes")
async def solicitacoes(request: Request): return page(request, "solicitacoes/lista.html")


@app.get("/solicitacoes/nova")
async def nova_solicitacao(request: Request): return page(request, "solicitacoes/nova.html")


@app.get("/solicitacoes/detalhe")
async def detalhe_solicitacao(request: Request): return page(request, "solicitacoes/detalhe.html")


@app.get("/indicadores")
async def indicadores(request: Request): return page(request, "indicadores/lista.html", role="administrator")


@app.get("/notificacoes")
async def notificacoes(request: Request): return page(request, "notificacoes/lista.html")


@app.get("/configuracoes")
async def configuracoes(request: Request): return page(request, "configuracoes/lista.html", role="administrator")
