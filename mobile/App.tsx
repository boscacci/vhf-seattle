import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Animated,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StatusBar as NativeStatusBar,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import * as Haptics from "expo-haptics";
import { Magnetometer } from "expo-sensors";
import { StatusBar as ExpoStatusBar } from "expo-status-bar";
import Svg, {
  Circle,
  Defs,
  LinearGradient as SvgLinearGradient,
  Line,
  Path,
  Stop,
  Text as SvgText,
} from "react-native-svg";

import {
  AUTH_METHODS,
  COMPASS_ROTATION_RANGE_DEGREES,
  COMPASS_SENSOR_INTERVAL_MS,
  formatHeading,
  magneticStrength,
  nearestCompassHeading,
  preciseHeadingFromMagnetometer,
  type MagneticVector,
} from "./src/compass";
import { topChromeGutter } from "./src/layout";

const initialVector: MagneticVector = { x: 0, y: 1, z: 0 };
const initialHeading = preciseHeadingFromMagnetometer(initialVector);
const COMPASS_UI_REFRESH_INTERVAL_MS = 66;

const compassTicks = Array.from({ length: 24 }, (_, index) => {
  const degrees = index * 15;
  const radians = (degrees - 90) * (Math.PI / 180);
  const outer = 124;
  const inner = index % 3 === 0 ? 104 : 114;
  return {
    degrees,
    x1: 140 + Math.cos(radians) * inner,
    y1: 140 + Math.sin(radians) * inner,
    x2: 140 + Math.cos(radians) * outer,
    y2: 140 + Math.sin(radians) * outer,
    major: index % 3 === 0,
  };
});

