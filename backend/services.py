"""Serviços de notificação, auditoria e regras de negócio no Supabase."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from backend.database import db
from backend.models import (
    TABLE_AUDIT_LOGS, TABLE_EQUIPMENT, TABLE_MAINTENANCE_CALLS, TABLE_NOTIFICATIONS,
    TABLE_USERS, TABLE_WORK_ORDERS,
)


def make_number(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc):%Y}-{uuid4().hex[:6].upper()}"


def notify_user(user_id: int, title: str, message: str, href: str, kind: str = "info") -> None:
    try:
        db.client.table(TABLE_NOTIFICATIONS).insert({
            "user_id": user_id,
            "title": title,
            "message": message,
            "href": href,
            "kind": kind,
        }).execute()
    except Exception:
        pass


def notify_administrators(title: str, message: str, href: str, kind: str = "info") -> None:
    try:
        admins = db.client.table(TABLE_USERS).select("id").eq("role", "administrator").eq("is_active", True).execute()
        for admin in admins.data:
            notify_user(admin["id"], title, message, href, kind)
    except Exception:
        pass


def log_audit(actor_id: int | None, action: str, entity_type: str, entity_id: int | None, details: str) -> None:
    """Registra uma entrada na trilha de auditoria (RF-13)."""
    try:
        db.client.table(TABLE_AUDIT_LOGS).insert({
            "actor_id": actor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": (details or "")[:500],
        }).execute()
    except Exception:
        # A auditoria não deve derrubar a operação principal (§7.3).
        pass


def approve_call(call_id: int, admin_id: int) -> dict:
    """Aprova um chamado e gera a ordem de serviço (compartilhado web/API)."""
    resp = db.client.table(TABLE_MAINTENANCE_CALLS).select("*").eq("id", call_id).execute()
    if not resp.data:
        raise HTTPException(404, "Chamado não encontrado.")
    call = resp.data[0]
    if call.get("status") == "Cancelado":
        raise HTTPException(409, "Chamados cancelados não podem gerar ordem de serviço.")
    number = make_number("OS")
    try:
        rpc = db.client.rpc("approve_call_atomic", {"p_call_id": call_id, "p_admin_id": admin_id, "p_number": number}).execute()
        order_data = rpc.data if isinstance(rpc.data, dict) else (rpc.data[0] if rpc.data else None)
        if isinstance(order_data, str):
            order_data = json.loads(order_data)
        order_id = order_data["id"]
        order_number = order_data["number"]
        order_status = order_data["status"]
    except Exception:
        wo = db.client.table(TABLE_WORK_ORDERS).select("*").eq("call_id", call_id).execute()
        if wo.data:
            w = wo.data[0]
            order_id, order_number, order_status = w["id"], w["number"], w["status"]
        else:
            created = db.client.table(TABLE_WORK_ORDERS).insert({
                "number": number, "call_id": call_id, "responsible_id": admin_id, "status": "Aguardando início",
            }).execute()
            order = created.data[0]
            order_id, order_number, order_status = order["id"], order["number"], order["status"]
            db.client.table(TABLE_MAINTENANCE_CALLS).update(
                {"status": "Em análise", "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", call_id).execute()
    notify_user(call["requester_id"], "Chamado aprovado", f"{call['number']} gerou a ordem {order_number}.", f"/chamados/detalhe?id={call_id}")
    log_audit(admin_id, "approved", "maintenance_call", call_id, f"Aprovou {call['number']} e gerou {order_number}.")
    return {"id": order_id, "number": order_number, "status": order_status}


def conclude_work_order(order_id: int, solution: str, actor_id: int) -> dict:
    """Conclui uma ordem de serviço (compartilhado web/API).

    Transições: somente se a OS não estiver já concluída. Ao concluir, define
    finished_at, atualiza o chamado para 'Concluído' e o equipamento para
    'Disponível'. Usa RPC quando disponível, com fallback sequencial.
    """
    resp = db.client.table(TABLE_WORK_ORDERS).select("*").eq("id", order_id).execute()
    if not resp.data:
        raise HTTPException(404, "Ordem de serviço não encontrada.")
    order = resp.data[0]
    if order.get("status") == "Concluída":
        raise HTTPException(409, "Ordem concluída não pode ser alterada.")

    solution = (solution or "").strip() or (order.get("solution") or "").strip()
    if not solution:
        raise HTTPException(422, "Não é possível concluir a OS sem registrar a solução aplicada.")

    # Busca chamado e equipamento associados.
    call_resp = db.client.table(TABLE_MAINTENANCE_CALLS).select("*").eq("id", order.get("call_id")).execute()
    call = call_resp.data[0] if call_resp.data else None
    equip = None
    if call and call.get("equipment_id"):
        eq_resp = db.client.table(TABLE_EQUIPMENT).select("*").eq("id", call["equipment_id"]).execute()
        equip = eq_resp.data[0] if eq_resp.data else None

    rpc_ok = False
    try:
        db.client.rpc("conclude_order_atomic", {"p_order_id": order_id, "p_solution": solution}).execute()
        rpc_ok = True
    except Exception:
        rpc_ok = False

    if rpc_ok:
        update = {"status": "Concluída"}
    else:
        update = {
            "status": "Concluída",
            "solution": solution,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        if call:
            db.client.table(TABLE_MAINTENANCE_CALLS).update(
                {"status": "Concluído", "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", call["id"]).execute()
            if equip:
                db.client.table(TABLE_EQUIPMENT).update({"state": "Disponível"}).eq("id", equip["id"]).execute()

    db.client.table(TABLE_WORK_ORDERS).update(update).eq("id", order_id).execute()

    if call:
        notify_user(
            call["requester_id"],
            "Ordem de serviço atualizada",
            f"{order['number']}: Concluída.",
            f"/chamados/detalhe?id={call['id']}",
        )
    log_audit(actor_id, "updated", "work_order", order_id, f"Concluiu {order['number']} pela web/API.")
    return db.client.table(TABLE_WORK_ORDERS).select("*").eq("id", order_id).execute().data[0]


def cancel_call(call_id: int, actor_id: int, actor_role: str) -> dict:
    """Cancela um chamado (compartilhado web/API).

    Professor só pode cancelar o próprio chamado quando está 'Aberto'.
    Administrador pode cancelar qualquer chamado 'Aberto'.
    """
    resp = db.client.table(TABLE_MAINTENANCE_CALLS).select("*").eq("id", call_id).execute()
    if not resp.data:
        raise HTTPException(404, "Chamado não encontrado.")
    call = resp.data[0]
    if actor_role == "professor" and call["requester_id"] != actor_id:
        raise HTTPException(404, "Chamado não encontrado.")
    if call["status"] != "Aberto":
        raise HTTPException(409, "Só é possível cancelar um chamado aberto.")

    db.client.table(TABLE_MAINTENANCE_CALLS).update(
        {"status": "Cancelado", "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", call_id).execute()

    if actor_role == "administrator":
        notify_user(
            call["requester_id"],
            "Chamado cancelado",
            f"{call['number']} foi cancelado pelo administrador.",
            f"/chamados/detalhe?id={call_id}",
            "warning",
        )
    else:
        notify_administrators(
            "Chamado cancelado",
            f"{call['number']} foi cancelado pelo solicitante.",
            f"/chamados/detalhe?id={call_id}",
            "warning",
        )
    log_audit(actor_id, "cancelled", "maintenance_call", call_id, f"Cancelou o chamado {call['number']}.")
    return call


def update_work_order_status(order_id: int, status: str, actor_id: int, actor_role: str) -> dict:
    """Atualiza o status de uma ordem de serviço (compartilhado web/API).

    Não conclui a OS. Trata transições para:
      - 'Em execução': define started_at se ainda não houver.
      - 'Aguardando peça': atualiza chamado para 'Aguardando peça' e
        equipamento para 'Em manutenção'.
      - Outros status válidos: atualiza chamado para 'Em manutenção' e
        equipamento para 'Em manutenção'.

    Técnico só pode alterar a OS de que é responsável.
    Administrador pode alterar qualquer OS.
    """
    resp = db.client.table(TABLE_WORK_ORDERS).select("*").eq("id", order_id).execute()
    if not resp.data:
        raise HTTPException(404, "Ordem de serviço não encontrada.")
    order = resp.data[0]
    if order.get("status") == "Concluída":
        raise HTTPException(409, "Ordem concluída não pode ser alterada.")

    if actor_role == "tecnico" and order.get("responsible_id") != actor_id:
        raise HTTPException(403, "Você não é o responsável por esta ordem de serviço.")

    # Busca chamado e equipamento associados.
    call_resp = db.client.table(TABLE_MAINTENANCE_CALLS).select("*").eq("id", order.get("call_id")).execute()
    call = call_resp.data[0] if call_resp.data else None
    equip = None
    if call and call.get("equipment_id"):
        eq_resp = db.client.table(TABLE_EQUIPMENT).select("*").eq("id", call["equipment_id"]).execute()
        equip = eq_resp.data[0] if eq_resp.data else None

    update = {"status": status}
    if status == "Em execução" and not order.get("started_at"):
        update["started_at"] = datetime.now(timezone.utc).isoformat()

    if status == "Aguardando peça":
        if call:
            db.client.table(TABLE_MAINTENANCE_CALLS).update(
                {"status": "Aguardando peça", "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", call["id"]).execute()
            if equip:
                db.client.table(TABLE_EQUIPMENT).update({"state": "Em manutenção"}).eq("id", equip["id"]).execute()
    else:
        if call:
            db.client.table(TABLE_MAINTENANCE_CALLS).update(
                {"status": "Em manutenção", "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", call["id"]).execute()
            if equip:
                db.client.table(TABLE_EQUIPMENT).update({"state": "Em manutenção"}).eq("id", equip["id"]).execute()

    db.client.table(TABLE_WORK_ORDERS).update(update).eq("id", order_id).execute()

    if call:
        notify_user(
            call["requester_id"],
            "Ordem de serviço atualizada",
            f"{order['number']}: {status}.",
            f"/chamados/detalhe?id={call['id']}",
        )
    log_audit(actor_id, "updated", "work_order", order_id, f"Atualizou {order['number']} para {status}.")
    return db.client.table(TABLE_WORK_ORDERS).select("*").eq("id", order_id).execute().data[0]


def update_work_order_diagnostic(order_id: int, payload: dict, actor_id: int, actor_role: str) -> dict:
    """Atualiza campos de diagnóstico de uma ordem de serviço (compartilhado web/API).

    Campos aceitos: defect, cause, solution, parts, notes.
    Técnico só pode editar a OS de que é responsável.
    """
    resp = db.client.table(TABLE_WORK_ORDERS).select("*").eq("id", order_id).execute()
    if not resp.data:
        raise HTTPException(404, "Ordem de serviço não encontrada.")
    order = resp.data[0]
    if order.get("status") == "Concluída":
        raise HTTPException(409, "Ordem concluída não pode ser alterada.")
    if actor_role == "tecnico" and order.get("responsible_id") != actor_id:
        raise HTTPException(403, "Você não é o responsável por esta ordem de serviço.")

    allowed = {"defect", "cause", "solution", "parts", "notes"}
    update = {k: (v.strip() if isinstance(v, str) else v) for k, v in payload.items() if k in allowed and v is not None}
    if not update:
        raise HTTPException(422, "Nenhum campo de diagnóstico informado.")

    db.client.table(TABLE_WORK_ORDERS).update(update).eq("id", order_id).execute()
    log_audit(actor_id, "updated", "work_order", order_id, f"Atualizou diagnóstico de {order['number']}.")
    return db.client.table(TABLE_WORK_ORDERS).select("*").eq("id", order_id).execute().data[0]