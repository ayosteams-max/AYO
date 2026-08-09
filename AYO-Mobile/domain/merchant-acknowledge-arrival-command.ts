import {
  MerchantCourierPickupContractError,
  parseMerchantCourierPickupStatus,
  type MerchantCourierPickupSnapshot,
} from './merchant-courier-pickup-status.ts';

export type MerchantAcknowledgeArrivalCommandScope = Readonly<{
  identityId: string;
  sessionId: string;
  identityGeneration: number;
  contextGeneration: number;
  merchantId: string;
  orderId: string;
  pickupId: string;
  pickupVersion: number;
  presentationAction: 'acknowledge_arrival';
}>;

export type MerchantAcknowledgeArrivalAttempt = Readonly<{
  action: 'acknowledge_arrival';
  identityId: string;
  sessionId: string;
  identityGeneration: number;
  contextGeneration: number;
  merchantId: string;
  orderId: string;
  pickupId: string;
  expectedVersion: number;
  idempotencyKey: string;
}>;

export type MerchantAcknowledgeArrivalResult = Readonly<{
  pickupId: string;
  state: 'waiting_for_pickup';
  version: number;
  arrivedAt: string;
  merchantAcknowledgedAt: string;
  waitingDurationSeconds: number;
  updatedAt: string;
}>;

export type MerchantAcknowledgeArrivalReconciliation =
  | Readonly<{ outcome: 'already_applied'; pickup: MerchantCourierPickupSnapshot }>
  | Readonly<{ outcome: 'retry_same_attempt'; pickup: MerchantCourierPickupSnapshot }>
  | Readonly<{ outcome: 'invalidated'; reason: 'authority_lost' | 'state_changed' }>;

export type MerchantAcknowledgeArrivalRejection =
  | 'version_conflict'
  | 'transition_not_allowed'
  | 'idempotency_conflict'
  | 'replay_unavailable'
  | 'temporarily_unavailable';

export class MerchantAcknowledgeArrivalContractError extends Error {
  constructor() { super('malformed_merchant_acknowledge_arrival_contract'); }
}
export class MerchantAcknowledgeArrivalAttemptInvalidError extends Error {
  constructor() { super('merchant_acknowledge_arrival_attempt_invalid'); }
}
export class MerchantAcknowledgeArrivalOutcomeUnknownError extends Error {
  constructor() { super('merchant_acknowledge_arrival_outcome_unknown'); }
}
export class MerchantAcknowledgeArrivalRejectedError extends Error {
  readonly reason: MerchantAcknowledgeArrivalRejection;
  constructor(reason: MerchantAcknowledgeArrivalRejection) {
    super('merchant_acknowledge_arrival_rejected');
    this.reason = reason;
  }
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const own = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);

function exactObject(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new MerchantAcknowledgeArrivalContractError();
  const record = value as Record<string, unknown>;
  if (Object.keys(record).length !== keys.length || keys.some((key) => !own(record, key))) throw new MerchantAcknowledgeArrivalContractError();
  return record;
}

function instant(value: unknown): string {
  if (typeof value !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value))) throw new MerchantAcknowledgeArrivalContractError();
  return value;
}

function scopeIsValid(scope: MerchantAcknowledgeArrivalCommandScope | undefined): scope is MerchantAcknowledgeArrivalCommandScope {
  return !!scope && UUID.test(scope.identityId) && UUID.test(scope.sessionId) && UUID.test(scope.merchantId) &&
    UUID.test(scope.orderId) && UUID.test(scope.pickupId) && Number.isSafeInteger(scope.pickupVersion) &&
    scope.pickupVersion >= 1 && Number.isSafeInteger(scope.identityGeneration) && scope.identityGeneration >= 0 &&
    Number.isSafeInteger(scope.contextGeneration) && scope.contextGeneration >= 0 &&
    scope.presentationAction === 'acknowledge_arrival';
}

function attemptIsValid(attempt: MerchantAcknowledgeArrivalAttempt): boolean {
  return attempt.action === 'acknowledge_arrival' && UUID.test(attempt.identityId) && UUID.test(attempt.sessionId) &&
    UUID.test(attempt.merchantId) && UUID.test(attempt.orderId) && UUID.test(attempt.pickupId) &&
    UUID.test(attempt.idempotencyKey) && attempt.idempotencyKey.length >= 16 && attempt.idempotencyKey.length <= 128 &&
    Number.isSafeInteger(attempt.expectedVersion) && attempt.expectedVersion >= 1 &&
    Number.isSafeInteger(attempt.identityGeneration) && attempt.identityGeneration >= 0 &&
    Number.isSafeInteger(attempt.contextGeneration) && attempt.contextGeneration >= 0;
}

export function secureMerchantAcknowledgeArrivalAttemptKey(): string {
  if (!globalThis.crypto?.randomUUID) throw new Error('secure_command_identity_unavailable');
  return globalThis.crypto.randomUUID();
}

