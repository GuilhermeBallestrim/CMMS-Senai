from __future__ import annotations

import secrets
from datetime import datetime, timezone
from hmac import compare_digest
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from backend.database import db
from backend.dependencies import get_current_user, require_roles
from backend.models import (
    TABLE_AUDIT_LOGS, TABLE_EQUIPMENT, TABLE_MAINTENANCE_CALLS, TABLE_NOTIFICATIONS,
    TABLE_PURCHASE_REQUESTS, TABLE_SECTORS, TABLE_UNIT_SETTINGS, TABLE_USERS, TABLE_WORK_ORDERS,
)
from backend.schemas import (
    AuditLogRead, CallCreate, CallRead, CallUpdate, EquipmentCreate, EquipmentRead, EquipmentUpdate,
    LoginRequest, NotificationRead, PurchaseCreate, PurchaseDecision, PurchaseRead, SectorCreate,
    SectorRead, UnitSettingsRead, UnitSettingsUpdate, UserCreate, UserRead, WorkOrderAssignment, WorkOrderUpdate,
)
from backend.security import hash_password, verify_password
from backend.services import log_audit, notify_administrators, notify_user
from backend.storage import file_path, save_image, save_pdf

router = APIRouter(prefix="/api")
admin_only = require_roles("administrator")
authenticated = get_current_user
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def check_csrf(request: Request, supplied: str | None) -> None:
    expected = request.session.get("csrf_token", "")
    if not supplied or not expected or not compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="Token CSRF inválido. Atualize a página e tente novamente.")


async def csrf_header(request: Request) -> None:
    check_csrf(request, request.headers.get("x-csrf-token"))


def make_number(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc):%Y}-{uuid4().hex[:6].upper()}"


def get_or_create_unit_settings() -> dict:
    resp = db.client.table(TABLE_UNIT_SETTINGS).select("*").eq("id", 1).execute()
    if resp.data:
        return resp.data[0]
    created = db.client.table(TABLE_UNIT_SETTINGS).insert({"id": 1}).execute()
    return created.data[0] if created.data else {"id": 1}


C = TABLE_MAINTENANCE_CALLS
E = TABLE_EQUIPMENT
OS = TABLE_WORK_ORDERS
N = TABLE_NOTIFICATIONS
U = TABLE_USERS
S = TABLE_SECTORS
SC = TABLE_PURCHASE_REQUESTS
US = TABLE_UNIT_SETTINGS
AL = TABLE_AUDIT_LOGS

# --------------------------------------------------
# Notificações
# --------------------------------------------------

@router.get("/notifications", response_model=list[NotificationRead])
def list_notifications(user: dict = Depends(authenticated), limit: int = 50, offset: int = 0):
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    return (
        db.client.table(N)
        .select("*")
        .eq("user_id", user["id"])
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
        .data
    )


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(_admin: dict = Depends(admin_only)):
    return db.client.table(AL).select("*").order("created_at", desc=True).limit(200).execute().data


@router.post("/notifications/read-all", status_code=204, dependencies=[Depends(csrf_header)])
def read_all_notifications(user: dict = Depends(authenticated)):
    db.client.table(N).update({"is_read": True}).eq("user_id", user["id"]).eq("is_read", False).execute()
    return None


@router.patch("/notifications/{notification_id}/read", response_model=NotificationRead, dependencies=[Depends(csrf_header)])
def read_notification(notification_id: int, user: dict = Depends(authenticated)):
    resp = db.client.table(N).select("*").eq("id", notification_id).eq("user_id", user["id"]).execute()
    if not resp.data:
        raise HTTPException(404, "Notificação não encontrada.")
    db.client.table(N).update({"is_read": True}).eq("id", notification_id).execute()
    row = resp.data[0]; row["is_read"] = True
    return row


# --------------------------------------------------
# Unit Settings
# --------------------------------------------------

@router.get("/unit-settings", response_model=UnitSettingsRead)
def get_unit_settings(_admin: dict = Depends(admin_only)):
    return get_or_create_unit_settings()


