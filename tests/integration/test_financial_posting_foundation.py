from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from BACKEND.financial_posting.application import FinancialPostingApplicationService
from BACKEND.financial_posting.engine import FinancialPostingConflict
from BACKEND.financial_posting.models import (
    FinancialPostingCommand,
    FinancialPostingEntrySide,
    FinancialPostingLineCommand,
    FinancialPostingSourceType,
)
from BACKEND.identity.models import IdentityType
from BACKEND.persistence.tables import (
    financial_posting_events,
    financial_posting_lines,
    financial_posting_outbox,
    financial_postings,
    ledger_entries,
    ledger_journals,
    wallet_lineage_entries,
)
from tests.integration.test_payment_foundation import (
    NOW,
    create_identity,
    grant_permissions,
    subject,
)
from tests.integration.test_settlement_foundation import _captured_attempt

pytestmark = [pytest.mark.integration]


def _posting_accounts(composition, journal_id):
    with composition.unit_of_work() as unit:
        return tuple(
            unit.connection.execute(
                select(ledger_entries.c.account_id)
                .where(ledger_entries.c.journal_id == journal_id)
                .order_by(ledger_entries.c.line_index)
            ).scalars()
        )


def _posting_command(
    *,
    source_id,
    rider_identity_id,
    debit_account_id,
    credit_account_id,
    amount_minor,
    idempotency_key,
    operation="financial.posting.create",
):
    return FinancialPostingCommand(
        source_type=FinancialPostingSourceType.COMPLETED_PAYMENT,
        source_id=source_id,
        operation=operation,
        reason_code="financial.posting.capture",
        currency="ETB",
        lines=(
            FinancialPostingLineCommand(
                line_index=1,
                account_id=debit_account_id,
                side=FinancialPostingEntrySide.DEBIT,
                amount_minor=amount_minor,
            ),
            FinancialPostingLineCommand(
                line_index=2,
                account_id=credit_account_id,
                side=FinancialPostingEntrySide.CREDIT,
                amount_minor=amount_minor,
            ),
        ),
        wallet_owner_identity_id=rider_identity_id,
        wallet_amount_minor=amount_minor,
        idempotency_key=idempotency_key,
        correlation_id=uuid4(),
        causation_id=source_id,
        occurred_at=NOW,
    )


