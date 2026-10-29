"""SENAI CMMS web application and HTML interface."""

from contextlib import asynccontextmanager
from pathlib import Path
import secrets
from hmac import compare_digest
from datetime import date, datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from backend.api import make_number, router as api_router
from backend.config import settings
from backend.database import db
from backend.dependencies import get_current_user
<<<<<<< HEAD
from backend.security import hash_password
from backend.services import log_audit, notify_administrators, notify_user
=======
from backend.models import (
    TABLE_EQUIPMENT, TABLE_MAINTENANCE_CALLS, TABLE_NOTIFICATIONS,
    TABLE_PURCHASE_REQUESTS, TABLE_SECTORS, TABLE_UNIT_SETTINGS,
    TABLE_USERS, TABLE_WORK_ORDERS,
)
from backend.security import hash_password, verify_password
from backend.services import notify_administrators, notify_user
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
from backend.storage import file_path, save_image, save_pdf

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
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
<<<<<<< HEAD
FALLBACK_TZ_OFFSETS = {
    "America/Sao_Paulo": -3,
    "America/Manaus": -4,
    "America/Belem": -3,
    "America/Fortaleza": -3,
    "America/Recife": -3,
    "America/Rio_Branco": -5,
    "UTC": 0,
}
def format_local_datetime(value: datetime | None, zone_name: str, pattern: str = "%d/%m/%Y %H:%M") -> str:
    if value is None:
        return "—"
    utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    try:
        local_zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        # tzdata is required on Windows. Keep local pages usable if it was not installed yet.
        local_zone = timezone(timedelta(hours=FALLBACK_TZ_OFFSETS.get(zone_name, -3)))
=======

C = TABLE_MAINTENANCE_CALLS
E = TABLE_EQUIPMENT
OS = TABLE_WORK_ORDERS
N = TABLE_NOTIFICATIONS
U = TABLE_USERS
S = TABLE_SECTORS
SC = TABLE_PURCHASE_REQUESTS
US = TABLE_UNIT_SETTINGS

TZ_OFFSETS = {"America/Sao_Paulo": -3, "America/Manaus": -4, "America/Belem": -3,
              "America/Fortaleza": -3, "America/Recife": -3, "America/Rio_Branco": -5, "UTC": 0}


def format_local_datetime(value: datetime | None, zone_name: str, pattern: str = "%d/%m/%Y %H:%M") -> str:
    if value is None:
        return "—"
    try:
        raw = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return "—"
    utc_value = raw.replace(tzinfo=timezone.utc) if raw.tzinfo is None else raw.astimezone(timezone.utc)
    local_zone = timezone(timedelta(hours=TZ_OFFSETS.get(zone_name, -3)))
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
    return utc_value.astimezone(local_zone).strftime(pattern)


templates.env.globals["local_datetime"] = format_local_datetime
app.include_router(api_router)


def _unit_preferences() -> dict:
    resp = db.client.table(US).select("*").eq("id", 1).execute()
    if resp.data:
        return resp.data[0]
    return {"unit_name": "SENAI — São Paulo", "timezone_name": "America/Sao_Paulo"}


def _unread_notifications(user_id: int | None) -> int:
    if not user_id:
        return 0
    resp = db.client.table(N).select("id").eq("user_id", user_id).eq("is_read", False).execute()
    return len(resp.data)


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


def page(request: Request, template: str, *, role: str | None = None, context: dict | None = None):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    resp = db.client.table(U).select("*").eq("id", user_id).execute()
    if not resp.data or not resp.data[0].get("is_active"):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)
    user = {"id": resp.data[0]["id"], "name": resp.data[0]["name"], "email": resp.data[0]["email"], "role": resp.data[0]["role"]}
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


# --------------------------------------------------
# Rotas auxiliares
# --------------------------------------------------

def _call_equipment(call_id: int | None) -> tuple[dict | None, dict | None]:
    if not call_id:
        return None, None
    cr = db.client.table(C).select("*").eq("id", call_id).execute()
    call = cr.data[0] if cr.data else None
    equip = None
    if call and call.get("equipment_id"):
        er = db.client.table(E).select("*").eq("id", call["equipment_id"]).execute()
        equip = er.data[0] if er.data else None
    return call, equip


def _order_call_equipment(order: dict | None) -> tuple[dict | None, dict | None]:
    if not order or not order.get("call_id"):
        return None, None
    return _call_equipment(order["call_id"])


# --------------------------------------------------
# Auth
# --------------------------------------------------

@app.get("/", include_in_schema=False)
async def home():
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/login", name="login")
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "login.html")