@router.put("/unit-settings", response_model=UnitSettingsRead, dependencies=[Depends(csrf_header)])
def update_unit_settings(payload: UnitSettingsUpdate, admin: dict = Depends(admin_only)):
    valid = {"America/Sao_Paulo", "America/Manaus", "America/Belem", "America/Fortaleza", "America/Recife", "America/Rio_Branco", "UTC"}
    if payload.timezone_name not in valid:
        raise HTTPException(422, "Fuso horário não permitido.")
    get_or_create_unit_settings()
    resp = db.client.table(US).update({
        "unit_name": payload.unit_name.strip(),
        "timezone_name": payload.timezone_name,
        "notify_admin_new_call": payload.notify_admin_new_call,
    }).eq("id", 1).execute()
    log_audit(admin["id"], "updated", "unit_settings", 1, "Atualizou as preferências da unidade pela API.")
    return resp.data[0] if resp.data else {}


# --------------------------------------------------
# Files
# --------------------------------------------------

@router.post("/calls/{call_id}/photo", status_code=204, dependencies=[Depends(csrf_header)])
async def upload_call_photo(call_id: int, photo: UploadFile = File(...), user: dict = Depends(authenticated)):
    resp = db.client.table(C).select("*").eq("id", call_id).execute()
    if not resp.data:
        raise HTTPException(404, "Chamado não encontrado.")
    call = resp.data[0]
    if user["role"] == "professor" and call["requester_id"] != user["id"]:
        raise HTTPException(404, "Chamado não encontrado.")
    filename, mime = await save_image(photo, "calls")
    db.client.table(C).update({"photo_name": filename, "photo_mime": mime}).eq("id", call_id).execute()
    log_audit(user["id"], "uploaded", "maintenance_call", call_id, f"Adicionou uma foto ao chamado {call['number']} pela API.")
    return None


@router.post("/equipment/{equipment_id}/files", status_code=204, dependencies=[Depends(csrf_header)])
async def upload_equipment_files(equipment_id: int, photo: UploadFile | None = File(None), manual: UploadFile | None = File(None), admin: dict = Depends(admin_only)):
    resp = db.client.table(E).select("*").eq("id", equipment_id).execute()
    if not resp.data:
        raise HTTPException(404, "Equipamento não encontrado.")
    if not photo and not manual:
        raise HTTPException(422, "Envie uma foto, um manual PDF ou ambos.")
    update = {}
    if photo:
        fn, mime = await save_image(photo, "equipment"); update["photo_name"], update["photo_mime"] = fn, mime
    if manual:
        fn, mime = await save_pdf(manual, "equipment"); update["manual_name"], update["manual_mime"] = fn, mime
    db.client.table(E).update(update).eq("id", equipment_id).execute()
    log_audit(admin["id"], "uploaded", "equipment", equipment_id, "Atualizou anexos do equipamento pela API.")
    return None


@router.get("/calls/{call_id}/photo")
def get_call_photo(call_id: int, user: dict = Depends(authenticated)):
    resp = db.client.table(C).select("*").eq("id", call_id).execute()
    if not resp.data:
        raise HTTPException(404, "Foto não encontrada.")
    call = resp.data[0]
    if not call.get("photo_name") or (user["role"] == "professor" and call["requester_id"] != user["id"]):
        raise HTTPException(404, "Foto não encontrada.")
    return FileResponse(file_path("calls", call["photo_name"]), media_type=call.get("photo_mime") or "application/octet-stream")


@router.get("/equipment/{equipment_id}/photo")
def get_equipment_photo(_user: dict = Depends(authenticated)):
    resp = db.client.table(E).select("*").eq("id", equipment_id).execute()
    if not resp.data or not resp.data[0].get("photo_name"):
        raise HTTPException(404, "Foto não encontrada.")
    e = resp.data[0]
    return FileResponse(file_path("equipment", e["photo_name"]), media_type=e.get("photo_mime") or "application/octet-stream")


@router.get("/equipment/{equipment_id}/manual")
def get_equipment_manual(_user: dict = Depends(authenticated)):
    resp = db.client.table(E).select("*").eq("id", equipment_id).execute()
    if not resp.data or not resp.data[0].get("manual_name"):
        raise HTTPException(404, "Manual não encontrado.")
    e = resp.data[0]
    return FileResponse(file_path("equipment", e["manual_name"]), media_type=e.get("manual_mime") or "application/pdf")


# --------------------------------------------------
# Auth & health
# --------------------------------------------------

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/auth/csrf")
def csrf_token(request: Request):
    t = request.session.get("csrf_token")
    if not t:
        t = secrets.token_urlsafe(32)
        request.session["csrf_token"] = t
    return {"csrf_token": t}


