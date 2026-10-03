import os
import httpx
from fastapi import Header, HTTPException

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()

async def current_user_id(authorization: str = Header(default="")):
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token ausente.")

    token = authorization.split(" ", 1)[1].strip()
    headers = {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": f"Bearer {token}",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers=headers,
        )

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    user_id = response.json().get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuário inválido.")
    return user_id
