from __future__ import annotations

import secrets
from datetime import datetime, timezone
from hmac import compare_digest
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, require_roles
from backend.models import Equipment, MaintenanceCall, PurchaseRequest, Sector, User, WorkOrder, utc_now
from backend.schemas import (
    CallCreate, CallRead, CallUpdate, EquipmentCreate, EquipmentRead, LoginRequest,
    PurchaseCreate, PurchaseDecision, PurchaseRead, SectorCreate, SectorRead,
    UserCreate, UserRead, WorkOrderUpdate,
)
from backend.security import hash_password, verify_password


router = APIRouter(prefix="/api")
admin_only = require_roles("administrator")
authenticated = get_current_user
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def check_csrf(request: Request, supplied: str | None) -> None:
    expected = request.session.get("csrf_token", "")
    if not supplied or not expected or not compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="Token CSRF inválido. Atualize a página e tente novamente.")


async def csrf_form(request: Request) -> None:
    form = await request.form()
    check_csrf(request, str(form.get("csrf_token", "")))


async def csrf_header(request: Request) -> None:
    check_csrf(request, request.headers.get("x-csrf-token"))


def make_number(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc):%Y}-{uuid4().hex[:6].upper()}"


def commit_or_conflict(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=message) from exc


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/auth/csrf")
def csrf_token(request: Request):
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return {"csrf_token": token}


@router.post("/auth/login", response_model=UserRead)
def api_login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).strip().lower()))
    stored_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    valid = verify_password(payload.password, stored_hash)
    if not user or not user.is_active or not valid:
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    request.session.clear()
    request.session.update({"user_id": user.id, "csrf_token": secrets.token_urlsafe(32)})
    return user


@router.post("/auth/logout", status_code=204, dependencies=[Depends(authenticated), Depends(csrf_header)])
def api_logout(request: Request):
    request.session.clear()
    return None


@router.get("/auth/me", response_model=UserRead)
def api_me(user: User = Depends(authenticated)):
    return user


