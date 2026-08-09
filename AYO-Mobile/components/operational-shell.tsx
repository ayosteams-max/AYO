import { Link, Redirect } from 'expo-router';
import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

import { TrustedCourierStartTravelCommandProvider, TrustedMerchantAcknowledgeArrivalProvider, useIdentitySession } from '@/contexts/identity-session';
import { useLanguage } from '@/contexts/language';
import { useOperationalContext } from '@/contexts/operational-context';
import type { OperationalArea } from '@/domain/mobile-context';
import { operationalShellCopy } from '@/localization/operational-shell';
import { TrustedCourierHandoffStatus } from '@/contexts/courier-start-travel-command-scope';
import { MerchantOperationalPickupProvider } from '@/contexts/merchant-operational-pickup';
import { MerchantOperationalOrders } from '@/components/merchant-operational-orders';

export function OperationalShell({ personal }: { personal: ReactNode }) {
  return (
    <TrustedCourierStartTravelCommandProvider>
      <MerchantOperationalPickupProvider>
        <TrustedMerchantAcknowledgeArrivalProvider>
          <OperationalShellContent personal={personal} />
        </TrustedMerchantAcknowledgeArrivalProvider>
      </MerchantOperationalPickupProvider>
    </TrustedCourierStartTravelCommandProvider>
  );
}

function OperationalShellContent({ personal }: { personal: ReactNode }) {
  const session = useIdentitySession();
  const context = useOperationalContext();
  const { locale } = useLanguage();
  const copy = operationalShellCopy[locale];

  if (session.status === 'restoring') return <StatusScreen busy message={copy.loading} />;
  if (session.status !== 'authenticated') return <Redirect href="/auth" />;
  if (context.status === 'loading' || context.status === 'idle') return <StatusScreen busy message={copy.loading} />;
  if (context.chooserVisible || !context.selected) return <Chooser />;

  if (context.selected.kind === 'personal') return <View key={context.selected.key} style={styles.fill}>
    {context.status === 'stale' ? <View style={styles.personalStale}>
      <Text accessibilityLiveRegion="assertive" style={styles.warning}>{copy.stale}</Text>
      <Pressable accessibilityLabel={copy.refresh} accessibilityRole="button" disabled={context.refreshing} onPress={() => void context.refresh()} style={styles.secondaryButton}>
        <Text style={styles.secondaryText}>{context.refreshing ? copy.refreshing : copy.refresh}</Text>
      </Pressable>
    </View> : null}
    {personal}<AreaFooter />
  </View>;
  if (context.selected.kind === 'courier') return <TrustedCourierHandoffStatus key={context.selected.pickupId} pickupId={context.selected.pickupId} />;
  return <View key={context.selected.key} style={styles.fill}>
    <MerchantOperationalOrders merchantId={context.selected.merchantId} merchantName={context.selected.displayName} />
    <AreaFooter />
  </View>;
}

function Chooser() {
  const context = useOperationalContext();
  const { locale } = useLanguage();
  const copy = operationalShellCopy[locale];
  const message = context.status === 'malformed' ? copy.malformed : context.status === 'unavailable' ? copy.unable : context.status === 'empty' ? copy.emptyHelp : undefined;
  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.badge}>{copy.preProduction}</Text>
        <Text style={styles.title}>{context.areas.length ? copy.choose : copy.empty}</Text>
        <Text accessibilityLiveRegion="polite" style={styles.help}>{message ?? copy.chooseHelp}</Text>
        {context.status === 'stale' ? <Text accessibilityLiveRegion="assertive" style={styles.warning}>{copy.stale}</Text> : null}
        <View style={styles.cards}>{context.areas.map((area) => <AreaCard area={area} key={area.key} />)}</View>
        <Pressable accessibilityLabel={copy.refresh} accessibilityRole="button" disabled={context.refreshing} onPress={() => void context.refresh()} style={styles.secondaryButton}>
          <Text style={styles.secondaryText}>{context.refreshing ? copy.refreshing : copy.refresh}</Text>
        </Pressable>
        <Link href="/auth" asChild><Pressable accessibilityLabel={copy.account} accessibilityRole="button" style={styles.accountButton}><Text style={styles.accountText}>{copy.account}</Text></Pressable></Link>
      </ScrollView>
    </SafeAreaView>
  );
}

