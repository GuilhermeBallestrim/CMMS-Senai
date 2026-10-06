# Tabelas no Supabase. Os campos são definidos pelo schema SQL (supabase_schema.sql),
# não por modelos ORM. Aqui só ficam constantes e tipos auxiliares.

TABLE_USERS = "users"
TABLE_SECTORS = "sectors"
TABLE_EQUIPMENT = "equipment"
TABLE_MAINTENANCE_CALLS = "maintenance_calls"
TABLE_WORK_ORDERS = "work_orders"
TABLE_PURCHASE_REQUESTS = "purchase_requests"
TABLE_NOTIFICATIONS = "notifications"
TABLE_UNIT_SETTINGS = "unit_settings"

VALID_ROLES = ("professor", "administrator")
VALID_CALL_STATUSES = ("Aberto", "Em análise", "Em manutenção", "Aguardando peça", "Concluído", "Cancelado")
VALID_ORDER_STATUSES = ("Aguardando início", "Em execução", "Aguardando peça", "Concluída")
VALID_PURCHASE_STATUSES = ("Em análise", "Aprovada", "Recusada")
VALID_EQUIPMENT_STATES = ("Disponível", "Em manutenção", "Indisponível")
VALID_PRIORITIES = ("Baixa", "Média", "Alta", "Crítica")
VALID_ITEM_TYPES = ("Novas máquinas", "Ferramentas", "Peças e componentes")
