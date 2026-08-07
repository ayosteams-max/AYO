import { createContext, type PropsWithChildren, useContext, useMemo } from 'react';

import { useIdentityCommandRuntime } from '@/contexts/identity-session';
import { useCourierCommandContext } from '@/contexts/operational-context';
import type { CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import type { StartTravelAttempt } from '@/domain/courier-start-travel-command';
import { CourierStartTravelCommandScope } from '@/services/courier-start-travel-command-scope';

type StartTravelAttemptCapability = Readonly<{ createAttempt(): StartTravelAttempt | undefined }>;
type FreshEvidencePublisher = Readonly<{
  publishFresh(pickupId: string, snapshot: CourierHandoffSnapshot): void;
  clearFresh(pickupId: string): void;
}>;

const CapabilityContext = createContext<StartTravelAttemptCapability | undefined>(undefined);
const EvidenceContext = createContext<FreshEvidencePublisher | undefined>(undefined);

export function CourierStartTravelCommandScopeProvider({ children }: PropsWithChildren) {
  const identity = useIdentityCommandRuntime();
  const courier = useCourierCommandContext();
  const scope = useMemo(() => new CourierStartTravelCommandScope(identity.readIdentity, courier.readCourierContext), [courier.readCourierContext, identity.readIdentity]);
  const capability = useMemo<StartTravelAttemptCapability>(() => ({ createAttempt: () => scope.createForCurrentPickup() }), [scope]);
  const evidence = useMemo<FreshEvidencePublisher>(() => ({
    publishFresh: (pickupId, snapshot) => scope.publishFresh(pickupId, snapshot),
    clearFresh: (pickupId) => scope.clearFresh(pickupId),
  }), [scope]);
  return <CapabilityContext.Provider value={capability}><EvidenceContext.Provider value={evidence}>{children}</EvidenceContext.Provider></CapabilityContext.Provider>;
}

/** Bounded future-facing capability: no session, generation, or raw scope is exposed. */
export function useStartTravelAttemptCapability() {
  const value = useContext(CapabilityContext);
  if (!value) throw new Error('courier_start_travel_scope_provider_required');
  return value;
}

/** Infrastructure-only handoff evidence publication; not a presentation API. */
export function useStartTravelFreshEvidencePublisher() {
  const value = useContext(EvidenceContext);
  if (!value) throw new Error('courier_start_travel_scope_provider_required');
  return value;
}