@app.post("/login", name="login_submit")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    expected = request.session.get("csrf_token", "")
    if not expected or not compare_digest(expected, csrf_token):
        return render(request, "login.html", notice="Sessão expirada. Tente novamente.", status_code=403)
    resp = db.client.table(U).select("*").eq("email", email.strip().lower()).execute()
    user = resp.data[0] if resp.data else None
    if not user or not user.get("is_active") or not verify_password(password, user["password_hash"]):
        return render(request, "login.html", notice="E-mail ou senha inválidos.", status_code=401)
    request.session.clear()
    request.session.update({
        "user_id": user["id"],
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
        "csrf_token": secrets.token_urlsafe(32),
    })
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/logout", name="logout")
async def logout(request: Request, csrf_token: str = Form(...)):
    expected = request.session.get("csrf_token", "")
    if not expected or not compare_digest(expected, csrf_token):
        return RedirectResponse("/dashboard?notice=Sessão%20expirada.", status_code=303)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/recuperar-senha", include_in_schema=False)
async def password_recovery(request: Request):
    return render(request, "login.html", notice="Solicite ao administrador a redefinição da sua senha.")


# --------------------------------------------------
# Dashboard
# --------------------------------------------------

@app.get("/dashboard")
async def dashboard(request: Request):
    user = request.session.get("user")
    q = db.client.table(C).select("*").order("created_at", desc=True)
    calls = q.execute().data
    if user and user["role"] == "professor":
        calls = [c for c in calls if c["requester_id"] == user["id"]]
    open_count = sum(1 for c in calls if c["status"] not in ("Concluído", "Cancelado"))
    analysis_count = sum(1 for c in calls if c["status"] in ("Aberto", "Em análise"))
    completed_count = sum(1 for c in calls if c["status"] == "Concluído")
    orders = db.client.table(OS).select("*").neq("status", "Concluída").order("id", desc=True).execute().data
    def _order_snippet(o):
        call, eq = _order_call_equipment(o)
        return {**o, "_equipment_name": eq["name"] if eq else "?", "_call_number": call["number"] if call else "?"}
    orders = [_order_snippet(o) for o in orders]

    def _call_snippet(c):
        equip = db.client.table(E).select("*").eq("id", c["equipment_id"]).execute().data
        requester = db.client.table(U).select("*").eq("id", c["requester_id"]).execute().data
        return {**c, "_equipment_name": equip[0]["name"] if equip else "?",
                "_requester_name": requester[0]["name"] if requester else "?"}
    calls_snippet = [_call_snippet(c) for c in calls]
    active_orders = orders[:4]
    return page(request, "dashboard.html", context={
        "recent_calls": calls_snippet[:5], "open_count": open_count, "analysis_count": analysis_count,
        "completed_count": completed_count, "total_calls": len(calls), "active_orders": active_orders,
        "priority_counts": {p: sum(1 for c in calls if c["priority"] == p and c["status"] not in ("Concluído", "Cancelado")) for p in ("Crítica", "Alta", "Média", "Baixa")},
        "status_class": status_class,
    })


# --------------------------------------------------
# Chamados
# --------------------------------------------------

@app.get("/chamados")
async def chamados(request: Request):
    items = db.client.table(C).select("*").order("created_at", desc=True).execute().data
    user = request.session.get("user")
    if user and user["role"] == "professor":
        items = [c for c in items if c["requester_id"] == user["id"]]
    def _call_snippet(c):
        equip = db.client.table(E).select("*").eq("id", c["equipment_id"]).execute().data
        requester = db.client.table(U).select("*").eq("id", c["requester_id"]).execute().data
        return {**c, "_equipment_name": equip[0]["name"] if equip else "?",
                "_requester_name": requester[0]["name"] if requester else "?"}
    items = [_call_snippet(c) for c in items]
    counts = {s: 0 for s in ("Aberto", "Em análise", "Em manutenção", "Aguardando peça", "Concluído")}
    for call in items:
        if call["status"] in counts:
            counts[call["status"]] += 1
    return page(request, "chamados/lista.html", context={"calls": items, "call_counts": counts, "status_class": status_class})


@app.get("/chamados/novo")
async def novo_chamado(request: Request):
    equipment = db.client.table(E).select("*").order("name").execute().data
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
    if not db.client.table(E).select("id").eq("id", equipment_id).execute().data:
        return RedirectResponse("/chamados/novo?notice=Equipamento%20não%20encontrado.", status_code=303)
    photo_name, photo_mime = await save_image(photo, "calls")
    resp = db.client.table(C).insert({
        "number": make_number("CH"),
        "equipment_id": equipment_id,
        "requester_id": user["id"],
        "description": description.strip(),
        "priority": priority,
        "photo_name": photo_name,
        "photo_mime": photo_mime,
    }).execute()
    call = resp.data[0]
    prefs = _unit_preferences()
    if prefs.get("notify_admin_new_call"):
        kind = "warning" if priority in {"Alta", "Crítica"} else "info"
        notify_administrators("Novo chamado", f"{call['number']}: prioridade {priority}.", f"/chamados/detalhe?id={call['id']}", kind)
    return RedirectResponse("/chamados?notice=Chamado%20registrado%20com%20sucesso.", status_code=303)


