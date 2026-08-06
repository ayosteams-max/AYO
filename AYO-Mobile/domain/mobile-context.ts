export type MerchantAvailability = 'pending' | 'available' | 'suspended';
export type PersonalMobileContext = Readonly<{ available: true }>;
export type MerchantMobileContext = Readonly<{ merchantId: string; displayName: string; availability: MerchantAvailability }>;
export type CourierMobileContext = Readonly<{ pickupId: string; availability: 'current_pickup' }>;
export type MobileContextSnapshot = Readonly<{ personal?: PersonalMobileContext; merchants: readonly MerchantMobileContext[]; courier?: CourierMobileContext }>;

export type OperationalArea =
  | Readonly<{ key: 'personal'; kind: 'personal'; enterable: true }>
  | Readonly<{ key: `merchant:${string}`; kind: 'merchant'; enterable: boolean; merchantId: string; displayName: string; availability: MerchantAvailability }>
  | Readonly<{ key: 'courier'; kind: 'courier'; enterable: true; pickupId: string }>;

export class MobileContextContractError extends Error {
  constructor() { super('malformed_mobile_context'); }
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const own = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);

function object(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new MobileContextContractError();
  const record = value as Record<string, unknown>;
  if (Object.keys(record).length !== keys.length || keys.some((key) => !own(record, key))) throw new MobileContextContractError();
  return record;
}

function identifier(value: unknown): string {
  if (typeof value !== 'string' || !uuid.test(value)) throw new MobileContextContractError();
  return value.toLowerCase();
}

export function parseMobileContext(value: unknown): MobileContextSnapshot {
  const root = object(value, ['personal', 'merchants', 'courier']);
  let personal: PersonalMobileContext | undefined;
  if (root.personal !== null) {
    const item = object(root.personal, ['available']);
    if (item.available !== true) throw new MobileContextContractError();
    personal = { available: true };
  }
  if (!Array.isArray(root.merchants) || root.merchants.length > 50) throw new MobileContextContractError();
  const seen = new Set<string>();
  const merchants = root.merchants.map((value) => {
    const item = object(value, ['merchant_id', 'display_name', 'availability']);
    const merchantId = identifier(item.merchant_id);
    if (seen.has(merchantId)) throw new MobileContextContractError();
    seen.add(merchantId);
    if (typeof item.display_name !== 'string' || item.display_name.length < 2 || item.display_name.length > 120 || item.display_name.trim() !== item.display_name) throw new MobileContextContractError();
    if (item.availability !== 'pending' && item.availability !== 'available' && item.availability !== 'suspended') throw new MobileContextContractError();
    return { merchantId, displayName: item.display_name, availability: item.availability } as const;
  });
  let courier: CourierMobileContext | undefined;
  if (root.courier !== null) {
    const item = object(root.courier, ['pickup_id', 'availability']);
    if (item.availability !== 'current_pickup') throw new MobileContextContractError();
    courier = { pickupId: identifier(item.pickup_id), availability: 'current_pickup' };
  }
  return Object.freeze({ personal, merchants: Object.freeze(merchants), courier });
}

export function operationalAreas(snapshot: MobileContextSnapshot): readonly OperationalArea[] {
  const areas: OperationalArea[] = [];
  if (snapshot.personal) areas.push({ key: 'personal', kind: 'personal', enterable: true });
  for (const merchant of snapshot.merchants) areas.push({ key: `merchant:${merchant.merchantId}`, kind: 'merchant', enterable: merchant.availability === 'available', ...merchant });
  if (snapshot.courier) areas.push({ key: 'courier', kind: 'courier', enterable: true, pickupId: snapshot.courier.pickupId });
  return areas;
}

export function reconcileAreaSelection(areas: readonly OperationalArea[], previous?: OperationalArea['key']) {
  const usable = areas.filter((area) => area.enterable);
  const selectedKey = previous && usable.some((area) => area.key === previous) ? previous : usable.length === 1 ? usable[0].key : undefined;
  return Object.freeze({ selectedKey, chooserVisible: selectedKey === undefined });
}
