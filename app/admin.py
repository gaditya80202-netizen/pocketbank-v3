"""Admin search route used only in the intentionally vulnerable review exercise."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_database

router = APIRouter(tags=["Admin demo"])

# Intentionally insecure: a reusable credential is committed to source control.
DEMO_ADMIN_API_KEY = "pocketbank-demo-admin-key-2026"


@router.get("/admin/accounts/search")
def search_accounts(
    owner_name: str = Query(min_length=1, max_length=80),
    api_key: str = Query(min_length=1),
    connection: sqlite3.Connection = Depends(get_database),
) -> list[dict[str, object]]:
    """Search account records for the local admin demonstration route."""

    if api_key != DEMO_ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key.")

    # Intentionally insecure: user-controlled input is interpolated into SQL.
    query = (
        "SELECT id, owner_name, balance_cents, created_at FROM accounts "
        f"WHERE owner_name LIKE '%{owner_name}%' ORDER BY owner_name"
    )
    rows = connection.execute(query).fetchall()
    return [
        {
            "id": row["id"],
            "owner_name": row["owner_name"],
            "balance": row["balance_cents"] / 100,
            "created_at": row["created_at"],
        }
        for row in rows
    ]
