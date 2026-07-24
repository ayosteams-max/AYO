from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from BACKEND.customer_profile.models import (
    PROFILE_TRANSITIONS,
    RELATIONSHIP_TRANSITIONS,
    CustomerProfile,
    EmergencyContact,
    HouseholdRelationship,
    ProfileLifecycle,
    RelationshipState,
)
from BACKEND.persistence.errors import OptimisticConcurrencyError, PersistenceError
from BACKEND.persistence.tables import (
    customer_emergency_contacts,
    customer_household_relationships,
    customer_profiles,
)


class CustomerProfileConflict(PersistenceError):
    pass


def _profile(row: Mapping[Any, Any]) -> CustomerProfile:
    return CustomerProfile.model_validate(dict(row))


def _relationship(row: Mapping[Any, Any]) -> HouseholdRelationship:
    return HouseholdRelationship.model_validate(dict(row))


def _contact(row: Mapping[Any, Any]) -> EmergencyContact:
    return EmergencyContact.model_validate(dict(row))


class PostgresCustomerProfileRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def create_profile(self, profile: CustomerProfile) -> CustomerProfile:
        try:
            row = (
                self._connection.execute(
                    insert(customer_profiles)
                    .values(**profile.model_dump(mode="python"))
                    .returning(customer_profiles)
                )
                .mappings()
                .one()
            )
        except IntegrityError as error:
            raise CustomerProfileConflict("Profile already exists") from error
        return _profile(row)

    def profile_for_subject(
        self, subject_id: UUID, *, lock: bool = False
    ) -> CustomerProfile | None:
        statement = select(customer_profiles).where(
            customer_profiles.c.subject_id == subject_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else _profile(row)

    def update_profile(
        self,
        profile: CustomerProfile,
        *,
        expected_version: int,
        at: datetime,
        changes: dict[str, object],
    ) -> CustomerProfile:
        row = (
            self._connection.execute(
                update(customer_profiles)
                .where(
                    customer_profiles.c.profile_id == profile.profile_id,
                    customer_profiles.c.version == expected_version,
                )
                .values(
                    **changes, updated_at=at, version=customer_profiles.c.version + 1
                )
                .returning(customer_profiles)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Customer profile changed")
        return _profile(row)

    def transition_profile(
        self,
        profile: CustomerProfile,
        *,
        target: ProfileLifecycle,
        expected_version: int,
        at: datetime,
    ) -> CustomerProfile:
        if target not in PROFILE_TRANSITIONS[profile.state]:
            raise ValueError(f"Invalid profile transition: {profile.state}->{target}")
        return self.update_profile(
            profile,
            expected_version=expected_version,
            at=at,
            changes={"state": target.value},
        )

    def create_relationship(
        self, relationship: HouseholdRelationship
    ) -> HouseholdRelationship:
        try:
            row = (
                self._connection.execute(
                    insert(customer_household_relationships)
                    .values(**relationship.model_dump(mode="python"))
                    .returning(customer_household_relationships)
                )
                .mappings()
                .one()
            )
        except IntegrityError as error:
            raise CustomerProfileConflict(
                "Household relationship already exists"
            ) from error
        return _relationship(row)

    def relationship(
        self, relationship_id: UUID, *, lock: bool = False
    ) -> HouseholdRelationship | None:
        statement = select(customer_household_relationships).where(
            customer_household_relationships.c.relationship_id == relationship_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else _relationship(row)

    def transition_relationship(
        self,
        relationship: HouseholdRelationship,
        *,
        target: RelationshipState,
        expected_version: int,
        at: datetime,
    ) -> HouseholdRelationship:
        if target not in RELATIONSHIP_TRANSITIONS[relationship.state]:
            raise ValueError(
                f"Invalid relationship transition: {relationship.state}->{target}"
            )
        row = (
            self._connection.execute(
                update(customer_household_relationships)
                .where(
                    customer_household_relationships.c.relationship_id
                    == relationship.relationship_id,
                    customer_household_relationships.c.version == expected_version,
                )
                .values(
                    state=target.value,
                    updated_at=at,
                    version=customer_household_relationships.c.version + 1,
                )
                .returning(customer_household_relationships)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Household relationship changed")
        return _relationship(row)

    def active_relationship_between(
        self, first: UUID, second: UUID
    ) -> HouseholdRelationship | None:
        row = (
            self._connection.execute(
                select(customer_household_relationships).where(
                    customer_household_relationships.c.state
                    == RelationshipState.ACTIVE.value,
                    or_(
                        (
                            customer_household_relationships.c.inviting_subject_id
                            == first
                        )
                        & (
                            customer_household_relationships.c.invited_subject_id
                            == second
                        ),
                        (
                            customer_household_relationships.c.inviting_subject_id
                            == second
                        )
                        & (
                            customer_household_relationships.c.invited_subject_id
                            == first
                        ),
                    ),
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _relationship(row)

    def create_contact(self, contact: EmergencyContact) -> EmergencyContact:
        try:
            row = (
                self._connection.execute(
                    insert(customer_emergency_contacts)
                    .values(**contact.model_dump(mode="python"))
                    .returning(customer_emergency_contacts)
                )
                .mappings()
                .one()
            )
        except IntegrityError as error:
            raise CustomerProfileConflict(
                "Emergency contact conflicts with existing priority"
            ) from error
        return _contact(row)

    def contact(
        self, contact_id: UUID, *, lock: bool = False
    ) -> EmergencyContact | None:
        statement = select(customer_emergency_contacts).where(
            customer_emergency_contacts.c.contact_id == contact_id
        )
        if lock:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().one_or_none()
        return None if row is None else _contact(row)

    def set_contact_active(
        self,
        contact: EmergencyContact,
        *,
        active: bool,
        expected_version: int,
        at: datetime,
    ) -> EmergencyContact:
        row = (
            self._connection.execute(
                update(customer_emergency_contacts)
                .where(
                    customer_emergency_contacts.c.contact_id == contact.contact_id,
                    customer_emergency_contacts.c.version == expected_version,
                )
                .values(
                    active=active,
                    updated_at=at,
                    version=customer_emergency_contacts.c.version + 1,
                )
                .returning(customer_emergency_contacts)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OptimisticConcurrencyError("Emergency contact changed")
        return _contact(row)
