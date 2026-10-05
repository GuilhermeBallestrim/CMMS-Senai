from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


Role = Literal["professor", "administrator"]
Priority = Literal["Baixa", "Média", "Alta", "Crítica"]
CallStatus = Literal["Aberto", "Em análise", "Em manutenção", "Aguardando peça", "Concluído", "Cancelado"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: Role


class UserRead(ORMModel):
    id: int
    name: str
    email: str
    role: Role
    is_active: bool
    created_at: datetime


class SectorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class SectorRead(ORMModel):
    id: int
    name: str


class EquipmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    sector_id: int
    model: str | None = Field(default=None, max_length=120)
    asset_tag: str = Field(min_length=1, max_length=80)
    serial_number: str | None = Field(default=None, max_length=100)
    state: Literal["Disponível", "Em manutenção", "Indisponível"] = "Disponível"
    responsible_id: int | None = None


class EquipmentRead(ORMModel):
    id: int
    name: str
    sector_id: int
    model: str | None
    asset_tag: str
    serial_number: str | None
    state: str
    responsible_id: int | None
    created_at: datetime


class CallCreate(BaseModel):
    equipment_id: int
    description: str = Field(min_length=10, max_length=5000)
    priority: Priority


class CallUpdate(BaseModel):
    status: CallStatus


class CallRead(ORMModel):
    id: int
    number: str
    equipment_id: int
    requester_id: int
    description: str
    priority: Priority
    status: CallStatus
    created_at: datetime
    updated_at: datetime


class PurchaseCreate(BaseModel):
    item_type: Literal["Novas máquinas", "Ferramentas", "Peças e componentes"]
    item: str = Field(min_length=2, max_length=180)
    quantity: int = Field(ge=1, le=10000)
    justification: str = Field(min_length=10, max_length=5000)


class PurchaseRead(ORMModel):
    id: int
    number: str
    item_type: str
    item: str
    quantity: int
    justification: str
    requester_id: int
    status: str
    reviewed_by_id: int | None
    created_at: datetime


class PurchaseDecision(BaseModel):
    status: Literal["Aprovada", "Recusada"]


class WorkOrderUpdate(BaseModel):
    status: Literal["Em execução", "Aguardando peça", "Concluída"]
    started_at: datetime | None = None
    defect: str | None = Field(default=None, max_length=5000)
    cause: str | None = Field(default=None, max_length=5000)
    solution: str | None = Field(default=None, max_length=5000)
    parts: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class LoginForm(BaseModel):
    email: str
    password: str
    csrf_token: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()
