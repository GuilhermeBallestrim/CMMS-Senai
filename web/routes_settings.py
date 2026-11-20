"""Settings and administration routes (web interface)."""
from __future__ import annotations

import re
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from backend.database import db
from backend.security import hash_password
from backend.services import log_audit
from web.common import (
    E, EMT, S, SC, U, US,
    render_template,
    require_page,
    status_class,
    validate_csrf,
)

router = APIRouter()


@router.get("/configuracoes")
async def configuracoes(request: Request, user_search: str | None = None, sector_search: str | None = None):
    users = db.client.table(U).select("*").order("name").execute().data
    if user_search:
        term = user_search.strip().lower()
        users = [u for u in users if term in u["name"].lower() or term in u["email"].lower()]
    sectors = db.client.table(S).select("*").order("name").execute().data
    if sector_search:
        term = sector_search.strip().lower()
        sectors = [s for s in sectors if term in s["name"].lower()]
    preferences = db.client.table(US).select("*").eq("id", 1).execute()
    preferences = preferences.data[0] if preferences.data else {}
    equip = db.client.table(E).select("id,sector_id").execute().data
    counts = {}
    for e in equip:
        counts[e["sector_id"]] = counts.get(e["sector_id"], 0) + 1
    return require_page(
        request,
        "configuracoes/lista.html",
        role="administrator",
        context={
            "users": users,
            "sectors": sectors,
            "equipment_counts": counts,
            "preferences": preferences,
            "user_search": user_search or "",
            "sector_search": sector_search or "",
        },
    )


