import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { useAuthenticatedRead, useIdentityContinuity } from '@/contexts/identity-session';
import { useLanguage } from '@/contexts/language';
import { useMerchantAcknowledgeArrivalCapability } from '@/contexts/merchant-acknowledge-arrival-capability';
import { useMerchantOperationalPickup } from '@/contexts/merchant-operational-pickup';
import { recommendMerchantOperationalAction, type MerchantAcknowledgementPresentationStatus } from '@/domain/merchant-operational-intelligence';
import { MerchantOperationalOrderContractError, type MerchantOperationalOrder } from '@/domain/merchant-operational-order';
import { explainMerchantOperationalIntelligence, type MerchantOperationalIntelligenceLanguage } from '@/localization/merchant-operational-intelligence';
import { merchantOperationalOrderCopy } from '@/localization/merchant-operational-orders';
import { PublicApiError } from '@/services/api-foundation';
import type { MerchantAcknowledgeArrivalControllerState } from '@/services/merchant-acknowledge-arrival-controller';
import { MerchantOperationalOrderService } from '@/services/merchant-operational-orders';

type ListState =
  | Readonly<{ status: 'loading' | 'empty' | 'unavailable' | 'malformed' | 'authority_lost' }>
  | Readonly<{ status: 'ready' | 'stale'; orders: readonly MerchantOperationalOrder[] }>;

