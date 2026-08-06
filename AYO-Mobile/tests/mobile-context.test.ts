import assert from 'node:assert/strict';
import test from 'node:test';

import { MobileContextContractError, operationalAreas, parseMobileContext, reconcileAreaSelection } from '../domain/mobile-context.ts';
import { MobileContextService } from '../services/mobile-context.ts';

const id = (digit: string) => `${digit.repeat(8)}-${digit.repeat(4)}-4${digit.repeat(3)}-8${digit.repeat(3)}-${digit.repeat(12)}`;
const empty = { personal: null, merchants: [], courier: null };
const complete = {
  personal: { available: true },
  merchants: [{ merchant_id: id('1'), display_name: 'AYO Market', availability: 'available' }],
  courier: { pickup_id: id('2'), availability: 'current_pickup' },
};

test('valid empty, personal, merchant, courier and multi-context responses parse', () => {
  assert.deepEqual(parseMobileContext(empty), { personal: undefined, merchants: [], courier: undefined });
  assert.equal(parseMobileContext({ ...empty, personal: { available: true } }).personal?.available, true);
  assert.equal(parseMobileContext({ ...empty, merchants: complete.merchants }).merchants[0].displayName, 'AYO Market');
  assert.equal(parseMobileContext({ ...empty, courier: complete.courier }).courier?.availability, 'current_pickup');
  assert.equal(operationalAreas(parseMobileContext(complete)).length, 3);
});

for (const [name, value] of [
  ['unknown top-level field', { ...empty, role: 'courier' }],
  ['unknown nested field', { ...empty, personal: { available: true, identity_id: id('3') } }],
  ['invalid merchant availability', { ...empty, merchants: [{ ...complete.merchants[0], availability: 'active' }] }],
  ['invalid courier availability', { ...empty, courier: { ...complete.courier, availability: 'assigned' } }],
  ['malformed merchant id', { ...empty, merchants: [{ ...complete.merchants[0], merchant_id: 'merchant-1' }] }],
  ['malformed pickup id', { ...empty, courier: { ...complete.courier, pickup_id: 'pickup-1' } }],
  ['missing field', { personal: null, merchants: [] }],
] as const) test(`${name} fails closed`, () => assert.throws(() => parseMobileContext(value), MobileContextContractError));

test('more than 50 merchants and duplicate merchant identifiers fail closed', () => {
  const merchants = Array.from({ length: 51 }, (_, index) => ({ merchant_id: `${index.toString(16).padStart(8, '0')}-1111-4111-8111-111111111111`, display_name: `Business ${index}`, availability: 'available' }));
  assert.throws(() => parseMobileContext({ ...empty, merchants }), MobileContextContractError);
  assert.throws(() => parseMobileContext({ ...empty, merchants: [complete.merchants[0], complete.merchants[0]] }), MobileContextContractError);
});

test('availability controls enterability without parsing presentation labels', () => {
  const snapshot = parseMobileContext({ ...empty, merchants: [
    { merchant_id: id('1'), display_name: 'Available shop', availability: 'available' },
    { merchant_id: id('2'), display_name: 'Pending shop', availability: 'pending' },
    { merchant_id: id('3'), display_name: 'Suspended shop', availability: 'suspended' },
  ] });
  assert.deepEqual(operationalAreas(snapshot).map((area) => area.enterable), [true, false, false]);
});

test('context service uses only the bounded authenticated GET route', async () => {
  const calls: string[] = [];
  const service = new MobileContextService(async (path) => { calls.push(path); return empty; });
  await service.load();
  assert.deepEqual(calls, ['/api/mobile/context']);
});

test('one usable context routes directly while multiple contexts require a chooser', () => {
  const personalAreas = operationalAreas(parseMobileContext({ ...empty, personal: { available: true } }));
  assert.deepEqual(reconcileAreaSelection(personalAreas), { selectedKey: 'personal', chooserVisible: false });
  const multiple = operationalAreas(parseMobileContext(complete));
  assert.deepEqual(reconcileAreaSelection(multiple), { selectedKey: undefined, chooserVisible: true });
});

test('removed selection is cleared and pending or suspended businesses remain non-enterable', () => {
  const restricted = operationalAreas(parseMobileContext({ ...empty, merchants: [
    { merchant_id: id('1'), display_name: 'Pending business', availability: 'pending' },
    { merchant_id: id('2'), display_name: 'Suspended business', availability: 'suspended' },
  ] }));
  assert.deepEqual(reconcileAreaSelection(restricted, 'personal'), { selectedKey: undefined, chooserVisible: true });
  assert.ok(restricted.every((area) => !area.enterable));
});