@router.post("/auth/login", response_model=UserRead)
def api_login(payload: LoginRequest, request: Request):
    email = str(payload.email).strip().lower()
    resp = db.client.table(U).select("*").eq("email", email).execute()
    user = resp.data[0] if resp.data else None
    stored = user["password_hash"] if user else DUMMY_PASSWORD_HASH
    valid = verify_password(payload.password, stored)
    if not user or not user.get("is_active") or not valid:
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    request.session.clear()
    request.session.update({"user_id": user["id"], "csrf_token": secrets.token_urlsafe(32)})
    return user


@router.post("/auth/logout", status_code=204, dependencies=[Depends(authenticated), Depends(csrf_header)])
def api_logout(request: Request):
    request.session.clear()
    return None


@router.get("/auth/me", response_model=UserRead)
def api_me(user: dict = Depends(authenticated)):
    return user


# --------------------------------------------------
# Users
# --------------------------------------------------

@router.get("/users", response_model=list[UserRead])
def list_users(_admin: dict = Depends(admin_only)):
    return db.client.table(U).select("*").order("name").execute().data


@router.post("/users", response_model=UserRead, status_code=201, dependencies=[Depends(csrf_header)])
def create_user(payload: UserCreate, admin: dict = Depends(admin_only)):
    resp = db.client.table(U).select("id").eq("email", str(payload.email).lower()).execute()
    if resp.data:
        raise HTTPException(409, "Este e-mail já está cadastrado.")
    resp = db.client.table(U).insert({
        "name": payload.name.strip(),
        "email": str(payload.email).lower(),
        "password_hash": hash_password(payload.password),
        "role": payload.role,
    }).execute()
    if resp.data:
        log_audit(admin["id"], "created", "user", resp.data[0]["id"], f"Cadastrou o usuário {payload.email} pela API.")
    return resp.data[0]


@router.patch("/users/{user_id}/active", response_model=UserRead, dependencies=[Depends(csrf_header)])
def set_user_active(user_id: int, active: bool, admin: dict = Depends(admin_only)):
    resp = db.client.table(U).select("*").eq("id", user_id).execute()
    if not resp.data:
        raise HTTPException(404, "Usuário não encontrado.")
    if user_id == admin["id"] and not active:
        raise HTTPException(400, "Não é possível desativar a própria conta administrativa.")
    db.client.table(U).update({"is_active": active}).eq("id", user_id).execute()
    log_audit(admin["id"], "activated" if active else "deactivated", "user", user_id, f"{'Ativou' if active else 'Desativou'} usuário pela API.")
    return db.client.table(U).select("*").eq("id", user_id).execute().data[0]


# --------------------------------------------------
# Sectors
# --------------------------------------------------

@router.get("/sectors", response_model=list[SectorRead])
def list_sectors(_user: dict = Depends(authenticated)):
    return db.client.table(S).select("*").order("name").execute().data


@router.post("/sectors", response_model=SectorRead, status_code=201, dependencies=[Depends(csrf_header)])
def create_sector(payload: SectorCreate, admin: dict = Depends(admin_only)):
    resp = db.client.table(S).select("id").eq("name", payload.name.strip()).execute()
    if resp.data:
        raise HTTPException(409, "Já existe um setor com este nome.")
    resp = db.client.table(S).insert({"name": payload.name.strip()}).execute()
    if resp.data:
        log_audit(admin["id"], "created", "sector", resp.data[0]["id"], f"Cadastrou o setor {payload.name.strip()} pela API.")
    return resp.data[0]


# --------------------------------------------------
# Equipment
# --------------------------------------------------

@router.get("/equipment", response_model=list[EquipmentRead])
def list_equipment(
    _user: dict = Depends(authenticated),
    limit: int = 50,
    offset: int = 0,
    sector_id: int | None = None,
    state: str | None = None,
    search: str | None = None,
):
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    q = db.client.table(E).select("*").order("name")
    if sector_id:
        q = q.eq("sector_id", sector_id)
    if state:
        q = q.eq("state", state)
    if search:
        q = q.or_(f"name.ilike.%{search}%,asset_tag.ilike.%{search}%")
    return q.range(offset, offset + limit - 1).execute().data


@router.post("/equipment", response_model=EquipmentRead, status_code=201, dependencies=[Depends(csrf_header)])
def create_equipment(payload: EquipmentCreate, admin: dict = Depends(admin_only)):
    if not db.client.table(S).select("id").eq("id", payload.sector_id).execute().data:
        raise HTTPException(422, "Setor não encontrado.")
    if payload.responsible_id and not db.client.table(U).select("id").eq("id", payload.responsible_id).execute().data:
        raise HTTPException(422, "Responsável não encontrado.")
    resp = db.client.table(E).insert(payload.model_dump()).execute()
    if resp.data:
        log_audit(admin["id"], "created", "equipment", resp.data[0]["id"], f"Cadastrou o equipamento {payload.asset_tag} pela API.")
    return resp.data[0]


