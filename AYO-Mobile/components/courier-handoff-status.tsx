import { Link } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

import { useAuthenticatedRead } from '@/contexts/identity-session';
import { useLanguage } from '@/contexts/language';
import { useOperationalContext } from '@/contexts/operational-context';
import { CourierHandoffConflictError, CourierHandoffContractError, CourierHandoffNoLongerCurrentError, type CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import { courierHandoffCopy, guidanceKey, type CourierHandoffCopy } from '@/localization/courier-handoff-status';
import { CourierHandoffStatusService } from '@/services/courier-handoff-status';
import type { StartTravelPresentationCommand } from '@/contexts/courier-start-travel-command-scope';

type ViewStatus = 'loading' | 'fresh' | 'stale' | 'unavailable' | 'malformed' | 'conflicting';
type StartTravelEvidenceIntegration = Readonly<{
  publishFresh(pickupId: string, snapshot: CourierHandoffSnapshot, explicitRecovery: boolean): void;
  clearFresh(pickupId: string): void;
}>;
type StartTravelResult = Awaited<ReturnType<StartTravelPresentationCommand['startTravel']>>;
type CommandPending = 'start' | 'reconcile';

export function CourierHandoffStatus({ pickupId, commandEvidence, startTravelCommand }: { pickupId: string; commandEvidence: StartTravelEvidenceIntegration; startTravelCommand: StartTravelPresentationCommand }) {
  const read = useAuthenticatedRead();
  const operational = useOperationalContext();
  const invalidateCourier = operational.invalidateCourier;
  const { locale } = useLanguage();
  const copy = courierHandoffCopy[locale];
  const service = useMemo(() => new CourierHandoffStatusService(read), [read]);
  const [viewStatus, setViewStatus] = useState<ViewStatus>('loading');
  const [snapshot, setSnapshot] = useState<CourierHandoffSnapshot>();
  const [refreshing, setRefreshing] = useState(false);
  const [commandPending, setCommandPending] = useState(false);
  const generation = useRef(0);
  const request = useRef<Promise<void> | undefined>(undefined);
  const controller = useRef<AbortController | undefined>(undefined);
  const snapshotRef = useRef<CourierHandoffSnapshot | undefined>(undefined);
  const commandPendingRef = useRef(false);

  useEffect(() => { snapshotRef.current = snapshot; }, [snapshot]);
  const refresh = useCallback((explicitRecovery = true) => {
    if (commandPendingRef.current) return Promise.resolve();
    if (request.current) return request.current;
    const current = generation.current;
    const abort = new AbortController(); controller.current = abort;
    setRefreshing(true); if (!snapshotRef.current) setViewStatus('loading');
    const operation = service.load(pickupId, abort.signal).then((next) => {
      if (current !== generation.current || abort.signal.aborted) return;
      commandEvidence.publishFresh(pickupId, next, explicitRecovery);
      snapshotRef.current = next; setSnapshot(next); setViewStatus('fresh');
    }).catch((error: unknown) => {
      if (current !== generation.current || abort.signal.aborted) return;
      commandEvidence.clearFresh(pickupId);
      if (error instanceof CourierHandoffNoLongerCurrentError) {
        snapshotRef.current = undefined; setSnapshot(undefined); invalidateCourier(pickupId); return;
      }
      if (snapshotRef.current) setViewStatus('stale');
      else if (error instanceof CourierHandoffConflictError) setViewStatus('conflicting');
      else if (error instanceof CourierHandoffContractError) setViewStatus('malformed');
      else setViewStatus('unavailable');
    }).finally(() => {
      if (request.current === operation) request.current = undefined;
      if (controller.current === abort) controller.current = undefined;
      if (current === generation.current) setRefreshing(false);
    });
    request.current = operation; return operation;
  }, [commandEvidence, invalidateCourier, pickupId, service]);

  const beginCommandInteraction = useCallback(() => {
    if (commandPendingRef.current) return undefined;
    commandPendingRef.current = true;
    generation.current += 1;
    controller.current?.abort();
    controller.current = undefined;
    request.current = undefined;
    setRefreshing(false);
    setCommandPending(true);
    let ended = false;
    return () => {
      if (ended) return;
      ended = true;
      commandPendingRef.current = false;
      setCommandPending(false);
    };
  }, []);

  useEffect(() => {
    generation.current += 1; controller.current?.abort(); request.current = undefined; commandEvidence.clearFresh(pickupId); snapshotRef.current = undefined; setSnapshot(undefined); setViewStatus('loading'); setRefreshing(false); void refresh(false);
    return () => { generation.current += 1; controller.current?.abort(); commandEvidence.clearFresh(pickupId); };
  }, [commandEvidence, pickupId, refresh]);

  useEffect(() => {
    if (operational.status !== 'ready') commandEvidence.clearFresh(pickupId);
  }, [commandEvidence, operational.status, pickupId]);

  const stale = viewStatus === 'stale' || operational.status === 'stale';
  const errorMessage = viewStatus === 'malformed' ? copy.malformed : viewStatus === 'conflicting' ? copy.conflicting : viewStatus === 'unavailable' ? copy.unavailable : undefined;
  return <SafeAreaView style={styles.safe}><ScrollView contentContainerStyle={styles.content}>
    <Text style={styles.badge}>{copy.preProduction}</Text>
    <Text accessibilityRole="header" style={styles.title}>{copy.title}</Text>
    {viewStatus === 'loading' ? <View accessibilityLiveRegion="polite" style={styles.status}><ActivityIndicator color="#A78BFA"/><Text style={styles.help}>{copy.loading}</Text></View> : null}
    {snapshot ? <View style={styles.card}>
      <Text accessibilityLiveRegion="polite" style={styles.state}>{copy[snapshot.status]}</Text>
      <Text style={styles.help}>{copy[guidanceKey(snapshot.status)]}</Text>
    </View> : null}
    {stale ? <Text accessibilityLiveRegion="assertive" style={styles.warning}>{copy.stale}</Text> : null}
    {errorMessage ? <Text accessibilityLiveRegion="assertive" style={styles.warning}>{errorMessage}</Text> : null}
    <CourierStartTravelAction beginCommandInteraction={beginCommandInteraction} key={pickupId} command={startTravelCommand} copy={copy} operationalReady={operational.status === 'ready'} refreshing={refreshing || commandPending} snapshot={snapshot} viewStatus={viewStatus} />
    <Pressable accessibilityLabel={copy.refresh} accessibilityRole="button" accessibilityState={{ disabled: refreshing || commandPending }} disabled={refreshing || commandPending} onPress={() => void refresh()} style={styles.refreshButton}><Text style={styles.secondaryText}>{refreshing ? copy.refreshing : copy.refresh}</Text></Pressable>
    <Pressable accessibilityLabel={copy.returnAreas} accessibilityRole="button" onPress={operational.showChooser} style={styles.secondary}><Text style={styles.secondaryText}>{copy.returnAreas}</Text></Pressable>
    <Link href="/auth" asChild><Pressable accessibilityLabel={copy.account} accessibilityRole="button" style={styles.secondary}><Text style={styles.secondaryText}>{copy.account}</Text></Pressable></Link>
  </ScrollView></SafeAreaView>;
}

export function CourierStartTravelAction({ beginCommandInteraction, command, copy, operationalReady, refreshing, snapshot, viewStatus }: {
  beginCommandInteraction: () => (() => void) | undefined;
  command: StartTravelPresentationCommand;
  copy: CourierHandoffCopy;
  operationalReady: boolean;
  refreshing: boolean;
  snapshot?: CourierHandoffSnapshot;
  viewStatus: ViewStatus;
}) {
  const [pending, setPending] = useState<CommandPending>();
  const [result, setResult] = useState<StartTravelResult>();
  const [localFailure, setLocalFailure] = useState(false);
  const busy = useRef(false);
  const freshActionEvidence = operationalReady && viewStatus === 'fresh' && !refreshing && snapshot?.presentationAction === 'start_travel';
  const actionable = freshActionEvidence && !pending && command.canStartTravel();
  const ambiguous = result?.outcome === 'outcome_unknown';
  const retryReady = result?.outcome === 'retry_same_attempt';
  const terminalApplied = result?.outcome === 'applied';
  const unavailable = result?.outcome === 'invalidated';
  const rejected = result?.outcome === 'rejected';
  const malformed = rejected && result.reason === 'malformed_response';
  const remountRecovery = freshActionEvidence && !pending && result === undefined && !command.canStartTravel();
  const showCheckStatus = !pending && (ambiguous || remountRecovery);
  const showRetry = retryReady && actionable;
  const showStart = actionable && !retryReady;

  const invoke = useCallback(async (kind: CommandPending) => {
    if (busy.current) return;
    const endCommandInteraction = beginCommandInteraction();
    if (!endCommandInteraction) return;
    busy.current = true; setPending(kind); setLocalFailure(false);
    try {
      const next = kind === 'start' ? await command.startTravel() : await command.reconcileStartTravel();
      setResult(next);
    } catch {
      setLocalFailure(true);
    } finally {
      busy.current = false; setPending(undefined); endCommandInteraction();
    }
  }, [beginCommandInteraction, command]);

  const message = localFailure || malformed ? copy.genericCommandFailure
    : unavailable ? copy.currentWorkChanged
    : rejected ? copy.refreshRequired
    : retryReady && !showRetry ? copy.currentWorkChanged
    : undefined;
  return <View style={styles.commandArea}>
    {pending ? <View accessibilityLiveRegion="polite" style={styles.commandProgress}><ActivityIndicator color="#A78BFA"/><Text style={styles.help}>{pending === 'start' ? copy.startingTravel : copy.checkingStatus}</Text></View> : null}
    {terminalApplied ? <View accessibilityLiveRegion="polite" style={styles.success}><Text style={styles.commandTitle}>{copy.startConfirmed}</Text><Text style={styles.help}>{copy.startConfirmedHelp}</Text></View> : null}
    {ambiguous ? <View accessibilityLiveRegion="assertive" style={styles.ambiguity}><Text style={styles.commandTitle}>{copy.outcomeUnknown}</Text><Text style={styles.help}>{copy.outcomeUnknownHelp}</Text></View> : null}
    {retryReady && showRetry ? <Text accessibilityLiveRegion="polite" style={styles.recoveryText}>{copy.retryReady}</Text> : null}
    {message && !ambiguous ? <Text accessibilityLiveRegion="polite" style={styles.recoveryText}>{message}</Text> : null}
    {showStart ? <Pressable accessibilityLabel={copy.startTravel} accessibilityRole="button" accessibilityState={{ disabled: false }} onPress={() => void invoke('start')} style={styles.commandButton}><Text style={styles.buttonText}>{copy.startTravel}</Text></Pressable> : null}
    {pending === 'start' ? <Pressable accessibilityLabel={copy.startingTravel} accessibilityRole="button" accessibilityState={{ disabled: true }} disabled style={styles.commandButtonDisabled}><Text style={styles.buttonText}>{copy.startingTravel}</Text></Pressable> : null}
    {showRetry ? <Pressable accessibilityLabel={copy.retryStartTravel} accessibilityRole="button" accessibilityState={{ disabled: false }} onPress={() => void invoke('start')} style={styles.commandButton}><Text style={styles.buttonText}>{copy.retryStartTravel}</Text></Pressable> : null}
    {showCheckStatus ? <Pressable accessibilityLabel={copy.checkStatus} accessibilityRole="button" accessibilityState={{ disabled: false }} onPress={() => void invoke('reconcile')} style={styles.recoveryButton}><Text style={styles.secondaryText}>{copy.checkStatus}</Text></Pressable> : null}
    {pending === 'reconcile' ? <Pressable accessibilityLabel={copy.checkingStatus} accessibilityRole="button" accessibilityState={{ disabled: true }} disabled style={styles.recoveryButtonDisabled}><Text style={styles.secondaryText}>{copy.checkingStatus}</Text></Pressable> : null}
  </View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#07111F' }, content: { flexGrow: 1, padding: 24, paddingTop: 54, paddingBottom: 44 },
  badge: { alignSelf: 'flex-start', color: '#C4B5FD', backgroundColor: '#2E1065', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 20, fontSize: 12, fontWeight: '800', letterSpacing: 0.8, overflow: 'hidden', marginBottom: 20 },
  title: { color: '#FFFFFF', fontSize: 30, fontWeight: '800', marginBottom: 18 }, status: { gap: 14, alignItems: 'center', paddingVertical: 32 },
  card: { minHeight: 150, padding: 22, borderRadius: 20, backgroundColor: '#151F31', borderWidth: 1, borderColor: '#7C3AED', justifyContent: 'center', gap: 12, marginBottom: 18 },
  state: { color: '#FFFFFF', fontSize: 22, fontWeight: '800' }, help: { color: '#B8C4D2', fontSize: 16, lineHeight: 24 },
  warning: { color: '#FDE68A', backgroundColor: '#422006', borderRadius: 12, padding: 14, marginBottom: 16, fontSize: 15 },
  commandArea: { gap: 12, marginBottom: 16 }, commandProgress: { gap: 10, alignItems: 'center', paddingVertical: 12 }, commandTitle: { color: '#FFFFFF', fontSize: 17, fontWeight: '800' },
  success: { gap: 6, padding: 16, borderRadius: 14, backgroundColor: '#12352B', borderWidth: 1, borderColor: '#34D399' }, ambiguity: { gap: 6, padding: 16, borderRadius: 14, backgroundColor: '#302712', borderWidth: 1, borderColor: '#D97706' }, recoveryText: { color: '#DDE6F0', backgroundColor: '#151F31', borderRadius: 12, padding: 14, fontSize: 15, lineHeight: 22 },
  commandButton: { minHeight: 54, borderRadius: 14, backgroundColor: '#7C3AED', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18 }, commandButtonDisabled: { minHeight: 54, borderRadius: 14, backgroundColor: '#4C3A73', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18, opacity: 0.72 },
  recoveryButton: { minHeight: 52, borderRadius: 14, borderWidth: 1, borderColor: '#A78BFA', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18 }, recoveryButtonDisabled: { minHeight: 52, borderRadius: 14, borderWidth: 1, borderColor: '#64748B', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18, opacity: 0.65 },
  refreshButton: { minHeight: 50, borderRadius: 14, borderWidth: 1, borderColor: '#475569', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18, marginTop: 'auto' },
  buttonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '800' }, secondary: { minHeight: 48, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18 }, secondaryText: { color: '#C7D2FE', fontSize: 16, fontWeight: '700' },
});