@app.get("/chamados/detalhe")
async def detalhe_chamado(request: Request, id: int | None = None):
    cr = db.client.table(C).select("*").eq("id", id).execute() if id else None
    call = cr.data[0] if cr and cr.data else None
    user = request.session.get("user")
    if not call or (user and user["role"] == "professor" and call["requester_id"] != user["id"]):
        return RedirectResponse("/chamados?notice=Chamado%20não%20encontrado.", status_code=303)
    eq_resp = db.client.table(E).select("*").eq("id", call["equipment_id"]).execute()
    equipment = eq_resp.data[0] if eq_resp.data else None
    sector = None
    if equipment:
        sec_resp = db.client.table(S).select("*").eq("id", equipment["sector_id"]).execute()
        sector = sec_resp.data[0] if sec_resp.data else None
    requester_resp = db.client.table(U).select("*").eq("id", call["requester_id"]).execute()
    requester = requester_resp.data[0] if requester_resp.data else None
    wo_resp = db.client.table(OS).select("*").eq("call_id", call["id"]).execute()
    work_order = wo_resp.data[0] if wo_resp.data else None
    call["_equipment"] = equipment
    call["_sector"] = sector
    call["_requester"] = requester
    call["_work_order"] = work_order
    return page(request, "chamados/detalhe.html", context={"call": call, "status_class": status_class(call["status"])})


