export type CourierPickupState = 'courier_assigned' | 'travelling_to_merchant' | 'arrived_at_merchant' | 'waiting_for_pickup' | 'pickup_attempt_ended_before_custody';
export type CourierPickupPresentationAction = 'start_travel' | 'none';
export type CustodyState = 'waiting_for_pickup' | 'order_sealed' | 'pickup_verified' | 'merchant_released' | 'courier_custody_accepted';
export type HandoffStatusCategory = 'pickup_current' | 'travelling' | 'at_merchant' | 'waiting_for_merchant' | 'ready_for_handoff' | 'handoff_in_progress' | 'pickup_confirmed' | 'pickup_ended';

export type CourierPickupSnapshot = Readonly<{ pickupId: string; state: CourierPickupState; version: number; updatedAt: string; presentationAction: CourierPickupPresentationAction }>;
export type CourierCustodySnapshot = Readonly<{ state: CustodyState; version: number; requiredAction: 'verify_pickup' | 'accept_custody' | 'wait_for_merchant' | 'handoff_complete' | 'none'; waitingFor?: 'merchant' | 'courier'; recovery?: 'verification_expired' | 'temporarily_unavailable' }>;
export type CourierHandoffSnapshot = Readonly<{ status: HandoffStatusCategory; pickupVersion: number; custodyVersion?: number; updatedAt: string; presentationAction: CourierPickupPresentationAction }>;

export class CourierHandoffContractError extends Error { constructor() { super('malformed_courier_handoff_status'); } }
export class CourierHandoffConflictError extends Error { constructor() { super('conflicting_courier_handoff_status'); } }
export class CourierHandoffNoLongerCurrentError extends Error { constructor() { super('courier_handoff_no_longer_current'); } }

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const own = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);
function object(value: unknown, keys: readonly string[]) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new CourierHandoffContractError();
  const record = value as Record<string, unknown>;
  if (Object.keys(record).length !== keys.length || keys.some((key) => !own(record, key))) throw new CourierHandoffContractError();
  return record;
}
function identifier(value: unknown) { if (typeof value !== 'string' || !uuid.test(value)) throw new CourierHandoffContractError(); return value.toLowerCase(); }
function version(value: unknown) { if (!Number.isSafeInteger(value) || (value as number) < 1) throw new CourierHandoffContractError(); return value as number; }
function instant(value: unknown) { if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(value) || !Number.isFinite(Date.parse(value))) throw new CourierHandoffContractError(); return value; }
function nullableInstant(value: unknown) { return value === null ? undefined : instant(value); }

const pickupStates = new Set<CourierPickupState>(['courier_assigned', 'travelling_to_merchant', 'arrived_at_merchant', 'waiting_for_pickup', 'pickup_attempt_ended_before_custody']);
export function parseCourierPickup(value: unknown): CourierPickupSnapshot {
  const item = object(value, ['pickup_id', 'state', 'version', 'assigned_at', 'travelling_at', 'arrived_at', 'merchant_acknowledged_at', 'waiting_duration_seconds', 'terminal_reason', 'updated_at', 'presentation_action']);
  if (typeof item.state !== 'string' || !pickupStates.has(item.state as CourierPickupState)) throw new CourierHandoffContractError();
  const assignedAt = instant(item.assigned_at); const travellingAt = nullableInstant(item.travelling_at); const arrivedAt = nullableInstant(item.arrived_at); const acknowledgedAt = nullableInstant(item.merchant_acknowledged_at); const updatedAt = instant(item.updated_at);
  if (Date.parse(updatedAt) < Date.parse(assignedAt) || (travellingAt && Date.parse(travellingAt) < Date.parse(assignedAt)) || (arrivedAt && (!travellingAt || Date.parse(arrivedAt) < Date.parse(travellingAt))) || (acknowledgedAt && (!arrivedAt || Date.parse(acknowledgedAt) < Date.parse(arrivedAt)))) throw new CourierHandoffContractError();
  if (item.waiting_duration_seconds !== null && (!Number.isSafeInteger(item.waiting_duration_seconds) || (item.waiting_duration_seconds as number) < 0)) throw new CourierHandoffContractError();
  if (item.terminal_reason !== null && typeof item.terminal_reason !== 'string') throw new CourierHandoffContractError();
  const state = item.state as CourierPickupState;
  if (item.presentation_action !== 'start_travel' && item.presentation_action !== 'none') throw new CourierHandoffContractError();
  if ((state === 'courier_assigned') !== (item.presentation_action === 'start_travel')) throw new CourierHandoffContractError();
  if (
    (state === 'courier_assigned' && (travellingAt || arrivedAt || acknowledgedAt)) ||
    (state === 'travelling_to_merchant' && (!travellingAt || arrivedAt || acknowledgedAt)) ||
    (state === 'arrived_at_merchant' && (!travellingAt || !arrivedAt || acknowledgedAt)) ||
    (state === 'waiting_for_pickup' && (!travellingAt || !arrivedAt || !acknowledgedAt)) ||
    (state === 'pickup_attempt_ended_before_custody' && item.terminal_reason === null)
  ) throw new CourierHandoffContractError();
  return Object.freeze({ pickupId: identifier(item.pickup_id), state, version: version(item.version), updatedAt, presentationAction: item.presentation_action });
}

