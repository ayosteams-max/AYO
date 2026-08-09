import { createContext, type PropsWithChildren, useCallback, useContext, useLayoutEffect, useMemo, useRef, useState } from 'react';

import { useAuthenticatedRead, useIdentityContinuity, type IdentityContinuityHandle } from '@/contexts/identity-session';
import { useOperationalContext } from '@/contexts/operational-context';
import { MerchantCourierPickupContractError, parseMerchantCourierPickupIdentifier, type MerchantCourierPickupSnapshot } from '@/domain/merchant-courier-pickup-status';
import { PublicApiError } from '@/services/api-foundation';
import { MerchantCourierPickupStatusService } from '@/services/merchant-courier-pickup-status';

type RetainedPickup = Readonly<{
  merchantId: string;
  orderId: string;
  pickup: MerchantCourierPickupSnapshot;
}>;

export type MerchantOperationalPickupState =
  | Readonly<{ status: 'idle' }>
  | Readonly<{ status: 'loading'; orderId: string }>
  | Readonly<{ status: 'ready'; value: RetainedPickup }>
  | Readonly<{ status: 'refreshing'; value: RetainedPickup }>
  | Readonly<{ status: 'stale'; value: RetainedPickup }>
  | Readonly<{ status: 'unavailable'; orderId: string }>
  | Readonly<{ status: 'malformed'; orderId: string }>
  | Readonly<{ status: 'authority_lost'; orderId: string }>;

export type MerchantOperationalPickupRead = Readonly<{
  state: MerchantOperationalPickupState;
  inspectOrder(orderId: string, signal?: AbortSignal): Promise<MerchantOperationalPickupState>;
  refresh(signal?: AbortSignal): Promise<MerchantOperationalPickupState>;
}>;

export type MerchantPickupOperationContextSnapshot = Readonly<{
  merchantId: string;
  orderId: string;
  pickupId: string;
  pickup: MerchantCourierPickupSnapshot;
  contextGeneration: number;
  identityContinuity: IdentityContinuityHandle;
}>;

export type MerchantPickupOperationContextReader = Readonly<{
  readMerchantPickupOperation(): MerchantPickupOperationContextSnapshot | undefined;
}>;

type Selection = Readonly<{ merchantId: string; identityContinuity: IdentityContinuityHandle }>;
type OperationIdentity = Readonly<{ merchantId: string; orderId: string; pickupId: string; identityContinuity: IdentityContinuityHandle }>;
type Flight = Readonly<{
  merchantId: string;
  orderId: string;
  identityContinuity: IdentityContinuityHandle;
  promise: Promise<MerchantOperationalPickupState>;
}>;

const idle = Object.freeze({ status: 'idle' as const });
const ReadContext = createContext<MerchantOperationalPickupRead | undefined>(undefined);
// Infrastructure-only, read-only boundary. Request ownership, freshness publication,
// context generation mutation, and the trusted writer remain file-private.
const OperationContext = createContext<MerchantPickupOperationContextReader | undefined>(undefined);

function retained(merchantId: string, orderId: string, pickup: MerchantCourierPickupSnapshot): RetainedPickup {
  return Object.freeze({ merchantId, orderId, pickup });
}

function sameOperation(left: OperationIdentity | undefined, right: OperationIdentity): boolean {
  return !!left && left.merchantId === right.merchantId && left.orderId === right.orderId &&
    left.pickupId === right.pickupId && left.identityContinuity === right.identityContinuity;
}