def test_increment13_financial_posting_authority_and_status_boundaries(
    postgres_composition,
) -> None:
    rider = create_identity(postgres_composition, IdentityType.RIDER)
    support = create_identity(postgres_composition, IdentityType.STAFF)
    service = create_identity(postgres_composition, IdentityType.SERVICE)
    staff = create_identity(postgres_composition, IdentityType.STAFF)
    grant_permissions(
        postgres_composition,
        service,
        (
            "payment.callback.ingest",
            "payment.trace.read",
            "settlement.batch.create",
            "settlement.collect.run",
            "settlement.reconcile.run",
            "settlement.trace.read",
            "financial.posting.create",
            "wallet.event.consume",
            "financial.posting.trace.read",
        ),
    )
    grant_permissions(
        postgres_composition,
        support,
        ("support.financial_posting.read_status",),
    )

    context, _, _, attempt = _captured_attempt(
        postgres_composition,
        callback_identity_id=service.identity_id,
    )
    account_ids = _posting_accounts(postgres_composition, context["journal"].journal_id)
    posting = FinancialPostingApplicationService(postgres_composition)

    with pytest.raises(FinancialPostingConflict, match="access_denied"):
        posting.post(
            subject(IdentityType.STAFF, staff.identity_id),
            _posting_command(
                source_id=attempt.payment_attempt_id,
                rider_identity_id=rider.identity_id,
                debit_account_id=account_ids[0],
                credit_account_id=account_ids[1],
                amount_minor=attempt.amount_minor,
                idempotency_key=f"posting-{uuid4()}",
            ),
        )

    grant_permissions(
        postgres_composition,
        staff,
        ("financial.posting.create",),
    )
    with pytest.raises(
        FinancialPostingConflict, match="financial_posting_service_identity_required"
    ):
        posting.post(
            subject(IdentityType.STAFF, staff.identity_id),
            _posting_command(
                source_id=attempt.payment_attempt_id,
                rider_identity_id=rider.identity_id,
                debit_account_id=account_ids[0],
                credit_account_id=account_ids[1],
                amount_minor=attempt.amount_minor,
                idempotency_key=f"posting-{uuid4()}",
            ),
        )

    result = posting.post(
        subject(IdentityType.SERVICE, service.identity_id),
        _posting_command(
            source_id=attempt.payment_attempt_id,
            rider_identity_id=rider.identity_id,
            debit_account_id=account_ids[0],
            credit_account_id=account_ids[1],
            amount_minor=attempt.amount_minor,
            idempotency_key=f"posting-{uuid4()}",
        ),
    )
    assert result.posting.total_debit_minor == attempt.amount_minor
    assert result.posting.total_credit_minor == attempt.amount_minor

    with postgres_composition.unit_of_work() as unit:
        assert (
            unit.connection.execute(
                select(func.count()).select_from(financial_postings)
            ).scalar_one()
            == 1
        )
        assert (
            unit.connection.execute(
                select(func.count()).select_from(financial_posting_lines)
            ).scalar_one()
            == 2
        )
        assert (
            unit.connection.execute(
                select(func.count()).select_from(financial_posting_events)
            ).scalar_one()
            == 1
        )
        assert (
            unit.connection.execute(
                select(func.count()).select_from(financial_posting_outbox)
            ).scalar_one()
            == 1
        )

    status = posting.posting_status(
        subject(IdentityType.STAFF, support.identity_id),
        posting_id=result.posting.posting_id,
        at=NOW,
    )
    assert status.posting.posting_id == result.posting.posting_id
    assert len(status.lines) == 2

    with pytest.raises(
        FinancialPostingConflict, match="financial_posting_status_not_found"
    ):
        posting.posting_status(
            subject(IdentityType.RIDER, rider.identity_id),
            posting_id=result.posting.posting_id,
            at=NOW,
        )


def test_increment13_financial_posting_idempotency_and_lineage_guards(
    postgres_composition,
) -> None:
    rider = create_identity(postgres_composition, IdentityType.RIDER)
    service = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        service,
        (
            "payment.callback.ingest",
            "payment.trace.read",
            "settlement.batch.create",
            "settlement.collect.run",
            "settlement.reconcile.run",
            "settlement.trace.read",
            "financial.posting.create",
            "wallet.event.consume",
        ),
    )

    context, _, _, attempt = _captured_attempt(
        postgres_composition,
        callback_identity_id=service.identity_id,
    )
    account_ids = _posting_accounts(postgres_composition, context["journal"].journal_id)
    posting = FinancialPostingApplicationService(postgres_composition)
    actor = subject(IdentityType.SERVICE, service.identity_id)
    key = f"posting-idem-{uuid4()}"

    first = posting.post(
        actor,
        _posting_command(
            source_id=attempt.payment_attempt_id,
            rider_identity_id=rider.identity_id,
            debit_account_id=account_ids[0],
            credit_account_id=account_ids[1],
            amount_minor=attempt.amount_minor,
            idempotency_key=key,
        ),
    )
    second = posting.post(
        actor,
        _posting_command(
            source_id=attempt.payment_attempt_id,
            rider_identity_id=rider.identity_id,
            debit_account_id=account_ids[0],
            credit_account_id=account_ids[1],
            amount_minor=attempt.amount_minor,
            idempotency_key=key,
        ),
    )
    assert first.posting.posting_id == second.posting.posting_id

    with pytest.raises(FinancialPostingConflict, match="idempotency_conflict"):
        posting.post(
            actor,
            _posting_command(
                source_id=attempt.payment_attempt_id,
                rider_identity_id=rider.identity_id,
                debit_account_id=account_ids[0],
                credit_account_id=account_ids[1],
                amount_minor=attempt.amount_minor + 1,
                idempotency_key=key,
            ),
        )

    with pytest.raises(
        FinancialPostingConflict, match="financial_posting_source_not_supported"
    ):
        posting.post(
            actor,
            FinancialPostingCommand(
                source_type=FinancialPostingSourceType.WALLET_ADJUSTMENT,
                source_id=uuid4(),
                operation="financial.posting.unsupported",
                reason_code="financial.posting.unsupported",
                currency="ETB",
                lines=(
                    FinancialPostingLineCommand(
                        line_index=1,
                        account_id=account_ids[0],
                        side=FinancialPostingEntrySide.DEBIT,
                        amount_minor=10,
                    ),
                    FinancialPostingLineCommand(
                        line_index=2,
                        account_id=account_ids[1],
                        side=FinancialPostingEntrySide.CREDIT,
                        amount_minor=10,
                    ),
                ),
                wallet_owner_identity_id=rider.identity_id,
                wallet_amount_minor=10,
                idempotency_key=f"posting-unsupported-{uuid4()}",
                correlation_id=uuid4(),
                causation_id=uuid4(),
                occurred_at=NOW,
            ),
        )