@router.get("/equipment/{equipment_id}", response_model=EquipmentRead)
def get_equipment(equipment_id: int, _user: dict = Depends(authenticated)):
    resp = db.client.table(E).select("*").eq("id", equipment_id).execute()
    if not resp.data:
        raise HTTPException(404, "Equipamento não encontrado.")
    return resp.data[0]


@router.get("/equipment/{equipment_id}/historico")
def get_equipment_history(equipment_id: int, _user: dict = Depends(authenticated)):
    # RF-05: intervenções e eventos associados ao ativo.
    if not db.client.table(E).select("id").eq("id", equipment_id).execute().data:
        raise HTTPException(404, "Equipamento não encontrado.")
    calls = db.client.table(C).select("*").eq("equipment_id", equipment_id).order("created_at", desc=True).execute().data
    call_ids = [c["id"] for c in calls]
    orders = []
    if call_ids:
        orders = db.client.table(OS).select("*").in_("call_id", call_ids).order("id", desc=True).execute().data
    call_map = {c["id"]: c for c in calls}
    result = []
    for o in orders:
        c = call_map.get(o.get("call_id"), {})
        result.append({
            "order": o,
            "call": c,
        })
    return {
        "equipment_id": equipment_id,
        "calls": calls,
        "work_orders": orders,
        "timeline": result,
    }


@router.patch("/equipment/{equipment_id}", response_model=EquipmentRead, dependencies=[Depends(csrf_header)])
def update_equipment(equipment_id: int, payload: EquipmentUpdate, admin: dict = Depends(admin_only)):
    resp = db.client.table(E).select("*").eq("id", equipment_id).execute()
    if not resp.data:
        raise HTTPException(404, "Equipamento não encontrado.")
    data = payload.model_dump(exclude_unset=True)
    if "sector_id" in data and data["sector_id"] is not None and not db.client.table(S).select("id").eq("id", data["sector_id"]).execute().data:
        raise HTTPException(422, "Setor não encontrado.")
    if "responsible_id" in data and data["responsible_id"] is not None and not db.client.table(U).select("id").eq("id", data["responsible_id"]).execute().data:
        raise HTTPException(422, "Responsável não encontrado.")
    if data:
        db.client.table(E).update(data).eq("id", equipment_id).execute()
    log_audit(admin["id"], "updated", "equipment", equipment_id, "Atualizou o equipamento pela API.")
    return db.client.table(E).select("*").eq("id", equipment_id).execute().data[0]


# --------------------------------------------------
# Calls
# --------------------------------------------------

@router.get("/calls", response_model=list[CallRead])
def list_calls(
    user: dict = Depends(authenticated),
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    priority: str | None = None,
    equipment_id: int | None = None,
):
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    q = db.client.table(C).select("*").order("created_at", desc=True)
    if user["role"] == "professor":
        q = q.eq("requester_id", user["id"])
    if status:
        q = q.eq("status", status)
    if priority:
        q = q.eq("priority", priority)
    if equipment_id:
        q = q.eq("equipment_id", equipment_id)
    return q.range(offset, offset + limit - 1).execute().data


@router.post("/calls", response_model=CallRead, status_code=201, dependencies=[Depends(csrf_header)])
def create_call(payload: CallCreate, user: dict = Depends(authenticated)):
    if not db.client.table(E).select("id").eq("id", payload.equipment_id).execute().data:
        raise HTTPException(422, "Equipamento não encontrado.")
    resp = db.client.table(C).insert({
        "number": make_number("CH"),
        "requester_id": user["id"],
        "equipment_id": payload.equipment_id,
        "description": payload.description,
        "priority": payload.priority,
    }).execute()
    call = resp.data[0]
    prefs = get_or_create_unit_settings()
    if prefs.get("notify_admin_new_call"):
        kind = "warning" if payload.priority in {"Alta", "Crítica"} else "info"
        notify_administrators("Novo chamado", f"{call['number']}: {payload.priority} prioridade.", f"/chamados/detalhe?id={call['id']}", kind)
    log_audit(user["id"], "created", "maintenance_call", call["id"], f"Abriu o chamado {call['number']} pela API.")
    return call


