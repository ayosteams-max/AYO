import { act, render, waitFor } from '@testing-library/react-native';
import { StrictMode, useLayoutEffect } from 'react';

import { CourierMarkArrivedCommandInfrastructureProvider, useTrustedMarkArrivedEvidence } from '@/contexts/courier-mark-arrived-command-scope';
import * as operational from '@/contexts/operational-context';

const identityId = '11111111-1111-4111-8111-111111111111';
const sessionId = '22222222-2222-4222-8222-222222222222';
const pickupId = '33333333-3333-4333-8333-333333333333';
const snapshot = Object.freeze({ status: 'travelling' as const, pickupVersion: 5, updatedAt: '2026-08-08T01:00:00Z', presentationAction: 'mark_arrived' as const });
type Evidence = ReturnType<typeof useTrustedMarkArrivedEvidence>;

function Capture({ set }: { set(value: Evidence): void }) {
  const evidence = useTrustedMarkArrivedEvidence();
  useLayoutEffect(() => set(evidence), [evidence, set]);
  return null;
}

test('mounted provider exposes only trusted evidence plumbing and constructs no privileged service eagerly', async () => {
  let evidence: Evidence;
  const createService = jest.fn(async () => { throw new Error('not_exposed'); });
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue({ readCourierContext: () => ({ pickupId, contextGeneration: 1, identityContinuity: { isCurrent: () => true } }) });
  try {
    const identity = { readIdentity: () => ({ identityId, sessionId, identityGeneration: 1 }), createMarkArrivedCommandService: createService };
    const mounted = await render(<CourierMarkArrivedCommandInfrastructureProvider identity={identity}><Capture set={(value) => { evidence = value; }} /></CourierMarkArrivedCommandInfrastructureProvider>);
    await waitFor(() => expect(evidence).toBeDefined());
    expect(Object.keys(evidence!).sort()).toEqual(['clearFresh', 'publishFresh']);
    expect(evidence).not.toHaveProperty('controller'); expect(evidence).not.toHaveProperty('service'); expect(evidence).not.toHaveProperty('attempt'); expect(evidence).not.toHaveProperty('idempotencyKey');
    await act(async () => evidence!.publishFresh(pickupId, snapshot));
    expect(createService).not.toHaveBeenCalled();
    await mounted.unmount();
    await act(async () => evidence!.publishFresh(pickupId, snapshot));
    expect(createService).not.toHaveBeenCalled();
  } finally { courierSpy.mockRestore(); }
});

test('committed replacement gives a distinct writer and old provider cannot revive', async () => {
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue({ readCourierContext: () => ({ pickupId, contextGeneration: 1, identityContinuity: { isCurrent: () => true } }) });
  try {
    const createService = jest.fn(async () => { throw new Error('not_exposed'); });
    const identityA = { readIdentity: () => ({ identityId, sessionId, identityGeneration: 1 }), createMarkArrivedCommandService: createService };
    const identityB = { readIdentity: () => ({ identityId, sessionId, identityGeneration: 1 }), createMarkArrivedCommandService: createService };
    let first: Evidence; let second: Evidence;
    const mounted = await render(<CourierMarkArrivedCommandInfrastructureProvider identity={identityA}><Capture set={(value) => { first = value; }} /></CourierMarkArrivedCommandInfrastructureProvider>);
    await waitFor(() => expect(first).toBeDefined());
    await mounted.rerender(<CourierMarkArrivedCommandInfrastructureProvider identity={identityB}><Capture set={(value) => { second = value; }} /></CourierMarkArrivedCommandInfrastructureProvider>);
    await waitFor(() => expect(second).toBeDefined());
    expect(second).not.toBe(first);
    await act(async () => { first!.publishFresh(pickupId, snapshot); second!.publishFresh(pickupId, snapshot); });
    expect(createService).not.toHaveBeenCalled();
    await mounted.unmount();
  } finally { courierSpy.mockRestore(); }
});

test('Strict Mode rehearsal retains the committed provider without constructing command authority', async () => {
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue({ readCourierContext: () => ({ pickupId, contextGeneration: 1, identityContinuity: { isCurrent: () => true } }) });
  try {
    const createService = jest.fn(async () => { throw new Error('not_exposed'); }); let evidence: Evidence;
    const identity = { readIdentity: () => ({ identityId, sessionId, identityGeneration: 1 }), createMarkArrivedCommandService: createService };
    const mounted = await render(<StrictMode><CourierMarkArrivedCommandInfrastructureProvider identity={identity}><Capture set={(value) => { evidence = value; }} /></CourierMarkArrivedCommandInfrastructureProvider></StrictMode>);
    await waitFor(() => expect(evidence).toBeDefined());
    await act(async () => evidence!.publishFresh(pickupId, snapshot));
    expect(createService).not.toHaveBeenCalled();
    await mounted.unmount();
  } finally { courierSpy.mockRestore(); }
});