def test_increment13_financial_posting_duplicate_source_rolls_back_downstream(
    postgres_composition,
) -> None:
    rider = create_identity(postgres_composition, IdentityType.RIDER)
    service = create_identity(postgres_composition, IdentityType.SERVICE)
    grant_permissions(
        postgres_composition,
        service,
        (
            "payment.callback.ingest",
            "payment.trace.read",
            "settlement.batch.create",
            "settlement.collect.run",
            "settlement.reconcile.run",
            "settlement.trace.read",
            "financial.posting.create",
            "wallet.event.consume",
        ),
    )

    context, _, _, attempt = _captured_attempt(
        postgres_composition,
        callback_identity_id=service.identity_id,
    )
    account_ids = _posting_accounts(postgres_composition, context["journal"].journal_id)
    posting = FinancialPostingApplicationService(postgres_composition)
    actor = subject(IdentityType.SERVICE, service.identity_id)
    operation = "financial.posting.duplicate"

    posting.post(
        actor,
        _posting_command(
            source_id=attempt.payment_attempt_id,
            rider_identity_id=rider.identity_id,
            debit_account_id=account_ids[0],
            credit_account_id=account_ids[1],
            amount_minor=attempt.amount_minor,
            idempotency_key=f"posting-a-{uuid4()}",
            operation=operation,
        ),
    )

    with postgres_composition.unit_of_work() as unit:
        journals_before = unit.connection.execute(
            select(func.count()).select_from(ledger_journals)
        ).scalar_one()
        wallet_before = unit.connection.execute(
            select(func.count()).select_from(wallet_lineage_entries)
        ).scalar_one()

    with pytest.raises(IntegrityError):
        posting.post(
            actor,
            _posting_command(
                source_id=attempt.payment_attempt_id,
                rider_identity_id=rider.identity_id,
                debit_account_id=account_ids[0],
                credit_account_id=account_ids[1],
                amount_minor=attempt.amount_minor,
                idempotency_key=f"posting-b-{uuid4()}",
                operation=operation,
            ),
        )

    with postgres_composition.unit_of_work() as unit:
        journals_after = unit.connection.execute(
            select(func.count()).select_from(ledger_journals)
        ).scalar_one()
        wallet_after = unit.connection.execute(
            select(func.count()).select_from(wallet_lineage_entries)
        ).scalar_one()
        postings = unit.connection.execute(
            select(func.count()).select_from(financial_postings)
        ).scalar_one()

    assert journals_after == journals_before
    assert wallet_after == wallet_before
    assert postings == 1
