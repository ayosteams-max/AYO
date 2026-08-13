# Booking Consent Authority Architecture

Status: PRE-PRODUCTION. Founder/CEO and CTO authorized this bounded contract correction. No public legal policy, deployment, feature enablement, or production activation is authorized.

## Problem and customer value

Booking confirmation previously accepted a syntactically valid client-provided consent-policy version on first confirmation. The server therefore persisted a version without first proving that it was the version the server required and the rider had been shown. The correction prevents a rider from being confirmed against invented, altered, missing, or stale consent metadata.

## Authority boundary

An explicitly composed immutable registry owns metadata for reviewed policies: version, document identity, content hash, effective interval, required acknowledgment, and the fixed `immediate_mandatory` rotation mode. The repository contains no legal policy prose and publishes no policy-document endpoint. An empty, duplicate, ambiguous, invalid, or unavailable registry fails closed.

Route preview resolves exactly one active policy at server time, incorporates its complete immutable metadata into the route-evidence hash, persists that binding in the existing route-evidence JSON record, and returns only bounded metadata. A legacy record without the binding remains distinguishable and cannot be assigned a guessed policy.

Confirmation requires explicit acknowledgment plus the exact bound version and document hash. Before any Ride Request, pricing, confirmation, outbox, ledger, evidence, or dispatch effect, the application proves that the binding is still the single mandatory policy. Immediate rotation invalidates the old preview; the rider must deliberately obtain and acknowledge a new preview. Rotation never authorizes a replacement booking.

Already canonical recovery remains rider-scoped. Exact mutation replay continues to require the complete immutable command and returns only the canonical confirmation. A replay with changed consent metadata produces the existing generic `idempotency_conflict` response.

## Security, privacy, and operations

Policy prose, location, rider data, booking identifiers, keys, hashes, and payloads are not logged by this boundary. Public failures identify only the safe categories `consent_policy_unavailable` and `consent_policy_changed`; field-specific mismatches are not disclosed. No database schema, migration, provider, mobile capability, or external service is introduced.

Legal approval, policy-content publication, native-language review, mobile presentation, retention approval, controlled activation, and production authorization remain separate leadership gates.

This mechanism establishes metadata authority only; it is not legal policy prose and does not establish legal compliance. No production consent policy is configured. Policy content requires separate legal and product approval. No mobile implementation or activation occurs, no schema migration is expected, and production remains prohibited.