export function MerchantOperationalOrders({ merchantId, merchantName }: { merchantId: string; merchantName: string }) {
  const read = useAuthenticatedRead();
  const continuityReader = useIdentityContinuity();
  const continuity = continuityReader.readIdentityContinuity();
  const service = useMemo(() => new MerchantOperationalOrderService(read), [read]);
  const pickup = useMerchantOperationalPickup();
  const { locale } = useLanguage();
  const copy = merchantOperationalOrderCopy[locale];
  const [state, setState] = useState<ListState>(Object.freeze({ status: 'loading' }));
  const [selectedOrderId, setSelectedOrderId] = useState<string>();
  const selectedOrderIdRef = useRef<string | undefined>(undefined);
  const generation = useRef(0);
  const abort = useRef<AbortController | undefined>(undefined);
  const pickupRef = useRef(pickup);
  const stateRef = useRef(state);
  pickupRef.current = pickup;
  stateRef.current = state;

  const load = useCallback(async (retain: boolean) => {
    const capturedContinuity = continuity;
    if (!capturedContinuity?.isCurrent()) { selectedOrderIdRef.current = undefined; setSelectedOrderId(undefined); pickup.clearInspection(); setState(Object.freeze({ status: 'authority_lost' })); return; }
    const request = ++generation.current;
    abort.current?.abort();
    const controller = new AbortController(); abort.current = controller;
    const prior = stateRef.current.status === 'ready' || stateRef.current.status === 'stale' ? stateRef.current.orders : undefined;
    setState(retain && prior ? Object.freeze({ status: 'stale', orders: prior }) : Object.freeze({ status: 'loading' }));
    try {
      const orders = await service.list(merchantId, controller.signal);
      if (request !== generation.current || controller.signal.aborted || !capturedContinuity.isCurrent() || continuityReader.readIdentityContinuity() !== capturedContinuity) return;
      setSelectedOrderId((selected) => {
        if (selected && !orders.some((order) => order.orderId === selected)) { selectedOrderIdRef.current = undefined; pickup.clearInspection(); return undefined; }
        return selected;
      });
      setState(orders.length ? Object.freeze({ status: 'ready', orders }) : Object.freeze({ status: 'empty' }));
    } catch (error) {
      if (request !== generation.current || controller.signal.aborted || !capturedContinuity.isCurrent() || continuityReader.readIdentityContinuity() !== capturedContinuity) return;
      if (error instanceof MerchantOperationalOrderContractError) setState(Object.freeze({ status: 'malformed' }));
      else if (error instanceof PublicApiError && (error.status === 401 || error.status === 403 || ['authentication_required', 'session_expired', 'access_denied'].includes(error.kind))) {
        selectedOrderIdRef.current = undefined; setSelectedOrderId(undefined); pickup.clearInspection(); setState(Object.freeze({ status: 'authority_lost' }));
      } else if (retain && prior) setState(Object.freeze({ status: 'stale', orders: prior }));
      else setState(Object.freeze({ status: 'unavailable' }));
    }
  }, [continuity, continuityReader, merchantId, pickup, service]);

  useLayoutEffect(() => {
    generation.current += 1;
    abort.current?.abort();
    selectedOrderIdRef.current = undefined;
    setSelectedOrderId(undefined);
    pickup.clearInspection();
    setState(Object.freeze({ status: 'loading' }));
    void load(false);
  }, [continuity, merchantId]); // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => () => {
    generation.current += 1;
    abort.current?.abort();
    pickupRef.current.clearInspection();
  }, []);

  const select = useCallback((orderId: string) => {
    if (selectedOrderIdRef.current === orderId) return;
    selectedOrderIdRef.current = orderId;
    setSelectedOrderId(orderId);
    void pickup.inspectOrder(orderId);
  }, [pickup]);

  const orders = state.status === 'ready' || state.status === 'stale' ? state.orders : [];
  const selected = orders.find((order) => order.orderId === selectedOrderId);
  return <View style={styles.fill}>
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.badge}>PRE-PRODUCTION</Text>
      <Text style={styles.title}>{merchantName}</Text>
      <Text style={styles.heading}>{copy.heading}</Text>
      <Text style={styles.help}>{copy.help}</Text>
      {state.status === 'loading' ? <View accessibilityLiveRegion="polite" style={styles.status}><ActivityIndicator color="#A78BFA" /><Text style={styles.help}>{copy.loading}</Text></View> : null}
      {state.status === 'empty' ? <Text accessibilityLiveRegion="polite" style={styles.empty}>{copy.empty}</Text> : null}
      {state.status === 'unavailable' || state.status === 'malformed' || state.status === 'authority_lost' ? <Text accessibilityLiveRegion="assertive" style={styles.warning}>{state.status === 'malformed' ? copy.malformed : state.status === 'authority_lost' ? copy.authorityLost : copy.unavailable}</Text> : null}
      {state.status === 'stale' ? <Text accessibilityLiveRegion="polite" style={styles.warning}>{copy.stale}</Text> : null}
      <View style={styles.orders}>{orders.map((order) => {
        const short = order.orderId.slice(0, 8).toUpperCase(); const active = order.orderId === selectedOrderId;
        return <Pressable key={order.orderId} accessibilityLabel={`${copy.orderLabel} ${short}. ${copy[order.state]}`} accessibilityRole="button" accessibilityState={{ selected: active }} onPress={() => select(order.orderId)} style={[styles.order, active && styles.orderSelected]}>
          <Text style={styles.orderTitle}>{copy.orderLabel} {short}</Text><Text style={styles.orderState}>{copy[order.state]}</Text><Text style={styles.meta}>{copy.createdLabel}: {new Date(order.createdAt).toLocaleString(locale)}</Text>
        </Pressable>;
      })}</View>
      {selected ? <SelectedPickup order={selected} /> : null}
      <Pressable accessibilityLabel={copy.refresh} accessibilityRole="button" disabled={state.status === 'loading'} onPress={() => void load(true)} style={styles.refresh}><Text style={styles.refreshText}>{state.status === 'stale' ? copy.refreshing : copy.refresh}</Text></Pressable>
    </ScrollView>
  </View>;
}

