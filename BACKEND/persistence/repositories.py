import logging
from collections.abc import Mapping
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.domain.rides import Ride, RideStatus
from BACKEND.persistence.errors import OptimisticConcurrencyError
from BACKEND.persistence.logging import database_event
from BACKEND.persistence.tables import legacy_wallets, rides
from BACKEND.repositories.contracts import LegacyWalletRecord

_logger = logging.getLogger("ayo.persistence")
_DECIMAL_TAG = "__ayo_decimal__"


def _ride_values(ride: Ride) -> dict[str, Any]:
    return {
        "public_ride_id": ride.ride_id,
        "rider_name": ride.rider_name,
        "pickup": ride.pickup,
        "destination": ride.destination,
        "ride_type": ride.ride_type,
        "status": ride.status.value,
        "driver_id": ride.driver_id,
        "driver_name": ride.driver_name,
        "driver_distance_km": ride.driver_distance_km,
        "driver_queue": ride.driver_queue,
        "current_offer_index": ride.current_offer_index,
        "current_offer": ride.current_offer,
        "gross_fare": ride.gross_fare,
        "payment_method": ride.payment_method,
        "tip": ride.tip,
        "bonus": ride.bonus,
    }


def _row_to_ride(row: Mapping[str, Any]) -> Ride:
    return Ride(
        ride_id=row["public_ride_id"],
        rider_name=row["rider_name"],
        pickup=row["pickup"],
        destination=row["destination"],
        ride_type=row["ride_type"],
        status=RideStatus(row["status"]),
        driver_id=row["driver_id"],
        driver_name=row["driver_name"],
        driver_distance_km=row["driver_distance_km"],
        driver_queue=row["driver_queue"],
        current_offer_index=row["current_offer_index"],
        current_offer=row["current_offer"],
        gross_fare=row["gross_fare"],
        payment_method=row["payment_method"],
        tip=row["tip"],
        bonus=row["bonus"],
    )


def _encode_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {_DECIMAL_TAG: str(value)}
    if isinstance(value, dict):
        return {key: _encode_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode_json(item) for item in value]
    return value


def _decode_json(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {_DECIMAL_TAG}:
            return Decimal(value[_DECIMAL_TAG])
        return {key: _decode_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_json(item) for item in value]
    return value


class PostgresRideRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._versions: dict[str, int] = {}

    def save(self, ride: Ride) -> Ride:
        started = perf_counter()
        outcome = "success"
        try:
            expected_version = self._versions.get(ride.ride_id)
            if expected_version is None:
                expected_version = self._connection.execute(
                    select(rides.c.version).where(
                        rides.c.public_ride_id == ride.ride_id
                    )
                ).scalar_one_or_none()

            if expected_version is None:
                try:
                    version = self._connection.execute(
                        insert(rides)
                        .values(**_ride_values(ride))
                        .returning(rides.c.version)
                    ).scalar_one()
                except IntegrityError as error:
                    outcome = "conflict"
                    raise OptimisticConcurrencyError(
                        "Ride was concurrently created."
                    ) from error
            else:
                version = self._connection.execute(
                    update(rides)
                    .where(
                        rides.c.public_ride_id == ride.ride_id,
                        rides.c.version == expected_version,
                    )
                    .values(
                        **_ride_values(ride),
                        version=rides.c.version + 1,
                        updated_at=self._utc_now_expression(),
                    )
                    .returning(rides.c.version)
                ).scalar_one_or_none()
                if version is None:
                    outcome = "conflict"
                    raise OptimisticConcurrencyError(
                        "Ride changed during the transaction."
                    )
            self._versions[ride.ride_id] = version
            return ride
        except Exception:
            if outcome == "success":
                outcome = "error"
            raise
        finally:
            database_event(
                _logger,
                event="ride.save",
                outcome=outcome,
                duration_ms=(perf_counter() - started) * 1_000,
            )

    def get(self, ride_id: str) -> Ride | None:
        started = perf_counter()
        result = (
            self._connection.execute(
                select(rides).where(rides.c.public_ride_id == ride_id)
            )
            .mappings()
            .one_or_none()
        )
        database_event(
            _logger,
            event="ride.get",
            outcome="found" if result is not None else "not_found",
            duration_ms=(perf_counter() - started) * 1_000,
        )
        if result is None:
            return None
        self._versions[ride_id] = result["version"]
        return _row_to_ride(result)

    def update_status(self, ride_id: str, status: RideStatus) -> Ride | None:
        ride = self.get(ride_id)
        if ride is None:
            return None
        ride.status = status
        return self.save(ride)

    @staticmethod
    def _utc_now_expression():
        from sqlalchemy import func

        return func.now()


class PostgresLegacyWalletRepository:
    """Non-authoritative compatibility storage; this is not a ledger."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._versions: dict[str, int] = {}

    def get(self, driver_id: str) -> LegacyWalletRecord | None:
        started = perf_counter()
        result = (
            self._connection.execute(
                select(legacy_wallets.c.payload, legacy_wallets.c.version).where(
                    legacy_wallets.c.driver_id == driver_id
                )
            )
            .mappings()
            .one_or_none()
        )
        database_event(
            _logger,
            event="legacy_wallet.get",
            outcome="found" if result is not None else "not_found",
            duration_ms=(perf_counter() - started) * 1_000,
        )
        if result is None:
            return None
        self._versions[driver_id] = result["version"]
        return _decode_json(result["payload"])

    def save(self, wallet: Mapping[str, Any]) -> LegacyWalletRecord:
        started = perf_counter()
        outcome = "success"
        driver_id = str(wallet["driver_id"])
        payload = _encode_json(dict(wallet))
        try:
            expected_version = self._versions.get(driver_id)
            if expected_version is None:
                expected_version = self._connection.execute(
                    select(legacy_wallets.c.version).where(
                        legacy_wallets.c.driver_id == driver_id
                    )
                ).scalar_one_or_none()

            if expected_version is None:
                try:
                    version = self._connection.execute(
                        insert(legacy_wallets)
                        .values(driver_id=driver_id, payload=payload)
                        .returning(legacy_wallets.c.version)
                    ).scalar_one()
                except IntegrityError as error:
                    outcome = "conflict"
                    raise OptimisticConcurrencyError(
                        "Legacy wallet was concurrently created."
                    ) from error
            else:
                version = self._connection.execute(
                    update(legacy_wallets)
                    .where(
                        legacy_wallets.c.driver_id == driver_id,
                        legacy_wallets.c.version == expected_version,
                    )
                    .values(
                        payload=payload,
                        version=legacy_wallets.c.version + 1,
                        updated_at=PostgresRideRepository._utc_now_expression(),
                    )
                    .returning(legacy_wallets.c.version)
                ).scalar_one_or_none()
                if version is None:
                    outcome = "conflict"
                    raise OptimisticConcurrencyError(
                        "Legacy wallet changed during the transaction."
                    )
            self._versions[driver_id] = version
            return _decode_json(payload)
        except Exception:
            if outcome == "success":
                outcome = "error"
            raise
        finally:
            database_event(
                _logger,
                event="legacy_wallet.save",
                outcome=outcome,
                duration_ms=(perf_counter() - started) * 1_000,
            )
