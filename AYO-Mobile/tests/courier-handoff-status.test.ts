import assert from 'node:assert/strict';
import test from 'node:test';

import { CourierHandoffConflictError, CourierHandoffContractError, parseCourierCustody, parseCourierPickup, projectCourierHandoff } from '../domain/courier-handoff-status.ts';
import { PublicApiError } from '../services/api-foundation.ts';
import { CourierHandoffStatusService } from '../services/courier-handoff-status.ts';

const pickupId = '11111111-1111-4111-8111-111111111111';
const pickup = (state = 'waiting_for_pickup') => ({
  pickup_id: pickupId, state, version: 4, assigned_at: '2026-08-07T01:00:00Z', travelling_at: '2026-08-07T01:05:00Z', arrived_at: '2026-08-07T01:15:00Z', merchant_acknowledged_at: state === 'waiting_for_pickup' ? '2026-08-07T01:16:00Z' : null, waiting_duration_seconds: state === 'waiting_for_pickup' ? 60 : null, terminal_reason: null, updated_at: '2026-08-07T01:16:00Z',
});
const custody = (state = 'waiting_for_pickup') => ({
  custody_id: '22222222-2222-4222-8222-222222222222', order_id: '33333333-3333-4333-8333-333333333333', state, version: 1,
  required_action: state === 'waiting_for_pickup' ? 'wait_for_merchant' : state === 'order_sealed' ? 'verify_pickup' : state === 'courier_custody_accepted' ? 'handoff_complete' : 'wait_for_merchant', waiting_for: state === 'courier_custody_accepted' ? null : state === 'order_sealed' ? 'courier' : 'merchant', recovery: null,
  challenge_available: state === 'order_sealed', challenge_expires_at: state === 'order_sealed' ? '2026-08-07T01:30:00Z' : null, supported_verification_methods: state === 'order_sealed' ? ['qr_code', 'barcode'] : [],
});

test('strictly parses exact public pickup and Custody responses', () => {
  assert.equal(parseCourierPickup(pickup()).state, 'waiting_for_pickup');
  assert.equal(parseCourierCustody(custody('order_sealed')).requiredAction, 'verify_pickup');
  assert.throws(() => parseCourierPickup({ ...pickup(), courier_id: pickupId }), CourierHandoffContractError);
  assert.throws(() => parseCourierCustody({ ...custody(), state: 'invented' }), CourierHandoffContractError);
  assert.throws(() => parseCourierPickup({ ...pickup(), pickup_id: 'not-an-id' }), CourierHandoffContractError);
});

test('projects only truthful lifecycle combinations', () => {
  assert.equal(projectCourierHandoff(parseCourierPickup({ ...pickup('courier_assigned'), travelling_at: null, arrived_at: null, updated_at: '2026-08-07T01:00:00Z' })).status, 'pickup_current');
  assert.equal(projectCourierHandoff(parseCourierPickup(pickup()), parseCourierCustody(custody())).status, 'waiting_for_merchant');
  assert.equal(projectCourierHandoff(parseCourierPickup(pickup()), parseCourierCustody(custody('order_sealed'))).status, 'ready_for_handoff');
  assert.equal(projectCourierHandoff(parseCourierPickup(pickup()), parseCourierCustody(custody('courier_custody_accepted'))).status, 'pickup_confirmed');
  assert.throws(() => projectCourierHandoff(parseCourierPickup(pickup())), CourierHandoffConflictError);
  assert.throws(() => projectCourierHandoff(parseCourierPickup({ ...pickup('arrived_at_merchant'), merchant_acknowledged_at: null }), parseCourierCustody(custody())), CourierHandoffConflictError);
});

test('service performs bounded sequential reads and treats only 404 as absent Custody', async () => {
  const paths: string[] = [];
  const service = new CourierHandoffStatusService(async (path) => { paths.push(path); return paths.length === 1 ? pickup() : custody('order_sealed'); });
  assert.equal((await service.load(pickupId)).status, 'ready_for_handoff');
  assert.deepEqual(paths, [`/mobile/courier-pickups/${pickupId}`, `/mobile/courier-pickups/${pickupId}/custody`]);
  const absent = new CourierHandoffStatusService(async (path) => { if (path.endsWith('/custody')) throw new PublicApiError('not_found', 404); return { ...pickup('arrived_at_merchant'), merchant_acknowledged_at: null }; });
  assert.equal((await absent.load(pickupId)).status, 'at_merchant');
  const failed = new CourierHandoffStatusService(async (path) => { if (path.endsWith('/custody')) throw new PublicApiError('temporarily_unavailable', 503); return pickup(); });
  await assert.rejects(failed.load(pickupId), PublicApiError);
});

test('localized resources remain exactly equivalent', async () => {
  const { courierHandoffCopy } = await import('../localization/courier-handoff-status.ts');
  assert.deepEqual(Object.keys(courierHandoffCopy.en), Object.keys(courierHandoffCopy.am));
});
