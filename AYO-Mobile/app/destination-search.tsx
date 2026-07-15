import { MaterialCommunityIcons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import type { Destination, DestinationCategory } from '@/domain/destination';
import { useDestinationSearch } from '@/hooks/use-destination-search';
import { destinationSearchGateway } from '@/services/destination-search';

const categories: readonly { label: string; value?: DestinationCategory; icon: keyof typeof MaterialCommunityIcons.glyphMap }[] = [
  { label: 'All', icon: 'map-marker-outline' },
  { label: 'Saved', value: 'saved', icon: 'heart-outline' },
  { label: 'Recent', value: 'recent', icon: 'history' },
  { label: 'Airport', value: 'airport', icon: 'airplane' },
];

export default function DestinationSearchScreen() {
  const params = useLocalSearchParams<{ category?: DestinationCategory }>();
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<DestinationCategory | undefined>(params.category);
  const inputRef = useRef<TextInput>(null);
  const state = useDestinationSearch(destinationSearchGateway, query, category);
  const activeLabel = useMemo(() => categories.find((item) => item.value === category)?.label, [category]);

  useEffect(() => {
    const timer = setTimeout(() => inputRef.current?.focus(), 250);
    return () => clearTimeout(timer);
  }, []);

  const selectDestination = (destination: Destination) => {
    router.dismissTo({ pathname: '/(tabs)', params: { destination: destination.name } });
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.header}>
          <Pressable accessibilityLabel="Go back" hitSlop={12} onPress={() => router.back()} style={styles.backButton}>
            <MaterialCommunityIcons name="arrow-left" size={24} color="#FFFFFF" />
          </Pressable>
          <View style={styles.titleBlock}>
            <Text style={styles.eyebrow}>YOUR TRIP</Text>
            <Text style={styles.title}>Choose destination</Text>
          </View>
        </View>

        <View style={styles.searchCard}>
          <View style={styles.routeLine}>
            <View style={styles.pickupDot} />
            <View style={styles.line} />
            <View style={styles.destinationDot} />
          </View>
          <View style={styles.fields}>
            <View style={styles.pickupField}>
              <Text style={styles.fieldLabel}>PICKUP</Text>
              <Text numberOfLines={1} style={styles.pickupText}>Your current location</Text>
            </View>
            <View style={styles.divider} />
            <View style={styles.searchRow}>
              <TextInput
                ref={inputRef}
                accessibilityLabel="Search destination"
                autoCapitalize="words"
                autoCorrect={false}
                clearButtonMode="while-editing"
                onChangeText={setQuery}
                placeholder="Where do you want to go?"
                placeholderTextColor="#71869C"
                returnKeyType="search"
                style={styles.input}
                value={query}
              />
              {query.length > 0 && Platform.OS !== 'ios' ? (
                <Pressable accessibilityLabel="Clear search" hitSlop={10} onPress={() => setQuery('')}>
                  <MaterialCommunityIcons name="close-circle" size={20} color="#71869C" />
                </Pressable>
              ) : null}
            </View>
          </View>
        </View>

        <FlatList
          data={state.results}
          keyExtractor={(item) => item.id}
          keyboardShouldPersistTaps="handled"
          ListHeaderComponent={
            <>
              <FlatList
                horizontal
                data={categories}
                keyExtractor={(item) => item.label}
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.categories}
                renderItem={({ item }) => {
                  const selected = item.value === category;
                  return (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityState={{ selected }}
                      onPress={() => setCategory(item.value)}
                      style={[styles.category, selected && styles.categorySelected]}>
                      <MaterialCommunityIcons name={item.icon} size={18} color={selected ? '#04131E' : '#B7C6D5'} />
                      <Text style={[styles.categoryText, selected && styles.categoryTextSelected]}>{item.label}</Text>
                    </Pressable>
                  );
                }}
              />
              <View style={styles.listHeading}>
                <Text style={styles.listTitle}>{query ? 'Search results' : activeLabel ?? 'Suggested places'}</Text>
                {state.status === 'loading' ? <ActivityIndicator color="#38BDF8" size="small" /> : null}
              </View>
            </>
          }
          ListEmptyComponent={
            state.status === 'ready' ? (
              <View style={styles.emptyState}>
                <MaterialCommunityIcons name="map-search-outline" size={38} color="#4D6680" />
                <Text style={styles.emptyTitle}>No places found</Text>
                <Text style={styles.emptyText}>Try another name or check a different category.</Text>
              </View>
            ) : state.status === 'error' ? (
              <View style={styles.emptyState}>
                <Text style={styles.emptyTitle}>Search is unavailable</Text>
                <Text style={styles.emptyText}>Your saved and recent places remain available when the connection returns.</Text>
              </View>
            ) : null
          }
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => <DestinationRow destination={item} onPress={() => selectDestination(item)} />}
          showsVerticalScrollIndicator={false}
        />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function DestinationRow({ destination, onPress }: { destination: Destination; onPress: () => void }) {
  const icon = destination.category === 'airport' ? 'airplane' : destination.category === 'saved' ? 'heart' : destination.category === 'recent' ? 'history' : 'map-marker';
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.resultRow, pressed && styles.resultPressed]}>
      <View style={styles.resultIcon}><MaterialCommunityIcons name={icon} size={21} color="#55C9F7" /></View>
      <View style={styles.resultText}>
        <Text numberOfLines={1} style={styles.resultName}>{destination.name}</Text>
        <Text numberOfLines={1} style={styles.resultAddress}>{destination.address}</Text>
      </View>
      <MaterialCommunityIcons name="chevron-right" size={22} color="#61768C" />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: '#07111F' },
  screen: { flex: 1, backgroundColor: '#07111F' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, paddingTop: 14, paddingBottom: 20 },
  backButton: { width: 44, height: 44, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: '#101D2C', borderWidth: 1, borderColor: '#20364D' },
  titleBlock: { marginLeft: 14 },
  eyebrow: { color: '#38BDF8', fontSize: 10, fontWeight: '900', letterSpacing: 1.5, marginBottom: 3 },
  title: { color: '#FFFFFF', fontSize: 24, fontWeight: '800' },
  searchCard: { marginHorizontal: 20, paddingHorizontal: 17, borderRadius: 22, backgroundColor: '#101D2C', borderWidth: 1, borderColor: '#244059', flexDirection: 'row' },
  routeLine: { width: 22, alignItems: 'center', paddingVertical: 24 },
  pickupDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#26C281' },
  line: { width: 1, flex: 1, minHeight: 35, backgroundColor: '#345068' },
  destinationDot: { width: 11, height: 11, borderRadius: 3, backgroundColor: '#38BDF8' },
  fields: { flex: 1, marginLeft: 12 },
  pickupField: { minHeight: 66, justifyContent: 'center' },
  fieldLabel: { color: '#70859B', fontSize: 10, fontWeight: '800', letterSpacing: 1, marginBottom: 4 },
  pickupText: { color: '#D9E4EE', fontSize: 15, fontWeight: '600' },
  divider: { height: 1, backgroundColor: '#263B4F' },
  searchRow: { minHeight: 66, flexDirection: 'row', alignItems: 'center' },
  input: { flex: 1, color: '#FFFFFF', fontSize: 16, fontWeight: '700', paddingVertical: 0, paddingRight: 8 },
  categories: { gap: 9, paddingVertical: 24 },
  category: { minHeight: 42, paddingHorizontal: 15, borderRadius: 14, flexDirection: 'row', gap: 7, alignItems: 'center', backgroundColor: '#101D2C', borderWidth: 1, borderColor: '#20364D' },
  categorySelected: { backgroundColor: '#38BDF8', borderColor: '#38BDF8' },
  categoryText: { color: '#B7C6D5', fontSize: 13, fontWeight: '700' },
  categoryTextSelected: { color: '#04131E' },
  listContent: { flexGrow: 1, paddingHorizontal: 20, paddingBottom: 35 },
  listHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  listTitle: { color: '#FFFFFF', fontSize: 18, fontWeight: '800' },
  resultRow: { minHeight: 75, flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#172A3C' },
  resultPressed: { opacity: 0.65 },
  resultIcon: { width: 43, height: 43, borderRadius: 14, backgroundColor: '#10283B', alignItems: 'center', justifyContent: 'center', marginRight: 13 },
  resultText: { flex: 1, marginRight: 8 },
  resultName: { color: '#F5F8FB', fontSize: 15, fontWeight: '700', marginBottom: 5 },
  resultAddress: { color: '#8094A8', fontSize: 13 },
  emptyState: { alignItems: 'center', paddingTop: 55, paddingHorizontal: 28 },
  emptyTitle: { color: '#DDE7F1', fontSize: 17, fontWeight: '800', marginTop: 13, marginBottom: 7 },
  emptyText: { color: '#71869C', fontSize: 13, lineHeight: 19, textAlign: 'center' },
});
