from datetime import UTC, datetime
from uuid import uuid4

import pytest

from BACKEND.pricing.application import PricingApplication
from BACKEND.pricing.mobile_quotes import MobileCashQuoteApplication
from tests.integration.test_dispatch_handoff_localization import ready_request
from tests.integration.test_pricing_foundation import published_policy, route

pytestmark = pytest.mark.integration


def test_mobile_quote_delegates_to_existing_pricing_authority(postgres_composition):
    request, rider = ready_request(postgres_composition)
    policy = published_policy(
        PricingApplication(postgres_composition), request.service_zone_id
    )

    class Inputs:
        metrics = route(at=datetime.now(UTC))

        def resolve(self, *, ride_request_id, subject, at):
            assert ride_request_id == request.request_id
            assert subject.identity_id == rider.identity_id
            assert at >= self.metrics.observed_at
            return policy.policy_id, self.metrics

    app = MobileCashQuoteApplication(PricingApplication(postgres_composition), Inputs())
    at = datetime.now(UTC)
    first = app.quote(
        rider,
        ride_request_id=request.request_id,
        idempotency_key="mobile-authoritative-quote-0001",
        correlation_id=uuid4(),
        at=at,
    )
    replay = app.quote(
        rider,
        ride_request_id=request.request_id,
        idempotency_key="mobile-authoritative-quote-0001",
        correlation_id=uuid4(),
        at=at,
    )
    assert replay.estimate_id == first.estimate_id
    assert first.breakdown.rider_total_minor > 0
    assert first.policy_version == policy.policy_version