@router.get("/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), _admin: User = Depends(admin_only)):
    return db.scalars(select(User).order_by(User.name)).all()


@router.post("/users", response_model=UserRead, status_code=201, dependencies=[Depends(csrf_header)])
def create_user(payload: UserCreate, db: Session = Depends(get_db), _admin: User = Depends(admin_only)):
    user = User(name=payload.name.strip(), email=str(payload.email).lower(), password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    commit_or_conflict(db, "Este e-mail já está cadastrado.")
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/active", response_model=UserRead, dependencies=[Depends(csrf_header)])
def set_user_active(user_id: int, active: bool, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Usuário não encontrado.")
    if user.id == admin.id and not active:
        raise HTTPException(400, "Não é possível desativar a própria conta administrativa.")
    user.is_active = active
    db.commit()
    return user


@router.get("/sectors", response_model=list[SectorRead])
def list_sectors(db: Session = Depends(get_db), _user: User = Depends(authenticated)):
    return db.scalars(select(Sector).order_by(Sector.name)).all()


@router.post("/sectors", response_model=SectorRead, status_code=201, dependencies=[Depends(csrf_header)])
def create_sector(payload: SectorCreate, db: Session = Depends(get_db), _admin: User = Depends(admin_only)):
    sector = Sector(name=payload.name.strip())
    db.add(sector)
    commit_or_conflict(db, "Já existe um setor com este nome.")
    db.refresh(sector)
    return sector


@router.get("/equipment", response_model=list[EquipmentRead])
def list_equipment(db: Session = Depends(get_db), _user: User = Depends(authenticated)):
    return db.scalars(select(Equipment).order_by(Equipment.name)).all()


@router.post("/equipment", response_model=EquipmentRead, status_code=201, dependencies=[Depends(csrf_header)])
def create_equipment(payload: EquipmentCreate, db: Session = Depends(get_db), _admin: User = Depends(admin_only)):
    if not db.get(Sector, payload.sector_id):
        raise HTTPException(422, "Setor não encontrado.")
    if payload.responsible_id and not db.get(User, payload.responsible_id):
        raise HTTPException(422, "Responsável não encontrado.")
    equipment = Equipment(**payload.model_dump())
    db.add(equipment)
    commit_or_conflict(db, "Já existe um equipamento com este patrimônio.")
    db.refresh(equipment)
    return equipment


@router.get("/equipment/{equipment_id}", response_model=EquipmentRead)
def get_equipment(equipment_id: int, db: Session = Depends(get_db), _user: User = Depends(authenticated)):
    equipment = db.get(Equipment, equipment_id)
    if not equipment:
        raise HTTPException(404, "Equipamento não encontrado.")
    return equipment


@router.get("/calls", response_model=list[CallRead])
def list_calls(db: Session = Depends(get_db), user: User = Depends(authenticated)):
    query = select(MaintenanceCall).order_by(MaintenanceCall.created_at.desc())
    if user.role == "professor":
        query = query.where(MaintenanceCall.requester_id == user.id)
    return db.scalars(query).all()


@router.post("/calls", response_model=CallRead, status_code=201, dependencies=[Depends(csrf_header)])
def create_call(payload: CallCreate, db: Session = Depends(get_db), user: User = Depends(authenticated)):
    if not db.get(Equipment, payload.equipment_id):
        raise HTTPException(422, "Equipamento não encontrado.")
    call = MaintenanceCall(number=make_number("CH"), requester_id=user.id, **payload.model_dump())
    db.add(call)
    db.commit()
    db.refresh(call)
    return call


@router.get("/calls/{call_id}", response_model=CallRead)
def get_call(call_id: int, db: Session = Depends(get_db), user: User = Depends(authenticated)):
    call = db.get(MaintenanceCall, call_id)
    if not call:
        raise HTTPException(404, "Chamado não encontrado.")
    if user.role == "professor" and call.requester_id != user.id:
        raise HTTPException(404, "Chamado não encontrado.")
    return call


@router.patch("/calls/{call_id}", response_model=CallRead, dependencies=[Depends(csrf_header)])
def update_call(call_id: int, payload: CallUpdate, db: Session = Depends(get_db), user: User = Depends(authenticated)):
    call = db.get(MaintenanceCall, call_id)
    if not call:
        raise HTTPException(404, "Chamado não encontrado.")
    if user.role == "professor":
        if call.requester_id != user.id or payload.status != "Cancelado" or call.status != "Aberto":
            raise HTTPException(403, "Professor só pode cancelar o próprio chamado enquanto estiver aberto.")
    call.status = payload.status
    call.updated_at = utc_now()
    db.commit()
    return call


@router.post("/calls/{call_id}/approve", status_code=201, dependencies=[Depends(csrf_header)])
def approve_call(call_id: int, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    call = db.get(MaintenanceCall, call_id)
    if not call:
        raise HTTPException(404, "Chamado não encontrado.")
    if call.status == "Cancelado":
        raise HTTPException(409, "Chamados cancelados não podem gerar ordem de serviço.")
    if call.work_order:
        return {"id": call.work_order.id, "number": call.work_order.number, "status": call.work_order.status}
    order = WorkOrder(number=make_number("OS"), call=call, responsible_id=admin.id, status="Aguardando início")
    call.status = "Em análise"
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"id": order.id, "number": order.number, "status": order.status}


@router.get("/work-orders")
def list_work_orders(db: Session = Depends(get_db), user: User = Depends(authenticated)):
    query = select(WorkOrder).join(MaintenanceCall).order_by(WorkOrder.id.desc())
    if user.role == "professor":
        query = query.where(MaintenanceCall.requester_id == user.id)
    return db.scalars(query).all()


@router.get("/work-orders/{order_id}")
def get_work_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(authenticated)):
    order = db.get(WorkOrder, order_id)
    if not order or (user.role == "professor" and order.call.requester_id != user.id):
        raise HTTPException(404, "Ordem de serviço não encontrada.")
    return order


@router.patch("/work-orders/{order_id}", dependencies=[Depends(csrf_header)])
def update_work_order(order_id: int, payload: WorkOrderUpdate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    order = db.get(WorkOrder, order_id)
    if not order:
        raise HTTPException(404, "Ordem de serviço não encontrada.")
    if order.status == "Concluída":
        raise HTTPException(409, "Ordem concluída não pode ser alterada.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(order, field, value)
    if payload.status == "Em execução" and not order.started_at:
        order.started_at = utc_now()
    if payload.status == "Concluída":
        order.finished_at = utc_now()
        order.call.status = "Concluído"
        order.call.equipment.state = "Disponível"
    else:
        order.call.status = "Aguardando peça" if payload.status == "Aguardando peça" else "Em manutenção"
        order.call.equipment.state = "Em manutenção"
    order.call.updated_at = utc_now()
    db.commit()
    return order


@router.get("/purchase-requests", response_model=list[PurchaseRead])
def list_purchase_requests(db: Session = Depends(get_db), user: User = Depends(authenticated)):
    query = select(PurchaseRequest).order_by(PurchaseRequest.created_at.desc())
    if user.role == "professor":
        query = query.where(PurchaseRequest.requester_id == user.id)
    return db.scalars(query).all()


@router.post("/purchase-requests", response_model=PurchaseRead, status_code=201, dependencies=[Depends(csrf_header)])
def create_purchase_request(payload: PurchaseCreate, db: Session = Depends(get_db), user: User = Depends(authenticated)):
    request = PurchaseRequest(number=make_number("SC"), requester_id=user.id, **payload.model_dump())
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


@router.patch("/purchase-requests/{request_id}", response_model=PurchaseRead, dependencies=[Depends(csrf_header)])
def decide_purchase_request(request_id: int, payload: PurchaseDecision, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    request = db.get(PurchaseRequest, request_id)
    if not request:
        raise HTTPException(404, "Solicitação não encontrada.")
    if request.status != "Em análise":
        raise HTTPException(409, "Esta solicitação já foi analisada.")
    request.status = payload.status
    request.reviewed_by_id = admin.id
    db.commit()
    return request


@router.get("/history")
def history(db: Session = Depends(get_db), user: User = Depends(authenticated)):
    query = select(WorkOrder).join(MaintenanceCall).where(WorkOrder.status == "Concluída").order_by(WorkOrder.finished_at.desc())
    if user.role == "professor":
        query = query.where(MaintenanceCall.requester_id == user.id)
    return db.scalars(query).all()


@router.get("/indicators")
def indicators(db: Session = Depends(get_db), _admin: User = Depends(admin_only)):
    call_total = db.scalar(select(func.count(MaintenanceCall.id))) or 0
    open_calls = db.scalar(select(func.count(MaintenanceCall.id)).where(MaintenanceCall.status.notin_(["Concluído", "Cancelado"]))) or 0
    equipment_total = db.scalar(select(func.count(Equipment.id))) or 0
    unavailable = db.scalar(select(func.count(Equipment.id)).where(Equipment.state == "Indisponível")) or 0
    orders = db.scalars(select(WorkOrder)).all()
    durations = [(order.finished_at - order.started_at).total_seconds() / 3600 for order in orders if order.finished_at and order.started_at]
    mttr = round(sum(durations) / len(durations), 1) if durations else 0
    completed = sum(order.status == "Concluída" for order in orders)
    completion_rate = round(completed / len(orders) * 100, 1) if orders else 0
    return {
        "calls_total": call_total,
        "backlog": open_calls,
        "equipment_total": equipment_total,
        "unavailable_equipment": unavailable,
        "mttr_hours": mttr,
        "completion_rate": completion_rate,
    }
