"""FastAPI entry point for the simulated banking demo."""

import os
from pathlib import Path
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Query, status

from app.database import get_database, initialize_database
from app.admin import router as admin_router
from app.models import (
    AccountCreate,
    AccountResponse,
    TransactionResponse,
    TransferCreate,
    TransferResponse,
)
from app.service import (
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidTransferError,
    create_account,
    get_account,
    get_transfer,
    list_accounts,
    list_transactions,
    transfer_funds,
)


def create_app(database_path: str | Path | None = None) -> FastAPI:
    """Build the API application and initialize its configured SQLite database."""

    resolved_database_path = database_path or os.getenv("BANKING_DATABASE_PATH", "banking_demo.db")
    initialize_database(resolved_database_path)

    application = FastAPI(
        title="PocketBank Demo API",
        description=(
            "A local-only simulated banking API for demonstrating automated pull-request reviews. "
            "It does not connect to real accounts or payment networks."
        ),
        version="1.0.0",
    )
    application.state.database_path = str(resolved_database_path)
    application.include_router(admin_router)

    @application.get("/", tags=["System"])
    def root() -> dict[str, str]:
        """Return basic service information and the interactive API documentation path."""

        return {
            "service": "PocketBank Demo API",
            "purpose": "Simulated banking operations for software-review demonstrations",
            "docs": "/docs",
        }

    @application.get("/health", tags=["System"])
    def health() -> dict[str, str]:
        """Report whether the API process is responding."""

        return {"status": "ok"}

    @application.post(
        "/accounts",
        response_model=AccountResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["Accounts"],
    )
    def create_new_account(
        payload: AccountCreate,
        connection: sqlite3.Connection = Depends(get_database),
    ) -> dict[str, object]:
        """Create a simulated account, optionally with an opening deposit."""

        return create_account(connection, payload.owner_name, payload.opening_deposit)

    @application.get("/accounts", response_model=list[AccountResponse], tags=["Accounts"])
    def get_accounts(
        connection: sqlite3.Connection = Depends(get_database),
    ) -> list[dict[str, object]]:
        """List all accounts in the local demonstration database."""

        return list_accounts(connection)

    @application.get("/accounts/{account_id}", response_model=AccountResponse, tags=["Accounts"])
    def get_one_account(
        account_id: str,
        connection: sqlite3.Connection = Depends(get_database),
    ) -> dict[str, object]:
        """Return the current balance and metadata for one account."""

        try:
            return get_account(connection, account_id)
        except AccountNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Account not found.") from exc

    @application.get(
        "/accounts/{account_id}/transactions",
        response_model=list[TransactionResponse],
        tags=["Transactions"],
    )
    def get_account_transactions(
        account_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        connection: sqlite3.Connection = Depends(get_database),
    ) -> list[dict[str, object]]:
        """Return up to 100 newest ledger entries for an account."""

        try:
            return list_transactions(connection, account_id, limit)
        except AccountNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Account not found.") from exc

    @application.post(
        "/transfers",
        response_model=TransferResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["Transfers"],
    )
    def create_transfer(
        payload: TransferCreate,
        connection: sqlite3.Connection = Depends(get_database),
    ) -> dict[str, object]:
        """Transfer simulated funds between two accounts in one database transaction."""

        try:
            return transfer_funds(
                connection,
                payload.from_account_id,
                payload.to_account_id,
                payload.amount,
                payload.reference,
            )
        except AccountNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Source or destination account not found.") from exc
        except InsufficientFundsError as exc:
            raise HTTPException(status_code=409, detail="Insufficient funds.") from exc
        except InvalidTransferError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.get(
        "/transfers/{transfer_id}",
        response_model=TransferResponse,
        tags=["Transfers"],
    )
    def get_transfer_receipt(
        transfer_id: str,
        connection: sqlite3.Connection = Depends(get_database),
    ) -> dict[str, object]:
        """Return the receipt for a completed simulated transfer."""

        try:
            return get_transfer(connection, transfer_id)
        except AccountNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Transfer not found.") from exc

    return application


app = create_app()
