from backend.firebase_config import db
from datetime import datetime

# ... (código da classe Database que passei antes)

# Função get_db para compatibilidade com código antigo
def get_db():
    """Compatibilidade com rotas que usam Depends(get_db)"""
    return db

class Base:
    """Wrapper para operações Firestore"""
    
    # ===== USUÁRIOS =====
    @staticmethod
    def create_user(email: str, name: str, role: str, active: bool = True):
        """Criar novo usuário"""
        user_data = {
            "email": email,
            "name": name,
            "role": role,  # "professor" ou "administrator"
            "active": active,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        db.collection("users").document(email).set(user_data)
        return user_data

    @staticmethod
    def get_user(email: str):
        """Buscar usuário por email"""
        doc = db.collection("users").document(email).get()
        if doc.exists:
            return doc.to_dict()
        return None

    @staticmethod
    def get_all_users():
        """Listar todos usuários"""
        docs = db.collection("users").stream()
        users = []
        for doc in docs:
            user = doc.to_dict()
            user["id"] = doc.id
            users.append(user)
        return users

    @staticmethod
    def update_user(email: str, data: dict):
        """Atualizar usuário"""
        data["updated_at"] = datetime.now()
        db.collection("users").document(email).update(data)

    @staticmethod
    def delete_user(email: str):
        """Deletar usuário"""
        db.collection("users").document(email).delete()

    # ===== CHAMADOS =====
    @staticmethod
    def create_call(user_email: str, sector: str, equipment: str, 
                   description: str, priority: str = "média"):
        """Criar novo chamado"""
        call_data = {
            "user_email": user_email,
            "sector": sector,
            "equipment": equipment,
            "description": description,
            "priority": priority,
            "status": "aberto",  # aberto, em_progresso, resolvido
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        doc_ref = db.collection("calls").document()
        doc_ref.set(call_data)
        return {"id": doc_ref.id, **call_data}

    @staticmethod
    def get_call(call_id: str):
        """Buscar chamado por ID"""
        doc = db.collection("calls").document(call_id).get()
        if doc.exists:
            return {"id": doc.id, **doc.to_dict()}
        return None

    @staticmethod
    def get_user_calls(user_email: str):
        """Listar chamados do usuário"""
        docs = db.collection("calls")\
                 .where("user_email", "==", user_email)\
                 .order_by("created_at", direction=firestore.Query.DESCENDING)\
                 .stream()
        calls = []
        for doc in docs:
            call = doc.to_dict()
            call["id"] = doc.id
            calls.append(call)
        return calls

    @staticmethod
    def get_all_calls():
        """Listar todos chamados"""
        docs = db.collection("calls")\
                 .order_by("created_at", direction=firestore.Query.DESCENDING)\
                 .stream()
        calls = []
        for doc in docs:
            call = doc.to_dict()
            call["id"] = doc.id
            calls.append(call)
        return calls

    @staticmethod
    def update_call(call_id: str, data: dict):
        """Atualizar chamado"""
        data["updated_at"] = datetime.now()
        db.collection("calls").document(call_id).update(data)

    # ===== EQUIPAMENTOS =====
    @staticmethod
    def create_equipment(name: str, sector: str, model: str = "", serial: str = ""):
        """Criar equipamento"""
        equipment_data = {
            "name": name,
            "sector": sector,
            "model": model,
            "serial": serial,
            "status": "ativo",
            "created_at": datetime.now()
        }
        doc_ref = db.collection("equipment").document()
        doc_ref.set(equipment_data)
        return {"id": doc_ref.id, **equipment_data}

    @staticmethod
    def get_equipment(equipment_id: str):
        """Buscar equipamento"""
        doc = db.collection("equipment").document(equipment_id).get()
        if doc.exists:
            return {"id": doc.id, **doc.to_dict()}
        return None

    @staticmethod
    def get_sector_equipment(sector: str):
        """Listar equipamentos de um setor"""
        docs = db.collection("equipment")\
                 .where("sector", "==", sector)\
                 .stream()
        equipment = []
        for doc in docs:
            eq = doc.to_dict()
            eq["id"] = doc.id
            equipment.append(eq)
        return equipment

    # ===== SETORES =====
    @staticmethod
    def create_sector(name: str):
        """Criar setor"""
        doc_ref = db.collection("sectors").document(name)
        doc_ref.set({"name": name, "created_at": datetime.now()})
        return {"id": name, "name": name}

    @staticmethod
    def get_all_sectors():
        """Listar setores"""
        docs = db.collection("sectors").stream()
        sectors = []
        for doc in docs:
            sector = doc.to_dict()
            sector["id"] = doc.id
            sectors.append(sector)
        return sectors