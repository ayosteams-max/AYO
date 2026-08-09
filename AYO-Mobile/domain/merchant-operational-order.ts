export type MerchantOperationalOrderState =
  | 'waiting_for_merchant_confirmation'
  | 'accepted'
  | 'rejected'
  | 'preparing'
  | 'ready_for_pickup';

export type MerchantOperationalOrder = Readonly<{
  orderId: string;
  merchantId: string;
  state: MerchantOperationalOrderState;
  version: number;
  createdAt: string;
}>;

export class MerchantOperationalOrderContractError extends Error {
  constructor() { super('malformed_merchant_operational_orders'); }
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const hash = /^[a-f0-9]{64}$/;
const eventType = /^[a-z][a-z0-9_.]{2,62}$/;
const rejectionReason = /^[a-z][a-z0-9_]{2,62}$/;
const states = new Set<MerchantOperationalOrderState>([
  'waiting_for_merchant_confirmation', 'accepted', 'rejected', 'preparing', 'ready_for_pickup',
]);
const own = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);

function object(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new MerchantOperationalOrderContractError();
  const record = value as Record<string, unknown>;
  if (Object.keys(record).length !== keys.length || keys.some((key) => !own(record, key))) throw new MerchantOperationalOrderContractError();
  return record;
}

function identifier(value: unknown): string {
  if (typeof value !== 'string' || !uuid.test(value)) throw new MerchantOperationalOrderContractError();
  return value.toLowerCase();
}

function instant(value: unknown): string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(value) || !Number.isFinite(Date.parse(value))) throw new MerchantOperationalOrderContractError();
  return value;
}

function safeInteger(value: unknown, minimum = 0): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum) throw new MerchantOperationalOrderContractError();
  return value as number;
}

function text(value: unknown, minimum: number, maximum: number): string {
  if (typeof value !== 'string' || value.length < minimum || value.length > maximum) throw new MerchantOperationalOrderContractError();
  return value;
}

function validateLine(value: unknown): void {
  const line = object(value, ['item_id', 'item_version', 'name', 'kind', 'category_id', 'quantity', 'unit_price_minor', 'line_total_minor', 'currency', 'modifier_selections', 'customer_instructions']);
  identifier(line.item_id); safeInteger(line.item_version, 1); text(line.name, 2, 160); text(line.kind, 3, 24);
  if (line.category_id !== null) identifier(line.category_id);
  const quantity = safeInteger(line.quantity, 1); if (quantity > 99) throw new MerchantOperationalOrderContractError();
  safeInteger(line.unit_price_minor); safeInteger(line.line_total_minor);
  if (line.currency !== 'ETB' || !Array.isArray(line.modifier_selections) || line.modifier_selections.length > 20 || line.modifier_selections.some((item) => typeof item !== 'string')) throw new MerchantOperationalOrderContractError();
  if (line.customer_instructions !== null && (typeof line.customer_instructions !== 'string' || line.customer_instructions.length > 500)) throw new MerchantOperationalOrderContractError();
}

function validateTimeline(value: unknown, orderId: string, merchantId: string): void {
  const event = object(value, ['event_id', 'order_id', 'merchant_id', 'event_type', 'from_state', 'to_state', 'actor_identity_id', 'order_version', 'customer_reason_code', 'occurred_at']);
  identifier(event.event_id);
  if (identifier(event.order_id) !== orderId || identifier(event.merchant_id) !== merchantId) throw new MerchantOperationalOrderContractError();
  if (!eventType.test(text(event.event_type, 3, 63))) throw new MerchantOperationalOrderContractError();
  safeInteger(event.order_version, 1); instant(event.occurred_at);
  if (event.actor_identity_id !== null) identifier(event.actor_identity_id);
  if (event.from_state !== null && (typeof event.from_state !== 'string' || !states.has(event.from_state as MerchantOperationalOrderState))) throw new MerchantOperationalOrderContractError();
  if (typeof event.to_state !== 'string' || !states.has(event.to_state as MerchantOperationalOrderState)) throw new MerchantOperationalOrderContractError();
  if (event.customer_reason_code !== null && (typeof event.customer_reason_code !== 'string' || event.customer_reason_code.length > 63)) throw new MerchantOperationalOrderContractError();
}

function parseView(value: unknown, expectedMerchantId: string): MerchantOperationalOrder {
  const view = object(value, ['order', 'timeline', 'rejection']);
  const order = object(view.order, ['order_id', 'merchant_id', 'merchant_display_name', 'state', 'lines', 'pricing', 'evidence_hash', 'version', 'created_at']);
  const orderId = identifier(order.order_id);
  const merchantId = identifier(order.merchant_id);
  if (merchantId !== expectedMerchantId) throw new MerchantOperationalOrderContractError();
  text(order.merchant_display_name, 2, 120);
  if (typeof order.state !== 'string' || !states.has(order.state as MerchantOperationalOrderState)) throw new MerchantOperationalOrderContractError();
  if (!Array.isArray(order.lines) || order.lines.length < 1 || order.lines.length > 50) throw new MerchantOperationalOrderContractError();
  order.lines.forEach(validateLine);
  const pricing = object(order.pricing, ['authority', 'policy_version', 'subtotal_minor', 'currency', 'evidence_hash']);
  if (pricing.authority !== 'commerce_pricing' || pricing.currency !== 'ETB') throw new MerchantOperationalOrderContractError();
  text(pricing.policy_version, 3, 63); safeInteger(pricing.subtotal_minor);
  if (typeof pricing.evidence_hash !== 'string' || !hash.test(pricing.evidence_hash)) throw new MerchantOperationalOrderContractError();
  if (typeof order.evidence_hash !== 'string' || !hash.test(order.evidence_hash)) throw new MerchantOperationalOrderContractError();
  if (!Array.isArray(view.timeline) || view.timeline.length > 100) throw new MerchantOperationalOrderContractError();
  view.timeline.forEach((event) => validateTimeline(event, orderId, merchantId));
  if (view.rejection !== null) {
    const rejection = object(view.rejection, ['order_id', 'customer_reason_code', 'customer_message', 'internal_merchant_note', 'decided_by_identity_id', 'decided_at']);
    if (identifier(rejection.order_id) !== orderId) throw new MerchantOperationalOrderContractError();
    if (!rejectionReason.test(text(rejection.customer_reason_code, 3, 63))) throw new MerchantOperationalOrderContractError();
    text(rejection.customer_message, 2, 240); identifier(rejection.decided_by_identity_id); instant(rejection.decided_at);
    if (rejection.internal_merchant_note !== null && (typeof rejection.internal_merchant_note !== 'string' || rejection.internal_merchant_note.length > 1000)) throw new MerchantOperationalOrderContractError();
  }
  if ((order.state === 'rejected') !== (view.rejection !== null)) throw new MerchantOperationalOrderContractError();
  return Object.freeze({ orderId, merchantId, state: order.state as MerchantOperationalOrderState, version: safeInteger(order.version, 1), createdAt: instant(order.created_at) });
}

export function parseMerchantOperationalOrders(value: unknown, merchantId: string): readonly MerchantOperationalOrder[] {
  const expectedMerchantId = identifier(merchantId);
  if (!Array.isArray(value) || value.length > 25) throw new MerchantOperationalOrderContractError();
  const seen = new Set<string>();
  const orders = value.map((item) => parseView(item, expectedMerchantId));
  for (const order of orders) { if (seen.has(order.orderId)) throw new MerchantOperationalOrderContractError(); seen.add(order.orderId); }
  return Object.freeze(orders);
}