export function MerchantOperationalPickupProvider({ children, service: suppliedService }: PropsWithChildren<{
  service?: Pick<MerchantCourierPickupStatusService, 'load'>;
}>) {
  const operational = useOperationalContext();
  const identity = useIdentityContinuity();
  const authenticatedRead = useAuthenticatedRead();
  const service = useMemo(() => suppliedService ?? new MerchantCourierPickupStatusService(authenticatedRead), [authenticatedRead, suppliedService]);
  const [state, setState] = useState<MerchantOperationalPickupState>(idle);
  const stateRef = useRef<MerchantOperationalPickupState>(idle);
  const selectionRef = useRef<Selection | undefined>(undefined);
  const trustedRef = useRef<MerchantPickupOperationContextSnapshot | undefined>(undefined);
  const lastOperationRef = useRef<OperationIdentity | undefined>(undefined);
  const contextGeneration = useRef(0);
  const requestGeneration = useRef(0);
  const abortRef = useRef<AbortController | undefined>(undefined);
  const flightRef = useRef<Flight | undefined>(undefined);

  const continuity = identity.readIdentityContinuity();
  const selectedMerchant = operational.status === 'ready' && operational.selected?.kind === 'merchant'
    ? operational.selected
    : undefined;
  selectionRef.current = selectedMerchant && continuity?.isCurrent()
    ? Object.freeze({ merchantId: selectedMerchant.merchantId.toLowerCase(), identityContinuity: continuity })
    : undefined;

  const publishState = useCallback((next: MerchantOperationalPickupState) => {
    stateRef.current = next;
    setState(next);
    return next;
  }, []);

  const retire = useCallback((clearOperationIdentity: boolean) => {
    trustedRef.current = undefined;
    if (clearOperationIdentity) lastOperationRef.current = undefined;
  }, []);

  const cancelFlight = useCallback(() => {
    requestGeneration.current += 1;
    abortRef.current?.abort();
    abortRef.current = undefined;
    flightRef.current = undefined;
  }, []);

  const inspectOrder = useCallback((requestedOrderId: string, signal?: AbortSignal): Promise<MerchantOperationalPickupState> => {
    let orderId: string;
    try { orderId = parseMerchantCourierPickupIdentifier(requestedOrderId); }
    catch {
      cancelFlight();
      retire(true);
      return Promise.resolve(publishState(Object.freeze({ status: 'unavailable', orderId: String(requestedOrderId) })));
    }
    const selection = selectionRef.current;
    if (!selection || !selection.identityContinuity.isCurrent()) {
      cancelFlight();
      retire(true);
      return Promise.resolve(publishState(Object.freeze({ status: 'authority_lost', orderId })));
    }
    const existing = flightRef.current;
    if (existing && existing.merchantId === selection.merchantId && existing.orderId === orderId &&
      existing.identityContinuity === selection.identityContinuity) return existing.promise;

    const request = ++requestGeneration.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    if (signal?.aborted) controller.abort();
    else signal?.addEventListener('abort', () => controller.abort(), { once: true });

    const priorState = stateRef.current;
    const prior = (priorState.status === 'ready' || priorState.status === 'refreshing' || priorState.status === 'stale') &&
      priorState.value.merchantId === selection.merchantId && priorState.value.orderId === orderId
      ? priorState.value
      : undefined;
    retire(false);
    publishState(prior
      ? Object.freeze({ status: 'refreshing', value: prior })
      : Object.freeze({ status: 'loading', orderId }));

    const promise = service.load(selection.merchantId, orderId, controller.signal).then((pickup) => {
      const currentSelection = selectionRef.current;
      if (request !== requestGeneration.current) return stateRef.current;
      if (controller.signal.aborted) {
        retire(false);
        return prior
          ? publishState(Object.freeze({ status: 'stale', value: prior }))
          : publishState(Object.freeze({ status: 'unavailable', orderId }));
      }
      if (
        !selection.identityContinuity.isCurrent() || currentSelection?.identityContinuity !== selection.identityContinuity ||
        currentSelection.merchantId !== selection.merchantId) return stateRef.current;
      const operation: OperationIdentity = Object.freeze({
        merchantId: selection.merchantId,
        orderId,
        pickupId: pickup.pickupId,
        identityContinuity: selection.identityContinuity,
      });
      if (!sameOperation(lastOperationRef.current, operation)) contextGeneration.current += 1;
      lastOperationRef.current = operation;
      trustedRef.current = Object.freeze({
        merchantId: operation.merchantId,
        orderId: operation.orderId,
        pickupId: operation.pickupId,
        pickup,
        contextGeneration: contextGeneration.current,
        identityContinuity: operation.identityContinuity,
      });
      return publishState(Object.freeze({ status: 'ready', value: retained(operation.merchantId, orderId, pickup) }));
    }).catch((error: unknown) => {
      if (request !== requestGeneration.current) return stateRef.current;
      if (controller.signal.aborted) {
        retire(false);
        return prior
          ? publishState(Object.freeze({ status: 'stale', value: prior }))
          : publishState(Object.freeze({ status: 'unavailable', orderId }));
      }
      if (error instanceof MerchantCourierPickupContractError) {
        retire(true);
        return publishState(Object.freeze({ status: 'malformed', orderId }));
      }
      if (error instanceof PublicApiError) {
        if (error.status === 401 || error.status === 403 || ['authentication_required', 'session_expired', 'access_denied'].includes(error.kind)) {
          retire(true);
          return publishState(Object.freeze({ status: 'authority_lost', orderId }));
        }
        if (error.status === 404 || error.kind === 'not_found') {
          retire(true);
          return publishState(Object.freeze({ status: 'unavailable', orderId }));
        }
      }
      retire(false);
      return prior
        ? publishState(Object.freeze({ status: 'stale', value: prior }))
        : publishState(Object.freeze({ status: 'unavailable', orderId }));
    }).finally(() => {
      if (flightRef.current?.promise === promise) flightRef.current = undefined;
      if (abortRef.current === controller) abortRef.current = undefined;
    });
    flightRef.current = Object.freeze({
      merchantId: selection.merchantId,
      orderId,
      identityContinuity: selection.identityContinuity,
      promise,
    });
    return promise;
  }, [cancelFlight, publishState, retire, service]);

  const refresh = useCallback((signal?: AbortSignal) => {
    const current = stateRef.current;
    const orderId = current.status === 'ready' || current.status === 'refreshing' || current.status === 'stale'
      ? current.value.orderId
      : undefined;
    return orderId ? inspectOrder(orderId, signal) : Promise.resolve(current);
  }, [inspectOrder]);

  useLayoutEffect(() => {
    const selection = selectionRef.current;
    const trusted = trustedRef.current;
    const flight = flightRef.current;
    const operation = lastOperationRef.current;
    if (!selection ||
      trusted && (trusted.merchantId !== selection.merchantId || trusted.identityContinuity !== selection.identityContinuity) ||
      flight && (flight.merchantId !== selection.merchantId || flight.identityContinuity !== selection.identityContinuity) ||
      operation && (operation.merchantId !== selection.merchantId || operation.identityContinuity !== selection.identityContinuity)) {
      cancelFlight();
      retire(true);
      publishState(idle);
    }
  }, [cancelFlight, continuity, publishState, retire, selectedMerchant?.merchantId]);

  useLayoutEffect(() => () => {
    requestGeneration.current += 1;
    abortRef.current?.abort();
    trustedRef.current = undefined;
    flightRef.current = undefined;
  }, []);

  const read = useMemo<MerchantOperationalPickupRead>(() => Object.freeze({ state, inspectOrder, refresh }), [inspectOrder, refresh, state]);
  const operation = useMemo<MerchantPickupOperationContextReader>(() => Object.freeze({
    readMerchantPickupOperation: () => trustedRef.current,
  }), []);
  return <ReadContext.Provider value={read}><OperationContext.Provider value={operation}>{children}</OperationContext.Provider></ReadContext.Provider>;
}

export function useMerchantOperationalPickup() {
  const value = useContext(ReadContext);
  if (!value) throw new Error('merchant_operational_pickup_provider_required');
  return value;
}

/** Infrastructure-only reader. No request, freshness, or context writer is exposed. */
export function useMerchantPickupOperationContext() {
  const value = useContext(OperationContext);
  if (!value) throw new Error('merchant_operational_pickup_provider_required');
  return value;
}