function AreaCard({ area }: { area: OperationalArea }) {
  const context = useOperationalContext();
  const { locale } = useLanguage();
  const copy = operationalShellCopy[locale];
  const title = area.kind === 'personal' ? copy.personal : area.kind === 'courier' ? copy.deliveries : area.displayName;
  const state = area.kind === 'merchant' ? copy[area.availability] : copy.available;
  const disabled = !area.enterable || context.status !== 'ready';
  return (
    <Pressable
      accessibilityLabel={`${title}. ${state}`}
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={() => context.selectArea(area.key)}
      style={[styles.card, disabled && styles.cardDisabled]}>
      <Text style={styles.cardTitle}>{title}</Text>
      <Text style={[styles.state, area.kind === 'merchant' && area.availability !== 'available' && styles.restricted]}>{state}</Text>
      {area.kind === 'merchant' && area.availability === 'pending' ? <Text style={styles.cardHelp}>{copy.pendingHelp}</Text> : null}
      {area.kind === 'merchant' && area.availability === 'suspended' ? <Text style={styles.cardHelp}>{copy.suspendedHelp}</Text> : null}
      {area.kind === 'courier' ? <Text style={styles.cardHelp}>{copy.currentPickup}</Text> : null}
    </Pressable>
  );
}

function AreaFooter() {
  const context = useOperationalContext();
  const { locale } = useLanguage();
  const copy = operationalShellCopy[locale];
  return <View style={styles.footer}>
    {context.areas.filter((area) => area.enterable).length > 1 ? <Pressable accessibilityLabel={copy.switchArea} accessibilityRole="button" onPress={context.showChooser} style={styles.secondaryButton}><Text style={styles.secondaryText}>{copy.switchArea}</Text></Pressable> : null}
    <Link href="/auth" asChild><Pressable accessibilityLabel={copy.account} accessibilityRole="button" style={styles.accountButton}><Text style={styles.accountText}>{copy.account}</Text></Pressable></Link>
  </View>;
}

function StatusScreen({ message, busy }: { message: string; busy?: boolean }) {
  return <SafeAreaView style={styles.safe}><View accessibilityLiveRegion="polite" style={styles.status}>{busy ? <ActivityIndicator color="#A78BFA" /> : null}<Text style={styles.help}>{message}</Text></View></SafeAreaView>;
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: '#07111F' }, safe: { flex: 1, backgroundColor: '#07111F' },
  personalStale: { gap: 10, paddingHorizontal: 20, paddingTop: 12 },
  content: { padding: 24, paddingTop: 54, paddingBottom: 44 }, placeholder: { flex: 1, padding: 24, justifyContent: 'center' },
  status: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16, padding: 24 },
  badge: { alignSelf: 'flex-start', color: '#C4B5FD', backgroundColor: '#2E1065', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 20, fontSize: 12, fontWeight: '800', letterSpacing: 0.8, overflow: 'hidden', marginBottom: 20 },
  title: { color: '#FFFFFF', fontSize: 30, fontWeight: '800', marginBottom: 10 }, help: { color: '#B8C4D2', fontSize: 16, lineHeight: 24 },
  warning: { color: '#FDE68A', backgroundColor: '#422006', borderRadius: 12, padding: 14, marginTop: 18, fontSize: 15 },
  cards: { gap: 12, marginTop: 28, marginBottom: 24 }, card: { minHeight: 92, padding: 18, borderRadius: 18, backgroundColor: '#151F31', borderWidth: 1, borderColor: '#7C3AED', justifyContent: 'center' },
  cardDisabled: { borderColor: '#374151', opacity: 0.78 }, cardTitle: { color: '#FFFFFF', fontSize: 18, fontWeight: '800', marginBottom: 6 },
  state: { color: '#86EFAC', fontSize: 14, fontWeight: '700' }, restricted: { color: '#FCA5A5' }, cardHelp: { color: '#AAB7C6', fontSize: 14, lineHeight: 20, marginTop: 6 },
  secondaryButton: { minHeight: 48, borderRadius: 14, borderWidth: 1, borderColor: '#7C3AED', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18 },
  secondaryText: { color: '#DDD6FE', fontSize: 16, fontWeight: '800' }, accountButton: { minHeight: 48, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18 }, accountText: { color: '#C7D2FE', fontSize: 16, fontWeight: '700' },
  footer: { gap: 8, padding: 20, backgroundColor: '#07111F' },
});
