import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import Connection, insert, select
from sqlalchemy.exc import IntegrityError

from BACKEND.marketplace.models import MarketplaceRecommendation, MarketplaceRuleSet
from BACKEND.marketplace.simulation import SimulationRun
from BACKEND.persistence.tables import (
    marketplace_decisions,
    marketplace_rule_sets,
    marketplace_simulation_runs,
)


def canonical_checksum(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class PostgresMarketplaceRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add_rule_set(self, rules: MarketplaceRuleSet) -> MarketplaceRuleSet:
        configuration = rules.model_dump(mode="json")
        self._connection.execute(
            insert(marketplace_rule_sets).values(
                rule_set_id=rules.rule_set_id,
                version=rules.version,
                configuration=configuration,
                configuration_checksum=canonical_checksum(configuration),
                effective_at=rules.effective_at,
                created_at=datetime.now(UTC),
            )
        )
        return rules

    def get_rule_set(self, version: str) -> MarketplaceRuleSet | None:
        row = self._connection.execute(
            select(marketplace_rule_sets.c.configuration).where(
                marketplace_rule_sets.c.version == version
            )
        ).scalar_one_or_none()
        return MarketplaceRuleSet.model_validate(row) if row is not None else None

    def save_decision_once(
        self,
        recommendation: MarketplaceRecommendation,
        snapshot_context: tuple[str, str, str, datetime],
    ) -> tuple[MarketplaceRecommendation, bool]:
        market_code, zone_code, service_type, window_ended_at = snapshot_context
        try:
            with self._connection.begin_nested():
                self._connection.execute(
                    insert(marketplace_decisions).values(
                        decision_id=recommendation.decision_id,
                        snapshot_id=recommendation.snapshot_id,
                        rule_set_id=recommendation.rule_set_id,
                        market_code=market_code,
                        zone_code=zone_code,
                        service_type=service_type,
                        window_ended_at=window_ended_at,
                        recommendation=recommendation.recommendation.value,
                        health_score_bps=recommendation.health_score_bps,
                        explanation=recommendation.model_dump(mode="json"),
                        generated_at=recommendation.generated_at,
                        expires_at=recommendation.expires_at,
                    )
                )
            return recommendation, True
        except IntegrityError:
            value = self._connection.execute(
                select(marketplace_decisions.c.explanation).where(
                    marketplace_decisions.c.snapshot_id == recommendation.snapshot_id,
                    marketplace_decisions.c.rule_set_id == recommendation.rule_set_id,
                )
            ).scalar_one()
            return MarketplaceRecommendation.model_validate(value), False

    def save_simulation(self, run: SimulationRun) -> SimulationRun:
        self._connection.execute(
            insert(marketplace_simulation_runs).values(
                run_id=run.run_id,
                baseline_rule_version=run.baseline_rule_version,
                candidate_rule_version=run.candidate_rule_version,
                dataset_checksum=run.dataset_checksum,
                result=run.model_dump(mode="json"),
                completed_at=run.completed_at,
            )
        )
        return run
