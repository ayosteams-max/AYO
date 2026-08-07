import { CourierHandoffContractError, parseCourierPickup, type CourierPickupSnapshot } from './courier-handoff-status.ts';

export type CourierCommandScope = Readonly<{
  identityId: string;
  sessionId: string;
  identityGeneration: number;
  contextGeneration: number;
  pickupId: string;
  pickupVersion: number;
  presentationAction: 'start_travel';
}>;

export type StartTravelAttempt = Readonly<{
  action: 'start_travel';
  pickupId: string;
  expectedVersion: number;
  idempotencyKey: string;
  identityId: string;
  sessionId: string;
  identityGeneration: number;
  contextGeneration: number;
}>;

export type StartTravelResult = Readonly<{
  pickupId: string;
  state: 'travelling_to_merchant';
  version: number;
  travellingAt: string;
  updatedAt: string;
}>;

export type StartTravelReconciliation =
  | Readonly<{ outcome: 'already_applied'; pickup: CourierPickupSnapshot }>
  | Readonly<{ outcome: 'retry_same_attempt'; pickup: CourierPickupSnapshot }>
  | Readonly<{ outcome: 'invalidated'; reason: 'authority_lost' | 'state_changed' }>;

export class StartTravelContractError extends Error { constructor() { super('malformed_start_travel_contract'); } }
export class StartTravelAttemptInvalidError extends Error { constructor() { super('start_travel_attempt_invalid'); } }
export class StartTravelOutcomeUnknownError extends Error { constructor() { super('start_travel_outcome_unknown'); } }
export type StartTravelRejection = 'authority_lost' | 'version_conflict' | 'transition_not_allowed' | 'idempotency_conflict' | 'replay_unavailable';
export class StartTravelRejectedError extends Error { readonly reason: StartTravelRejection; constructor(reason: StartTravelRejection) { super('start_travel_rejected'); this.reason = reason; } }

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const own = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);
function exactObject(value: unknown, keys: readonly string[]) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new StartTravelContractError();
  const record = value as Record<string, unknown>;
  if (Object.keys(record).length !== keys.length || keys.some((key) => !own(record, key))) throw new StartTravelContractError();
  return record;
}
function instant(value: unknown) {
  if (typeof value !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value))) throw new StartTravelContractError();
  return value;
}

export function secureAttemptKey(): string {
  if (!globalThis.crypto?.randomUUID) throw new Error('secure_command_identity_unavailable');
  return globalThis.crypto.randomUUID();
}

export function createStartTravelAttempt(scope: CourierCommandScope, generateKey: () => string = secureAttemptKey): StartTravelAttempt {
  if (!UUID.test(scope.identityId) || !UUID.test(scope.sessionId) || !UUID.test(scope.pickupId)) throw new StartTravelAttemptInvalidError();
  if (!Number.isSafeInteger(scope.identityGeneration) || scope.identityGeneration < 0 || !Number.isSafeInteger(scope.contextGeneration) || scope.contextGeneration < 0) throw new StartTravelAttemptInvalidError();
  if (!Number.isSafeInteger(scope.pickupVersion) || scope.pickupVersion < 1 || scope.presentationAction !== 'start_travel') throw new StartTravelAttemptInvalidError();
  const key = generateKey();
  if (typeof key !== 'string' || key.length < 16 || key.length > 128 || !UUID.test(key)) throw new StartTravelAttemptInvalidError();
  return Object.freeze({
    action: 'start_travel', pickupId: scope.pickupId.toLowerCase(), expectedVersion: scope.pickupVersion,
    idempotencyKey: key.toLowerCase(), identityId: scope.identityId.toLowerCase(), sessionId: scope.sessionId.toLowerCase(),
    identityGeneration: scope.identityGeneration, contextGeneration: scope.contextGeneration,
  });
}

export function attemptMatchesScope(attempt: StartTravelAttempt, scope: CourierCommandScope | undefined): boolean {
  return !!scope && scope.presentationAction === 'start_travel' &&
    attempt.identityId === scope.identityId.toLowerCase() && attempt.sessionId === scope.sessionId.toLowerCase() &&
    attempt.identityGeneration === scope.identityGeneration && attempt.contextGeneration === scope.contextGeneration &&
    attempt.pickupId === scope.pickupId.toLowerCase() && attempt.expectedVersion === scope.pickupVersion;
}

export function parseStartTravelResult(value: unknown, attempt: StartTravelAttempt): StartTravelResult {
  const item = exactObject(value, ['pickup_id', 'state', 'version', 'assigned_at', 'travelling_at', 'arrived_at', 'merchant_acknowledged_at', 'waiting_duration_seconds', 'terminal_reason', 'updated_at']);
  if (typeof item.pickup_id !== 'string' || item.pickup_id.toLowerCase() !== attempt.pickupId || item.state !== 'travelling_to_merchant') throw new StartTravelContractError();
  if (!Number.isSafeInteger(item.version) || item.version !== attempt.expectedVersion + 1) throw new StartTravelContractError();
  const assignedAt = instant(item.assigned_at); const travellingAt = instant(item.travelling_at); const updatedAt = instant(item.updated_at);
  if (Date.parse(travellingAt) < Date.parse(assignedAt) || Date.parse(updatedAt) < Date.parse(travellingAt)) throw new StartTravelContractError();
  if (item.arrived_at !== null || item.merchant_acknowledged_at !== null || item.waiting_duration_seconds !== null || item.terminal_reason !== null) throw new StartTravelContractError();
  return Object.freeze({ pickupId: attempt.pickupId, state: 'travelling_to_merchant', version: item.version as number, travellingAt, updatedAt });
}

export function reconcileStartTravelRead(value: unknown, attempt: StartTravelAttempt): StartTravelReconciliation {
  let pickup: CourierPickupSnapshot;
  try { pickup = parseCourierPickup(value); } catch (error) { if (error instanceof CourierHandoffContractError) throw new StartTravelContractError(); throw error; }
  if (pickup.pickupId !== attempt.pickupId) return Object.freeze({ outcome: 'invalidated', reason: 'state_changed' });
  if (pickup.state === 'travelling_to_merchant' && pickup.version === attempt.expectedVersion + 1) return Object.freeze({ outcome: 'already_applied', pickup });
  if (pickup.state === 'courier_assigned' && pickup.version === attempt.expectedVersion && pickup.presentationAction === 'start_travel') return Object.freeze({ outcome: 'retry_same_attempt', pickup });
  return Object.freeze({ outcome: 'invalidated', reason: 'state_changed' });
}
