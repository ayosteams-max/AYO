from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from BACKEND.repositories.contracts import LegacyWalletRepository
from BACKEND.repositories.registry import get_wallet_repository
from BACKEND.services.wallet_service import (
    get_wallet,
    request_withdrawal,
)

router = APIRouter(
    prefix="/wallet",
    tags=["Driver Wallet"],
)


class WithdrawalRequest(BaseModel):
    driver_id: str = Field(min_length=1, max_length=50)
    amount: float = Field(gt=0)


def money_number(value: Any) -> float:
    """
    Return money as a safe number with two-decimal accuracy.
    Negative cash-out values are never shown.
    """

    amount = Decimal(str(value or 0))

    if amount < 0:
        amount = Decimal("0.00")

    return float(amount.quantize(Decimal("0.01")))


def money_display(value: Any) -> str:
    """
    Return money exactly as the driver should see it.

    Example:
    0 becomes "0.00"
    792.5 becomes "792.50"
    """

    amount = Decimal(str(value or 0))

    if amount < 0:
        amount = Decimal("0.00")

    return f"{amount.quantize(Decimal('0.01')):,.2f}"


def clean_wallet_response(
    driver_id: str, repository: LegacyWalletRepository
) -> dict[str, Any]:
    wallet = get_wallet(driver_id, repository)

    available = wallet.get(
        "available_to_cashout",
        wallet.get("available_balance", 0),
    )

    pending = wallet.get(
        "pending_cashout",
        wallet.get("pending_balance", 0),
    )

    today = wallet.get("today_earnings", 0)

    week = wallet.get(
        "week_earnings",
        wallet.get("today_earnings", 0),
    )

    lifetime = wallet.get(
        "total_earnings",
        0,
    )

    commission_due = wallet.get(
        "cash_commission_due",
        0,
    )

    available_number = money_number(available)

    return {
        "driver_id": driver_id,
        "currency": wallet.get("currency", "ETB"),
        "balance": {
            "available_to_cashout": available_number,
            "available_display": money_display(available),
            "pending_cashout": money_number(pending),
            "pending_display": money_display(pending),
            "can_cash_out": available_number > 0,
        },
        "earnings": {
            "today": money_number(today),
            "today_display": money_display(today),
            "this_week": money_number(week),
            "this_week_display": money_display(week),
            "lifetime": money_number(lifetime),
            "lifetime_display": money_display(lifetime),
        },
        "cash": {
            "collected": money_number(wallet.get("cash_collected", 0)),
            "collected_display": money_display(wallet.get("cash_collected", 0)),
            "commission_due": money_number(commission_due),
            "commission_due_display": money_display(commission_due),
        },
        "transactions": wallet.get("transactions", []),
    }


@router.post("/withdraw")
def withdraw(
    request: WithdrawalRequest,
    repository: Annotated[LegacyWalletRepository, Depends(get_wallet_repository)],
):
    try:
        result = request_withdrawal(
            driver_id=request.driver_id,
            amount=request.amount,
            repository=repository,
        )

        return {
            "success": True,
            "message": result.get(
                "message",
                "Quick cash-out request created.",
            ),
            "amount": money_number(request.amount),
            "amount_display": money_display(request.amount),
            "wallet": clean_wallet_response(request.driver_id, repository),
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@router.get("/{driver_id}")
def driver_wallet(
    driver_id: str,
    repository: Annotated[LegacyWalletRepository, Depends(get_wallet_repository)],
):
    return clean_wallet_response(driver_id, repository)