const custodyStates = new Set<CustodyState>(['waiting_for_pickup', 'order_sealed', 'pickup_verified', 'merchant_released', 'courier_custody_accepted']);
const actions = new Set(['verify_pickup', 'accept_custody', 'wait_for_merchant', 'handoff_complete', 'none']);
export function parseCourierCustody(value: unknown): CourierCustodySnapshot {
  const item = object(value, ['state', 'version', 'required_action', 'waiting_for', 'recovery', 'challenge_available', 'challenge_expires_at', 'supported_verification_methods']);
  if (typeof item.state !== 'string' || !custodyStates.has(item.state as CustodyState) || typeof item.required_action !== 'string' || !actions.has(item.required_action)) throw new CourierHandoffContractError();
  if (item.waiting_for !== null && item.waiting_for !== 'merchant' && item.waiting_for !== 'courier') throw new CourierHandoffContractError();
  if (item.recovery !== null && item.recovery !== 'verification_expired' && item.recovery !== 'temporarily_unavailable') throw new CourierHandoffContractError();
  if (typeof item.challenge_available !== 'boolean' || !Array.isArray(item.supported_verification_methods) || item.supported_verification_methods.some((method) => method !== 'qr_code' && method !== 'barcode')) throw new CourierHandoffContractError();
  if (item.challenge_expires_at !== null) instant(item.challenge_expires_at);
  if (item.challenge_available && (item.state !== 'order_sealed' || item.challenge_expires_at === null || item.supported_verification_methods.length === 0)) throw new CourierHandoffContractError();
  const expected = {
    waiting_for_pickup: ['wait_for_merchant', 'merchant'], pickup_verified: ['wait_for_merchant', 'merchant'],
    merchant_released: ['accept_custody', 'courier'], courier_custody_accepted: ['handoff_complete', null],
  }[item.state as string];
  if (expected && (item.required_action !== expected[0] || item.waiting_for !== expected[1] || item.challenge_available || item.recovery !== null)) throw new CourierHandoffContractError();
  if (item.state === 'order_sealed') {
    const healthy = item.required_action === 'verify_pickup' && item.waiting_for === 'courier' && item.recovery === null && item.challenge_available;
    const recovering = item.required_action === 'none' && item.waiting_for === null && item.recovery !== null && !item.challenge_available && item.supported_verification_methods.length === 0;
    if (!healthy && !recovering) throw new CourierHandoffContractError();
  }
  return Object.freeze({ state: item.state as CustodyState, version: version(item.version), requiredAction: item.required_action as CourierCustodySnapshot['requiredAction'], waitingFor: item.waiting_for ?? undefined, recovery: item.recovery ?? undefined });
}

export function parseCourierCustodyRead(value: unknown): CourierCustodySnapshot | undefined {
  if (value && typeof value === 'object' && !Array.isArray(value) && own(value, 'availability')) {
    const item = object(value, ['availability']);
    if (item.availability !== 'not_started') throw new CourierHandoffContractError();
    return undefined;
  }
  return parseCourierCustody(value);
}

export function projectCourierHandoff(pickup: CourierPickupSnapshot, custody?: CourierCustodySnapshot): CourierHandoffSnapshot {
  if (pickup.state === 'pickup_attempt_ended_before_custody') {
    if (custody) throw new CourierHandoffConflictError();
    return Object.freeze({ status: 'pickup_ended', pickupVersion: pickup.version, updatedAt: pickup.updatedAt, presentationAction: pickup.presentationAction });
  }
  if (pickup.state !== 'waiting_for_pickup') {
    if (custody) throw new CourierHandoffConflictError();
    const status = pickup.state === 'courier_assigned' ? 'pickup_current' : pickup.state === 'travelling_to_merchant' ? 'travelling' : 'at_merchant';
    return Object.freeze({ status, pickupVersion: pickup.version, updatedAt: pickup.updatedAt, presentationAction: pickup.presentationAction });
  }
  if (!custody) throw new CourierHandoffConflictError();
  const status: HandoffStatusCategory = custody.state === 'waiting_for_pickup' ? 'waiting_for_merchant' : custody.state === 'order_sealed' ? 'ready_for_handoff' : custody.state === 'courier_custody_accepted' ? 'pickup_confirmed' : 'handoff_in_progress';
  return Object.freeze({ status, pickupVersion: pickup.version, custodyVersion: custody.version, updatedAt: pickup.updatedAt, presentationAction: pickup.presentationAction });
}