export default function App() {
  const { heading, needleRotation, sensorAvailable, vector } = useLiveCompass();
  const [signalPulse, setSignalPulse] = useState(0);
  const strength = useMemo(() => magneticStrength(vector), [vector]);
  const topGutter = useMemo(
    () => topChromeGutter(Platform.OS, NativeStatusBar.currentHeight),
    [],
  );
  const sensorLabel =
    sensorAvailable === null ? "Seeking sensor" : sensorAvailable ? "Compass live" : "Compass demo";

  function pingBridge() {
    setSignalPulse((value) => value + 1);
    Haptics.selectionAsync().catch(() => undefined);
  }

  return (
    <LinearGradient colors={["#041411", "#071f24", "#100f1c"]} style={styles.shell}>
      <ExpoStatusBar backgroundColor="#041411" style="light" translucent />
      <SafeAreaView style={[styles.safeArea, { paddingTop: topGutter }]}>
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          <View style={styles.topBar}>
            <View>
              <Text style={styles.eyebrow}>Elliott Bay</Text>
              <Text style={styles.title}>VHF Mobile</Text>
            </View>
            <View style={styles.versionBadge}>
              <Text style={styles.versionText}>Dev shell</Text>
            </View>
          </View>

          <LinearGradient colors={["#123c36", "#0a272d"]} style={styles.captainPanel}>
            <CaptainHat />
            <View style={styles.captainCopy}>
              <Text style={styles.panelLabel}>Hello world</Text>
              <Text style={styles.panelTitle}>Harbor watch in your hand</Text>
            </View>
          </LinearGradient>

          <View style={styles.compassPanel}>
            <View style={styles.panelHeader}>
              <View>
                <Text style={styles.panelLabel}>Compass</Text>
                <Text style={styles.headingText}>{formatHeading(heading)}</Text>
              </View>
              <View style={styles.liveBadge}>
                <View style={[styles.statusDot, sensorAvailable === false && styles.statusDotMuted]} />
                <Text style={styles.liveBadgeText}>{sensorLabel}</Text>
              </View>
            </View>

            <CompassDial needleRotation={needleRotation} />

            <View style={styles.metricGrid}>
              <Metric label="Magnetic field" value={`${strength.toFixed(1)} uT`} />
              <Metric label="Bearing" value={`${Math.round(heading)} deg`} />
            </View>
          </View>

          <View style={styles.signalRow}>
            <Pressable
              accessibilityRole="button"
              onPress={pingBridge}
              style={({ pressed }) => [styles.signalButton, pressed && styles.signalButtonPressed]}
            >
              <Text style={styles.signalButtonText}>Tap the bridge</Text>
            </Pressable>
            <View style={styles.signalCount}>
              <Text style={styles.signalCountValue}>{signalPulse}</Text>
              <Text style={styles.signalCountLabel}>pulses</Text>
            </View>
          </View>

          <View style={styles.authPanel}>
            <Text style={styles.panelLabel}>Access</Text>
            <View style={styles.authGrid}>
              {AUTH_METHODS.map((method) => (
                <View key={method.id} style={styles.authCard}>
                  <Text style={styles.authLabel}>{method.label}</Text>
                  <Text style={styles.authCaption}>{method.caption}</Text>
                </View>
              ))}
            </View>
          </View>
        </ScrollView>
      </SafeAreaView>
    </LinearGradient>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function CaptainHat() {
  return (
    <Svg width={120} height={92} viewBox="0 0 120 92" accessibilityLabel="Captain hat illustration">
      <Defs>
        <SvgLinearGradient id="hatBand" x1="0" x2="1" y1="0" y2="1">
          <Stop offset="0" stopColor="#f8f2d6" />
          <Stop offset="1" stopColor="#86efe1" />
        </SvgLinearGradient>
      </Defs>
      <Path
        d="M23 47 C28 20 43 8 60 8 C77 8 92 20 97 47 C85 39 74 36 60 36 C46 36 35 39 23 47 Z"
        fill="#f3f4e7"
      />
      <Path d="M19 48 C46 39 74 39 101 48 L93 69 C70 62 50 62 27 69 Z" fill="#0a1718" />
      <Path d="M28 52 C50 46 70 46 92 52 L88 61 C69 56 51 56 32 61 Z" fill="url(#hatBand)" />
      <Circle cx="60" cy="29" r="8" fill="#d6a844" />
      <Path d="M56 29 L60 20 L64 29 L60 37 Z" fill="#071411" opacity={0.72} />
      <Path d="M23 47 C37 39 48 36 60 36 C72 36 83 39 97 47" stroke="#d8f8ef" strokeWidth="3" />
    </Svg>
  );
}

function CompassDial({ needleRotation }: { needleRotation: ReturnType<Animated.Value["interpolate"]> }) {
  return (
    <View style={styles.compassWrap}>
      <Svg width="100%" height="100%" viewBox="0 0 280 280" accessibilityLabel="Compass bearing dial">
        <Defs>
          <SvgLinearGradient id="dial" x1="0" x2="1" y1="0" y2="1">
            <Stop offset="0" stopColor="#103f42" />
            <Stop offset="1" stopColor="#061413" />
          </SvgLinearGradient>
        </Defs>
        <Circle cx="140" cy="140" r="132" fill="url(#dial)" stroke="#3ce8d2" strokeWidth="2" opacity={0.96} />
        <Circle cx="140" cy="140" r="102" fill="#071918" stroke="#244d4b" strokeWidth="1" />
        {compassTicks.map((tick) => (
          <Line
            key={tick.degrees}
            x1={tick.x1}
            y1={tick.y1}
            x2={tick.x2}
            y2={tick.y2}
            stroke={tick.major ? "#f8c660" : "#6fc9c1"}
            strokeLinecap="round"
            strokeWidth={tick.major ? 3 : 1.4}
          />
        ))}
        <SvgText
          x="140"
          y="42"
          fill="#fbfff8"
          fontFamily="System"
          fontSize="24"
          fontWeight="700"
          textAnchor="middle"
        >
          N
        </SvgText>
        <SvgText
          x="140"
          y="252"
          fill="#b0c7c1"
          fontFamily="System"
          fontSize="18"
          fontWeight="700"
          textAnchor="middle"
        >
          S
        </SvgText>
        <SvgText
          x="246"
          y="148"
          fill="#b0c7c1"
          fontFamily="System"
          fontSize="18"
          fontWeight="700"
          textAnchor="middle"
        >
          E
        </SvgText>
        <SvgText
          x="34"
          y="148"
          fill="#b0c7c1"
          fontFamily="System"
          fontSize="18"
          fontWeight="700"
          textAnchor="middle"
        >
          W
        </SvgText>
      </Svg>
      <Animated.View
        pointerEvents="none"
        style={[styles.needleLayer, { transform: [{ rotate: needleRotation }] }]}
      >
        <Svg width="100%" height="100%" viewBox="0 0 280 280" accessibilityLabel="Compass needle">
          <Path d="M140 48 L155 142 L140 131 L125 142 Z" fill="#ff5c7a" />
          <Path d="M140 232 L125 142 L140 151 L155 142 Z" fill="#55f0df" opacity={0.92} />
          <Circle cx="140" cy="140" r="12" fill="#f7f0d1" stroke="#081716" strokeWidth="4" />
        </Svg>
      </Animated.View>
    </View>
  );
}

function useLiveCompass() {
  const [vector, setVector] = useState<MagneticVector>(initialVector);
  const [heading, setHeading] = useState(initialHeading);
  const [sensorAvailable, setSensorAvailable] = useState<boolean | null>(null);
  const rotation = useRef(new Animated.Value(initialHeading)).current;
  const continuousHeading = useRef(initialHeading);
  const lastUiRefresh = useRef(0);

  const needleRotation = useMemo(
    () =>
      rotation.interpolate({
        extrapolate: "extend",
        inputRange: [-COMPASS_ROTATION_RANGE_DEGREES, COMPASS_ROTATION_RANGE_DEGREES],
        outputRange: [`-${COMPASS_ROTATION_RANGE_DEGREES}deg`, `${COMPASS_ROTATION_RANGE_DEGREES}deg`],
      }),
    [rotation],
  );

  const animateNeedleToHeading = useCallback(
    (nextHeading: number) => {
      const targetHeading = nearestCompassHeading(continuousHeading.current, nextHeading);
      continuousHeading.current = targetHeading;
      Animated.spring(rotation, {
        damping: 48,
        mass: 0.42,
        overshootClamping: false,
        restDisplacementThreshold: 0.005,
        restSpeedThreshold: 0.005,
        stiffness: 620,
        toValue: targetHeading,
        useNativeDriver: true,
      }).start();
    },
    [rotation],
  );

  useEffect(() => {
    let mounted = true;
    let subscription: { remove: () => void } | null = null;

    Magnetometer.isAvailableAsync()
      .then((available) => {
        if (!mounted) {
          return;
        }
        setSensorAvailable(available);
        if (!available) {
          return;
        }
        Magnetometer.setUpdateInterval(COMPASS_SENSOR_INTERVAL_MS);
        subscription = Magnetometer.addListener((reading) => {
          const nextHeading = preciseHeadingFromMagnetometer(reading);
          animateNeedleToHeading(nextHeading);

          const now = Date.now();
          if (now - lastUiRefresh.current >= COMPASS_UI_REFRESH_INTERVAL_MS) {
            lastUiRefresh.current = now;
            setVector(reading);
            setHeading(nextHeading);
          }
        });
      })
      .catch(() => {
        if (mounted) {
          setSensorAvailable(false);
        }
      });

    return () => {
      mounted = false;
      subscription?.remove();
    };
  }, [animateNeedleToHeading]);

  return { heading, needleRotation, sensorAvailable, vector };
}

const styles = StyleSheet.create({
  shell: {
    flex: 1,
  },
  safeArea: {
    flex: 1,
  },
  content: {
    gap: 12,
    paddingBottom: 28,
    paddingHorizontal: 18,
    paddingTop: 14,
  },
  topBar: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  eyebrow: {
    color: "#82f4e5",
    fontSize: 13,
    fontWeight: "800",
    letterSpacing: 0,
    textTransform: "uppercase",
  },
  title: {
    color: "#fbfff8",
    fontSize: 32,
    fontWeight: "900",
    letterSpacing: 0,
  },
  versionBadge: {
    backgroundColor: "#143238",
    borderColor: "#356b70",
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 11,
    paddingVertical: 8,
  },
  versionText: {
    color: "#d8fff7",
    fontSize: 13,
    fontWeight: "800",
  },
  captainPanel: {
    alignItems: "center",
    borderColor: "#2b5a56",
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    gap: 14,
    minHeight: 104,
    overflow: "hidden",
    padding: 12,
  },
  captainCopy: {
    flex: 1,
    minWidth: 0,
  },
  panelLabel: {
    color: "#9fb8b2",
    fontSize: 12,
    fontWeight: "900",
    letterSpacing: 0,
    textTransform: "uppercase",
  },
  panelTitle: {
    color: "#fbfff8",
    fontSize: 23,
    fontWeight: "900",
    letterSpacing: 0,
    lineHeight: 27,
    marginTop: 4,
  },
  compassPanel: {
    backgroundColor: "rgba(6, 22, 22, 0.92)",
    borderColor: "#204943",
    borderRadius: 8,
    borderWidth: 1,
    gap: 12,
    padding: 14,
  },
  panelHeader: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
  },
  headingText: {
    color: "#ffffff",
    fontSize: 38,
    fontWeight: "900",
    letterSpacing: 0,
    lineHeight: 46,
  },
  liveBadge: {
    alignItems: "center",
    backgroundColor: "#0d2a2f",
    borderColor: "#21565c",
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  statusDot: {
    backgroundColor: "#18e4c4",
    borderRadius: 5,
    height: 10,
    width: 10,
  },
  statusDotMuted: {
    backgroundColor: "#f3b95d",
  },
  liveBadgeText: {
    color: "#dcfff9",
    fontSize: 12,
    fontWeight: "800",
  },
  compassWrap: {
    alignSelf: "center",
    aspectRatio: 1,
    maxWidth: 252,
    position: "relative",
    width: "100%",
  },
  needleLayer: {
    ...StyleSheet.absoluteFillObject,
  },
  metricGrid: {
    flexDirection: "row",
    gap: 10,
  },
  metricCard: {
    backgroundColor: "#0e2427",
    borderColor: "#24484b",
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    gap: 4,
    padding: 10,
  },
  metricLabel: {
    color: "#99b0ab",
    fontSize: 12,
    fontWeight: "800",
  },
  metricValue: {
    color: "#fbfff8",
    fontSize: 20,
    fontWeight: "900",
  },
  signalRow: {
    alignItems: "stretch",
    flexDirection: "row",
    gap: 10,
  },
  signalButton: {
    alignItems: "center",
    backgroundColor: "#13dec0",
    borderRadius: 8,
    flex: 1,
    justifyContent: "center",
    minHeight: 58,
    paddingHorizontal: 16,
  },
  signalButtonPressed: {
    backgroundColor: "#8dffec",
  },
  signalButtonText: {
    color: "#031514",
    fontSize: 19,
    fontWeight: "900",
  },
  signalCount: {
    alignItems: "center",
    backgroundColor: "#181a2a",
    borderColor: "#37345b",
    borderRadius: 8,
    borderWidth: 1,
    justifyContent: "center",
    minWidth: 86,
  },
  signalCountValue: {
    color: "#ffd36d",
    fontSize: 23,
    fontWeight: "900",
  },
  signalCountLabel: {
    color: "#bdb6d4",
    fontSize: 12,
    fontWeight: "800",
  },
  authPanel: {
    backgroundColor: "rgba(10, 25, 26, 0.9)",
    borderColor: "#254542",
    borderRadius: 8,
    borderWidth: 1,
    gap: 12,
    padding: 14,
  },
  authGrid: {
    flexDirection: "row",
    gap: 8,
  },
  authCard: {
    backgroundColor: "#111d2a",
    borderColor: "#2e4660",
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    minHeight: 74,
    padding: 10,
  },
  authLabel: {
    color: "#f4fbff",
    fontSize: 15,
    fontWeight: "900",
  },
  authCaption: {
    color: "#a9bfd2",
    fontSize: 12,
    fontWeight: "800",
    marginTop: 6,
  },
});
