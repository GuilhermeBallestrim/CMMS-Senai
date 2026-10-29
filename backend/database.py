from __future__ import annotations

from supabase import Client, create_client

from backend.config import settings


class SupabaseDatabase:
    def __init__(self) -> None:
        if not settings.supabase_url or not settings.supabase_key:
            raise RuntimeError(
                "Configure CMMS_SUPABASE_URL e CMMS_SUPABASE_KEY no arquivo .env"
            )
        self._client: Client = create_client(
            settings.supabase_url, settings.supabase_key
        )

    @property
    def client(self) -> Client:
        return self._client

    # Helpers para acesso direto às tabelas
    def table(self, name: str):
        return self._client.table(name)

    # Compatibilidade removida: não use mais get_db como gerador de sessão


db = SupabaseDatabase()
