import { act, render } from '@testing-library/react-native';
import { StrictMode } from 'react';

import * as commandScopeModule from '@/contexts/courier-start-travel-command-scope';
import {
  CourierStartTravelCommandInfrastructureProvider,
  TrustedCourierHandoffStatus,
  useMarkArrivedCommand,
  useStartTravelCommand,
} from '@/contexts/courier-start-travel-command-scope';
import { MarkArrivedOutcomeUnknownError } from '@/domain/courier-mark-arrived-command';
import type { CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import { CourierMarkArrivedCommandScope } from '@/services/courier-mark-arrived-command-scope';
import { CourierMarkArrivedCommandService } from '@/services/courier-mark-arrived-command';
import * as operational from '@/contexts/operational-context';

const mockHandoffProps = jest.fn();
jest.mock('@/components/courier-handoff-status', () => ({
  CourierHandoffStatus: (props: unknown) => { mockHandoffProps(props); return null; },
}));

const identityId = '11111111-1111-4111-8111-111111111111';
const sessionId = '22222222-2222-4222-8222-222222222222';
const pickupId = '33333333-3333-4333-8333-333333333333';
const snapshot = Object.freeze({
  status: 'travelling' as const,
  pickupVersion: 5,
  updatedAt: '2026-08-08T01:00:00Z',
  presentationAction: 'mark_arrived' as const,
}) satisfies CourierHandoffSnapshot;
const startSnapshot = Object.freeze({
  status: 'pickup_current' as const,
  pickupVersion: 4,
  updatedAt: '2026-08-08T00:59:00Z',
  presentationAction: 'start_travel' as const,
}) satisfies CourierHandoffSnapshot;

function identity() {
  return {
    readIdentity: () => ({ identityId, sessionId, identityGeneration: 1 }),
    createStartTravelCommandService: jest.fn(async () => { throw new Error('not_exposed'); }),
    createMarkArrivedCommandService: jest.fn(async () => { throw new Error('not_exposed'); }),
  };
}

function currentCourier() {
  return {
    readCourierContext: () => ({ pickupId, contextGeneration: 1, identityContinuity: { isCurrent: () => true } }),
  };
}

type HandoffIntegration = Readonly<{
  publishFresh(currentPickupId: string, value: CourierHandoffSnapshot, explicitRecovery: boolean): void;
  clearFresh(currentPickupId: string): void;
}>;

function lastHandoffIntegration(): HandoffIntegration {
  const props = mockHandoffProps.mock.calls.at(-1)?.[0] as { commandEvidence?: HandoffIntegration } | undefined;
  if (!props?.commandEvidence) throw new Error('trusted_handoff_not_mounted');
  return props.commandEvidence;
}

beforeEach(() => mockHandoffProps.mockClear());

test('public module surface exposes no MARK_ARRIVED writer, scope, controller, handle, service, session, attempt, or key', () => {
  expect(Object.keys(commandScopeModule).sort()).toEqual([
    'CourierStartTravelCommandInfrastructureProvider',
    'TrustedCourierHandoffStatus',
    'useMarkArrivedCommand',
    'useStartTravelCommand',
  ]);
  for (const forbidden of [
    'useTrustedMarkArrivedEvidence', 'publishFresh', 'clearFresh', 'EvidenceContext',
    'MarkArrivedEvidenceContext', 'markArrivedScope', 'markArrivedController',
    'attempt', 'idempotencyKey', 'service', 'SessionManager',
  ]) expect(commandScopeModule).not.toHaveProperty(forbidden);
});

test('public MARK_ARRIVED hook exposes only the frozen bounded presentation facade', async () => {
  let capability: ReturnType<typeof useMarkArrivedCommand> | undefined;
  function Presentation() { capability = useMarkArrivedCommand(); return null; }
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue(currentCourier());
  try {
    const mounted = await render(<CourierStartTravelCommandInfrastructureProvider identity={identity()}><Presentation /></CourierStartTravelCommandInfrastructureProvider>);
    expect(capability).toBeDefined(); expect(Object.isFrozen(capability)).toBe(true);
    expect(Object.keys(capability!).sort()).toEqual(['canMarkArrived', 'canReconcileMarkArrived', 'markArrived', 'reconcileMarkArrived']);
    for (const forbidden of ['handle', 'attempt', 'idempotencyKey', 'scope', 'controller', 'service', 'publishFresh', 'clearFresh', 'SessionManager', 'identityId', 'sessionId', 'identityGeneration', 'contextGeneration']) {
      expect(capability).not.toHaveProperty(forbidden);
    }
    expect(capability!.canMarkArrived()).toBe(false); expect(capability!.canReconcileMarkArrived()).toBe(false);
    await mounted.unmount();
  } finally { courierSpy.mockRestore(); }
});

test('trusted fan-out makes only the bounded MARK_ARRIVED capability actionable', async () => {
  let capability: ReturnType<typeof useMarkArrivedCommand> | undefined;
  function Presentation() { capability = useMarkArrivedCommand(); return null; }
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue(currentCourier());
  try {
    const mounted = await render(<CourierStartTravelCommandInfrastructureProvider identity={identity()}><Presentation /><TrustedCourierHandoffStatus pickupId={pickupId} /></CourierStartTravelCommandInfrastructureProvider>);
    expect(capability!.canMarkArrived()).toBe(false);
    await act(async () => lastHandoffIntegration().publishFresh(pickupId, snapshot, false));
    expect(capability!.canMarkArrived()).toBe(true); expect(capability!.canReconcileMarkArrived()).toBe(false);
    await act(async () => lastHandoffIntegration().clearFresh(pickupId));
    expect(capability!.canMarkArrived()).toBe(false);
    await mounted.unmount();
  } finally { courierSpy.mockRestore(); }
});

test('released provider revokes an old bounded facade without migrating custody', async () => {
  const capabilities: ReturnType<typeof useMarkArrivedCommand>[] = [];
  function Presentation() { const value = useMarkArrivedCommand(); if (capabilities.at(-1) !== value) capabilities.push(value); return null; }
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue(currentCourier());
  try {
    const first = identity(); const second = identity();
    const mounted = await render(<CourierStartTravelCommandInfrastructureProvider identity={first}><Presentation /><TrustedCourierHandoffStatus pickupId={pickupId} /></CourierStartTravelCommandInfrastructureProvider>);
    await act(async () => lastHandoffIntegration().publishFresh(pickupId, snapshot, false));
    const old = capabilities.at(-1)!; expect(old.canMarkArrived()).toBe(true);
    await mounted.rerender(<CourierStartTravelCommandInfrastructureProvider identity={second}><Presentation /><TrustedCourierHandoffStatus pickupId={pickupId} /></CourierStartTravelCommandInfrastructureProvider>);
    expect(old.canMarkArrived()).toBe(false); expect(capabilities.at(-1)).not.toBe(old);
    expect(await old.markArrived()).toEqual({ outcome: 'invalidated', reason: 'scope_changed' });
    expect(first.createMarkArrivedCommandService).not.toHaveBeenCalled(); expect(second.createMarkArrivedCommandService).not.toHaveBeenCalled();
    await mounted.unmount();
  } finally { courierSpy.mockRestore(); }
});

test('only explicit trusted recovery clears an unexpected MARK_ARRIVED latch and preserves the attempt key', async () => {
  let capability: ReturnType<typeof useMarkArrivedCommand> | undefined;
  const submittedKeys: string[] = [];
  function Presentation() { capability = useMarkArrivedCommand(); return null; }
  const runtime = {
    ...identity(),
    createMarkArrivedCommandService: jest.fn(async (scope: CourierMarkArrivedCommandScope) => new CourierMarkArrivedCommandService(
      { post: async (attempt) => { submittedKeys.push(attempt.idempotencyKey); throw new Error('unexpected_mark_failure'); } },
      async () => { throw new Error('not_reconcilable'); },
      () => scope.currentScope(),
      (attempt) => scope.operationIsCurrent(attempt),
    )),
  };
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue(currentCourier());
  try {
    const mounted = await render(<CourierStartTravelCommandInfrastructureProvider identity={runtime}><Presentation /><TrustedCourierHandoffStatus pickupId={pickupId} /></CourierStartTravelCommandInfrastructureProvider>);
    await act(async () => lastHandoffIntegration().publishFresh(pickupId, snapshot, false));
    await expect(capability!.markArrived()).rejects.toThrow('unexpected_mark_failure');
    expect(capability!.canMarkArrived()).toBe(false);
    await act(async () => lastHandoffIntegration().publishFresh(pickupId, snapshot, false));
    expect(capability!.canMarkArrived()).toBe(false);
    await act(async () => lastHandoffIntegration().publishFresh(pickupId, snapshot, true));
    expect(capability!.canMarkArrived()).toBe(true);
    await expect(capability!.markArrived()).rejects.toThrow('unexpected_mark_failure');
    expect(submittedKeys).toHaveLength(2); expect(submittedKeys[1]).toBe(submittedKeys[0]);
    await mounted.unmount();
  } finally { courierSpy.mockRestore(); }
});

test('outcome-unknown reconciliation capability survives ordinary presentation remount', async () => {
  let capability: ReturnType<typeof useMarkArrivedCommand> | undefined;
  function Presentation() { capability = useMarkArrivedCommand(); return null; }
  const runtime = {
    ...identity(),
    createMarkArrivedCommandService: jest.fn(async (scope: CourierMarkArrivedCommandScope) => new CourierMarkArrivedCommandService(
      { post: async () => { throw new MarkArrivedOutcomeUnknownError(); } },
      async () => { throw new Error('explicit_reconcile_only'); },
      () => scope.currentScope(),
      (attempt) => scope.operationIsCurrent(attempt),
    )),
  };
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue(currentCourier());
  try {
    const mounted = await render(<CourierStartTravelCommandInfrastructureProvider identity={runtime}><Presentation /><TrustedCourierHandoffStatus pickupId={pickupId} /></CourierStartTravelCommandInfrastructureProvider>);
    await act(async () => lastHandoffIntegration().publishFresh(pickupId, snapshot, false));
    await expect(capability!.markArrived()).resolves.toEqual({ outcome: 'outcome_unknown' });
    expect(capability!.canReconcileMarkArrived()).toBe(true);
    await mounted.rerender(<CourierStartTravelCommandInfrastructureProvider identity={runtime}><TrustedCourierHandoffStatus pickupId={pickupId} /></CourierStartTravelCommandInfrastructureProvider>);
    capability = undefined;
    await mounted.rerender(<CourierStartTravelCommandInfrastructureProvider identity={runtime}><Presentation /><TrustedCourierHandoffStatus pickupId={pickupId} /></CourierStartTravelCommandInfrastructureProvider>);
    expect(capability!.canReconcileMarkArrived()).toBe(true); expect(capability!.canMarkArrived()).toBe(false);
    await mounted.unmount();
  } finally { courierSpy.mockRestore(); }
});

test('START and MARK_ARRIVED capabilities remain action-specific and failure-isolated', async () => {
  let mark: ReturnType<typeof useMarkArrivedCommand> | undefined;
  let start: ReturnType<typeof useStartTravelCommand> | undefined;
  function Presentation() { mark = useMarkArrivedCommand(); start = useStartTravelCommand(); return null; }
  const runtime = {
    ...identity(),
    createMarkArrivedCommandService: jest.fn(async (scope: CourierMarkArrivedCommandScope) => new CourierMarkArrivedCommandService(
      { post: async () => { throw new Error('unexpected_mark_failure'); } },
      async () => { throw new Error('not_reconcilable'); },
      () => scope.currentScope(),
      (attempt) => scope.operationIsCurrent(attempt),
    )),
  };
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue(currentCourier());
  try {
    const mounted = await render(<CourierStartTravelCommandInfrastructureProvider identity={runtime}><Presentation /><TrustedCourierHandoffStatus pickupId={pickupId} /></CourierStartTravelCommandInfrastructureProvider>);
    const evidence = lastHandoffIntegration();
    await act(async () => evidence.publishFresh(pickupId, snapshot, false));
    expect(mark!.canMarkArrived()).toBe(true); expect(start!.canStartTravel()).toBe(false);
    await expect(mark!.markArrived()).rejects.toThrow('unexpected_mark_failure');
    await act(async () => evidence.publishFresh(pickupId, startSnapshot, false));
    expect(mark!.canMarkArrived()).toBe(false); expect(start!.canStartTravel()).toBe(true);
    expect(runtime.createStartTravelCommandService).not.toHaveBeenCalled();
    await mounted.unmount();
  } finally { courierSpy.mockRestore(); }
});

test('ordinary mounted descendants receive no MARK_ARRIVED writer capability', async () => {
  let childProps: Record<string, unknown> | undefined;
  function OrdinaryPresentation(props: Record<string, unknown>) { childProps = props; return null; }
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue(currentCourier());
  try {
    const mounted = await render(
      <CourierStartTravelCommandInfrastructureProvider identity={identity()}>
        <OrdinaryPresentation bounded="presentation-only" />
      </CourierStartTravelCommandInfrastructureProvider>,
    );
    expect(childProps).toEqual({ bounded: 'presentation-only' });
    expect(childProps).not.toHaveProperty('publishFresh');
    expect(childProps).not.toHaveProperty('clearFresh');
    await mounted.unmount();
  } finally { courierSpy.mockRestore(); }
});

test('trusted Handoff fan-out publishes and clears MARK_ARRIVED evidence internally', async () => {
  const publish = jest.spyOn(CourierMarkArrivedCommandScope.prototype, 'publishFresh');
  const clear = jest.spyOn(CourierMarkArrivedCommandScope.prototype, 'clearFresh');
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue(currentCourier());
  try {
    const runtime = identity();
    const mounted = await render(
      <CourierStartTravelCommandInfrastructureProvider identity={runtime}>
        <TrustedCourierHandoffStatus pickupId={pickupId} />
      </CourierStartTravelCommandInfrastructureProvider>,
    );
    const evidence = lastHandoffIntegration();
    await act(async () => evidence.publishFresh(pickupId, snapshot, false));
    expect(publish).toHaveBeenCalledWith(pickupId, snapshot);
    const containedScope = publish.mock.instances.at(-1) as unknown as CourierMarkArrivedCommandScope;
    expect(containedScope.currentScope()).toMatchObject({ pickupId, pickupVersion: 5, presentationAction: 'mark_arrived' });
    expect(containedScope.createForCurrentPickup()).toBeDefined();
    await act(async () => evidence.clearFresh(pickupId));
    expect(clear).toHaveBeenCalledWith(pickupId);
    expect(containedScope.currentScope()).toBeUndefined();
    expect(runtime.createMarkArrivedCommandService).not.toHaveBeenCalled();
    await mounted.unmount();
  } finally { publish.mockRestore(); clear.mockRestore(); courierSpy.mockRestore(); }
});

test('provider replacement and Strict Mode retain one contained MARK_ARRIVED lifetime without eager service authority', async () => {
  const retain = jest.spyOn(CourierMarkArrivedCommandScope.prototype, 'retainProviderLifetime');
  const release = jest.spyOn(CourierMarkArrivedCommandScope.prototype, 'releaseProviderLifetime');
  const courierSpy = jest.spyOn(operational, 'useCourierCommandContext').mockReturnValue(currentCourier());
  try {
    const first = identity();
    const second = identity();
    const mounted = await render(
      <StrictMode><CourierStartTravelCommandInfrastructureProvider identity={first}><TrustedCourierHandoffStatus pickupId={pickupId} /></CourierStartTravelCommandInfrastructureProvider></StrictMode>,
    );
    expect(retain).toHaveBeenCalled();
    await mounted.rerender(
      <StrictMode><CourierStartTravelCommandInfrastructureProvider identity={second}><TrustedCourierHandoffStatus pickupId={pickupId} /></CourierStartTravelCommandInfrastructureProvider></StrictMode>,
    );
    expect(release).toHaveBeenCalled();
    expect(first.createMarkArrivedCommandService).not.toHaveBeenCalled();
    expect(second.createMarkArrivedCommandService).not.toHaveBeenCalled();
    await mounted.unmount();
  } finally { retain.mockRestore(); release.mockRestore(); courierSpy.mockRestore(); }
});
