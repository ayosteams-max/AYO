import { act, render } from '@testing-library/react-native';
import { StrictMode } from 'react';

import * as commandScopeModule from '@/contexts/courier-start-travel-command-scope';
import {
  CourierStartTravelCommandInfrastructureProvider,
  TrustedCourierHandoffStatus,
} from '@/contexts/courier-start-travel-command-scope';
import type { CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import { CourierMarkArrivedCommandScope } from '@/services/courier-mark-arrived-command-scope';
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
    'useStartTravelCommand',
  ]);
  for (const forbidden of [
    'useTrustedMarkArrivedEvidence', 'publishFresh', 'clearFresh', 'EvidenceContext',
    'MarkArrivedEvidenceContext', 'markArrivedScope', 'markArrivedController',
    'attempt', 'idempotencyKey', 'service', 'SessionManager',
  ]) expect(commandScopeModule).not.toHaveProperty(forbidden);
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
