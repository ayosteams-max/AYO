import { useState } from "react";
import {
  Alert,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

type RideType = "AYO Go" | "Comfort" | "Premium";

const rideOptions = [
  {
    name: "AYO Go" as RideType,
    description: "Affordable everyday rides",
    eta: "3 min",
    price: "ETB 180",
    icon: "🚕",
  },
  {
    name: "Comfort" as RideType,
    description: "More space and comfort",
    eta: "5 min",
    price: "ETB 260",
    icon: "🚘",
  },
  {
    name: "Premium" as RideType,
    description: "Top-rated drivers and cars",
    eta: "7 min",
    price: "ETB 390",
    icon: "✨",
  },
];

export default function HomeScreen() {
  const [selectedRide, setSelectedRide] = useState<RideType>("AYO Go");

  const selectedOption = rideOptions.find(
    (option) => option.name === selectedRide
  );

  const requestRide = () => {
    Alert.alert(
      "AYO Ride",
      `${selectedRide} selected. Real ride booking will be connected later.`
    );
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.header}>
          <View>
            <Text style={styles.greeting}>Good afternoon 👋</Text>
            <Text style={styles.name}>Where are you going?</Text>
          </View>

          <Pressable style={styles.profileButton}>
            <Text style={styles.profileText}>I</Text>
          </Pressable>
        </View>

        <View style={styles.locationCard}>
          <Pressable style={styles.locationRow}>
            <View style={styles.pickupDot} />

            <View style={styles.locationTextContainer}>
              <Text style={styles.locationLabel}>Pickup</Text>
              <Text style={styles.locationValue}>Your current location</Text>
            </View>

            <Text style={styles.chevron}>›</Text>
          </Pressable>

          <View style={styles.locationDivider} />

          <Pressable style={styles.locationRow}>
            <View style={styles.destinationDot} />

            <View style={styles.locationTextContainer}>
              <Text style={styles.locationLabel}>Destination</Text>
              <Text style={styles.destinationPlaceholder}>
                Where do you want to go?
              </Text>
            </View>

            <Text style={styles.chevron}>›</Text>
          </Pressable>
        </View>

        <Text style={styles.sectionTitle}>Quick places</Text>

        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.quickPlaces}
        >
          <QuickPlace icon="🏠" label="Home" />
          <QuickPlace icon="💼" label="Work" />
          <QuickPlace icon="✈️" label="Airport" />
          <QuickPlace icon="🕘" label="Recent" />
        </ScrollView>

        <View style={styles.promoCard}>
          <View style={styles.promoTextContainer}>
            <Text style={styles.promoTag}>AYO AIRPORT</Text>
            <Text style={styles.promoTitle}>Reliable airport pickup</Text>
            <Text style={styles.promoDescription}>
              Verified drivers, clear pricing and dependable arrival.
            </Text>
          </View>

          <Text style={styles.promoIcon}>✈️</Text>
        </View>

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Choose your ride</Text>
          <Text style={styles.availableText}>Nearby now</Text>
        </View>

        <View style={styles.rideList}>
          {rideOptions.map((option) => {
            const isSelected = option.name === selectedRide;

            return (
              <Pressable
                key={option.name}
                onPress={() => setSelectedRide(option.name)}
                style={[
                  styles.rideCard,
                  isSelected && styles.rideCardSelected,
                ]}
              >
                <View style={styles.rideIconContainer}>
                  <Text style={styles.rideIcon}>{option.icon}</Text>
                </View>

                <View style={styles.rideDetails}>
                  <Text style={styles.rideName}>{option.name}</Text>
                  <Text style={styles.rideDescription}>
                    {option.description}
                  </Text>
                  <Text style={styles.rideEta}>{option.eta} away</Text>
                </View>

                <View style={styles.ridePriceContainer}>
                  <Text style={styles.ridePrice}>{option.price}</Text>
                  <View
                    style={[
                      styles.radioOuter,
                      isSelected && styles.radioOuterSelected,
                    ]}
                  >
                    {isSelected && <View style={styles.radioInner} />}
                  </View>
                </View>
              </Pressable>
            );
          })}
        </View>

        <View style={styles.summaryCard}>
          <View>
            <Text style={styles.summaryLabel}>Estimated fare</Text>
            <Text style={styles.summaryPrice}>{selectedOption?.price}</Text>
          </View>

          <View style={styles.summaryRight}>
            <Text style={styles.summaryLabel}>Driver arrival</Text>
            <Text style={styles.summaryEta}>{selectedOption?.eta}</Text>
          </View>
        </View>

        <Pressable
          onPress={requestRide}
          style={({ pressed }) => [
            styles.requestButton,
            pressed && styles.requestButtonPressed,
          ]}
        >
          <Text style={styles.requestButtonText}>
            Request {selectedRide}
          </Text>
        </Pressable>

        <Text style={styles.footerText}>
          Safe rides. Fair prices. Built for Ethiopia.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function QuickPlace({ icon, label }: { icon: string; label: string }) {
  return (
    <Pressable style={styles.quickPlaceButton}>
      <View style={styles.quickPlaceIcon}>
        <Text style={styles.quickPlaceEmoji}>{icon}</Text>
      </View>

      <Text style={styles.quickPlaceLabel}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#07111F",
  },
  screen: {
    flex: 1,
    backgroundColor: "#07111F",
  },
  content: {
    paddingHorizontal: 20,
    paddingTop: 18,
    paddingBottom: 42,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 24,
  },
  greeting: {
    color: "#8FA3BA",
    fontSize: 15,
    marginBottom: 5,
  },
  name: {
    color: "#FFFFFF",
    fontSize: 27,
    fontWeight: "800",
  },
  profileButton: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: "#12304D",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#1C527D",
  },
  profileText: {
    color: "#FFFFFF",
    fontSize: 18,
    fontWeight: "800",
  },
  locationCard: {
    backgroundColor: "#101D2C",
    borderRadius: 22,
    paddingHorizontal: 18,
    marginBottom: 28,
    borderWidth: 1,
    borderColor: "#1C3045",
  },
  locationRow: {
    minHeight: 82,
    flexDirection: "row",
    alignItems: "center",
  },
  pickupDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: "#26C281",
    marginRight: 16,
  },
  destinationDot: {
    width: 12,
    height: 12,
    borderRadius: 3,
    backgroundColor: "#38BDF8",
    marginRight: 16,
  },
  locationTextContainer: {
    flex: 1,
  },
  locationLabel: {
    color: "#7F92A8",
    fontSize: 12,
    marginBottom: 5,
  },
  locationValue: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "700",
  },
  destinationPlaceholder: {
    color: "#DDE7F1",
    fontSize: 16,
    fontWeight: "700",
  },
  chevron: {
    color: "#8398AE",
    fontSize: 29,
  },
  locationDivider: {
    height: 1,
    backgroundColor: "#22364A",
    marginLeft: 28,
  },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  sectionTitle: {
    color: "#FFFFFF",
    fontSize: 19,
    fontWeight: "800",
    marginBottom: 15,
  },
  availableText: {
    color: "#26C281",
    fontSize: 13,
    fontWeight: "700",
    marginBottom: 15,
  },
  quickPlaces: {
    gap: 12,
    paddingBottom: 27,
  },
  quickPlaceButton: {
    width: 78,
    alignItems: "center",
  },
  quickPlaceIcon: {
    width: 58,
    height: 58,
    borderRadius: 18,
    backgroundColor: "#101D2C",
    borderWidth: 1,
    borderColor: "#20364D",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 9,
  },
  quickPlaceEmoji: {
    fontSize: 24,
  },
  quickPlaceLabel: {
    color: "#C8D4E1",
    fontSize: 13,
    fontWeight: "600",
  },
  promoCard: {
    minHeight: 145,
    borderRadius: 22,
    backgroundColor: "#123B5A",
    padding: 20,
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 29,
    overflow: "hidden",
  },
  promoTextContainer: {
    flex: 1,
    paddingRight: 10,
  },
  promoTag: {
    color: "#65D5FF",
    fontSize: 11,
    fontWeight: "900",
    letterSpacing: 1.2,
    marginBottom: 8,
  },
  promoTitle: {
    color: "#FFFFFF",
    fontSize: 20,
    fontWeight: "800",
    marginBottom: 7,
  },
  promoDescription: {
    color: "#B9CEE0",
    fontSize: 13,
    lineHeight: 19,
  },
  promoIcon: {
    fontSize: 48,
  },
  rideList: {
    gap: 12,
  },
  rideCard: {
    minHeight: 104,
    borderRadius: 20,
    backgroundColor: "#101D2C",
    borderWidth: 1,
    borderColor: "#1D3146",
    padding: 15,
    flexDirection: "row",
    alignItems: "center",
  },
  rideCardSelected: {
    borderColor: "#38BDF8",
    backgroundColor: "#11263A",
  },
  rideIconContainer: {
    width: 58,
    height: 58,
    borderRadius: 17,
    backgroundColor: "#1A2A3B",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 14,
  },
  rideIcon: {
    fontSize: 28,
  },
  rideDetails: {
    flex: 1,
  },
  rideName: {
    color: "#FFFFFF",
    fontSize: 17,
    fontWeight: "800",
    marginBottom: 4,
  },
  rideDescription: {
    color: "#8295AA",
    fontSize: 12,
    marginBottom: 6,
  },
  rideEta: {
    color: "#38BDF8",
    fontSize: 12,
    fontWeight: "700",
  },
  ridePriceContainer: {
    alignItems: "flex-end",
    gap: 15,
  },
  ridePrice: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "800",
  },
  radioOuter: {
    width: 21,
    height: 21,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: "#5B6E82",
    alignItems: "center",
    justifyContent: "center",
  },
  radioOuterSelected: {
    borderColor: "#38BDF8",
  },
  radioInner: {
    width: 11,
    height: 11,
    borderRadius: 6,
    backgroundColor: "#38BDF8",
  },
  summaryCard: {
    backgroundColor: "#0D1927",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "#1B3046",
    padding: 17,
    marginTop: 18,
    marginBottom: 15,
    flexDirection: "row",
    justifyContent: "space-between",
  },
  summaryRight: {
    alignItems: "flex-end",
  },
  summaryLabel: {
    color: "#788DA3",
    fontSize: 12,
    marginBottom: 5,
  },
  summaryPrice: {
    color: "#FFFFFF",
    fontSize: 19,
    fontWeight: "900",
  },
  summaryEta: {
    color: "#26C281",
    fontSize: 17,
    fontWeight: "800",
  },
  requestButton: {
    minHeight: 58,
    borderRadius: 18,
    backgroundColor: "#21A6E5",
    alignItems: "center",
    justifyContent: "center",
  },
  requestButtonPressed: {
    opacity: 0.82,
    transform: [{ scale: 0.99 }],
  },
  requestButtonText: {
    color: "#03121D",
    fontSize: 17,
    fontWeight: "900",
  },
  footerText: {
    color: "#657A91",
    fontSize: 12,
    textAlign: "center",
    marginTop: 16,
  },
});