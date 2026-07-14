import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from BACKEND.repositories.contracts import LegacyWalletRepository
from BACKEND.repositories.registry import get_wallet_repository

MONEY_PLACES = Decimal("0.01")
COMMISSION_RATE = Decimal("0.15")


def money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_wallet(
    driver_id: str,
    repository: LegacyWalletRepository | None = None,
) -> dict[str, Any]:
    wallet_repository = repository or get_wallet_repository()
    existing_wallet = wallet_repository.get(driver_id)

    if existing_wallet is not None:
        return existing_wallet

    wallet = {
        "driver_id": driver_id,
        "currency": "ETB",
        "digital_balance": money(0),
        "cash_commission_due": money(0),
        "available_to_cashout": money(0),
        "pending_cashout": money(0),
        "today_earnings": money(0),
        "week_earnings": money(0),
        "total_earnings": money(0),
        "cash_collected": money(0),
        "online_payments": money(0),
        "tips": money(0),
        "bonuses": money(0),
        "commission_paid": money(0),
        "transactions": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

    refresh_wallet(wallet)
    return wallet_repository.save(wallet)


def refresh_wallet(wallet: dict[str, Any]) -> None:
    digital_balance = money(wallet["digital_balance"])
    commission_due = money(wallet["cash_commission_due"])

    if digital_balance >= commission_due:
        wallet["available_to_cashout"] = money(digital_balance - commission_due)
        wallet["cash_commission_due"] = money(0)
    else:
        wallet["available_to_cashout"] = money(0)
        wallet["cash_commission_due"] = money(commission_due - digital_balance)

    # Keep these names so older code does not break.
    wallet["available_balance"] = wallet["available_to_cashout"]
    wallet["pending_balance"] = wallet["pending_cashout"]

    wallet["updated_at"] = now_iso()


def get_wallet(
    driver_id: str,
    repository: LegacyWalletRepository | None = None,
) -> dict[str, Any]:
    wallet_repository = repository or get_wallet_repository()
    wallet = create_wallet(driver_id, wallet_repository)
    refresh_wallet(wallet)
    return wallet_repository.save(wallet)


def _append_transaction(
    wallet: dict[str, Any],
    transaction_type: str,
    amount: Decimal | float | int | str,
    description: str,
    status: str,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    transaction = {
        "transaction_id": str(uuid.uuid4())[:12],
        "driver_id": wallet["driver_id"],
        "type": transaction_type,
        "amount": money(amount),
        "currency": wallet["currency"],
        "description": description,
        "status": status,
        "metadata": metadata or {},
        "created_at": now_iso(),
    }
    wallet["transactions"].insert(0, transaction)
    wallet["updated_at"] = now_iso()
    return transaction


def add_transaction(
    driver_id: str,
    transaction_type: str,
    amount: Decimal | float | int | str,
    description: str,
    status: str = "COMPLETED",
    metadata: dict[str, Any] | None = None,
    repository: LegacyWalletRepository | None = None,
) -> dict[str, Any]:
    wallet_repository = repository or get_wallet_repository()
    wallet = create_wallet(driver_id, wallet_repository)
    transaction = _append_transaction(
        wallet, transaction_type, amount, description, status, metadata
    )
    wallet_repository.save(wallet)
    return transaction


def add_trip_earning(
    driver_id: str,
    ride_id: str,
    gross_fare: Decimal | float | int | str,
    payment_method: str,
    commission_rate: Decimal | float | int | str = (COMMISSION_RATE),
    tip: Decimal | float | int | str = 0,
    bonus: Decimal | float | int | str = 0,
    repository: LegacyWalletRepository | None = None,
) -> dict[str, Any]:
    wallet_repository = repository or get_wallet_repository()
    wallet = create_wallet(driver_id, wallet_repository)

    gross = money(gross_fare)
    tip_amount = money(tip)
    bonus_amount = money(bonus)
    rate = Decimal(str(commission_rate))

    if gross <= 0:
        raise ValueError("Gross fare must be greater than zero.")

    if rate < 0 or rate > 1:
        raise ValueError("Commission rate must be between 0 and 1.")

    commission = money(gross * rate)

    driver_net = money(gross - commission + tip_amount + bonus_amount)

    payment = payment_method.strip().upper()

    if payment == "CASH":
        # Driver already received the cash fare and cash tip.
        wallet["cash_collected"] += money(gross + tip_amount)

        # Commission is owed to AYO.
        wallet["cash_commission_due"] += commission

        # AYO bonus is digital money.
        wallet["digital_balance"] += bonus_amount

    elif payment in {
        "CARD",
        "MOBILE_MONEY",
        "AYO_WALLET",
    }:
        # AYO received the payment, so the driver's net
        # becomes available in the digital wallet.
        wallet["online_payments"] += gross
        wallet["digital_balance"] += driver_net

    else:
        raise ValueError(
            "Payment method must be CASH, CARD, MOBILE_MONEY, or AYO_WALLET."
        )

    wallet["today_earnings"] += driver_net
    wallet["week_earnings"] += driver_net
    wallet["total_earnings"] += driver_net

    wallet["tips"] += tip_amount
    wallet["bonuses"] += bonus_amount
    wallet["commission_paid"] += commission

    refresh_wallet(wallet)

    transaction = _append_transaction(
        wallet=wallet,
        transaction_type="TRIP_EARNING",
        amount=driver_net,
        description=f"Earnings from ride {ride_id}.",
        status="COMPLETED",
        metadata={
            "ride_id": ride_id,
            "gross_fare": gross,
            "commission": commission,
            "commission_rate": str(rate),
            "tip": tip_amount,
            "bonus": bonus_amount,
            "payment_method": payment,
            "driver_net": driver_net,
        },
    )
    wallet = wallet_repository.save(wallet)

    return {
        "wallet": wallet,
        "transaction": transaction,
        "breakdown": {
            "gross_fare": gross,
            "commission": commission,
            "tip": tip_amount,
            "bonus": bonus_amount,
            "driver_net": driver_net,
            "payment_method": payment,
        },
    }


def request_withdrawal(
    driver_id: str,
    amount: Decimal | float | int | str,
    repository: LegacyWalletRepository | None = None,
) -> dict[str, Any]:
    wallet_repository = repository or get_wallet_repository()
    wallet = get_wallet(driver_id, wallet_repository)
    withdrawal_amount = money(amount)

    if withdrawal_amount <= 0:
        raise ValueError("Cash-out amount must be greater than zero.")

    if withdrawal_amount > wallet["available_to_cashout"]:
        raise ValueError("Insufficient amount available to cash out.")

    wallet["digital_balance"] -= withdrawal_amount
    wallet["pending_cashout"] += withdrawal_amount

    refresh_wallet(wallet)

    transaction = _append_transaction(
        wallet=wallet,
        transaction_type="CASHOUT_REQUEST",
        amount=-withdrawal_amount,
        description="Driver requested quick cash-out.",
        status="PENDING",
        metadata=None,
    )
    wallet = wallet_repository.save(wallet)

    return {
        "success": True,
        "message": "Quick cash-out request created.",
        "amount": withdrawal_amount,
        "wallet": wallet,
        "transaction": transaction,
    }


def complete_withdrawal(
    driver_id: str,
    amount: Decimal | float | int | str,
    payout_reference: str | None = None,
    repository: LegacyWalletRepository | None = None,
) -> dict[str, Any]:
    wallet_repository = repository or get_wallet_repository()
    wallet = get_wallet(driver_id, wallet_repository)
    withdrawal_amount = money(amount)

    if withdrawal_amount <= 0:
        raise ValueError("Cash-out amount must be greater than zero.")

    if withdrawal_amount > wallet["pending_cashout"]:
        raise ValueError("Insufficient pending cash-out balance.")

    wallet["pending_cashout"] -= withdrawal_amount

    refresh_wallet(wallet)

    transaction = _append_transaction(
        wallet=wallet,
        transaction_type="CASHOUT_COMPLETED",
        amount=-withdrawal_amount,
        description="Quick cash-out paid to driver.",
        status="COMPLETED",
        metadata={
            "payout_reference": payout_reference,
        },
    )
    wallet = wallet_repository.save(wallet)

    return {
        "success": True,
        "message": "Quick cash-out completed.",
        "amount": withdrawal_amount,
        "wallet": wallet,
        "transaction": transaction,
    }
