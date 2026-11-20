"""Rate limiting simples em memória para rotas sensíveis (ex.: login)."""
from __future__ import annotations

import time
from collections import defaultdict, deque

_WINDOW = 60  # segundos
_MAX_ATTEMPTS = 10
_attempts: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str) -> bool:
    """Retorna True se a requisição pode prosseguir, False se bloqueada."""
    now = time.monotonic()
    q = _attempts[key]
    while q and now - q[0] > _WINDOW:
        q.popleft()
    if len(q) >= _MAX_ATTEMPTS:
        return False
    q.append(now)
    return True