@router.post("/configuracoes/preferencias")
async def save_preferences(
    request: Request,
    unit_name: str = Form(...),
    timezone_name: str = Form(...),
    notify_admin_new_call: bool = Form(False),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem salvar preferências.")
    valid_timezones = {"America/Sao_Paulo", "America/Manaus", "America/Belem", "America/Fortaleza", "America/Recife", "America/Rio_Branco", "UTC"}
    if not 2 <= len(unit_name.strip()) <= 160 or timezone_name not in valid_timezones:
        return RedirectResponse("/configuracoes?notice=Nome%20da%20unidade%20ou%20fuso%20hor%C3%A1rio%20inv%C3%A1lido.", status_code=303)
    resp = db.client.table(US).select("*").eq("id", 1).execute()
    if resp.data:
        db.client.table(US).update({"unit_name": unit_name.strip(), "timezone_name": timezone_name, "notify_admin_new_call": notify_admin_new_call}).eq("id", 1).execute()
    else:
        db.client.table(US).insert({"id": 1, "unit_name": unit_name.strip(), "timezone_name": timezone_name, "notify_admin_new_call": notify_admin_new_call}).execute()
    log_audit(user["id"], "updated", "unit_settings", 1, "Atualizou as preferências da unidade pela web.")
    return RedirectResponse("/configuracoes?notice=Prefer%C3%AAncias%20salvas.", status_code=303)


@router.post("/configuracoes/usuarios")
async def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem cadastrar usuários.")
    email = email.strip().lower()
    if (role not in {"professor", "tecnico", "administrator"} or len(password) < 12 or
            len(name.strip()) < 2 or len(name.strip()) > 120 or
            not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
        return RedirectResponse("/configuracoes?notice=Selecione%20um%20dos%20perfis%20v%C3%A1lidos%20e%20use%20senha%20com%20ao%20menos%2012%20caracteres.", status_code=303)
    resp = db.client.table(U).select("id").eq("email", email).execute()
    if resp.data:
        return RedirectResponse("/configuracoes?notice=J%C3%A1%20existe%20uma%20conta%20com%20esse%20e-mail.", status_code=303)
    db.client.table(U).insert({"name": name.strip(), "email": email, "password_hash": hash_password(password), "role": role}).execute()
    log_audit(user["id"], "created", "user", None, f"Cadastrou o usuário {email} pela web.")
    return RedirectResponse("/configuracoes?notice=Usu%C3%A1rio%20cadastrado.", status_code=303)


@router.post("/configuracoes/setores")
async def create_sector(request: Request, name: str = Form(...), csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem cadastrar setores.")
    if not 2 <= len(name.strip()) <= 100:
        return RedirectResponse("/configuracoes?notice=Informe%20um%20nome%20de%20setor%20v%C3%A1lido.", status_code=303)
    existing = db.client.table(S).select("id").eq("name", name.strip()).execute()
    if existing.data:
        return RedirectResponse("/configuracoes?notice=Esse%20setor%20j%C3%A1%20existe.", status_code=303)
    db.client.table(S).insert({"name": name.strip()}).execute()
    log_audit(user["id"], "created", "sector", None, f"Cadastrou o setor {name.strip()} pela web.")
    return RedirectResponse("/configuracoes?notice=Setor%20cadastrado.", status_code=303)


@router.post("/configuracoes/setores/{sector_id}/excluir")
async def delete_sector(request: Request, sector_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem excluir setores.")
    sec_resp = db.client.table(S).select("*").eq("id", sector_id).execute()
    sector = sec_resp.data[0] if sec_resp.data else None
    if not sector:
        raise HTTPException(404, "Setor não encontrado.")
    equip = db.client.table(E).select("id").eq("sector_id", sector_id).execute()
    if equip.data:
        return RedirectResponse("/configuracoes?notice=N%C3%A3o%20é%20poss%C3%ADvel%20excluir%20um%20setor%20com%20equipamentos.", status_code=303)
    db.client.table(S).delete().eq("id", sector_id).execute()
    log_audit(user["id"], "deleted", "sector", sector_id, f"Excluiu o setor {sector['name']}.")
    return RedirectResponse("/configuracoes?notice=Setor%20exclu%C3%ADdo.", status_code=303)


@router.get("/configuracoes/tipos-manutencao")
async def maintenance_types(request: Request):
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        return RedirectResponse("/dashboard?notice=Acesso%20restrito.", status_code=303)

    equipments = db.client.table(E).select("id, name, asset_tag").order("name").execute().data
    types = db.client.table(EMT).select("*").order("name").execute().data
    equip_map = {e["id"]: e for e in equipments}
    for t in types:
        e = equip_map.get(t["equipment_id"])
        t["_equipment_name"] = e["name"] if e else "?"
        t["_equipment_asset_tag"] = e["asset_tag"] if e else "?"

    return require_page(
        request,
        "configuracoes/tipos_manutencao.html",
        role="administrator",
        context={
            "equipments": equipments,
            "maintenance_types": types,
        },
    )


@router.post("/configuracoes/tipos-manutencao")
async def create_maintenance_type(
    request: Request, equipment_id: int = Form(...), name: str = Form(...), csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem cadastrar tipos de manutenção.")
    if not 2 <= len(name.strip()) <= 120:
        return RedirectResponse("/configuracoes/tipos-manutencao?notice=Nome%20do%20tipo%20inv%C3%A1lido.", status_code=303)
    if not db.client.table(E).select("id").eq("id", equipment_id).execute().data:
        return RedirectResponse("/configuracoes/tipos-manutencao?notice=Equipamento%20não%20encontrado.", status_code=303)
    existing = db.client.table(EMT).select("id").eq("equipment_id", equipment_id).eq("name", name.strip()).execute()
    if existing.data:
        return RedirectResponse("/configuracoes/tipos-manutencao?notice=Esse%20tipo%20j%C3%A1%20existe%20para%20este%20equipamento.", status_code=303)
    db.client.table(EMT).insert({"equipment_id": equipment_id, "name": name.strip(), "is_active": True}).execute()
    log_audit(user["id"], "created", "equipment_maintenance_type", None,
              f"Cadastrou tipo de manutenção '{name.strip()}' para equipamento {equipment_id}.")
    return RedirectResponse("/configuracoes/tipos-manutencao?notice=Tipo%20de%20manuten%C3%A7%C3%A3o%20cadastrado.", status_code=303)


@router.post("/configuracoes/tipos-manutencao/{type_id}/atualizar")
async def update_maintenance_type(
    request: Request, type_id: int, name: str = Form(""), is_active: bool = Form(True), csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem atualizar tipos de manutenção.")
    resp = db.client.table(EMT).select("*").eq("id", type_id).execute()
    if not resp.data:
        raise HTTPException(404, "Tipo de manutenção não encontrado.")
    update = {}
    if name and len(name.strip()) >= 2:
        update["name"] = name.strip()
    update["is_active"] = is_active
    if update:
        db.client.table(EMT).update(update).eq("id", type_id).execute()
    log_audit(user["id"], "updated", "equipment_maintenance_type", type_id, "Atualizou tipo de manutenção de equipamento.")
    return RedirectResponse("/configuracoes/tipos-manutencao?notice=Tipo%20de%20manuten%C3%A7%C3%A3o%20atualizado.", status_code=303)


@router.post("/configuracoes/tipos-manutencao/{type_id}/excluir")
async def delete_maintenance_type(
    request: Request, type_id: int, csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = request.session.get("user")
    if not user or user["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem excluir tipos de manutenção.")
    resp = db.client.table(EMT).select("*").eq("id", type_id).execute()
    if not resp.data:
        raise HTTPException(404, "Tipo de manutenção não encontrado.")
    db.client.table(EMT).delete().eq("id", type_id).execute()
    log_audit(user["id"], "deleted", "equipment_maintenance_type", type_id, "Excluiu tipo de manutenção de equipamento.")
    return RedirectResponse("/configuracoes/tipos-manutencao?notice=Tipo%20de%20manuten%C3%A7%C3%A3o%20excluído.", status_code=303)


@router.post("/configuracoes/usuarios/{user_id}/atualizar")
async def update_user(
    request: Request, user_id: int, role: str = Form(...), new_password: str = Form(""), csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    admin = request.session.get("user")
    if not admin or admin["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem gerenciar usuários.")
    if role not in {"professor", "tecnico", "administrator"} or (new_password and len(new_password) < 12):
        return RedirectResponse("/configuracoes?notice=Perfil%20ou%20senha%20inválidos.", status_code=303)
    if user_id == admin["id"] and role != "administrator":
        return RedirectResponse("/configuracoes?notice=N%C3%A3o%20é%20poss%C3%ADvel%20remover%20o%20pr%C3%B3prio%20perfil%20de%20administrador.", status_code=303)
    resp = db.client.table(U).select("*").eq("id", user_id).execute()
    account = resp.data[0] if resp.data else None
    if not account:
        raise HTTPException(404, "Usuário não encontrado.")
    update = {"role": role}
    if new_password:
        update["password_hash"] = hash_password(new_password)
    db.client.table(U).update(update).eq("id", user_id).execute()
    log_audit(admin["id"], "updated", "user", user_id, f"Atualizou o perfil de {account['email']}." + (" Redefiniu a senha." if new_password else ""))
    return RedirectResponse("/configuracoes?notice=Usu%C3%A1rio%20atualizado.", status_code=303)


@router.post("/configuracoes/usuarios/{user_id}/ativar")
async def set_user_active(request: Request, user_id: int, active: bool = Form(...), csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    admin = request.session.get("user")
    if not admin or admin["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem gerenciar usuários.")
    resp = db.client.table(U).select("*").eq("id", user_id).execute()
    account = resp.data[0] if resp.data else None
    if not account:
        raise HTTPException(404, "Usuário não encontrado.")
    if user_id == admin["id"] and not active:
        raise HTTPException(400, "Não é possível desativar a própria conta.")
    db.client.table(U).update({"is_active": active}).eq("id", user_id).execute()
    log_audit(admin["id"], "activated" if active else "deactivated", "user", user_id, f"{'Ativou' if active else 'Desativou'} o usuário {account['email']}.")
    return RedirectResponse("/configuracoes?notice=Status%20do%20usu%C3%A1rio%20atualizado.", status_code=303)


@router.post("/configuracoes/usuarios/{user_id}/excluir")
async def delete_user(request: Request, user_id: int, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    admin = request.session.get("user")
    if not admin or admin["role"] != "administrator":
        raise HTTPException(403, "Apenas administradores podem excluir usuários.")
    if user_id == admin["id"]:
        raise HTTPException(400, "Não é possível excluir a própria conta.")
    resp = db.client.table(U).select("*").eq("id", user_id).execute()
    account = resp.data[0] if resp.data else None
    if not account:
        raise HTTPException(404, "Usuário não encontrado.")
    if account["role"] == "administrator":
        admins = db.client.table(U).select("id").eq("role", "administrator").eq("is_active", True).execute().data
        if len(admins) <= 1:
            raise HTTPException(400, "Não é possível excluir o único administrador ativo.")
    db.client.table(U).delete().eq("id", user_id).execute()
    log_audit(admin["id"], "deleted", "user", user_id, f"Excluiu o usuário {account['email']}.")
    return RedirectResponse("/configuracoes?notice=Usu%C3%A1rio%20excluído.", status_code=303)