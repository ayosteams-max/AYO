export type MerchantCourierPickupState =
  | 'courier_assigned'
  | 'travelling_to_merchant'
  | 'arrived_at_merchant'
  | 'waiting_for_pickup'
  | 'pickup_attempt_ended_before_custody';

export type MerchantCourierPickupPresentationAction = 'acknowledge_arrival' | 'none';

export type MerchantCourierPickupTerminalReason =
  | 'assignment_closed_or_revoked'
  | 'merchant_location_unreachable'
  | 'merchant_not_found'
  | 'merchant_unavailable'
  | 'order_not_ready'
  | 'readiness_corrected'
  | 'courier_unable_to_continue'
  | 'authority_or_identity_failure'
  | 'duplicate_or_invalid_attempt'
  | 'other_review_required';

export type MerchantCourierPickupSnapshot = Readonly<{
  pickupId: string;
  state: MerchantCourierPickupState;
  version: number;
  arrivedAt?: string;
  merchantAcknowledgedAt?: string;
  waitingDurationSeconds?: number;
  terminalReason?: MerchantCourierPickupTerminalReason;
  updatedAt: string;
  presentationAction: MerchantCourierPickupPresentationAction;
}>;

export class MerchantCourierPickupContractError extends Error {
  constructor() { super('malformed_merchant_courier_pickup_status'); }
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const states = new Set<MerchantCourierPickupState>([
  'courier_assigned',
  'travelling_to_merchant',
  'arrived_at_merchant',
  'waiting_for_pickup',
  'pickup_attempt_ended_before_custody',
]);
const terminalReasons = new Set<MerchantCourierPickupTerminalReason>([
  'assignment_closed_or_revoked',
  'merchant_location_unreachable',
  'merchant_not_found',
  'merchant_unavailable',
  'order_not_ready',
  'readiness_corrected',
  'courier_unable_to_continue',
  'authority_or_identity_failure',
  'duplicate_or_invalid_attempt',
  'other_review_required',
]);
const fields = [
  'pickup_id',
  'state',
  'version',
  'arrived_at',
  'merchant_acknowledged_at',
  'waiting_duration_seconds',
  'terminal_reason',
  'updated_at',
  'presentation_action',
] as const;
const own = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new MerchantCourierPickupContractError();
  const record = value as Record<string, unknown>;
  if (Object.keys(record).length !== fields.length || fields.some((key) => !own(record, key))) throw new MerchantCourierPickupContractError();
  return record;
}

export function parseMerchantCourierPickupIdentifier(value: unknown): string {
  if (typeof value !== 'string' || !uuid.test(value)) throw new MerchantCourierPickupContractError();
  return value.toLowerCase();
}

function instant(value: unknown): string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(value) || !Number.isFinite(Date.parse(value))) throw new MerchantCourierPickupContractError();
  return value;
}

function nullableInstant(value: unknown): string | undefined {
  return value === null ? undefined : instant(value);
}

function positiveVersion(value: unknown): number {
  if (!Number.isSafeInteger(value) || (value as number) < 1) throw new MerchantCourierPickupContractError();
  return value as number;
}

function waitingDuration(value: unknown): number | undefined {
  if (value === null) return undefined;
  if (!Number.isSafeInteger(value) || (value as number) < 0) throw new MerchantCourierPickupContractError();
  return value as number;
}

function terminalReason(value: unknown): MerchantCourierPickupTerminalReason | undefined {
  if (value === null) return undefined;
  if (typeof value !== 'string' || !terminalReasons.has(value as MerchantCourierPickupTerminalReason)) throw new MerchantCourierPickupContractError();
  return value as MerchantCourierPickupTerminalReason;
}

export function parseMerchantCourierPickupStatus(value: unknown): MerchantCourierPickupSnapshot {
  const item = object(value);
  if (typeof item.state !== 'string' || !states.has(item.state as MerchantCourierPickupState)) throw new MerchantCourierPickupContractError();
  if (item.presentation_action !== 'acknowledge_arrival' && item.presentation_action !== 'none') throw new MerchantCourierPickupContractError();
  const state = item.state as MerchantCourierPickupState;
  const presentationAction = item.presentation_action as MerchantCourierPickupPresentationAction;
  if (presentationAction === 'acknowledge_arrival' && state !== 'arrived_at_merchant') throw new MerchantCourierPickupContractError();

  return Object.freeze({
    pickupId: parseMerchantCourierPickupIdentifier(item.pickup_id),
    state,
    version: positiveVersion(item.version),
    arrivedAt: nullableInstant(item.arrived_at),
    merchantAcknowledgedAt: nullableInstant(item.merchant_acknowledged_at),
    waitingDurationSeconds: waitingDuration(item.waiting_duration_seconds),
    terminalReason: terminalReason(item.terminal_reason),
    updatedAt: instant(item.updated_at),
    presentationAction,
  });
}