function SelectedPickup({ order }: { order: MerchantOperationalOrder }) {
  const pickup = useMerchantOperationalPickup(); const { locale } = useLanguage(); const copy = merchantOperationalOrderCopy[locale];
  const state = pickup.state;
  let message = copy.pickupUnavailable;
  if ((state.status === 'loading' || state.status === 'unavailable' || state.status === 'malformed' || state.status === 'authority_lost') && state.orderId === order.orderId) message = state.status === 'loading' ? copy.pickupLoading : state.status === 'malformed' ? copy.pickupMalformed : state.status === 'authority_lost' ? copy.pickupAuthorityLost : copy.pickupUnavailable;
  if ((state.status === 'ready' || state.status === 'refreshing' || state.status === 'stale') && state.value.orderId === order.orderId) message = state.status === 'stale' || state.status === 'refreshing' ? copy.pickupStale : copy[state.value.pickup.state];
  return <View accessibilityLiveRegion="polite" style={styles.pickup}><Text style={styles.selected}>{copy.selected}</Text><Text style={styles.orderTitle}>{copy.orderLabel} {order.orderId.slice(0, 8).toUpperCase()}</Text><Text style={styles.help}>{message}</Text><MerchantArrivalAcknowledgement /></View>;
}

function MerchantArrivalAcknowledgement() {
  const capability = useMerchantAcknowledgeArrivalCapability();
  const { locale } = useLanguage();
  const copy = merchantOperationalOrderCopy[locale];
  const state = capability.state;
  const canAcknowledge = capability.canAcknowledgeArrival();
  const canReconcile = capability.canReconcileAcknowledgeArrival();
  const intelligence = recommendMerchantOperationalAction({
    acknowledgementStatus: intelligenceStatus(state),
    canAcknowledgeArrival: canAcknowledge,
    canReconcileAcknowledgeArrival: canReconcile,
  });
  const guidance = explainMerchantOperationalIntelligence(intelligence, locale);
  const acknowledge = () => { void capability.acknowledgeArrival().catch(() => undefined); };
  const reconcile = () => { void capability.reconcileAcknowledgeArrival().catch(() => undefined); };

  if (state.status === 'submitting') return <View style={styles.ackStatus}><ActivityIndicator color="#A78BFA" /><IntelligenceGuidance guidance={guidance} /><Pressable accessibilityLabel={copy.acknowledgingArrival} accessibilityRole="button" accessibilityState={{ disabled: true, busy: true }} disabled style={[styles.ackButton, styles.ackButtonDisabled]}><Text style={styles.ackButtonText}>{copy.acknowledgingArrival}</Text></Pressable></View>;
  if (state.status === 'reconciling') return <View style={styles.ackStatus}><ActivityIndicator color="#A78BFA" /><IntelligenceGuidance guidance={guidance} /><Pressable accessibilityLabel={copy.checkingArrivalStatus} accessibilityRole="button" accessibilityState={{ disabled: true, busy: true }} disabled style={[styles.ackButton, styles.ackButtonDisabled]}><Text style={styles.ackButtonText}>{copy.checkingArrivalStatus}</Text></Pressable></View>;
  if (state.status === 'applied') return <IntelligenceGuidance guidance={guidance} />;
  if (state.status === 'outcome_unknown') return <View style={styles.ackStatus}><IntelligenceGuidance guidance={guidance} assertive />{canReconcile ? <Pressable accessibilityLabel={copy.checkArrivalStatus} accessibilityRole="button" onPress={reconcile} style={styles.ackButton}><Text style={styles.ackButtonText}>{copy.checkArrivalStatus}</Text></Pressable> : null}</View>;
  if (state.status === 'retry_same_attempt') return <View style={styles.ackStatus}><IntelligenceGuidance guidance={guidance} />{canAcknowledge ? <Pressable accessibilityLabel={copy.tryArrivalAgain} accessibilityRole="button" onPress={acknowledge} style={styles.ackButton}><Text style={styles.ackButtonText}>{copy.tryArrivalAgain}</Text></Pressable> : null}</View>;
  if (state.status === 'rejected') return <View style={styles.ackStatus}><IntelligenceGuidance guidance={guidance} assertive />{canAcknowledge ? <Pressable accessibilityLabel={copy.tryArrivalAgain} accessibilityRole="button" onPress={acknowledge} style={styles.ackButton}><Text style={styles.ackButtonText}>{copy.tryArrivalAgain}</Text></Pressable> : null}</View>;
  if (state.status === 'invalidated') return null;
  return canAcknowledge ? <View style={styles.ackStatus}><IntelligenceGuidance guidance={guidance} /><Pressable accessibilityLabel={copy.acknowledgeArrival} accessibilityRole="button" onPress={acknowledge} style={styles.ackButton}><Text style={styles.ackButtonText}>{copy.acknowledgeArrival}</Text></Pressable></View> : null;
}