@router.get("/calls/{call_id}", response_model=CallRead)
def get_call(call_id: int, user: dict = Depends(authenticated)):
    resp = db.client.table(C).select("*").eq("id", call_id).execute()
    if not resp.data:
        raise HTTPException(404, "Chamado não encontrado.")
    call = resp.data[0]
    if user["role"] == "professor" and call["requester_id"] != user["id"]:
        raise HTTPException(404, "Chamado não encontrado.")
    return call


@router.patch("/calls/{call_id}", response_model=CallRead, dependencies=[Depends(csrf_header)])
def update_call(call_id: int, payload: CallUpdate, user: dict = Depends(authenticated)):
    resp = db.client.table(C).select("*").eq("id", call_id).execute()
    if not resp.data:
        raise HTTPException(404, "Chamado não encontrado.")
    call = resp.data[0]
    old = call["status"]
    if user["role"] == "professor":
        if call["requester_id"] != user["id"] or payload.status != "Cancelado" or call["status"] != "Aberto":
            raise HTTPException(403, "Professor só pode cancelar o próprio chamado enquanto estiver aberto.")
    else:
        # Apenas cancelamento de chamado aberto é permitido por esta rota;
        # avanço de atendimento ocorre via aprovação e atualização de OS (§3.2).
        if payload.status != "Cancelado" or call["status"] != "Aberto":
            raise HTTPException(409, "Use a aprovação do chamado e as atualizações da ordem de serviço para avançar o atendimento.")
    db.client.table(C).update({"status": payload.status, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", call_id).execute()
    if old != payload.status:
        if user["role"] == "professor":
            notify_administrators("Chamado cancelado", f"{call['number']} foi cancelado pelo solicitante.", f"/chamados/detalhe?id={call_id}", "warning")
        else:
            notify_user(call["requester_id"], "Chamado atualizado", f"{call['number']}: {payload.status}.", f"/chamados/detalhe?id={call_id}")
        log_audit(user["id"], "cancelled" if payload.status == "Cancelado" else "updated", "maintenance_call", call_id, f"Alterou o chamado {call['number']} para {payload.status} pela API.")
    call["status"] = payload.status
    return call


@router.post("/calls/{call_id}/approve", status_code=201, dependencies=[Depends(csrf_header)])
def approve_call(call_id: int, admin: dict = Depends(admin_only)):
    resp = db.client.table(C).select("*").eq("id", call_id).execute()
    if not resp.data:
        raise HTTPException(404, "Chamado não encontrado.")
    call = resp.data[0]
    if call["status"] == "Cancelado":
        raise HTTPException(409, "Chamados cancelados não podem gerar ordem de serviço.")
    number = make_number("OS")
    # Tenta operação atômica via RPC (§7.3). Se a função não existir, fallback sequencial.
    try:
        rpc = db.client.rpc("approve_call_atomic", {"p_call_id": call_id, "p_admin_id": admin["id"], "p_number": number}).execute()
        order_data = rpc.data if isinstance(rpc.data, dict) else (rpc.data[0] if rpc.data else None)
        if isinstance(order_data, str):
            import json as _json
            order_data = _json.loads(order_data)
        order_id = order_data["id"]
        order_number = order_data["number"]
        order_status = order_data["status"]
    except Exception:
        # Fallback sequencial (sem atomicidade) para ambientes sem a função RPC.
        wo = db.client.table(OS).select("*").eq("call_id", call_id).execute()
        if wo.data:
            w = wo.data[0]
            return {"id": w["id"], "number": w["number"], "status": w["status"]}
        created = db.client.table(OS).insert({
            "number": number, "call_id": call_id, "responsible_id": admin["id"], "status": "Aguardando início",
        }).execute()
        order = created.data[0]
        order_id, order_number, order_status = order["id"], order["number"], order["status"]
        db.client.table(C).update({"status": "Em análise", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", call_id).execute()
    notify_user(call["requester_id"], "Chamado aprovado", f"{call['number']} gerou a ordem {order_number}.", f"/chamados/detalhe?id={call_id}")
    log_audit(admin["id"], "approved", "maintenance_call", call_id, f"Aprovou {call['number']} e gerou {order_number} pela API.")
    return {"id": order_id, "number": order_number, "status": order_status}


@router.post("/calls/{call_id}/atribuicoes", status_code=201, dependencies=[Depends(csrf_header)])
def assign_call(call_id: int, payload: WorkOrderAssignment, admin: dict = Depends(admin_only)):
    # RF-09: atribui a OS do chamado a um técnico/administrador responsável.
    resp = db.client.table(C).select("*").eq("id", call_id).execute()
    if not resp.data:
        raise HTTPException(404, "Chamado não encontrado.")
    call = resp.data[0]
    wo = db.client.table(OS).select("*").eq("call_id", call_id).execute()
    if not wo.data:
        raise HTTPException(409, "Chamado ainda não foi aprovado (sem ordem de serviço).")
    order = wo.data[0]
    if order["status"] == "Concluída":
        raise HTTPException(409, "Ordem concluída não pode ser reatribuída.")
    if not db.client.table(U).select("id").eq("id", payload.responsible_id).eq("is_active", True).execute().data:
        raise HTTPException(422, "Responsável não encontrado ou inativo.")
    db.client.table(OS).update({"responsible_id": payload.responsible_id}).eq("id", order["id"]).execute()
    notify_user(payload.responsible_id, "Ordem de serviço atribuída", f"{order['number']}: {call['number']}.", f"/chamados/detalhe?id={call_id}")
    log_audit(admin["id"], "assigned", "work_order", order["id"], f"Atribuiu {order['number']} ao usuário {payload.responsible_id}.")
    return db.client.table(OS).select("*").eq("id", order["id"]).execute().data[0]


# --------------------------------------------------
# Work Orders
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


@router.get("/work-orders")
def list_work_orders(
    user: dict = Depends(authenticated),
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
):
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    q = db.client.table(OS).select("*").order("id", desc=True)
    if user["role"] == "professor":
        ids = {c["id"] for c in db.client.table(C).select("id").eq("requester_id", user["id"]).execute().data}
        if not ids:
            return []
        q = q.in_("call_id", list(ids))
    if status:
        q = q.eq("status", status)
    return q.range(offset, offset + limit - 1).execute().data


@router.get("/work-orders/{order_id}")
def get_work_order(order_id: int, user: dict = Depends(authenticated)):
    resp = db.client.table(OS).select("*").eq("id", order_id).execute()
    if not resp.data:
        raise HTTPException(404, "Ordem de serviço não encontrada.")
    order = resp.data[0]
    call, _ = _call_equipment(order.get("call_id"))
    if user["role"] == "professor" and call and call["requester_id"] != user["id"]:
        raise HTTPException(404, "Ordem de serviço não encontrada.")
    return order


@router.patch("/work-orders/{order_id}", dependencies=[Depends(csrf_header)])
def update_work_order(order_id: int, payload: WorkOrderUpdate, user: dict = Depends(authenticated)):
    if user["role"] not in ("administrator", "tecnico"):
        raise HTTPException(403, "Seu perfil não permite esta operação.")
    resp = db.client.table(OS).select("*").eq("id", order_id).execute()
    if not resp.data:
        raise HTTPException(404, "Ordem de serviço não encontrada.")
    order = resp.data[0]
    if order["status"] == "Concluída":
        raise HTTPException(409, "Ordem concluída não pode ser alterada.")
    # Técnico só pode atuar na própria OS e não reatribui responsável.
    if user["role"] == "tecnico" and order.get("responsible_id") != user["id"]:
        raise HTTPException(403, "Você não é o responsável por esta ordem de serviço.")
    update = payload.model_dump(exclude_unset=True)
    if user["role"] == "tecnico":
        update.pop("responsible_id", None)
    new_status = update.get("status") or order["status"]
    status_changed = "status" in update and update.get("status") is not None

    # RF-12 CA2: conclusão exige solução registrada.
    if status_changed and new_status == "Concluída":
        solution = (update.get("solution") or order.get("solution") or "").strip()
        if not solution:
            raise HTTPException(422, "Não é possível concluir a OS sem registrar a solução aplicada.")

    # Reatribuição de responsável (somente administrador).
    if "responsible_id" in update and update["responsible_id"] is not None:
        if user["role"] != "administrator":
            raise HTTPException(403, "Apenas administradores podem reatribuir a OS.")
        if not db.client.table(U).select("id").eq("id", update["responsible_id"]).eq("is_active", True).execute().data:
            raise HTTPException(422, "Responsável não encontrado ou inativo.")

    call, equip = _call_equipment(order.get("call_id"))

    if status_changed:
        if new_status == "Em execução" and not order.get("started_at"):
            update["started_at"] = datetime.now(timezone.utc).isoformat()
        if new_status == "Concluída":
            solution = (update.get("solution") or order.get("solution") or "").strip()
            # Tenta operação atômica via RPC (§7.3).
            rpc_ok = False
            try:
                db.client.rpc("conclude_order_atomic", {"p_order_id": order_id, "p_solution": solution}).execute()
                rpc_ok = True
            except Exception:
                rpc_ok = False
            if rpc_ok:
                # Remove campos já tratados pela RPC do update restante.
                update.pop("status", None)
                update.pop("solution", None)
                update.pop("finished_at", None)
            else:
                update["finished_at"] = datetime.now(timezone.utc).isoformat()
                if call:
                    db.client.table(C).update({"status": "Concluído", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", call["id"]).execute()
                    if equip:
                        db.client.table(E).update({"state": "Disponível"}).eq("id", equip["id"]).execute()
        elif new_status == "Aguardando peça":
            if call:
                db.client.table(C).update({"status": "Aguardando peça", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", call["id"]).execute()
                if equip:
                    db.client.table(E).update({"state": "Em manutenção"}).eq("id", equip["id"]).execute()
        else:
            if call:
                db.client.table(C).update({"status": "Em manutenção", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", call["id"]).execute()
                if equip:
                    db.client.table(E).update({"state": "Em manutenção"}).eq("id", equip["id"]).execute()

    # Se a RPC concluiu, garante que o status persistido reflita a conclusão.
    if status_changed and new_status == "Concluída":
        update.setdefault("status", "Concluída")
    if update:
        db.client.table(OS).update(update).eq("id", order_id).execute()

    if call:
        notify_user(call["requester_id"], "Ordem de serviço atualizada", f"{order['number']}: {new_status}.", f"/chamados/detalhe?id={call['id']}")
    log_audit(user["id"], "updated", "work_order", order_id, f"Atualizou {order['number']} para {new_status} pela API.")
    return db.client.table(OS).select("*").eq("id", order_id).execute().data[0]


# --------------------------------------------------
# Purchase Requests
# --------------------------------------------------

@router.get("/purchase-requests", response_model=list[PurchaseRead])
def list_purchase_requests(
    user: dict = Depends(authenticated),
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
):
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    q = db.client.table(SC).select("*").order("created_at", desc=True)
    if user["role"] == "professor":
        q = q.eq("requester_id", user["id"])
    if status:
        q = q.eq("status", status)
    return q.range(offset, offset + limit - 1).execute().data


@router.post("/purchase-requests", response_model=PurchaseRead, status_code=201, dependencies=[Depends(csrf_header)])
def create_purchase_request(payload: PurchaseCreate, user: dict = Depends(authenticated)):
    resp = db.client.table(SC).insert({
        "number": make_number("SC"),
        "requester_id": user["id"],
        "item_type": payload.item_type,
        "item": payload.item,
        "quantity": payload.quantity,
        "justification": payload.justification,
    }).execute()
    r = resp.data[0]
    notify_administrators("Nova solicitação de compra", f"{r['number']}: {r['item']}.", "/solicitacoes", "info")
    log_audit(user["id"], "created", "purchase_request", r["id"], f"Criou a solicitação {r['number']} pela API.")
    return r


@router.patch("/purchase-requests/{request_id}", response_model=PurchaseRead, dependencies=[Depends(csrf_header)])
def decide_purchase_request(request_id: int, payload: PurchaseDecision, admin: dict = Depends(admin_only)):
    resp = db.client.table(SC).select("*").eq("id", request_id).execute()
    if not resp.data:
        raise HTTPException(404, "Solicitação não encontrada.")
    r = resp.data[0]
    if r["status"] != "Em análise":
        raise HTTPException(409, "Esta solicitação já foi analisada.")
    db.client.table(SC).update({"status": payload.status, "reviewed_by_id": admin["id"]}).eq("id", request_id).execute()
    notify_user(r["requester_id"], "Solicitação analisada", f"{r['number']}: {payload.status.lower()}.", "/solicitacoes")
    log_audit(admin["id"], "reviewed", "purchase_request", request_id, f"{r['number']} marcada como {payload.status} pela API.")
    return db.client.table(SC).select("*").eq("id", request_id).execute().data[0]


# --------------------------------------------------
# History & Indicators
# --------------------------------------------------

@router.get("/history")
def history(user: dict = Depends(authenticated), limit: int = 50, offset: int = 0):
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    q = db.client.table(OS).select("*").eq("status", "Concluída").order("finished_at", desc=True)
    if user["role"] == "professor":
        ids = {c["id"] for c in db.client.table(C).select("id").eq("requester_id", user["id"]).execute().data}
        if not ids:
            return []
        q = q.in_("call_id", list(ids))
    return q.range(offset, offset + limit - 1).execute().data


@router.get("/indicators")
def indicators(_admin: dict = Depends(admin_only)):
    calls = db.client.table(C).select("*").execute().data
    open_calls = [c for c in calls if c["status"] not in ("Concluído", "Cancelado")]
    equipment = db.client.table(E).select("*").execute().data
    equipment_map = {e["id"]: e for e in equipment}
    unavailable = [e for e in equipment if e.get("state") == "Indisponível"]
    orders = db.client.table(OS).select("*").execute().data
    completed = [o for o in orders if o["status"] == "Concluída"]

    # MTTR: tempo médio de reparo (início -> conclusão da OS).
    repair_durations = []
    for o in orders:
        s, e = o.get("started_at"), o.get("finished_at")
        if s and e:
            try:
                repair_durations.append((datetime.fromisoformat(str(e).replace("Z", "+00:00")) - datetime.fromisoformat(str(s).replace("Z", "+00:00"))).total_seconds() / 3600)
            except Exception:
                pass
    mttr = round(sum(repair_durations) / len(repair_durations), 1) if repair_durations else None

    # MTBF: tempo médio entre falhas (por equipamento, média dos intervalos entre chamados).
    # Agrupa chamados por equipamento ordenados por data de abertura.
    calls_by_equip = {}
    for c in calls:
        calls_by_equip.setdefault(c["equipment_id"], []).append(c)
    mtbf_per_equip = []
    for eq_id, eq_calls in calls_by_equip.items():
        if len(eq_calls) < 2:
            continue
        eq_calls.sort(key=lambda x: x.get("created_at") or "")
        intervals = []
        for i in range(1, len(eq_calls)):
            try:
                a = datetime.fromisoformat(str(eq_calls[i - 1].get("created_at")).replace("Z", "+00:00"))
                b = datetime.fromisoformat(str(eq_calls[i].get("created_at")).replace("Z", "+00:00"))
                intervals.append((b - a).total_seconds() / 3600)
            except Exception:
                pass
        if intervals:
            mtbf_per_equip.append(sum(intervals) / len(intervals))
    mtbf = round(sum(mtbf_per_equip) / len(mtbf_per_equip), 1) if mtbf_per_equip else None

    # Disponibilidade aproximada: MTBF / (MTBF + MTTR) * 100.
    availability = None
    if mtbf is not None and mttr is not None and (mtbf + mttr) > 0:
        availability = round(mtbf / (mtbf + mttr) * 100, 1)

    # Tempo médio de atendimento (lead time): abertura do chamado -> conclusão da OS.
    lead_times = []
    order_by_call = {o.get("call_id"): o for o in orders}
    for c in calls:
        o = order_by_call.get(c["id"])
        if o and o.get("finished_at") and c.get("created_at"):
            try:
                a = datetime.fromisoformat(str(c["created_at"]).replace("Z", "+00:00"))
                b = datetime.fromisoformat(str(o["finished_at"]).replace("Z", "+00:00"))
                lead_times.append((b - a).total_seconds() / 3600)
            except Exception:
                pass
    avg_lead_time = round(sum(lead_times) / len(lead_times), 1) if lead_times else None

    completion_rate = round(len(completed) / len(orders) * 100, 1) if orders else None

    # Chamados por equipamento + ranking de falhas.
    calls_per_equip = []
    for eq_id, eq_calls in calls_by_equip.items():
        eq = equipment_map.get(eq_id, {})
        calls_per_equip.append({
            "equipment_id": eq_id,
            "equipment_name": eq.get("name", "?"),
            "count": len(eq_calls),
        })
    calls_per_equip.sort(key=lambda x: x["count"], reverse=True)
    top_failing = calls_per_equip[:5]

    return {
        "calls_total": len(calls),
        "backlog": len(open_calls),
        "equipment_total": len(equipment),
        "unavailable_equipment": len(unavailable),
        "mttr_hours": mttr,
        "mtbf_hours": mtbf,
        "availability_percent": availability,
        "completion_rate": completion_rate,
        "avg_lead_time_hours": avg_lead_time,
        "calls_per_equipment": calls_per_equip,
        "top_failing_equipment": top_failing,
        "insufficient_data": not bool(repair_durations) or not orders,
    }