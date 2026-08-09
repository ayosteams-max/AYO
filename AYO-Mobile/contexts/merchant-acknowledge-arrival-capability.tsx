import { createContext, type PropsWithChildren, useContext, useLayoutEffect, useMemo, useRef, useState } from 'react';

import { useMerchantOperationalPickup, useMerchantPickupOperationContext } from '@/contexts/merchant-operational-pickup';
import type { MerchantAcknowledgeArrivalCommandService } from '@/services/merchant-acknowledge-arrival-command';
import { MerchantAcknowledgeArrivalCommandScope } from '@/services/merchant-acknowledge-arrival-command-scope';
import {
  MerchantAcknowledgeArrivalController,
  type MerchantAcknowledgeArrivalControllerResult,
  type MerchantAcknowledgeArrivalControllerState,
} from '@/services/merchant-acknowledge-arrival-controller';

type TrustedIdentityCommandRuntime = Readonly<{
  readIdentity(): Readonly<{ identityId: string; sessionId: string; identityGeneration: number }> | undefined;
  createMerchantAcknowledgeArrivalCommandService(
    scope: MerchantAcknowledgeArrivalCommandScope,
  ): Promise<MerchantAcknowledgeArrivalCommandService>;
}>;

export type MerchantAcknowledgeArrivalPresentationCapability = Readonly<{
  state: MerchantAcknowledgeArrivalControllerState;
  canAcknowledgeArrival(): boolean;
  canReconcileAcknowledgeArrival(): boolean;
  acknowledgeArrival(signal?: AbortSignal): Promise<MerchantAcknowledgeArrivalControllerResult>;
  reconcileAcknowledgeArrival(signal?: AbortSignal): Promise<MerchantAcknowledgeArrivalControllerResult>;
}>;

const CapabilityContext = createContext<MerchantAcknowledgeArrivalPresentationCapability | undefined>(undefined);
const idleState = Object.freeze({ status: 'idle' as const });
type Publication = Readonly<{
  merchantId: string;
  orderId: string;
  pickupId: string;
  contextGeneration: number;
  pickupVersion: number;
  identityContinuity: Readonly<{ isCurrent(): boolean }>;
}>;

function samePublication(left: Publication | undefined, right: Publication | undefined) {
  return left === right || !!left && !!right && left.merchantId === right.merchantId &&
    left.orderId === right.orderId && left.pickupId === right.pickupId &&
    left.contextGeneration === right.contextGeneration && left.pickupVersion === right.pickupVersion &&
    left.identityContinuity === right.identityContinuity;
}

/** Stable infrastructure composition. No command writer or custody object escapes this provider. */
export function MerchantAcknowledgeArrivalInfrastructureProvider({
  children,
  identity,
}: PropsWithChildren<{ identity: TrustedIdentityCommandRuntime }>) {
  const readSignal = useMerchantOperationalPickup().state;
  const operationReader = useMerchantPickupOperationContext();
  const readContext = useMemo(() => () => {
    const operation = operationReader.readMerchantPickupOperation();
    if (!operation?.identityContinuity.isCurrent()) return undefined;
    return Object.freeze({
      merchantId: operation.merchantId,
      orderId: operation.orderId,
      pickupId: operation.pickupId,
      contextGeneration: operation.contextGeneration,
      identityContinuity: operation.identityContinuity,
    });
  }, [operationReader]);
  const scope = useMemo(
    () => new MerchantAcknowledgeArrivalCommandScope(identity.readIdentity, readContext),
    [identity.readIdentity, readContext],
  );
  const controller = useMemo(
    () => new MerchantAcknowledgeArrivalController(
      scope,
      () => identity.createMerchantAcknowledgeArrivalCommandService(scope),
    ),
    [identity, scope],
  );
  const [state, setState] = useState<MerchantAcknowledgeArrivalControllerState>(() => controller.state());
  const publicationRef = useRef<Publication | undefined>(undefined);
  const statePublicationRef = useRef<Publication | undefined>(undefined);
  const [publicationGeneration, setPublicationGeneration] = useState(0);

  useLayoutEffect(() => {
    scope.retainProviderLifetime();
    return () => scope.releaseProviderLifetime();
  }, [scope]);

  useLayoutEffect(() => {
    const operation = operationReader.readMerchantPickupOperation();
    let nextPublication: Publication | undefined;
    if (operation?.identityContinuity.isCurrent() &&
      operation.pickup.state === 'arrived_at_merchant' &&
      operation.pickup.presentationAction === 'acknowledge_arrival') {
      scope.publishFresh(operation.merchantId, operation.orderId, operation.pickup);
      nextPublication = Object.freeze({
        merchantId: operation.merchantId,
        orderId: operation.orderId,
        pickupId: operation.pickupId,
        contextGeneration: operation.contextGeneration,
        pickupVersion: operation.pickup.version,
        identityContinuity: operation.identityContinuity,
      });
    } else {
      scope.clearFresh();
    }
    if (!samePublication(publicationRef.current, nextPublication)) {
      publicationRef.current = nextPublication;
      setPublicationGeneration((value) => value + 1);
    }
  }, [operationReader, readSignal, scope]);

  const capability = useMemo<MerchantAcknowledgeArrivalPresentationCapability>(() => {
    const publication = publicationRef.current;
    const publicationIsCurrent = () => publicationRef.current === publication && !!publication?.identityContinuity.isCurrent();
    const invoke = (
      operation: (signal?: AbortSignal) => Promise<MerchantAcknowledgeArrivalControllerResult>,
      operationIsAvailable: () => boolean,
      signal?: AbortSignal,
    ) => {
      if (!publicationIsCurrent()) return Promise.resolve(Object.freeze({ outcome: 'invalidated' as const, reason: 'scope_changed' as const }));
      if (operationIsAvailable()) statePublicationRef.current = publication;
      const pending = operation(signal);
      setState(controller.state());
      const synchronize = () => setState(controller.state());
      void pending.then(synchronize, synchronize);
      return pending;
    };
    return Object.freeze({
      state: samePublication(statePublicationRef.current, publication) ? state : idleState,
      canAcknowledgeArrival: () => publicationIsCurrent() && controller.isAcknowledgeArrivalActionable(),
      canReconcileAcknowledgeArrival: () => publicationIsCurrent() && controller.isReconciliationAvailable(),
      acknowledgeArrival: (signal) => invoke(
        (currentSignal) => controller.acknowledgeArrival(currentSignal),
        () => controller.isAcknowledgeArrivalActionable() || samePublication(statePublicationRef.current, publication),
        signal,
      ),
      reconcileAcknowledgeArrival: (signal) => invoke(
        (currentSignal) => controller.reconcileAcknowledgeArrival(currentSignal),
        () => controller.isReconciliationAvailable() || samePublication(statePublicationRef.current, publication),
        signal,
      ),
    });
  }, [controller, publicationGeneration, state]);

  return <CapabilityContext.Provider value={capability}>{children}</CapabilityContext.Provider>;
}

/** Presentation-safe switch. Command internals and trusted writers remain private. */
export function useMerchantAcknowledgeArrivalCapability() {
  const value = useContext(CapabilityContext);
  if (!value) throw new Error('merchant_acknowledge_arrival_provider_required');
  return value;
}
