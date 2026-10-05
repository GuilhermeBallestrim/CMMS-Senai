"""SENAI CMMS web application and HTML interface."""

from contextlib import asynccontextmanager
from pathlib import Path
import secrets
from hmac import compare_digest
from datetime import date, datetime, timedelta, timezone
import re

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from backend import models
from backend.api import make_number, router as api_router
from backend.config import settings
from backend.database import Base, SessionLocal, engine, get_db, migrate_schema
from backend.dependencies import get_current_user
from backend.security import hash_password
from backend.services import notify_administrators, notify_user
from backend.storage import file_path, save_image, save_pdf
from backend.security import verify_password


ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    with SessionLocal() as db:
        for name in ("Usinagem", "Plástico", "Utilidades", "Marcenaria"):
            if not db.scalar(select(models.Sector).where(models.Sector.name == name)):
                db.add(models.Sector(name=name))
        if not db.get(models.UnitSettings, 1):
            db.add(models.UnitSettings(id=1))
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
TZ_OFFSETS = {"America/Sao_Paulo": -3, "America/Manaus": -4, "America/Belem": -3,
              "America/Fortaleza": -3, "America/Recife": -3, "America/Rio_Branco": -5, "UTC": 0}


def format_local_datetime(value: datetime | None, zone_name: str, pattern: str = "%d/%m/%Y %H:%M") -> str:
    if value is None:
        return "—"
    utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    local_zone = timezone(timedelta(hours=TZ_OFFSETS.get(zone_name, -3)))
    return utc_value.astimezone(local_zone).strftime(pattern)


templates.env.globals["local_datetime"] = format_local_datetime
app.include_router(api_router)


def render(request: Request, template: str, *, notice: str | None = None, status_code: int = 200, context: dict | None = None):
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
            "notification_count": _unread_notifications(request.session.get("user_id")),
            "unit_settings": _unit_preferences(),
            **(context or {}),
        },
        status_code=status_code,
    )


def _unread_notifications(user_id: int | None) -> int:
    if not user_id:
        return 0
    with SessionLocal() as db:
        return db.scalar(select(func.count(models.Notification.id)).where(
            models.Notification.user_id == user_id, models.Notification.is_read.is_(False)
        )) or 0


def _unit_preferences() -> models.UnitSettings:
    with SessionLocal() as db:
        return db.get(models.UnitSettings, 1) or models.UnitSettings(id=1)


def page(request: Request, template: str, *, role: str | None = None, context: dict | None = None):
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
    return render(request, template, context=context)


def validate_csrf(request: Request, submitted: str) -> None:
    expected = request.session.get("csrf_token", "")
    if not expected or not compare_digest(expected, submitted):
        raise HTTPException(status_code=403, detail="Sessão expirada. Atualize a página e tente novamente.")


def status_class(value: str) -> str:
    return {
        "Aberto": "status--gray", "Em análise": "status--blue", "Em manutenção": "status--orange",
        "Aguardando peça": "status--yellow", "Concluído": "status--green", "Concluída": "status--green",
        "Cancelado": "status--red", "Aguardando início": "status--blue", "Em execução": "status--orange",
        "Aprovada": "status--green", "Recusada": "status--red",
    }.get(value, "status--gray")


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
async def dashboard(request: Request):
    with SessionLocal() as db:
        user = request.session.get("user")
        calls_query = select(models.MaintenanceCall).options(
            selectinload(models.MaintenanceCall.equipment), selectinload(models.MaintenanceCall.requester)
        ).order_by(models.MaintenanceCall.created_at.desc())
        calls = db.scalars(calls_query).all()
        if user and user["role"] == "professor":
            calls = [call for call in calls if call.requester_id == user["id"]]
        total = len(calls)
        open_count = sum(call.status not in {"Concluído", "Cancelado"} for call in calls)
        analysis_count = sum(call.status in {"Aberto", "Em análise"} for call in calls)
        completed_count = sum(call.status == "Concluído" for call in calls)
        orders = db.scalars(select(models.WorkOrder).options(
            selectinload(models.WorkOrder.call).selectinload(models.MaintenanceCall.equipment),
            selectinload(models.WorkOrder.responsible),
        ).where(models.WorkOrder.status != "Concluída").order_by(models.WorkOrder.id.desc())).all()
        return page(request, "dashboard.html", context={
            "recent_calls": calls[:5], "open_count": open_count, "analysis_count": analysis_count,
            "completed_count": completed_count, "total_calls": total, "active_orders": orders[:4],
            "priority_counts": {priority: sum(call.priority == priority and call.status not in {"Concluído", "Cancelado"} for call in calls) for priority in ("Crítica", "Alta", "Média", "Baixa")},
            "status_class": status_class,
        })


