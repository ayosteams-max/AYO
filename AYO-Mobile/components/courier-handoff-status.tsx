import { Link } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

import { useAuthenticatedRead } from '@/contexts/identity-session';
import { useLanguage } from '@/contexts/language';
import { useOperationalContext } from '@/contexts/operational-context';
import { CourierHandoffConflictError, CourierHandoffContractError, type CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import { courierHandoffCopy, guidanceKey } from '@/localization/courier-handoff-status';
import { CourierHandoffStatusService } from '@/services/courier-handoff-status';

type ViewStatus = 'loading' | 'fresh' | 'stale' | 'unavailable' | 'malformed' | 'conflicting';

export function CourierHandoffStatus({ pickupId }: { pickupId: string }) {
  const read = useAuthenticatedRead();
  const operational = useOperationalContext();
  const { locale } = useLanguage();
  const copy = courierHandoffCopy[locale];
  const service = useMemo(() => new CourierHandoffStatusService(read), [read]);
  const [viewStatus, setViewStatus] = useState<ViewStatus>('loading');
  const [snapshot, setSnapshot] = useState<CourierHandoffSnapshot>();
  const [refreshing, setRefreshing] = useState(false);
  const generation = useRef(0);
  const request = useRef<Promise<void> | undefined>(undefined);
  const controller = useRef<AbortController | undefined>(undefined);
  const snapshotRef = useRef<CourierHandoffSnapshot | undefined>(undefined);

  useEffect(() => { snapshotRef.current = snapshot; }, [snapshot]);
  const refresh = useCallback(() => {
    if (request.current) return request.current;
    const current = generation.current;
    const abort = new AbortController(); controller.current = abort;
    setRefreshing(true); if (!snapshotRef.current) setViewStatus('loading');
    const operation = service.load(pickupId, abort.signal).then((next) => {
      if (current !== generation.current || abort.signal.aborted) return;
      snapshotRef.current = next; setSnapshot(next); setViewStatus('fresh');
    }).catch((error: unknown) => {
      if (current !== generation.current || abort.signal.aborted) return;
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
  }, [pickupId, service]);

  useEffect(() => {
    generation.current += 1; controller.current?.abort(); request.current = undefined; snapshotRef.current = undefined; setSnapshot(undefined); setViewStatus('loading'); setRefreshing(false); void refresh();
    return () => { generation.current += 1; controller.current?.abort(); };
  }, [pickupId, refresh]);

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
    <Pressable accessibilityLabel={copy.refresh} accessibilityRole="button" disabled={refreshing} onPress={() => void refresh()} style={styles.button}><Text style={styles.buttonText}>{refreshing ? copy.refreshing : copy.refresh}</Text></Pressable>
    <Pressable accessibilityLabel={copy.returnAreas} accessibilityRole="button" onPress={operational.showChooser} style={styles.secondary}><Text style={styles.secondaryText}>{copy.returnAreas}</Text></Pressable>
    <Link href="/auth" asChild><Pressable accessibilityLabel={copy.account} accessibilityRole="button" style={styles.secondary}><Text style={styles.secondaryText}>{copy.account}</Text></Pressable></Link>
  </ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#07111F' }, content: { flexGrow: 1, padding: 24, paddingTop: 54, paddingBottom: 44 },
  badge: { alignSelf: 'flex-start', color: '#C4B5FD', backgroundColor: '#2E1065', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 20, fontSize: 12, fontWeight: '800', letterSpacing: 0.8, overflow: 'hidden', marginBottom: 20 },
  title: { color: '#FFFFFF', fontSize: 30, fontWeight: '800', marginBottom: 18 }, status: { gap: 14, alignItems: 'center', paddingVertical: 32 },
  card: { minHeight: 150, padding: 22, borderRadius: 20, backgroundColor: '#151F31', borderWidth: 1, borderColor: '#7C3AED', justifyContent: 'center', gap: 12, marginBottom: 18 },
  state: { color: '#FFFFFF', fontSize: 22, fontWeight: '800' }, help: { color: '#B8C4D2', fontSize: 16, lineHeight: 24 },
  warning: { color: '#FDE68A', backgroundColor: '#422006', borderRadius: 12, padding: 14, marginBottom: 16, fontSize: 15 },
  button: { minHeight: 52, borderRadius: 14, backgroundColor: '#7C3AED', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18, marginTop: 'auto' },
  buttonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '800' }, secondary: { minHeight: 48, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18 }, secondaryText: { color: '#C7D2FE', fontSize: 16, fontWeight: '700' },
});