function intelligenceStatus(state: MerchantAcknowledgeArrivalControllerState): MerchantAcknowledgementPresentationStatus {
  switch (state.status) {
    case 'idle': case 'submitting': case 'reconciling': case 'applied': case 'outcome_unknown':
    case 'retry_same_attempt': case 'rejected': case 'invalidated': return state.status;
    default: return unsupportedState(state);
  }
}

function unsupportedState(value: never): MerchantAcknowledgementPresentationStatus {
  void value;
  return '__unsupported__' as MerchantAcknowledgementPresentationStatus;
}

function IntelligenceGuidance({ guidance, assertive = false }: { guidance: MerchantOperationalIntelligenceLanguage; assertive?: boolean }) {
  if (!guidance.visible) return null;
  return <View accessibilityLiveRegion={assertive ? 'assertive' : 'polite'} style={[styles.intelligence, guidance.tone === 'caution' && styles.intelligenceCaution]}>
    <Text style={styles.intelligenceHeadline}>{guidance.headline}</Text><Text style={styles.help}>{guidance.body}</Text>
  </View>;
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: '#07111F' }, content: { padding: 24, paddingTop: 42, paddingBottom: 36 }, badge: { alignSelf: 'flex-start', color: '#C4B5FD', backgroundColor: '#2E1065', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 20, fontSize: 12, fontWeight: '800', marginBottom: 16, overflow: 'hidden' },
  title: { color: '#FFFFFF', fontSize: 28, fontWeight: '800' }, heading: { color: '#DDD6FE', fontSize: 20, fontWeight: '800', marginTop: 8 }, help: { color: '#B8C4D2', fontSize: 15, lineHeight: 22, marginTop: 6 }, status: { flexDirection: 'row', gap: 12, alignItems: 'center', marginTop: 24 }, empty: { color: '#B8C4D2', fontSize: 16, paddingVertical: 28 }, warning: { color: '#FDE68A', backgroundColor: '#422006', borderRadius: 12, padding: 14, marginTop: 18 }, intelligence: { borderRadius: 12, padding: 14, backgroundColor: '#172033' }, intelligenceCaution: { backgroundColor: '#422006' }, intelligenceHeadline: { color: '#FFFFFF', fontSize: 16, fontWeight: '800' },
  orders: { gap: 12, marginTop: 22 }, order: { minHeight: 92, padding: 16, borderRadius: 16, backgroundColor: '#151F31', borderWidth: 1, borderColor: '#334155' }, orderSelected: { borderColor: '#8B5CF6', backgroundColor: '#21183B' }, orderTitle: { color: '#FFFFFF', fontSize: 17, fontWeight: '800' }, orderState: { color: '#C4B5FD', fontSize: 14, fontWeight: '700', marginTop: 5 }, meta: { color: '#94A3B8', fontSize: 12, marginTop: 7 }, pickup: { marginTop: 22, borderRadius: 16, padding: 18, backgroundColor: '#111827', borderWidth: 1, borderColor: '#7C3AED' }, selected: { color: '#A78BFA', fontSize: 12, fontWeight: '800', marginBottom: 6 }, ackStatus: { gap: 10, marginTop: 14 }, ackButton: { minHeight: 48, marginTop: 14, borderRadius: 14, backgroundColor: '#7C3AED', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18 }, ackButtonDisabled: { opacity: 0.65 }, ackButtonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '800' }, ackConfirmed: { color: '#86EFAC', fontSize: 15, fontWeight: '800', marginTop: 14 }, refresh: { minHeight: 48, marginTop: 22, borderRadius: 14, borderWidth: 1, borderColor: '#7C3AED', alignItems: 'center', justifyContent: 'center' }, refreshText: { color: '#DDD6FE', fontSize: 16, fontWeight: '800' },
});