@app.get("/chamados")
async def chamados(request: Request):
    with SessionLocal() as db:
        items = db.scalars(select(models.MaintenanceCall).options(
            selectinload(models.MaintenanceCall.equipment), selectinload(models.MaintenanceCall.requester)
        ).order_by(models.MaintenanceCall.created_at.desc())).all()
        user = request.session.get("user")
        if user and user["role"] == "professor":
            items = [call for call in items if call.requester_id == user["id"]]
        counts = {status: 0 for status in ("Aberto", "Em análise", "Em manutenção", "Aguardando peça", "Concluído")}
        for call in items:
            if call.status in counts:
                counts[call.status] += 1
        return page(request, "chamados/lista.html", context={"calls": items, "call_counts": counts, "status_class": status_class})


@app.get("/chamados/novo")
async def novo_chamado(request: Request):
    with SessionLocal() as db:
        equipment = db.scalars(select(models.Equipment).order_by(models.Equipment.name)).all()
        return page(request, "chamados/novo.html", context={"equipment_items": equipment})


@app.post("/chamados", name="criar_chamado")
async def criar_chamado(
    request: Request,
    equipment_id: int = Form(...),
    description: str = Form(...),
    priority: str = Form(...),
    csrf_token: str = Form(...),
    photo: UploadFile | None = File(None),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    if priority not in {"Baixa", "Média", "Alta", "Crítica"} or not 10 <= len(description.strip()) <= 5000:
        return RedirectResponse("/chamados/novo?notice=Confira%20a%20descrição%20e%20a%20prioridade.", status_code=303)
    with SessionLocal() as db:
        if not db.get(models.Equipment, equipment_id):
            return RedirectResponse("/chamados/novo?notice=Equipamento%20não%20encontrado.", status_code=303)
        photo_name, photo_mime = await save_image(photo, "calls")
        call = models.MaintenanceCall(
            number=make_number("CH"),
            equipment_id=equipment_id, requester_id=user["id"], description=description.strip(), priority=priority,
            photo_name=photo_name, photo_mime=photo_mime,
        )
        db.add(call)
        db.flush()
        prefs = db.get(models.UnitSettings, 1)
        if prefs is None or prefs.notify_admin_new_call:
            notify_administrators(db, "Novo chamado", f"{call.number}: prioridade {priority}.", f"/chamados/detalhe?id={call.id}", "warning" if priority in {"Alta", "Crítica"} else "info")
        db.commit()
    return RedirectResponse("/chamados?notice=Chamado%20registrado%20com%20sucesso.", status_code=303)


@app.get("/chamados/detalhe")
async def detalhe_chamado(request: Request, id: int | None = None):
    with SessionLocal() as db:
        call = db.scalar(select(models.MaintenanceCall).options(
            selectinload(models.MaintenanceCall.equipment).selectinload(models.Equipment.sector),
            selectinload(models.MaintenanceCall.requester), selectinload(models.MaintenanceCall.work_order),
        ).where(models.MaintenanceCall.id == id)) if id else None
        user = request.session.get("user")
        if not call or (user and user["role"] == "professor" and call.requester_id != user["id"]):
            return RedirectResponse("/chamados?notice=Chamado%20não%20encontrado.", status_code=303)
        return page(request, "chamados/detalhe.html", context={"call": call, "status_class": status_class(call.status)})


@app.post("/chamados/{call_id}/aprovar")
async def aprovar_chamado(request: Request, call_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem aprovar chamados.")
    with SessionLocal() as db:
        call = db.get(models.MaintenanceCall, call_id)
        if not call:
            raise HTTPException(404, "Chamado não encontrado.")
        if not call.work_order:
            order = models.WorkOrder(
                number=make_number("OS"),
                call=call, responsible_id=user["id"], status="Aguardando início",
            )
            db.add(order)
            db.flush()
            call.status = "Em análise"
            notify_user(db, call.requester_id, "Chamado aprovado", f"{call.number} gerou a ordem {order.number}.", f"/chamados/detalhe?id={call.id}")
            db.commit()
    return RedirectResponse(f"/chamados/detalhe?id={call_id}&notice=Ordem%20de%20serviço%20gerada.", status_code=303)


@app.post("/chamados/{call_id}/cancelar")
async def cancelar_chamado(request: Request, call_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    with SessionLocal() as db:
        call = db.get(models.MaintenanceCall, call_id)
        if not call or (user["role"] == "professor" and call.requester_id != user["id"]):
            raise HTTPException(404, "Chamado não encontrado.")
        if call.status != "Aberto":
            raise HTTPException(409, "Só é possível cancelar um chamado aberto.")
        call.status = "Cancelado"
        if user["role"] == "administrator":
            notify_user(db, call.requester_id, "Chamado cancelado", f"{call.number} foi cancelado pelo administrador.", f"/chamados/detalhe?id={call.id}", "warning")
        else:
            notify_administrators(db, "Chamado cancelado", f"{call.number} foi cancelado pelo solicitante.", f"/chamados/detalhe?id={call.id}", "warning")
        db.commit()
    return RedirectResponse("/chamados?notice=Chamado%20cancelado.", status_code=303)


@app.get("/equipamentos")
async def equipamentos(request: Request):
    with SessionLocal() as db:
        items = db.scalars(select(models.Equipment).options(selectinload(models.Equipment.sector)).order_by(models.Equipment.name)).all()
        return page(request, "equipamentos/lista.html", context={"equipment_items": items})


@app.get("/equipamentos/novo")
async def novo_equipamento(request: Request):
    with SessionLocal() as db:
        sectors = db.scalars(select(models.Sector).order_by(models.Sector.name)).all()
        return page(request, "equipamentos/novo.html", role="administrator", context={"sectors": sectors})


@app.post("/equipamentos")
async def criar_equipamento(
    request: Request, name: str = Form(...), sector_id: int = Form(...), model_name: str = Form(""),
    serial_number: str = Form(""), acquired_at: str = Form(""),
    asset_tag: str = Form(...), state: str = Form("Disponível"), csrf_token: str = Form(...),
    photo: UploadFile | None = File(None), manual: UploadFile | None = File(None),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem cadastrar equipamentos.")
    if state not in {"Disponível", "Em manutenção", "Indisponível"} or not 2 <= len(name.strip()) <= 120 or not 1 <= len(asset_tag.strip()) <= 80:
        raise HTTPException(422, "Estado inválido.")
    try:
        acquired_date = date.fromisoformat(acquired_at) if acquired_at else None
    except ValueError:
        raise HTTPException(422, "Data de aquisição inválida.") from None
    with SessionLocal() as db:
        if not db.get(models.Sector, sector_id):
            raise HTTPException(422, "Setor não encontrado.")
        photo_name, photo_mime = await save_image(photo, "equipment")
        manual_name, manual_mime = await save_pdf(manual, "equipment")
        equipment = models.Equipment(name=name.strip(), sector_id=sector_id, model=model_name.strip() or None,
                                     serial_number=serial_number.strip() or None, acquired_at=acquired_date,
                                     asset_tag=asset_tag.strip(), state=state, photo_name=photo_name,
                                     photo_mime=photo_mime, manual_name=manual_name, manual_mime=manual_mime)
        db.add(equipment)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return RedirectResponse("/equipamentos/novo?notice=Patrimônio%20já%20cadastrado%20ou%20dados%20inválidos.", status_code=303)
    return RedirectResponse("/equipamentos?notice=Equipamento%20cadastrado.", status_code=303)


@app.get("/equipamentos/detalhe")
async def detalhe_equipamento(request: Request, id: int | None = None):
    with SessionLocal() as db:
        equipment = db.scalar(select(models.Equipment).options(selectinload(models.Equipment.sector)).where(models.Equipment.id == id)) if id else None
        if not equipment:
            return RedirectResponse("/equipamentos?notice=Equipamento%20não%20encontrado.", status_code=303)
        return page(request, "equipamentos/detalhe.html", context={"equipment": equipment})


@app.get("/files/calls/{call_id}/photo")
def view_call_photo(call_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    call = db.get(models.MaintenanceCall, call_id)
    if not call or not call.photo_name or (user.role == "professor" and call.requester_id != user.id):
        raise HTTPException(404, "Foto não encontrada.")
    return FileResponse(file_path("calls", call.photo_name), media_type=call.photo_mime or "application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})


@app.get("/files/equipment/{equipment_id}/{kind}")
def view_equipment_file(equipment_id: int, kind: str, db: Session = Depends(get_db), _user: models.User = Depends(get_current_user)):
    equipment = db.get(models.Equipment, equipment_id)
    if not equipment or kind not in {"photo", "manual"}:
        raise HTTPException(404, "Arquivo não encontrado.")
    filename = equipment.photo_name if kind == "photo" else equipment.manual_name
    mime = equipment.photo_mime if kind == "photo" else equipment.manual_mime
    if not filename:
        raise HTTPException(404, "Arquivo não encontrado.")
    return FileResponse(file_path("equipment", filename), media_type=mime or "application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})


@app.get("/ordens-servico")
async def ordens_servico(request: Request):
    with SessionLocal() as db:
        items = db.scalars(select(models.WorkOrder).options(
            selectinload(models.WorkOrder.call).selectinload(models.MaintenanceCall.equipment),
            selectinload(models.WorkOrder.responsible),
        ).order_by(models.WorkOrder.id.desc())).all()
        counts = {status: sum(item.status == status for item in items) for status in ("Aguardando início", "Em execução", "Concluída")}
        return page(request, "ordens_servico/lista.html", role="administrator", context={"work_orders": items, "order_counts": counts})


@app.get("/ordens-servico/detalhe")
async def detalhe_ordem_servico(request: Request, id: int | None = None):
    with SessionLocal() as db:
        order = db.scalar(select(models.WorkOrder).options(
            selectinload(models.WorkOrder.call).selectinload(models.MaintenanceCall.equipment),
        ).where(models.WorkOrder.id == id)) if id else None
        if not order:
            return RedirectResponse("/ordens-servico?notice=Ordem%20de%20serviço%20não%20encontrada.", status_code=303)
        return page(request, "ordens_servico/detalhe.html", role="administrator", context={"order": order})


@app.post("/ordens-servico/{order_id}")
async def salvar_ordem_servico(
    request: Request, order_id: int, status: str = Form(...), solution: str = Form(""), notes: str = Form(""),
    defect: str = Form(""), cause: str = Form(""), parts: str = Form(""), csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem atualizar ordens de serviço.")
    if status not in {"Em execução", "Aguardando peça", "Concluída"}:
        raise HTTPException(422, "Status inválido.")
    with SessionLocal() as db:
        order = db.get(models.WorkOrder, order_id)
        if not order:
            raise HTTPException(404, "Ordem de serviço não encontrada.")
        if status == "Em execução" and not order.started_at:
            order.started_at = models.utc_now()
        if status == "Concluída":
            order.finished_at = models.utc_now()
            order.call.status = "Concluído"
            order.call.equipment.state = "Disponível"
        else:
            order.call.status = "Aguardando peça" if status == "Aguardando peça" else "Em manutenção"
            order.call.equipment.state = "Em manutenção"
        order.status, order.solution, order.notes = status, solution.strip() or None, notes.strip() or None
        order.defect, order.cause, order.parts = defect.strip() or None, cause.strip() or None, parts.strip() or None
        notify_user(db, order.call.requester_id, "Ordem de serviço atualizada", f"{order.number}: {order.status}.", f"/chamados/detalhe?id={order.call.id}")
        db.commit()
    return RedirectResponse(f"/ordens-servico/detalhe?id={order_id}&notice=Ordem%20atualizada.", status_code=303)


@app.get("/historico")
async def historico(request: Request):
    with SessionLocal() as db:
        items = db.scalars(select(models.WorkOrder).options(
            selectinload(models.WorkOrder.call).selectinload(models.MaintenanceCall.equipment),
            selectinload(models.WorkOrder.responsible),
        ).where(models.WorkOrder.status == "Concluída").order_by(models.WorkOrder.finished_at.desc())).all()
        return page(request, "historico/lista.html", role="administrator", context={"completed_orders": items})


@app.get("/solicitacoes")
async def solicitacoes(request: Request):
    with SessionLocal() as db:
        items = db.scalars(select(models.PurchaseRequest).options(selectinload(models.PurchaseRequest.requester)).order_by(models.PurchaseRequest.created_at.desc())).all()
        user = request.session.get("user")
        if user and user["role"] == "professor":
            items = [item for item in items if item.requester_id == user["id"]]
        return page(request, "solicitacoes/lista.html", context={"purchase_requests": items, "status_class": status_class})


@app.get("/solicitacoes/nova")
async def nova_solicitacao(request: Request): return page(request, "solicitacoes/nova.html")


@app.post("/solicitacoes")
async def criar_solicitacao(
    request: Request, item_type: str = Form(...), item: str = Form(...), quantity: int = Form(...),
    justification: str = Form(...), csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    if item_type not in {"Novas máquinas", "Ferramentas", "Peças e componentes"} or quantity < 1 or not 10 <= len(justification.strip()) <= 5000 or not 2 <= len(item.strip()) <= 180:
        return RedirectResponse("/solicitacoes/nova?notice=Confira%20os%20dados%20da%20solicitação.", status_code=303)
    with SessionLocal() as db:
        db.add(models.PurchaseRequest(
            number=make_number("SC"),
            item_type=item_type, item=item.strip(), quantity=quantity, justification=justification.strip(), requester_id=user["id"],
        ))
        notify_administrators(db, "Nova solicitação de compra", f"{item.strip()} ({quantity}).", "/solicitacoes", "info")
        db.commit()
    return RedirectResponse("/solicitacoes?notice=Solicitação%20registrada.", status_code=303)


@app.post("/solicitacoes/{request_id}/decidir")
async def decidir_solicitacao(request: Request, request_id: int, decision: str = Form(...), csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem analisar solicitações.")
    if decision not in {"Aprovada", "Recusada"}:
        raise HTTPException(422, "Decisão inválida.")
    with SessionLocal() as db:
        purchase = db.get(models.PurchaseRequest, request_id)
        if not purchase:
            raise HTTPException(404, "Solicitação não encontrada.")
        if purchase.status != "Em análise":
            raise HTTPException(409, "Esta solicitação já foi analisada.")
        purchase.status, purchase.reviewed_by_id = decision, user["id"]
        notify_user(db, purchase.requester_id, "Solicitação analisada", f"{purchase.number}: {decision.lower()}.", "/solicitacoes")
        db.commit()
    return RedirectResponse("/solicitacoes?notice=Decisão%20registrada.", status_code=303)


@app.get("/solicitacoes/detalhe")
async def detalhe_solicitacao(request: Request): return page(request, "solicitacoes/detalhe.html")


@app.get("/indicadores")
async def indicadores(request: Request):
    with SessionLocal() as db:
        calls = db.scalars(select(models.MaintenanceCall)).all()
        orders = db.scalars(select(models.WorkOrder)).all()
        equipment = db.scalars(select(models.Equipment)).all()
        elapsed = [(item.finished_at - item.started_at).total_seconds() / 3600 for item in orders if item.started_at and item.finished_at]
        context = {
            "calls_total": len(calls), "backlog": sum(item.status not in {"Concluído", "Cancelado"} for item in calls),
            "equipment_total": len(equipment), "unavailable": sum(item.state == "Indisponível" for item in equipment),
            "completion_rate": round(sum(item.status == "Concluída" for item in orders) / len(orders) * 100, 1) if orders else 0,
            "mttr": round(sum(elapsed) / len(elapsed), 1) if elapsed else 0,
        }
        return page(request, "indicadores/lista.html", role="administrator", context=context)


@app.get("/notificacoes")
async def notificacoes(request: Request):
    user = request.session.get("user")
    with SessionLocal() as db:
        items = db.scalars(select(models.Notification).where(models.Notification.user_id == user["id"]).order_by(models.Notification.created_at.desc())).all() if user else []
        return page(request, "notificacoes/lista.html", context={"notifications": items})


@app.post("/notificacoes/ler-todas")
async def ler_notificacoes(request: Request, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    with SessionLocal() as db:
        db.query(models.Notification).filter(models.Notification.user_id == user["id"], models.Notification.is_read.is_(False)).update({"is_read": True})
        db.commit()
    return RedirectResponse("/notificacoes?notice=Notificações%20marcadas%20como%20lidas.", status_code=303)


@app.post("/notificacoes/{notification_id}/ler")
async def ler_notificacao(request: Request, notification_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    with SessionLocal() as db:
        item = db.get(models.Notification, notification_id)
        if not item or item.user_id != user["id"]:
            raise HTTPException(404, "Notificação não encontrada.")
        item.is_read = True
        href = item.href
        db.commit()
    return RedirectResponse(href, status_code=303)


@app.get("/configuracoes")
async def configuracoes(request: Request):
    with SessionLocal() as db:
        users = db.scalars(select(models.User).order_by(models.User.name)).all()
        sectors = db.scalars(select(models.Sector).order_by(models.Sector.name)).all()
        preferences = db.get(models.UnitSettings, 1)
        if not preferences:
            preferences = models.UnitSettings(id=1)
            db.add(preferences)
            db.commit()
        counts = dict(db.execute(select(models.Equipment.sector_id, func.count()).group_by(models.Equipment.sector_id)).all())
        return page(request, "configuracoes/lista.html", role="administrator", context={"users": users, "sectors": sectors, "equipment_counts": counts, "preferences": preferences})


@app.post("/configuracoes/preferencias")
async def salvar_preferencias(
    request: Request, unit_name: str = Form(...), timezone_name: str = Form(...),
    notify_admin_new_call: bool = Form(False), csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem salvar preferências.")
    valid_timezones = {"America/Sao_Paulo", "America/Manaus", "America/Belem", "America/Fortaleza", "America/Recife", "America/Rio_Branco", "UTC"}
    if not 2 <= len(unit_name.strip()) <= 160 or timezone_name not in valid_timezones:
        return RedirectResponse("/configuracoes?notice=Nome%20da%20unidade%20ou%20fuso%20horário%20inválido.", status_code=303)
    with SessionLocal() as db:
        preferences = db.get(models.UnitSettings, 1)
        if preferences is None:
            preferences = models.UnitSettings(id=1)
            db.add(preferences)
        preferences.unit_name = unit_name.strip()
        preferences.timezone_name = timezone_name
        preferences.notify_admin_new_call = notify_admin_new_call
        db.commit()
    return RedirectResponse("/configuracoes?notice=Preferências%20salvas.", status_code=303)


@app.post("/configuracoes/usuarios")
async def web_create_user(
    request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...),
    role: str = Form(...), csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem cadastrar usuários.")
    email = email.strip().lower()
    if (role not in {"professor", "administrator"} or len(password) < 12 or
            len(name.strip()) < 2 or len(name.strip()) > 120 or
            not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
        return RedirectResponse("/configuracoes?notice=Selecione%20um%20dos%20dois%20perfis%20e%20use%20senha%20com%20ao%20menos%2012%20caracteres.", status_code=303)
    with SessionLocal() as db:
        db.add(models.User(name=name.strip(), email=email, password_hash=hash_password(password), role=role))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return RedirectResponse("/configuracoes?notice=Já%20existe%20uma%20conta%20com%20esse%20e-mail.", status_code=303)
    return RedirectResponse("/configuracoes?notice=Usuário%20cadastrado.", status_code=303)


@app.post("/configuracoes/setores")
async def web_create_sector(request: Request, name: str = Form(...), csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem cadastrar setores.")
    if not 2 <= len(name.strip()) <= 100:
        return RedirectResponse("/configuracoes?notice=Informe%20um%20nome%20de%20setor%20válido.", status_code=303)
    with SessionLocal() as db:
        db.add(models.Sector(name=name.strip()))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return RedirectResponse("/configuracoes?notice=Esse%20setor%20já%20existe.", status_code=303)
    return RedirectResponse("/configuracoes?notice=Setor%20cadastrado.", status_code=303)


@app.post("/configuracoes/usuarios/{user_id}/ativar")
async def web_set_user_active(request: Request, user_id: int, active: bool = Form(...), csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    admin = request.session.get("user")
    if not admin or admin["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem gerenciar usuários.")
    with SessionLocal() as db:
        account = db.get(models.User, user_id)
        if not account:
            raise HTTPException(404, "Usuário não encontrado.")
        if account.id == admin["id"] and not active:
            raise HTTPException(400, "Não é possível desativar a própria conta.")
        account.is_active = active
        db.commit()
    return RedirectResponse("/configuracoes?notice=Status%20do%20usuário%20atualizado.", status_code=303)
