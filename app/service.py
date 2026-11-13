"""Business rules for accounts, transfers, and account activity."""

import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal


class AccountNotFoundError(Exception):
    """Raised when an account identifier does not exist."""


class InsufficientFundsError(Exception):
    """Raised when an account cannot cover a requested transfer."""


class InvalidTransferError(Exception):
    """Raised when a transfer violates a business rule."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_cents(amount: Decimal) -> int:
    scaled = amount * 100
    if scaled != scaled.to_integral_value():
        raise ValueError("Money values may have at most two decimal places.")
    return int(scaled)


def _from_cents(amount_cents: int) -> Decimal:
    return (Decimal(amount_cents) / Decimal(100)).quantize(Decimal("0.01"))


def _account_response(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "owner_name": row["owner_name"],
        "balance": _from_cents(row["balance_cents"]),
        "created_at": row["created_at"],
    }


def create_account(
    connection: sqlite3.Connection,
    owner_name: str,
    opening_deposit: Decimal,
) -> dict[str, object]:
    """Create an account and optionally record its simulated opening deposit."""

    opening_cents = _to_cents(opening_deposit)
    account_id = uuid.uuid4().hex
    created_at = _now()

    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            "INSERT INTO accounts(id, owner_name, balance_cents, created_at) VALUES (?, ?, ?, ?)",
            (account_id, owner_name, opening_cents, created_at),
        )
        if opening_cents > 0:
            connection.execute(
                """INSERT INTO transactions
                   (id, transfer_id, account_id, entry_type, amount_cents, description, created_at)
                   VALUES (?, NULL, ?, 'DEPOSIT', ?, 'Opening deposit', ?)""",
                (uuid.uuid4().hex, account_id, opening_cents, created_at),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    row = connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return _account_response(row)


def list_accounts(connection: sqlite3.Connection) -> list[dict[str, object]]:
    """Return all demo accounts in most-recently-created order."""

    rows = connection.execute("SELECT * FROM accounts ORDER BY created_at DESC, id").fetchall()
    return [_account_response(row) for row in rows]


def get_account(connection: sqlite3.Connection, account_id: str) -> dict[str, object]:
    """Return one account or raise AccountNotFoundError."""

    row = connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise AccountNotFoundError(account_id)
    return _account_response(row)


def transfer_funds(
    connection: sqlite3.Connection,
    from_account_id: str,
    to_account_id: str,
    amount: Decimal,
    reference: str | None = None,
) -> dict[str, object]:
    """Move simulated funds atomically and write matching debit and credit entries."""

    if from_account_id == to_account_id:
        raise InvalidTransferError("Source and destination accounts must be different.")

    amount_cents = _to_cents(amount)
    if amount_cents <= 0:
        raise InvalidTransferError("Transfer amount must be greater than zero.")

    connection.execute("BEGIN IMMEDIATE")
    try:
        sender = connection.execute(
            "SELECT * FROM accounts WHERE id = ?", (from_account_id,)
        ).fetchone()
        recipient = connection.execute(
            "SELECT * FROM accounts WHERE id = ?", (to_account_id,)
        ).fetchone()

        if sender is None:
            raise AccountNotFoundError(from_account_id)
        if recipient is None:
            raise AccountNotFoundError(to_account_id)
        if sender["balance_cents"] < 0:
            raise InsufficientFundsError(from_account_id)

        transfer_id = uuid.uuid4().hex
        created_at = _now()
        connection.execute(
            """INSERT INTO transfers
               (id, from_account_id, to_account_id, amount_cents, reference, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (transfer_id, from_account_id, to_account_id, amount_cents, reference, created_at),
        )
        connection.execute(
            "UPDATE accounts SET balance_cents = balance_cents - ? WHERE id = ?",
            (amount_cents, from_account_id),
        )
        connection.execute(
            "UPDATE accounts SET balance_cents = balance_cents + ? WHERE id = ?",
            (amount_cents, to_account_id),
        )

        connection.executemany(
            """INSERT INTO transactions
               (id, transfer_id, account_id, entry_type, amount_cents, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    uuid.uuid4().hex,
                    transfer_id,
                    from_account_id,
                    "DEBIT",
                    amount_cents,
                    f"Transfer to {recipient['owner_name']}",
                    created_at,
                ),
                (
                    uuid.uuid4().hex,
                    transfer_id,
                    to_account_id,
                    "CREDIT",
                    amount_cents,
                    f"Transfer from {sender['owner_name']}",
                    created_at,
                ),
            ],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return {
        "id": transfer_id,
        "from_account_id": from_account_id,
        "to_account_id": to_account_id,
        "amount": _from_cents(amount_cents),
        "reference": reference,
        "created_at": created_at,
    }


def get_transfer(connection: sqlite3.Connection, transfer_id: str) -> dict[str, object]:
    """Return a transfer receipt or raise AccountNotFoundError if absent."""

    row = connection.execute("SELECT * FROM transfers WHERE id = ?", (transfer_id,)).fetchone()
    if row is None:
        raise AccountNotFoundError(transfer_id)
    return {
        "id": row["id"],
        "from_account_id": row["from_account_id"],
        "to_account_id": row["to_account_id"],
        "amount": _from_cents(row["amount_cents"]),
        "reference": row["reference"],
        "created_at": row["created_at"],
    }


def list_transactions(
    connection: sqlite3.Connection,
    account_id: str,
    limit: int = 50,
) -> list[dict[str, object]]:
    """Return the newest ledger entries for an account."""

    if connection.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone() is None:
        raise AccountNotFoundError(account_id)

    rows = connection.execute(
        """SELECT * FROM transactions
           WHERE account_id = ?
           ORDER BY created_at DESC, id DESC
           LIMIT ?""",
        (account_id, limit),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "transfer_id": row["transfer_id"],
            "account_id": row["account_id"],
            "entry_type": row["entry_type"],
            "amount": _from_cents(row["amount_cents"]),
            "description": row["description"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]