export function createMerchantAcknowledgeArrivalAttempt(
  scope: MerchantAcknowledgeArrivalCommandScope,
  generateKey: () => string = secureMerchantAcknowledgeArrivalAttemptKey,
): MerchantAcknowledgeArrivalAttempt {
  if (!scopeIsValid(scope)) throw new MerchantAcknowledgeArrivalAttemptInvalidError();
  const key = generateKey();
  if (typeof key !== 'string' || !UUID.test(key) || key.length < 16 || key.length > 128) throw new MerchantAcknowledgeArrivalAttemptInvalidError();
  return Object.freeze({
    action: 'acknowledge_arrival',
    identityId: scope.identityId.toLowerCase(),
    sessionId: scope.sessionId.toLowerCase(),
    identityGeneration: scope.identityGeneration,
    contextGeneration: scope.contextGeneration,
    merchantId: scope.merchantId.toLowerCase(),
    orderId: scope.orderId.toLowerCase(),
    pickupId: scope.pickupId.toLowerCase(),
    expectedVersion: scope.pickupVersion,
    idempotencyKey: key.toLowerCase(),
  });
}

export function merchantAcknowledgeArrivalAttemptMatchesScope(
  attempt: MerchantAcknowledgeArrivalAttempt,
  scope: MerchantAcknowledgeArrivalCommandScope | undefined,
): boolean {
  return attemptIsValid(attempt) && scopeIsValid(scope) &&
    attempt.identityId === scope.identityId.toLowerCase() && attempt.sessionId === scope.sessionId.toLowerCase() &&
    attempt.identityGeneration === scope.identityGeneration && attempt.contextGeneration === scope.contextGeneration &&
    attempt.merchantId === scope.merchantId.toLowerCase() && attempt.orderId === scope.orderId.toLowerCase() &&
    attempt.pickupId === scope.pickupId.toLowerCase() && attempt.expectedVersion === scope.pickupVersion;
}

export function parseMerchantAcknowledgeArrivalResult(
  value: unknown,
  attempt: MerchantAcknowledgeArrivalAttempt,
): MerchantAcknowledgeArrivalResult {
  if (!attemptIsValid(attempt)) throw new MerchantAcknowledgeArrivalContractError();
  const item = exactObject(value, [
    'pickup_id', 'state', 'version', 'arrived_at', 'merchant_acknowledged_at',
    'waiting_duration_seconds', 'terminal_reason', 'updated_at',
  ]);
  if (typeof item.pickup_id !== 'string' || item.pickup_id.toLowerCase() !== attempt.pickupId || item.state !== 'waiting_for_pickup') throw new MerchantAcknowledgeArrivalContractError();
  if (!Number.isSafeInteger(item.version) || item.version !== attempt.expectedVersion + 1) throw new MerchantAcknowledgeArrivalContractError();
  const arrivedAt = instant(item.arrived_at);
  const merchantAcknowledgedAt = instant(item.merchant_acknowledged_at);
  const updatedAt = instant(item.updated_at);
  if (!Number.isSafeInteger(item.waiting_duration_seconds) || (item.waiting_duration_seconds as number) < 0 || item.terminal_reason !== null) throw new MerchantAcknowledgeArrivalContractError();
  if (Date.parse(merchantAcknowledgedAt) < Date.parse(arrivedAt) || Date.parse(updatedAt) < Date.parse(merchantAcknowledgedAt)) throw new MerchantAcknowledgeArrivalContractError();
  return Object.freeze({
    pickupId: attempt.pickupId,
    state: 'waiting_for_pickup',
    version: item.version as number,
    arrivedAt,
    merchantAcknowledgedAt,
    waitingDurationSeconds: item.waiting_duration_seconds as number,
    updatedAt,
  });
}

function waitingProvesAcknowledgement(pickup: MerchantCourierPickupSnapshot): boolean {
  return pickup.state === 'waiting_for_pickup' && !!pickup.arrivedAt && !!pickup.merchantAcknowledgedAt &&
    pickup.waitingDurationSeconds !== undefined && pickup.terminalReason === undefined &&
    Date.parse(pickup.merchantAcknowledgedAt) >= Date.parse(pickup.arrivedAt) &&
    Date.parse(pickup.updatedAt) >= Date.parse(pickup.merchantAcknowledgedAt);
}

export function reconcileMerchantAcknowledgeArrivalRead(
  value: unknown,
  attempt: MerchantAcknowledgeArrivalAttempt,
): MerchantAcknowledgeArrivalReconciliation {
  if (!attemptIsValid(attempt)) throw new MerchantAcknowledgeArrivalContractError();
  let pickup: MerchantCourierPickupSnapshot;
  try { pickup = parseMerchantCourierPickupStatus(value); }
  catch (error) {
    if (error instanceof MerchantCourierPickupContractError) throw new MerchantAcknowledgeArrivalContractError();
    throw error;
  }
  if (pickup.pickupId !== attempt.pickupId) return Object.freeze({ outcome: 'invalidated', reason: 'state_changed' });
  if (pickup.state === 'arrived_at_merchant' && pickup.version === attempt.expectedVersion) {
    return pickup.presentationAction === 'acknowledge_arrival'
      ? Object.freeze({ outcome: 'retry_same_attempt', pickup })
      : Object.freeze({ outcome: 'invalidated', reason: 'authority_lost' });
  }
  if (pickup.state === 'waiting_for_pickup' && pickup.version >= attempt.expectedVersion + 1) {
    if (!waitingProvesAcknowledgement(pickup)) throw new MerchantAcknowledgeArrivalContractError();
    return Object.freeze({ outcome: 'already_applied', pickup });
  }
  return Object.freeze({ outcome: 'invalidated', reason: 'state_changed' });
}
