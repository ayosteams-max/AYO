import { CourierHandoffContractError, parseCourierPickup, type CourierPickupSnapshot } from './courier-handoff-status.ts';

export type MarkArrivedCommandScope = Readonly<{
  identityId: string;
  sessionId: string;
  identityGeneration: number;
  contextGeneration: number;
  pickupId: string;
  pickupVersion: number;
  presentationAction: 'mark_arrived';
}>;

export type MarkArrivedAttempt = Readonly<{
  action: 'mark_arrived';
  pickupId: string;
  expectedVersion: number;
  idempotencyKey: string;
  identityId: string;
  sessionId: string;
  identityGeneration: number;
  contextGeneration: number;
}>;

export type MarkArrivedResult = Readonly<{
  pickupId: string;
  state: 'arrived_at_merchant';
  version: number;
  travellingAt: string;
  arrivedAt: string;
  updatedAt: string;
}>;

export type MarkArrivedReconciliation =
  | Readonly<{ outcome: 'already_applied'; pickup: CourierPickupSnapshot }>
  | Readonly<{ outcome: 'retry_same_attempt'; pickup: CourierPickupSnapshot }>
  | Readonly<{ outcome: 'invalidated'; reason: 'authority_lost' | 'state_changed' }>;

export type MarkArrivedRejection = 'version_conflict' | 'transition_not_allowed' | 'idempotency_conflict' | 'replay_unavailable';

export class MarkArrivedContractError extends Error { constructor() { super('malformed_mark_arrived_contract'); } }
export class MarkArrivedAttemptInvalidError extends Error { constructor() { super('mark_arrived_attempt_invalid'); } }
export class MarkArrivedOutcomeUnknownError extends Error { constructor() { super('mark_arrived_outcome_unknown'); } }
export class MarkArrivedRejectedError extends Error {
  readonly reason: MarkArrivedRejection;
  constructor(reason: MarkArrivedRejection) { super('mark_arrived_rejected'); this.reason = reason; }
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const own = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);

function exactObject(value: unknown, keys: readonly string[]) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new MarkArrivedContractError();
  const record = value as Record<string, unknown>;
  if (Object.keys(record).length !== keys.length || keys.some((key) => !own(record, key))) throw new MarkArrivedContractError();
  return record;
}

function instant(value: unknown) {
  if (typeof value !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value))) throw new MarkArrivedContractError();
  return value;
}

export function secureMarkArrivedAttemptKey(): string {
  if (!globalThis.crypto?.randomUUID) throw new Error('secure_command_identity_unavailable');
  return globalThis.crypto.randomUUID();
}

export function createMarkArrivedAttempt(scope: MarkArrivedCommandScope, generateKey: () => string = secureMarkArrivedAttemptKey): MarkArrivedAttempt {
  if (!UUID.test(scope.identityId) || !UUID.test(scope.sessionId) || !UUID.test(scope.pickupId)) throw new MarkArrivedAttemptInvalidError();
  if (!Number.isSafeInteger(scope.identityGeneration) || scope.identityGeneration < 0 || !Number.isSafeInteger(scope.contextGeneration) || scope.contextGeneration < 0) throw new MarkArrivedAttemptInvalidError();
  if (!Number.isSafeInteger(scope.pickupVersion) || scope.pickupVersion < 1 || scope.presentationAction !== 'mark_arrived') throw new MarkArrivedAttemptInvalidError();
  const key = generateKey();
  if (typeof key !== 'string' || key.length < 16 || key.length > 128 || !UUID.test(key)) throw new MarkArrivedAttemptInvalidError();
  return Object.freeze({
    action: 'mark_arrived', pickupId: scope.pickupId.toLowerCase(), expectedVersion: scope.pickupVersion,
    idempotencyKey: key.toLowerCase(), identityId: scope.identityId.toLowerCase(), sessionId: scope.sessionId.toLowerCase(),
    identityGeneration: scope.identityGeneration, contextGeneration: scope.contextGeneration,
  });
}

export function markArrivedAttemptMatchesScope(attempt: MarkArrivedAttempt, scope: MarkArrivedCommandScope | undefined): boolean {
  return !!scope && scope.presentationAction === 'mark_arrived' &&
    attempt.identityId === scope.identityId.toLowerCase() && attempt.sessionId === scope.sessionId.toLowerCase() &&
    attempt.identityGeneration === scope.identityGeneration && attempt.contextGeneration === scope.contextGeneration &&
    attempt.pickupId === scope.pickupId.toLowerCase() && attempt.expectedVersion === scope.pickupVersion;
}

export function parseMarkArrivedResult(value: unknown, attempt: MarkArrivedAttempt): MarkArrivedResult {
  const item = exactObject(value, ['pickup_id', 'state', 'version', 'assigned_at', 'travelling_at', 'arrived_at', 'merchant_acknowledged_at', 'waiting_duration_seconds', 'terminal_reason', 'updated_at']);
  if (typeof item.pickup_id !== 'string' || item.pickup_id.toLowerCase() !== attempt.pickupId || item.state !== 'arrived_at_merchant') throw new MarkArrivedContractError();
  if (!Number.isSafeInteger(item.version) || item.version !== attempt.expectedVersion + 1) throw new MarkArrivedContractError();
  const assignedAt = instant(item.assigned_at); const travellingAt = instant(item.travelling_at); const arrivedAt = instant(item.arrived_at); const updatedAt = instant(item.updated_at);
  if (Date.parse(travellingAt) < Date.parse(assignedAt) || Date.parse(arrivedAt) < Date.parse(travellingAt) || Date.parse(updatedAt) < Date.parse(arrivedAt)) throw new MarkArrivedContractError();
  if (item.merchant_acknowledged_at !== null || item.waiting_duration_seconds !== null || item.terminal_reason !== null) throw new MarkArrivedContractError();
  return Object.freeze({ pickupId: attempt.pickupId, state: 'arrived_at_merchant', version: item.version as number, travellingAt, arrivedAt, updatedAt });
}

export function reconcileMarkArrivedRead(value: unknown, attempt: MarkArrivedAttempt): MarkArrivedReconciliation {
  let pickup: CourierPickupSnapshot;
  try { pickup = parseCourierPickup(value); } catch (error) { if (error instanceof CourierHandoffContractError) throw new MarkArrivedContractError(); throw error; }
  if (pickup.pickupId !== attempt.pickupId) return Object.freeze({ outcome: 'invalidated', reason: 'state_changed' });
  if (pickup.state === 'travelling_to_merchant' && pickup.version === attempt.expectedVersion && pickup.presentationAction === 'mark_arrived') return Object.freeze({ outcome: 'retry_same_attempt', pickup });
  if (pickup.state === 'arrived_at_merchant' && pickup.version >= attempt.expectedVersion + 1) return Object.freeze({ outcome: 'already_applied', pickup });
  if (pickup.state === 'waiting_for_pickup' && pickup.version >= attempt.expectedVersion + 2) return Object.freeze({ outcome: 'already_applied', pickup });
  return Object.freeze({ outcome: 'invalidated', reason: 'state_changed' });
}