@app.post("/chamados/{call_id}/aprovar")
async def aprovar_chamado(request: Request, call_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem aprovar chamados.")
<<<<<<< HEAD
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
            log_audit(db, user["id"], "approved", "maintenance_call", call.id, f"Aprovou {call.number} e gerou {order.number}.")
            db.commit()
=======
    call = db.client.table(C).select("*").eq("id", call_id).execute().data
    if not call:
        raise HTTPException(404, "Chamado não encontrado.")
    call = call[0]
    wo = db.client.table(OS).select("*").eq("call_id", call_id).execute().data
    if not wo:
        resp = db.client.table(OS).insert({
            "number": make_number("OS"),
            "call_id": call_id,
            "responsible_id": user["id"],
            "status": "Aguardando início",
        }).execute()
        order = resp.data[0]
        db.client.table(C).update({"status": "Em análise"}).eq("id", call_id).execute()
        notify_user(call["requester_id"], "Chamado aprovado", f"{call['number']} gerou a ordem {order['number']}.", f"/chamados/detalhe?id={call_id}")
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
    return RedirectResponse(f"/chamados/detalhe?id={call_id}&notice=Ordem%20de%20serviço%20gerada.", status_code=303)


@app.post("/chamados/{call_id}/cancelar")
async def cancelar_chamado(request: Request, call_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
<<<<<<< HEAD
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
        log_audit(db, user["id"], "cancelled", "maintenance_call", call.id, f"Cancelou o chamado {call.number}.")
        db.commit()
=======
    resp = db.client.table(C).select("*").eq("id", call_id).execute()
    call = resp.data[0] if resp.data else None
    if not call or (user["role"] == "professor" and call["requester_id"] != user["id"]):
        raise HTTPException(404, "Chamado não encontrado.")
    if call["status"] != "Aberto":
        raise HTTPException(409, "Só é possível cancelar um chamado aberto.")
    db.client.table(C).update({"status": "Cancelado"}).eq("id", call_id).execute()
    if user["role"] == "administrator":
        notify_user(call["requester_id"], "Chamado cancelado", f"{call['number']} foi cancelado pelo administrador.", f"/chamados/detalhe?id={call_id}", "warning")
    else:
        notify_administrators("Chamado cancelado", f"{call['number']} foi cancelado pelo solicitante.", f"/chamados/detalhe?id={call_id}", "warning")
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
    return RedirectResponse("/chamados?notice=Chamado%20cancelado.", status_code=303)


# --------------------------------------------------
# Equipamentos
# --------------------------------------------------

@app.get("/equipamentos")
async def equipamentos(request: Request):
    items = db.client.table(E).select("*").order("name").execute().data
    for e in items:
        sec = db.client.table(S).select("*").eq("id", e["sector_id"]).execute().data
        e["_sector"] = sec[0] if sec else None
        resp_user = db.client.table(U).select("*").eq("id", e.get("responsible_id")).execute().data if e.get("responsible_id") else []
        e["_responsible"] = resp_user[0] if resp_user else None
    return page(request, "equipamentos/lista.html", context={"equipment_items": items})


@app.get("/equipamentos/novo")
async def novo_equipamento(request: Request):
    sectors = db.client.table(S).select("*").order("name").execute().data
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
        acquired_date = date.fromisoformat(acquired_at).isoformat() if acquired_at else None
    except ValueError:
        raise HTTPException(422, "Data de aquisição inválida.") from None
<<<<<<< HEAD
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
            db.flush()
            log_audit(db, user["id"], "created", "equipment", equipment.id, f"Cadastrou o equipamento {equipment.asset_tag}.")
            db.commit()
        except IntegrityError:
            db.rollback()
            return RedirectResponse("/equipamentos/novo?notice=Patrimônio%20já%20cadastrado%20ou%20dados%20inválidos.", status_code=303)
=======
    if not db.client.table(S).select("id").eq("id", sector_id).execute().data:
        raise HTTPException(422, "Setor não encontrado.")
    photo_name, photo_mime = await save_image(photo, "equipment")
    manual_name, manual_mime = await save_pdf(manual, "equipment")
    resp = db.client.table(E).insert({
        "name": name.strip(), "sector_id": sector_id, "model": model_name.strip() or None,
        "serial_number": serial_number.strip() or None, "acquired_at": acquired_date,
        "asset_tag": asset_tag.strip(), "state": state, "photo_name": photo_name,
        "photo_mime": photo_mime, "manual_name": manual_name, "manual_mime": manual_mime,
    }).execute()
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
    return RedirectResponse("/equipamentos?notice=Equipamento%20cadastrado.", status_code=303)


@app.get("/equipamentos/detalhe")
async def detalhe_equipamento(request: Request, id: int | None = None):
    resp = db.client.table(E).select("*").eq("id", id).execute() if id else None
    equipment = resp.data[0] if resp and resp.data else None
    if not equipment:
        return RedirectResponse("/equipamentos?notice=Equipamento%20não%20encontrado.", status_code=303)
    sec = db.client.table(S).select("*").eq("id", equipment["sector_id"]).execute().data
    equipment["_sector"] = sec[0] if sec else None
    return page(request, "equipamentos/detalhe.html", context={"equipment": equipment})


@app.get("/equipamentos/{equipment_id}/editar")
async def editar_equipamento_page(request: Request, equipment_id: int):
    with SessionLocal() as db:
        equipment = db.get(models.Equipment, equipment_id)
        sectors = db.scalars(select(models.Sector).order_by(models.Sector.name)).all()
        if not equipment:
            return RedirectResponse("/equipamentos?notice=Equipamento%20não%20encontrado.", status_code=303)
        return page(request, "equipamentos/editar.html", role="administrator", context={"equipment": equipment, "sectors": sectors})


@app.post("/equipamentos/{equipment_id}/editar")
async def editar_equipamento(
    request: Request, equipment_id: int, name: str = Form(...), sector_id: int = Form(...), model_name: str = Form(""),
    serial_number: str = Form(""), acquired_at: str = Form(""), asset_tag: str = Form(...), state: str = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem editar equipamentos.")
    if state not in {"Disponível", "Em manutenção", "Indisponível"} or not 2 <= len(name.strip()) <= 120 or not 1 <= len(asset_tag.strip()) <= 80:
        raise HTTPException(422, "Dados do equipamento inválidos.")
    try:
        acquired_date = date.fromisoformat(acquired_at) if acquired_at else None
    except ValueError:
        raise HTTPException(422, "Data de aquisição inválida.") from None
    with SessionLocal() as db:
        equipment = db.get(models.Equipment, equipment_id)
        if not equipment or not db.get(models.Sector, sector_id):
            raise HTTPException(404, "Equipamento ou setor não encontrado.")
        if state != equipment.state:
            active_order = db.scalar(select(models.WorkOrder.id).join(models.MaintenanceCall).where(
                models.MaintenanceCall.equipment_id == equipment.id,
                models.WorkOrder.status != "Concluída",
            ))
            if active_order:
                return RedirectResponse(
                    f"/equipamentos/{equipment_id}/editar?notice=O%20estado%20é%20controlado%20pela%20ordem%20de%20serviço%20ativa.",
                    status_code=303,
                )
        equipment.name, equipment.sector_id, equipment.model = name.strip(), sector_id, model_name.strip() or None
        equipment.serial_number, equipment.acquired_at = serial_number.strip() or None, acquired_date
        equipment.asset_tag, equipment.state = asset_tag.strip(), state
        try:
            db.flush()
            log_audit(db, user["id"], "updated", "equipment", equipment.id, f"Atualizou o equipamento {equipment.asset_tag}.")
            db.commit()
        except IntegrityError:
            db.rollback()
            return RedirectResponse(f"/equipamentos/{equipment_id}/editar?notice=Patrimônio%20já%20cadastrado.", status_code=303)
    return RedirectResponse(f"/equipamentos/detalhe?id={equipment_id}&notice=Equipamento%20atualizado.", status_code=303)


@app.get("/files/calls/{call_id}/photo")
def view_call_photo(call_id: int, user: dict = Depends(get_current_user)):
    resp = db.client.table(C).select("*").eq("id", call_id).execute()
    call = resp.data[0] if resp.data else None
    if not call or not call.get("photo_name") or (user.get("role") == "professor" and call["requester_id"] != user["id"]):
        raise HTTPException(404, "Foto não encontrada.")
    return FileResponse(file_path("calls", call["photo_name"]), media_type=call.get("photo_mime") or "application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})


@app.get("/files/equipment/{equipment_id}/{kind}")
def view_equipment_file(equipment_id: int, kind: str, _user: dict = Depends(get_current_user)):
    resp = db.client.table(E).select("*").eq("id", equipment_id).execute()
    equipment = resp.data[0] if resp.data else None
    if not equipment or kind not in {"photo", "manual"}:
        raise HTTPException(404, "Arquivo não encontrado.")
    filename = equipment.get("photo_name") if kind == "photo" else equipment.get("manual_name")
    mime = equipment.get("photo_mime") if kind == "photo" else equipment.get("manual_mime")
    if not filename:
        raise HTTPException(404, "Arquivo não encontrado.")
    return FileResponse(file_path("equipment", filename), media_type=mime or "application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})


# --------------------------------------------------
# Ordens de Serviço
# --------------------------------------------------

def _order_snippet(o):
    call, eq = _order_call_equipment(o)
    return {**o, "_equipment_name": eq["name"] if eq else "?", "_equipment_id": eq["id"] if eq else None,
            "_call_number": call["number"] if call else "?", "_call_id": call["id"] if call else None,
            "_call_description": call["description"] if call else "",
            "_call_priority": call["priority"] if call else "",
            "_call_created_at": call["created_at"] if call else None}


@app.get("/ordens-servico")
async def ordens_servico(request: Request):
    items = db.client.table(OS).select("*").order("id", desc=True).execute().data
    items = [_order_snippet(o) for o in items]
    counts = {s: sum(1 for i in items if i["status"] == s) for s in ("Aguardando início", "Em execução", "Concluída")}
    return page(request, "ordens_servico/lista.html", role="administrator", context={"work_orders": items, "order_counts": counts})


@app.get("/ordens-servico/detalhe")
async def detalhe_ordem_servico(request: Request, id: int | None = None):
    resp = db.client.table(OS).select("*").eq("id", id).execute() if id else None
    order = resp.data[0] if resp and resp.data else None
    if not order:
        return RedirectResponse("/ordens-servico?notice=Ordem%20de%20serviço%20não%20encontrada.", status_code=303)
    order = _order_snippet(order)
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
<<<<<<< HEAD
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
        log_audit(db, user["id"], "updated", "work_order", order.id, f"Atualizou {order.number} para {order.status}.")
        db.commit()
=======
    resp = db.client.table(OS).select("*").eq("id", order_id).execute()
    order = resp.data[0] if resp.data else None
    if not order:
        raise HTTPException(404, "Ordem de serviço não encontrada.")
    call, equip = _order_call_equipment(order)
    update = {"status": status, "solution": solution.strip() or None, "notes": notes.strip() or None,
              "defect": defect.strip() or None, "cause": cause.strip() or None, "parts": parts.strip() or None}
    if status == "Em execução" and not order.get("started_at"):
        update["started_at"] = datetime.now(timezone.utc).isoformat()
    if status == "Concluída":
        update["finished_at"] = datetime.now(timezone.utc).isoformat()
        if call:
            db.client.table(C).update({"status": "Concluído"}).eq("id", call["id"]).execute()
            if equip:
                db.client.table(E).update({"state": "Disponível"}).eq("id", equip["id"]).execute()
    elif status == "Aguardando peça":
        if call:
            db.client.table(C).update({"status": "Aguardando peça"}).eq("id", call["id"]).execute()
            if equip:
                db.client.table(E).update({"state": "Em manutenção"}).eq("id", equip["id"]).execute()
    else:
        if call:
            db.client.table(C).update({"status": "Em manutenção"}).eq("id", call["id"]).execute()
            if equip:
                db.client.table(E).update({"state": "Em manutenção"}).eq("id", equip["id"]).execute()
    db.client.table(OS).update(update).eq("id", order_id).execute()
    if call:
        notify_user(call["requester_id"], "Ordem de serviço atualizada", f"{order['number']}: {status}.", f"/chamados/detalhe?id={call['id']}")
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
    return RedirectResponse(f"/ordens-servico/detalhe?id={order_id}&notice=Ordem%20atualizada.", status_code=303)


# --------------------------------------------------
# Histórico
# --------------------------------------------------

@app.get("/historico")
async def historico(request: Request):
    items = db.client.table(OS).select("*").eq("status", "Concluída").order("finished_at", desc=True).execute().data
    items = [_order_snippet(o) for o in items]
    return page(request, "historico/lista.html", role="administrator", context={"completed_orders": items})


# --------------------------------------------------
# Solicitações
# --------------------------------------------------

def _sc_snippet(r):
    requester = db.client.table(U).select("*").eq("id", r["requester_id"]).execute().data
    return {**r, "_requester_name": requester[0]["name"] if requester else "?"}


@app.get("/solicitacoes")
async def solicitacoes(request: Request):
    items = db.client.table(SC).select("*").order("created_at", desc=True).execute().data
    user = request.session.get("user")
    if user and user["role"] == "professor":
        items = [r for r in items if r["requester_id"] == user["id"]]
    items = [_sc_snippet(r) for r in items]
    return page(request, "solicitacoes/lista.html", context={"purchase_requests": items, "status_class": status_class})


@app.get("/solicitacoes/nova")
async def nova_solicitacao(request: Request):
    return page(request, "solicitacoes/nova.html")


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
    db.client.table(SC).insert({
        "number": make_number("SC"),
        "item_type": item_type, "item": item.strip(), "quantity": quantity,
        "justification": justification.strip(), "requester_id": user["id"],
    }).execute()
    notify_administrators("Nova solicitação de compra", f"{item.strip()} ({quantity}).", "/solicitacoes", "info")
    return RedirectResponse("/solicitacoes?notice=Solicitação%20registrada.", status_code=303)


@app.post("/solicitacoes/{request_id}/decidir")
async def decidir_solicitacao(request: Request, request_id: int, decision: str = Form(...), csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem analisar solicitações.")
    if decision not in {"Aprovada", "Recusada"}:
        raise HTTPException(422, "Decisão inválida.")
<<<<<<< HEAD
    with SessionLocal() as db:
        purchase = db.get(models.PurchaseRequest, request_id)
        if not purchase:
            raise HTTPException(404, "Solicitação não encontrada.")
        if purchase.status != "Em análise":
            raise HTTPException(409, "Esta solicitação já foi analisada.")
        purchase.status, purchase.reviewed_by_id = decision, user["id"]
        notify_user(db, purchase.requester_id, "Solicitação analisada", f"{purchase.number}: {decision.lower()}.", "/solicitacoes")
        log_audit(db, user["id"], "reviewed", "purchase_request", purchase.id, f"{purchase.number} marcada como {decision}.")
        db.commit()
=======
    resp = db.client.table(SC).select("*").eq("id", request_id).execute()
    purchase = resp.data[0] if resp.data else None
    if not purchase:
        raise HTTPException(404, "Solicitação não encontrada.")
    if purchase["status"] != "Em análise":
        raise HTTPException(409, "Esta solicitação já foi analisada.")
    db.client.table(SC).update({"status": decision, "reviewed_by_id": user["id"]}).eq("id", request_id).execute()
    notify_user(purchase["requester_id"], "Solicitação analisada", f"{purchase['number']}: {decision.lower()}.", "/solicitacoes")
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
    return RedirectResponse("/solicitacoes?notice=Decisão%20registrada.", status_code=303)


@app.get("/solicitacoes/detalhe")
<<<<<<< HEAD
async def detalhe_solicitacao(request: Request, id: int | None = None):
    with SessionLocal() as db:
        purchase = db.scalar(select(models.PurchaseRequest).options(
            selectinload(models.PurchaseRequest.requester),
            selectinload(models.PurchaseRequest.reviewed_by),
        ).where(models.PurchaseRequest.id == id)) if id else None
        user = request.session.get("user")
        if not purchase or (user and user["role"] == "professor" and purchase.requester_id != user["id"]):
            return RedirectResponse("/solicitacoes?notice=Solicitação%20não%20encontrada.", status_code=303)
        return page(request, "solicitacoes/detalhe.html", context={"purchase": purchase, "status_class": status_class})
=======
async def detalhe_solicitacao(request: Request):
    return page(request, "solicitacoes/detalhe.html")
>>>>>>> 763faa02520857295d80a222e5a2a365debda955


# --------------------------------------------------
# Indicadores
# --------------------------------------------------

@app.get("/indicadores")
async def indicadores(request: Request):
    calls = db.client.table(C).select("*").execute().data
    orders = db.client.table(OS).select("*").execute().data
    equipment = db.client.table(E).select("*").execute().data
    durations = []
    for o in orders:
        s, e = o.get("started_at"), o.get("finished_at")
        if s and e:
            try:
                durations.append((datetime.fromisoformat(str(e).replace("Z", "+00:00")) - datetime.fromisoformat(str(s).replace("Z", "+00:00"))).total_seconds() / 3600)
            except Exception:
                pass
    context = {
        "calls_total": len(calls),
        "backlog": sum(1 for c in calls if c["status"] not in ("Concluído", "Cancelado")),
        "equipment_total": len(equipment),
        "unavailable": sum(1 for e in equipment if e.get("state") == "Indisponível"),
        "completion_rate": round(sum(1 for o in orders if o["status"] == "Concluída") / len(orders) * 100, 1) if orders else 0,
        "mttr": round(sum(durations) / len(durations), 1) if durations else 0,
    }
    return page(request, "indicadores/lista.html", role="administrator", context=context)


<<<<<<< HEAD
@app.get("/auditoria")
async def auditoria(request: Request):
    with SessionLocal() as db:
        entries = db.scalars(select(models.AuditLog).options(
            selectinload(models.AuditLog.actor),
        ).order_by(models.AuditLog.created_at.desc()).limit(200)).all()
        return page(request, "auditoria/lista.html", role="administrator", context={"entries": entries})

=======
# --------------------------------------------------
# Notificações
# --------------------------------------------------
>>>>>>> 763faa02520857295d80a222e5a2a365debda955

@app.get("/notificacoes")
async def notificacoes(request: Request):
    user = request.session.get("user")
    items = []
    if user:
        items = db.client.table(N).select("*").eq("user_id", user["id"]).order("created_at", desc=True).execute().data
    return page(request, "notificacoes/lista.html", context={"notifications": items})


@app.post("/notificacoes/ler-todas")
async def ler_notificacoes(request: Request, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    db.client.table(N).update({"is_read": True}).eq("user_id", user["id"]).eq("is_read", False).execute()
    return RedirectResponse("/notificacoes?notice=Notificações%20marcadas%20como%20lidas.", status_code=303)


@app.post("/notificacoes/{notification_id}/ler")
async def ler_notificacao(request: Request, notification_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    resp = db.client.table(N).select("*").eq("id", notification_id).execute()
    item = resp.data[0] if resp.data else None
    if not item or item["user_id"] != user["id"]:
        raise HTTPException(404, "Notificação não encontrada.")
    db.client.table(N).update({"is_read": True}).eq("id", notification_id).execute()
    return RedirectResponse(item["href"], status_code=303)


# --------------------------------------------------
# Configurações
# --------------------------------------------------

@app.get("/configuracoes")
async def configuracoes(request: Request):
    users = db.client.table(U).select("*").order("name").execute().data
    sectors = db.client.table(S).select("*").order("name").execute().data
    preferences = _unit_preferences()
    equip = db.client.table(E).select("id,sector_id").execute().data
    counts = {}
    for e in equip:
        counts[e["sector_id"]] = counts.get(e["sector_id"], 0) + 1
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
<<<<<<< HEAD
    with SessionLocal() as db:
        preferences = db.get(models.UnitSettings, 1)
        if preferences is None:
            preferences = models.UnitSettings(id=1)
            db.add(preferences)
        preferences.unit_name = unit_name.strip()
        preferences.timezone_name = timezone_name
        preferences.notify_admin_new_call = notify_admin_new_call
        log_audit(db, user["id"], "updated", "unit_settings", 1, "Atualizou as preferências da unidade.")
        db.commit()
=======
    resp = db.client.table(US).select("*").eq("id", 1).execute()
    if resp.data:
        db.client.table(US).update({"unit_name": unit_name.strip(), "timezone_name": timezone_name, "notify_admin_new_call": notify_admin_new_call}).eq("id", 1).execute()
    else:
        db.client.table(US).insert({"id": 1, "unit_name": unit_name.strip(), "timezone_name": timezone_name, "notify_admin_new_call": notify_admin_new_call}).execute()
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
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
<<<<<<< HEAD
    with SessionLocal() as db:
        account = models.User(name=name.strip(), email=email, password_hash=hash_password(password), role=role)
        db.add(account)
        try:
            db.flush()
            log_audit(db, user["id"], "created", "user", account.id, f"Cadastrou o usuário {account.email}.")
            db.commit()
        except IntegrityError:
            db.rollback()
            return RedirectResponse("/configuracoes?notice=Já%20existe%20uma%20conta%20com%20esse%20e-mail.", status_code=303)
=======
    resp = db.client.table(U).select("id").eq("email", email).execute()
    if resp.data:
        return RedirectResponse("/configuracoes?notice=Já%20existe%20uma%20conta%20com%20esse%20e-mail.", status_code=303)
    db.client.table(U).insert({"name": name.strip(), "email": email, "password_hash": hash_password(password), "role": role}).execute()
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
    return RedirectResponse("/configuracoes?notice=Usuário%20cadastrado.", status_code=303)


@app.post("/configuracoes/setores")
async def web_create_sector(request: Request, name: str = Form(...), csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem cadastrar setores.")
    if not 2 <= len(name.strip()) <= 100:
        return RedirectResponse("/configuracoes?notice=Informe%20um%20nome%20de%20setor%20válido.", status_code=303)
<<<<<<< HEAD
    with SessionLocal() as db:
        sector = models.Sector(name=name.strip())
        db.add(sector)
        try:
            db.flush()
            log_audit(db, user["id"], "created", "sector", sector.id, f"Cadastrou o setor {sector.name}.")
            db.commit()
        except IntegrityError:
            db.rollback()
            return RedirectResponse("/configuracoes?notice=Esse%20setor%20já%20existe.", status_code=303)
=======
    existing = db.client.table(S).select("id").eq("name", name.strip()).execute()
    if existing.data:
        return RedirectResponse("/configuracoes?notice=Esse%20setor%20já%20existe.", status_code=303)
    db.client.table(S).insert({"name": name.strip()}).execute()
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
    return RedirectResponse("/configuracoes?notice=Setor%20cadastrado.", status_code=303)


@app.post("/configuracoes/setores/{sector_id}/excluir")
async def web_delete_sector(request: Request, sector_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem excluir setores.")
    with SessionLocal() as db:
        sector = db.get(models.Sector, sector_id)
        if not sector:
            raise HTTPException(404, "Setor não encontrado.")
        if db.scalar(select(func.count(models.Equipment.id)).where(models.Equipment.sector_id == sector_id)):
            return RedirectResponse("/configuracoes?notice=Não%20é%20possível%20excluir%20um%20setor%20com%20equipamentos.", status_code=303)
        log_audit(db, user["id"], "deleted", "sector", sector.id, f"Excluiu o setor {sector.name}.")
        db.delete(sector)
        db.commit()
    return RedirectResponse("/configuracoes?notice=Setor%20excluído.", status_code=303)


@app.post("/configuracoes/usuarios/{user_id}/atualizar")
async def web_update_user(
    request: Request, user_id: int, role: str = Form(...), new_password: str = Form(""), csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    admin = request.session.get("user")
    if not admin or admin["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem gerenciar usuários.")
    if role not in {"professor", "administrator"} or (new_password and len(new_password) < 12):
        return RedirectResponse("/configuracoes?notice=Perfil%20ou%20senha%20inválidos.", status_code=303)
    if user_id == admin["id"] and role != "administrator":
        return RedirectResponse("/configuracoes?notice=Não%20é%20possível%20remover%20o%20próprio%20perfil%20de%20administrador.", status_code=303)
    with SessionLocal() as db:
        account = db.get(models.User, user_id)
        if not account:
            raise HTTPException(404, "Usuário não encontrado.")
        account.role = role
        if new_password:
            account.password_hash = hash_password(new_password)
        log_audit(db, admin["id"], "updated", "user", account.id, f"Atualizou o perfil de {account.email}." + (" Redefiniu a senha." if new_password else ""))
        db.commit()
    return RedirectResponse("/configuracoes?notice=Usuário%20atualizado.", status_code=303)


@app.post("/configuracoes/usuarios/{user_id}/ativar")
async def web_set_user_active(request: Request, user_id: int, active: bool = Form(...), csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    admin = request.session.get("user")
    if not admin or admin["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem gerenciar usuários.")
<<<<<<< HEAD
    with SessionLocal() as db:
        account = db.get(models.User, user_id)
        if not account:
            raise HTTPException(404, "Usuário não encontrado.")
        if account.id == admin["id"] and not active:
            raise HTTPException(400, "Não é possível desativar a própria conta.")
        account.is_active = active
        log_audit(db, admin["id"], "activated" if active else "deactivated", "user", account.id, f"{'Ativou' if active else 'Desativou'} o usuário {account.email}.")
        db.commit()
=======
    resp = db.client.table(U).select("*").eq("id", user_id).execute()
    account = resp.data[0] if resp.data else None
    if not account:
        raise HTTPException(404, "Usuário não encontrado.")
    if user_id == admin["id"] and not active:
        raise HTTPException(400, "Não é possível desativar a própria conta.")
    db.client.table(U).update({"is_active": active}).eq("id", user_id).execute()
>>>>>>> 763faa02520857295d80a222e5a2a365debda955
    return RedirectResponse("/configuracoes?notice=Status%20do%20usuário%20atualizado.", status_code=303)
