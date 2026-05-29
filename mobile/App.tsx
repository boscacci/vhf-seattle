import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Animated,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  Linking,
  StyleSheet,
  Text,
  View,
  type ViewStyle,
} from "react-native";
import * as AuthSession from "expo-auth-session";
import * as WebBrowser from "expo-web-browser";
import * as Location from "expo-location";
import { StatusBar as NativeStatusBar } from "react-native";
import { StatusBar as ExpoStatusBar } from "expo-status-bar";
import { DeviceMotion, Magnetometer } from "expo-sensors";
import Svg, {
  Circle,
  Defs,
  Ellipse,
  LinearGradient as SvgLinearGradient,
  Line,
  Path,
  Stop,
  Text as SvgText,
} from "react-native-svg";

import {
  COMPASS_NEEDLE_RESPONSE_MS,
  COMPASS_NORTH_NEEDLE_ROTATION_DEGREES,
  COMPASS_ROTATION_RANGE_DEGREES,
  COMPASS_SENSOR_INTERVAL_MS,
  COMPASS_UI_REFRESH_INTERVAL_MS,
  clampedCompassGimbalTilt,
  compassBodyRotationOutputRange,
  formatHeading,
  headingFromDeviceMotionRotation,
  magneticStrength,
  nearestCompassHeading,
  preciseHeadingFromMagnetometer,
  type MagneticVector,
} from "./src/compass";
import {
  authorizeCognitoClaims,
  cognitoDiscovery,
  cognitoLogoutUrl,
  decodeJwtClaims,
  readCognitoAuthConfig,
} from "./src/auth";
import { topChromeGutter } from "./src/layout";

WebBrowser.maybeCompleteAuthSession();

const initialVector: MagneticVector = { x: 0, y: 1, z: 0 };
const initialHeading = preciseHeadingFromMagnetometer(initialVector);
const MAGNETIC_FIELD_REFRESH_INTERVAL_MS = 100;
const fixedNorthNeedleTransform = [
  { rotate: `${COMPASS_NORTH_NEEDLE_ROTATION_DEGREES}deg` },
] as ViewStyle["transform"];
const METERS_TO_FEET = 3.28084;

const MOBILE_API_BASE_URL = (() => {
  const envValue = process.env.EXPO_PUBLIC_MOBILE_API_BASE_URL?.trim();
  return envValue ? envValue.replace(/\/$/, "") : "https://vhf-dev.robertboscacci.com";
})();

type CompassSensorSource = "seeking" | "motion" | "magnetometer" | "demo";

type AdminSession = {
  email: string;
  groups: string[];
  isSuperAdmin: true;
};

type WebFeatureId = "compass" | "cognito" | "clips" | "live-monitor" | "ais-map" | "analysis" | "performance";

type RemoteState<T> = {
  status: "idle" | "loading" | "ready" | "error";
  data: T | null;
  error: string | null;
};

type ClipItem = {
  channel?: string;
  channel_label?: string;
  started_at?: string;
  ended_at?: string;
  duration_seconds?: number | null;
  transcript?: string;
  transcript_public?: string;
  playback_url?: string;
};

type ClipsPayload = {
  clips?: ClipItem[];
  clip_count?: number;
  filtered_clip_count?: number;
  limit?: number;
  offset?: number;
  channel_counts?: Record<string, number>;
  channel_labels?: Record<string, string>;
};

type LiveChannel = {
  channel: string;
  label: string;
  frequencyMhz: string;
  streamPath?: string;
  statusPath?: string;
};

type LiveChannelsPayload = {
  defaultChannel?: string;
  channels?: LiveChannel[];
};

type LiveStatusPayload = {
  activeChannelId?: string;
  channel?: string;
  label?: string;
  frequencyMhz?: string;
  streamDelaySeconds?: { minimum?: number; maximum?: number };
};

type LexicalPayload = {
  status?: string;
  source_clip_count?: number;
  generated_at?: string;
  generatedAt?: string;
  channels?: Record<string, number>;
  frequency?: { by_channel?: Record<string, number> };
  terms?: {
    unigrams?: unknown[];
    semantic_buckets?: Record<string, unknown>;
  };
};

type PublicManifestPayload = {
  generated_at?: string;
  stats?: {
    clip_count?: number;
    channel_counts?: Record<string, number>;
  };
  ais_tracks?: unknown[];
};

type PerformanceHost = {
  role?: string;
  status?: string;
  cpu?: { utilizationPercent?: number; status?: string };
  memory?: { usedPercent?: number; availableBytes?: number; status?: string };
  thermal?: { temperatureC?: number; status?: string };
};

type PerformancePayload = {
  status?: string;
  generatedAt?: string;
  host?: PerformanceHost;
  hosts?: PerformanceHost[];
};

const FEATURE_NAV_ITEMS: Array<{ id: WebFeatureId; label: string; caption: string; detail: string }> = [
  {
    id: "compass",
    label: "Compass",
    caption: "Live steering heading",
    detail: "Primary navigation: magnetic heading, direction status, and field strength.",
  },
  {
    id: "cognito",
    label: "Google federated login",
    caption: "Mobile auth path",
    detail: "OAuth via Cognito hosted UI with admin access gate and super-admin role check.",
  },
  {
    id: "clips",
    label: "Clip Review",
    caption: "Recent receiver clips",
    detail: "Match the web Clip Review tab with latest VHF clip transcripts and playback flow.",
  },
  {
    id: "live-monitor",
    label: "Live Monitor",
    caption: "Live receiver stream",
    detail: "Native hook point for live audio channel status, signal telemetry, and playback controls.",
  },
  {
    id: "ais-map",
    label: "AIS Map",
    caption: "Vessel traffic map",
    detail: "Mobile space for AIS vessel positions and ship-to-ship traffic visibility.",
  },
  {
    id: "analysis",
    label: "Analysis",
    caption: "Lexical analysis",
    detail: "View lexical analysis summaries and topic clusters for recent marine traffic transcripts.",
  },
  {
    id: "performance",
    label: "Performance",
    caption: "Dev operations metrics",
    detail: "System and ingestion health from the live monitoring pipeline.",
  },
];

const COMPASS_VIEWBOX = 260;
const CENTER = COMPASS_VIEWBOX / 2;
const COMPASS_OUTER_RADIUS = 124;
const COMPASS_OUTER_TICK_RADIUS = 124;
const COMPASS_MAJOR_TICK_RADIUS = 102;
const COMPASS_SUB_TICK_RADIUS = 110;
const COMPASS_MINOR_TICK_RADIUS = 116;
const NORTH_LABEL_RADIUS = 118;
const CARDINAL_LABEL_RADIUS = 112;
const FRAME_STUD_RADIUS = 120;
const RAD = Math.PI / 180;
const COMPASS_TICK_COUNT = 72;

const compassTicks = Array.from({ length: COMPASS_TICK_COUNT }, (_, index) => {
  const degrees = index * (360 / COMPASS_TICK_COUNT);
  const radians = (degrees - 90) * RAD;
  const outer = COMPASS_OUTER_TICK_RADIUS;
  const inner =
    index % 12 === 0 ? COMPASS_MAJOR_TICK_RADIUS : index % 3 === 0 ? COMPASS_SUB_TICK_RADIUS : COMPASS_MINOR_TICK_RADIUS;

  return {
    degrees,
    x1: CENTER + Math.cos(radians) * inner,
    y1: CENTER + Math.sin(radians) * inner,
    x2: CENTER + Math.cos(radians) * outer,
    y2: CENTER + Math.sin(radians) * outer,
    major: index % 12 === 0,
  };
});

const northIndicators = [
  { label: "N", degrees: 0, r: NORTH_LABEL_RADIUS, size: 23 },
  { label: "E", degrees: 90, r: CARDINAL_LABEL_RADIUS, size: 15 },
  { label: "S", degrees: 180, r: CARDINAL_LABEL_RADIUS, size: 15 },
  { label: "W", degrees: 270, r: CARDINAL_LABEL_RADIUS, size: 15 },
];

const frameStuds = Array.from({ length: 24 }, (_, index) => {
  const degrees = index * (360 / 24);
  const radians = (degrees - 90) * RAD;
  return {
    cx: CENTER + Math.cos(radians) * FRAME_STUD_RADIUS,
    cy: CENTER + Math.sin(radians) * FRAME_STUD_RADIUS,
    r: (index % 2) * 2.4 + 2.2,
  };
});

export default function App() {
  const adminAuth = useCognitoAdminAuth();
  const {
    compassBodyTransform,
    heading,
    sensorSource,
    vector,
  } = useLiveCompass();
  const gpsAltitudeFeet = useGpsAltitudeFeet();
  const [activeFeatureId, setActiveFeatureId] = useState<WebFeatureId>("compass");
  const strength = useMemo(() => magneticStrength(vector), [vector]);
  const topGutter = useMemo(
    () => topChromeGutter(Platform.OS, NativeStatusBar.currentHeight),
    [],
  );
  const sensorLabel = compassSensorLabel(sensorSource);

  return (
    <View style={styles.shell}>
      <ExpoStatusBar backgroundColor="#041411" style="light" translucent />
      <SafeAreaView style={[styles.safeArea, { paddingTop: topGutter }]}>
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          <View style={styles.titleSection}>
            <Text style={styles.title}>Steampunk Compass</Text>
            <Text style={styles.subtitle}>Welcome back, Captain.</Text>
          </View>

          <View style={styles.compassPanel}>
            <View style={styles.panelHeader}>
              <View>
                <Text style={styles.panelLabel}>Compass</Text>
                <Text style={styles.headingText}>{formatHeading(heading)}</Text>
              </View>
              <View style={styles.liveBadge}>
                <View
                  style={[styles.statusDot, sensorSource === "demo" && styles.statusDotMuted]}
                />
                <Text style={styles.liveBadgeText}>{sensorLabel}</Text>
              </View>
            </View>

            <CompassDial compassBodyTransform={compassBodyTransform} />

            <View style={styles.metricGrid}>
              <Metric label="Magnetic field" value={`${strength.toFixed(1)} uT`} />
              <Metric label="Elevation" value={formatAltitudeFeet(gpsAltitudeFeet)} />
            </View>
          </View>
          <FeaturePanel
            activeFeatureId={activeFeatureId}
            setActiveFeatureId={setActiveFeatureId}
            adminAuth={adminAuth}
          />
        </ScrollView>
      </SafeAreaView>
    </View>
  );
}

function FeaturePanel({
  activeFeatureId,
  setActiveFeatureId,
  adminAuth,
}: {
  activeFeatureId: WebFeatureId;
  setActiveFeatureId: (featureId: WebFeatureId) => void;
  adminAuth: ReturnType<typeof useCognitoAdminAuth>;
}) {
  return (
    <View style={styles.featurePanel}>
      <Text style={styles.panelLabel}>Features</Text>
      <View style={styles.featureTabs}>
        {FEATURE_NAV_ITEMS.map((feature) => (
          <Pressable
            key={feature.id}
            accessibilityRole="button"
            accessibilityLabel={`Open ${feature.label}`}
            onPress={() => setActiveFeatureId(feature.id)}
            style={({ pressed }) => [
              styles.featureTab,
              activeFeatureId === feature.id && styles.featureTabActive,
              pressed && styles.featureTabPressed,
            ]}
          >
            <Text style={styles.featureLabel}>{feature.label}</Text>
          </Pressable>
        ))}
      </View>
      <View>
        {activeFeatureId === "compass" && <CompassFeature />}
        {activeFeatureId === "cognito" && <AuthPanel adminAuth={adminAuth} />}
        {activeFeatureId === "clips" && <ClipReviewFeature />}
        {activeFeatureId === "live-monitor" && <LiveMonitorFeature />}
        {activeFeatureId === "ais-map" && <AisMapFeature />}
        {activeFeatureId === "analysis" && <AnalysisFeature />}
        {activeFeatureId === "performance" && <PerformanceFeature />}
      </View>
    </View>
  );
}

function CompassFeature() {
  return (
    <FeatureStatus
      title="Compass"
      message="Magnetic compass with live heading and sea-level elevation from GPS."
    />
  );
}

function activeFeatureText(id: WebFeatureId): string {
  const item = FEATURE_NAV_ITEMS.find((feature) => feature.id === id);
  return item?.detail || "";
}

function FeatureStatus({
  title,
  message,
  isError = false,
}: {
  title: string;
  message: string;
  isError?: boolean;
}) {
  return (
    <View>
      <Text style={styles.featureSectionTitle}>{title}</Text>
      <Text style={[styles.featureSectionBody, isError && styles.featureError]}>{message}</Text>
    </View>
  );
}

function ClipReviewFeature() {
  const state = useJsonData<ClipsPayload>(`${MOBILE_API_BASE_URL}/api/clips/recent?limit=6`);

  if (state.status === "loading") {
    return <FeatureStatus title="Clip review" message="Loading latest clips..." />;
  }
  if (state.status === "error") {
    return <FeatureStatus title="Clip review" message={`Unable to load clips: ${state.error}`} isError />;
  }

  const payload = state.data || {};
  const clips = Array.isArray(payload.clips) ? payload.clips : [];

  return (
    <View>
      <Text style={styles.featureSectionTitle}>Clip review</Text>
      <View style={styles.metricGrid}>
        <Metric label="Total" value={`${payload.clip_count ?? clips.length}`} />
        <Metric label="Filtered" value={`${payload.filtered_clip_count ?? clips.length}`} />
      </View>
      {payload.channel_counts && Object.keys(payload.channel_counts).length > 0 ? (
        <Text style={styles.featureSectionBody}>
          Channels:{" "}
          {Object.entries(payload.channel_counts)
            .map(([channel, count]) => `VHF ${channel} (${count})`)
            .join(", ")}
        </Text>
      ) : null}
      {clips.length === 0 ? (
        <Text style={styles.featureSectionBody}>No recent clips to display.</Text>
      ) : (
        <View style={styles.listBlock}>
          {clips.map((clip, index) => (
            <ClipListItem
              key={`${clip.playback_url || clip.started_at || clip.channel || "clip"}-${index}`}
              clip={clip}
            />
          ))}
        </View>
      )}
    </View>
  );
}

function ClipListItem({ clip }: { clip: ClipItem }) {
  const started = formatDateTime(clip.started_at);
  const duration = formatDuration(clip.duration_seconds);
  const channel = clip.channel ? `VHF ${clip.channel}` : "VHF";
  const channelLabel = clip.channel_label ? ` • ${clip.channel_label}` : "";
  const transcript = clip.transcript || clip.transcript_public || "";

  return (
    <View style={styles.listItem}>
      <Text style={styles.listTitle}>
        {channel}
        {channelLabel}
      </Text>
      <Text style={styles.listMeta}>
        {started} • {duration}
      </Text>
      {transcript ? <Text style={styles.listBody}>{transcript.slice(0, 220)}</Text> : null}
      {clip.playback_url ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Open clip ${channel}`}
          onPress={() => openExternalUrl(clip.playback_url || "")}
          style={styles.actionLink}
        >
          <Text style={styles.actionLinkText}>Open clip</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function LiveMonitorFeature() {
  const channelState = useJsonData<LiveChannelsPayload>(`${MOBILE_API_BASE_URL}/api/live/channels`);
  const statusState = useJsonData<LiveStatusPayload>(
    channelState.status === "ready" ? `${MOBILE_API_BASE_URL}/api/live/status` : null,
  );

  if (channelState.status === "loading" || statusState.status === "loading") {
    return <FeatureStatus title="Live monitor" message="Loading live channel status..." />;
  }
  if (channelState.status === "error") {
    return <FeatureStatus title="Live monitor" message={`Unable to load channels: ${channelState.error}`} isError />;
  }
  const channels = channelState.data?.channels ?? [];
  if (channels.length === 0) {
    return <FeatureStatus title="Live monitor" message="No live channels reported by API." isError />;
  }

  return (
    <View>
      <Text style={styles.featureSectionTitle}>Live monitor</Text>
      <Text style={styles.featureSectionBody}>
        {statusState.data
          ? `Active: VHF ${statusState.data.channel || "unknown"} · ${statusState.data.frequencyMhz || "unknown"}`
          : activeFeatureText("live-monitor")}
      </Text>
      <View style={styles.metricGrid}>
        <Metric
          label="Default channel"
          value={channelState.data?.defaultChannel || channels[0]?.channel || "unknown"}
        />
        <Metric
          label="Delay window"
          value={statusState.status === "ready" ? formatDelayWindow(statusState.data?.streamDelaySeconds) : "—"}
        />
      </View>
      <View style={styles.listBlock}>
        {channels.map((channel) => (
          <View key={channel.channel} style={styles.listItem}>
            <Text style={styles.listTitle}>VHF {channel.channel}</Text>
            <Text style={styles.listBody}>
              {channel.label} • {channel.frequencyMhz} MHz
            </Text>
            <View style={styles.actionLinksRow}>
              {channel.streamPath ? (
              <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`Open live stream for VHF ${channel.channel}`}
                  onPress={() =>
                    openExternalUrl(channel.streamPath || "")
                  }
                  style={styles.actionLink}
                >
                  <Text style={styles.actionLinkText}>Open stream</Text>
                </Pressable>
              ) : null}
              {channel.statusPath ? (
              <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`Open live status for VHF ${channel.channel}`}
                  onPress={() =>
                    openExternalUrl(channel.statusPath || "")
                  }
                  style={styles.actionLink}
                >
                  <Text style={styles.actionLinkText}>Open status</Text>
                </Pressable>
              ) : null}
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

function AisMapFeature() {
  const state = useJsonData<PublicManifestPayload>(`${MOBILE_API_BASE_URL}/public_manifest.json`);
  if (state.status === "loading") {
    return <FeatureStatus title="AIS map" message="Loading AIS publication manifest..." />;
  }
  if (state.status === "error") {
    return <FeatureStatus title="AIS map" message={`Unable to load map manifest: ${state.error}`} isError />;
  }

  const payload = state.data || {};
  const stats = payload.stats || {};
  const tracks = Array.isArray(payload.ais_tracks) ? payload.ais_tracks : [];
  const generated = formatDateTime(payload.generated_at);

  return (
    <View>
      <Text style={styles.featureSectionTitle}>AIS map</Text>
      <Text style={styles.featureSectionBody}>Last manifest: {generated}</Text>
      <View style={styles.metricGrid}>
        <Metric label="Manifest clips" value={`${stats.clip_count || 0}`} />
        <Metric label="AIS tracks" value={`${tracks.length}`} />
      </View>
      {tracks.length === 0 ? (
        <Text style={styles.featureSectionBody}>No AIS tracks are present in this manifest.</Text>
      ) : (
        <View style={styles.listBlock}>
          {tracks.slice(0, 4).map((track, index) => {
            const asObject = isRecord(track) ? track : {};
            const trackName = typeof asObject.name === "string" ? asObject.name : "Unknown vessel";
            const trackType = typeof asObject.vessel_type === "string" ? asObject.vessel_type : "vessel";
            return (
              <View key={String((asObject.track_id ?? index) || `track-${index}`)} style={styles.listItem}>
                <Text style={styles.listTitle}>{trackName}</Text>
                <Text style={styles.listBody}>{trackType}</Text>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}

function AnalysisFeature() {
  const state = useJsonData<LexicalPayload>(`${MOBILE_API_BASE_URL}/api/analysis/lexical`);

  if (state.status === "loading") {
    return <FeatureStatus title="Analysis" message="Loading lexical analysis..." />;
  }
  if (state.status === "error") {
    return <FeatureStatus title="Analysis" message={`Unable to load analysis: ${state.error}`} isError />;
  }
  const payload = state.data || {};
  const channelCounts = payload.channels || payload.frequency?.by_channel || {};
  const updated = formatDateTime(payload.generated_at || payload.generatedAt);
  const terms = listableTerms(Array.isArray(payload.terms?.unigrams) ? payload.terms.unigrams : []);

  return (
    <View>
      <Text style={styles.featureSectionTitle}>Analysis</Text>
      <Text style={styles.featureSectionBody}>Updated: {updated}</Text>
      <View style={styles.metricGrid}>
        <Metric label="Status" value={payload.status || "ok"} />
        <Metric label="Clips analyzed" value={`${payload.source_clip_count ?? 0}`} />
      </View>
      <Text style={styles.featureSectionBody}>
        Active channels: {Object.keys(channelCounts).length ? Object.keys(channelCounts).join(", ") : "none"}
      </Text>
      {terms.length > 0 ? (
        <View style={styles.termList}>
          {terms.map((term) => (
            <Text key={term} style={styles.termItem}>
              {term}
            </Text>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function PerformanceFeature() {
  const state = useJsonData<PerformancePayload>(`${MOBILE_API_BASE_URL}/api/live/performance`);
  if (state.status === "loading") {
    return <FeatureStatus title="Performance" message="Loading performance snapshot..." />;
  }
  if (state.status === "error") {
    return <FeatureStatus title="Performance" message={`Unable to load performance: ${state.error}`} isError />;
  }

  const hosts = Array.isArray(state.data?.hosts)
    ? state.data?.hosts
    : state.data?.host
      ? [state.data.host]
      : [];
  if (!hosts.length) {
    return (
      <View>
        <Text style={styles.featureSectionTitle}>Performance</Text>
        <Text style={styles.featureSectionBody}>No performance hosts available.</Text>
      </View>
    );
  }

  return (
    <View>
      <Text style={styles.featureSectionTitle}>Performance</Text>
      <Text style={styles.featureSectionBody}>Status: {state.data?.status || "unknown"}</Text>
      <Text style={styles.featureSectionBody}>
        Snapshot: {state.data?.generatedAt ? formatDateTime(state.data.generatedAt) : "not available"}
      </Text>
      <View style={styles.listBlock}>
        {hosts.map((host, index) => (
          <View key={`${host?.role || "host"}-${index}`} style={styles.listItem}>
            <Text style={styles.listTitle}>{host?.role || `Host ${index + 1}`}</Text>
            <Text style={styles.listBody}>
              CPU {typeof host?.cpu?.utilizationPercent === "number" ? `${host.cpu.utilizationPercent.toFixed(1)}%` : "n/a"} •
              Memory {typeof host?.memory?.usedPercent === "number" ? `${host.memory.usedPercent.toFixed(1)}%` : "n/a"} •
              Thermal {typeof host?.thermal?.temperatureC === "number" ? `${host.thermal.temperatureC.toFixed(1)}°C` : "n/a"} •
              State {host?.status || "unknown"}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function AuthPanel({ adminAuth }: { adminAuth: ReturnType<typeof useCognitoAdminAuth> }) {
  const { busy, configured, error, session, signIn, signOut } = adminAuth;

  return (
    <View style={styles.authPanel}>
      <View style={styles.authHeader}>
        <View>
          <Text style={styles.panelLabel}>Access</Text>
          <Text style={styles.authTitle}>{session ? "Super admin" : "Google federated login"}</Text>
          <Text style={styles.authSubtitle}>
            Sign in with Google through the Cognito hosted auth flow.
          </Text>
        </View>
        <View style={[styles.authStateBadge, session && styles.authStateBadgeActive]}>
          <Text style={[styles.authStateText, session && styles.authStateTextActive]}>
            {session ? "Signed in" : configured ? "Ready" : "Missing config"}
          </Text>
        </View>
      </View>

      <Pressable
        accessibilityLabel={session ? "Sign out" : "Sign in with Google"}
        accessibilityRole="button"
        disabled={busy || !configured}
        onPress={session ? signOut : signIn}
        style={({ pressed }) => [
          styles.authAction,
          (!configured || busy) && styles.authActionDisabled,
          pressed && configured && styles.authActionPressed,
        ]}
      >
        <Text style={[styles.authActionText, (!configured || busy) && styles.authActionTextDisabled]}>
          {busy ? "Working..." : session ? "Sign out" : "Sign in with Google"}
        </Text>
      </Pressable>

      {session ? (
        <View style={styles.adminCard}>
          <Text style={styles.adminEmail}>{session.email}</Text>
          <Text style={styles.adminRole}>super-admins</Text>
        </View>
      ) : null}
      {!configured ? (
        <Text style={styles.authError}>
          Set `EXPO_PUBLIC_COGNITO_CLIENT_ID` and `EXPO_PUBLIC_COGNITO_DOMAIN` in mobile env to
          enable login.
        </Text>
      ) : null}

      {error ? <Text style={styles.authError}>{error}</Text> : null}
    </View>
  );
}

function useJsonData<T>(url: string | null) {
  const [state, setState] = useState<RemoteState<T>>({
    status: "idle",
    data: null,
    error: null,
  });

  useEffect(() => {
    if (!url) {
      setState({ status: "idle", data: null, error: null });
      return;
    }

    let mounted = true;
    const controller = new AbortController();

    setState((previous) => ({
      ...previous,
      status: "loading",
      error: null,
    }));

    (async () => {
      try {
        const response = await fetch(url, { signal: controller.signal, cache: "no-store" });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = (await response.json()) as T;
        if (!mounted) {
          return;
        }
        setState({ status: "ready", data, error: null });
      } catch (error_) {
        if (!mounted || (error_ as Error).name === "AbortError") {
          return;
        }
        setState({ status: "error", data: null, error: error_ instanceof Error ? error_.message : "Request failed" });
      }
    })();

    return () => {
      mounted = false;
      controller.abort();
    };
  }, [url]);

  return state;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function listableTerms(items: unknown[]): string[] {
  return items
    .map((item) => {
      if (typeof item === "string") {
        return item;
      }
      if (isRecord(item) && typeof item.text === "string") {
        return item.text;
      }
      return "";
    })
    .filter(Boolean)
    .slice(0, 8);
}

function formatDateTime(timestamp?: string): string {
  if (!timestamp) {
    return "—";
  }
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return "—";
  }
  return parsed.toLocaleString();
}

function formatDuration(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) {
    return "—";
  }
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const remainingSeconds = total % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
}

function formatAltitudeFeet(altitudeFeet: number | null): string {
  if (altitudeFeet == null || Number.isNaN(altitudeFeet)) {
    return "n/a";
  }
  return `${altitudeFeet.toLocaleString()} ft`;
}

function formatDelayWindow(delay?: { minimum?: number; maximum?: number }) {
  if (!delay || (delay.minimum == null && delay.maximum == null)) {
    return "Unknown";
  }
  const min = delay.minimum == null ? "?" : `${delay.minimum}s`;
  const max = delay.maximum == null ? "?" : `${delay.maximum}s`;
  return `${min} to ${max}`;
}

function useGpsAltitudeFeet(): number | null {
  const [altitudeFeet, setAltitudeFeet] = useState<number | null>(null);

  useEffect(() => {
    if (Platform.OS === "web") {
      return;
    }

    let mounted = true;
    let subscription: Location.LocationSubscription | null = null;

    async function startTracking() {
      try {
        const initialPermission = await Location.getForegroundPermissionsAsync();
        let permissionStatus = initialPermission.status;
        if (permissionStatus !== "granted") {
          const requestedPermission = await Location.requestForegroundPermissionsAsync();
          permissionStatus = requestedPermission.status;
        }
        if (!mounted || permissionStatus !== "granted") {
          return;
        }

        const watch = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.Balanced,
            distanceInterval: 2,
            timeInterval: 3000,
          },
          ({ coords }) => {
            if (!mounted) {
              return;
            }
            const altitude = coords.altitude;
            if (typeof altitude !== "number" || !Number.isFinite(altitude)) {
              setAltitudeFeet(null);
              return;
            }
            setAltitudeFeet(Math.round(altitude * METERS_TO_FEET));
          },
        );

        if (!mounted) {
          watch.remove();
          return;
        }
        subscription = watch;
      } catch (error_) {
        if (!mounted) {
          return;
        }
        if (error_ instanceof Error) {
          console.warn(`Could not get GPS altitude: ${error_.message}`);
        } else {
          console.warn("Could not get GPS altitude.");
        }
      }
    }

    void startTracking();

    return () => {
      mounted = false;
      subscription?.remove();
    };
  }, []);

  return altitudeFeet;
}

function openExternalUrl(url: string) {
  if (!url) {
    return;
  }
  const resolved = url.startsWith("http") ? url : `${MOBILE_API_BASE_URL}${url}`;
  void Linking.openURL(resolved);
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function CompassDial({
  compassBodyTransform,
}: {
  compassBodyTransform: ViewStyle["transform"];
}) {
  return (
    <View style={styles.compassStage}>
      <Animated.View
        style={[
          styles.compassWrap,
          { transform: compassBodyTransform },
        ]}
      >
        <Svg
          width="100%"
          height="100%"
          viewBox={`0 0 ${COMPASS_VIEWBOX} ${COMPASS_VIEWBOX}`}
          accessibilityLabel="Compass dial"
        >
          <Defs>
            <SvgLinearGradient id="brass" x1="0" y1="0" x2="1" y2="1">
              <Stop offset="0" stopColor="#b37a26" />
              <Stop offset="0.4" stopColor="#e5c26a" />
              <Stop offset="1" stopColor="#6c4215" />
            </SvgLinearGradient>
            <SvgLinearGradient id="steel" x1="0" y1="0" x2="1" y2="1">
              <Stop offset="0" stopColor="#5cc4d6" stopOpacity={0.75} />
              <Stop offset="1" stopColor="#0f5f70" stopOpacity={0.75} />
            </SvgLinearGradient>
            <SvgLinearGradient id="glass" x1="0" y1="0" x2="1" y2="1">
              <Stop offset="0" stopColor="#ffffff" stopOpacity={0.1} />
              <Stop offset="1" stopColor="#ffffff" stopOpacity={0.02} />
            </SvgLinearGradient>
          </Defs>

          <Ellipse cx={CENTER} cy={CENTER} rx={COMPASS_OUTER_RADIUS} ry={COMPASS_OUTER_RADIUS} fill="url(#brass)" />
          <Circle
            cx={CENTER}
            cy={CENTER}
            r={COMPASS_OUTER_RADIUS - 8}
            fill="#160f07"
            opacity={0.78}
          />
          <Circle
            cx={CENTER}
            cy={CENTER}
            r={COMPASS_OUTER_RADIUS - 14}
            fill="url(#steel)"
            stroke="#87f5df"
            strokeOpacity={0.5}
            strokeWidth="2"
          />
          <Ellipse
            cx={CENTER}
            cy={CENTER}
            rx={COMPASS_OUTER_RADIUS - 20}
            ry={COMPASS_OUTER_RADIUS - 22}
            fill="#081512"
            stroke="#3c8a92"
            strokeWidth="1.8"
            opacity={0.9}
          />
          <Ellipse cx={CENTER - 4} cy={CENTER - 42} rx="60" ry="20" fill="url(#glass)" opacity="0.56" />

          <Circle cx={CENTER} cy={CENTER} r="110" fill="transparent" stroke="#5e3e19" strokeWidth="1.5" opacity={0.62} />

          {frameStuds.map((stud, index) => (
            <Circle
              key={index}
              cx={stud.cx}
              cy={stud.cy}
              r={stud.r}
              fill={index % 2 ? "#ead19d" : "#7b4f1c"}
              opacity={0.74}
            />
          ))}

          {compassTicks.map((tick) => (
            <Line
              key={tick.degrees}
              x1={tick.x1}
              y1={tick.y1}
              x2={tick.x2}
              y2={tick.y2}
              stroke={tick.major ? "#ffecb0" : "#6ec7c8"}
              strokeWidth={tick.major ? 2.5 : 1}
              strokeLinecap="round"
              opacity={tick.major ? 0.95 : 0.45}
            />
          ))}

          {northIndicators.map((item) => {
            const radians = (item.degrees - 90) * RAD;
            const x = CENTER + Math.cos(radians) * item.r;
            const y = CENTER + Math.sin(radians) * item.r;
            return (
              <SvgText
                key={item.label}
                x={x}
                y={y}
                fill="#fff8cd"
                fontFamily="serif"
                fontSize={item.size}
                fontWeight="700"
                textAnchor="middle"
                alignmentBaseline="middle"
              >
                {item.label}
              </SvgText>
            );
          })}

          <Circle cx={CENTER} cy={CENTER} r="20" fill="#f0d6aa" stroke="#261d0f" strokeWidth="3" />
          <Circle cx={CENTER} cy={CENTER} r="8" fill="#2a1a08" />
          <Ellipse cx={CENTER - 1} cy={CENTER - 32} rx="7" ry="2" fill="#fcecc7" opacity="0.45" />
        </Svg>
      </Animated.View>

      <View pointerEvents="none" style={[styles.fixedNorthNeedleLayer, { transform: fixedNorthNeedleTransform }]}>
        <Svg
          width="100%"
          height="100%"
          viewBox={`0 0 ${COMPASS_VIEWBOX} ${COMPASS_VIEWBOX}`}
          accessibilityLabel="North pointer"
        >
          <Path
            d={`M ${CENTER} 20 L ${CENTER - 7} ${CENTER + 12} L ${CENTER + 7} ${CENTER + 12} Z`}
            fill="#c8192f"
            stroke="#ffd7b0"
            strokeWidth="0.9"
          />
          <Path
            d={`M ${CENTER} ${CENTER + 44} L ${CENTER - 11} ${CENTER + 12} L ${CENTER + 11} ${CENTER + 12} Z`}
            fill="#ffffff"
            stroke="#d4d4d4"
            strokeWidth="0.9"
          />
          <Circle cx={CENTER} cy={CENTER} r="10" fill="#ffe2b6" />
          <Circle cx={CENTER} cy={CENTER} r="3.4" fill="#2a1a08" />
        </Svg>
      </View>
    </View>
  );
}

function compassSensorLabel(source: CompassSensorSource): string {
  switch (source) {
    case "motion":
    case "magnetometer":
      return "Live";
    case "demo":
      return "Demo";
    case "seeking":
    default:
      return "Starting";
  }
}

function useCognitoAdminAuth() {
  const config = useMemo(() => readCognitoAuthConfig(), []);
  const redirectUri = useMemo(
    () =>
      config?.redirectUri ??
      AuthSession.makeRedirectUri({
        path: "auth/callback",
        scheme: "elliottbayvhf",
      }),
    [config?.redirectUri],
  );
  const discovery = useMemo(() => (config ? cognitoDiscovery(config) : null), [config]);
  const [session, setSession] = useState<AdminSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authRequest, , promptAsync] = AuthSession.useAuthRequest(
    {
      clientId: config?.clientId ?? "missing-cognito-client",
      redirectUri,
      responseType: AuthSession.ResponseType.Code,
      scopes: ["openid", "email", "profile"],
      usePKCE: true,
    },
    discovery,
  );

  const signIn = useCallback(async () => {
    if (!config || !discovery || !authRequest) {
      setError("Cognito is not configured for this build.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const result = await promptAsync();
      if (result.type !== "success") {
        setBusy(false);
        return;
      }

      const code = result.params.code;
      if (!code) {
        throw new Error("Cognito did not return an authorization code.");
      }

      const tokenResponse = await AuthSession.exchangeCodeAsync(
        {
          clientId: config.clientId,
          code,
          extraParams: {
            code_verifier: authRequest.codeVerifier ?? "",
          },
          redirectUri,
        },
        discovery,
      );
      const idToken = tokenResponse.idToken;
      if (!idToken) {
        throw new Error("Cognito did not return an ID token.");
      }

      const authorization = authorizeCognitoClaims(decodeJwtClaims(idToken), config);
      if (!authorization.ok) {
        throw new Error(authorization.reason);
      }

      setSession({
        email: authorization.email,
        groups: authorization.groups,
        isSuperAdmin: authorization.isSuperAdmin,
      });
    } catch (authError) {
      setSession(null);
      setError(authError instanceof Error ? authError.message : "Cognito sign-in failed.");
    } finally {
      setBusy(false);
    }
  }, [authRequest, config, discovery, promptAsync, redirectUri]);

  const signOut = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      if (config) {
        await WebBrowser.openAuthSessionAsync(cognitoLogoutUrl(config, redirectUri), redirectUri);
      }
      setSession(null);
    } catch (signOutError) {
      setSession(null);
      setError(signOutError instanceof Error ? signOutError.message : "Cognito sign-out failed.");
    } finally {
      setBusy(false);
    }
  }, [config, redirectUri]);

  return {
    busy,
    configured: Boolean(config),
    error,
    session,
    signIn,
    signOut,
  };
}

function useLiveCompass() {
  const [vector, setVector] = useState<MagneticVector>(initialVector);
  const [heading, setHeading] = useState(initialHeading);
  const [sensorSource, setSensorSource] = useState<CompassSensorSource>("seeking");
  const rotation = useRef(new Animated.Value(initialHeading)).current;
  const tiltPitch = useRef(new Animated.Value(0)).current;
  const tiltRoll = useRef(new Animated.Value(0)).current;
  const continuousHeading = useRef(initialHeading);
  const lastUiRefresh = useRef(0);
  const lastMagneticFieldRefresh = useRef(0);

  const compassBodyRotation = useMemo(
    () =>
      rotation.interpolate({
        extrapolate: "extend",
        inputRange: [-COMPASS_ROTATION_RANGE_DEGREES, COMPASS_ROTATION_RANGE_DEGREES],
        outputRange: compassBodyRotationOutputRange(COMPASS_ROTATION_RANGE_DEGREES),
      }),
    [rotation],
  );
  const compassBodyTransform = useMemo(
    () =>
      [
        { perspective: 760 },
        {
          rotateX: tiltPitch.interpolate({
            extrapolate: "clamp",
            inputRange: [-16, 16],
            outputRange: ["-16deg", "16deg"],
          }),
        },
        {
          rotateY: tiltRoll.interpolate({
            extrapolate: "clamp",
            inputRange: [-16, 16],
            outputRange: ["-16deg", "16deg"],
          }),
        },
        { rotate: compassBodyRotation },
      ] as ViewStyle["transform"],
    [compassBodyRotation, tiltPitch, tiltRoll],
  );

  const animateCompassBodyToHeading = useCallback(
    (nextHeading: number) => {
      const targetHeading = nearestCompassHeading(continuousHeading.current, nextHeading);
      continuousHeading.current = targetHeading;
      rotation.stopAnimation();
      if (COMPASS_NEEDLE_RESPONSE_MS === 0) {
        rotation.setValue(targetHeading);
        return;
      }
      Animated.timing(rotation, {
        duration: COMPASS_NEEDLE_RESPONSE_MS,
        toValue: targetHeading,
        useNativeDriver: true,
      }).start();
    },
    [rotation],
  );

  useEffect(() => {
    let mounted = true;
    let motionSubscription: { remove: () => void } | null = null;
    let magnetometerSubscription: { remove: () => void } | null = null;

    function updateHeading(nextHeading: number) {
      const now = Date.now();
      if (now - lastUiRefresh.current >= COMPASS_UI_REFRESH_INTERVAL_MS) {
        lastUiRefresh.current = now;
        setHeading(nextHeading);
        animateCompassBodyToHeading(nextHeading);
      }
    }

    function updateMagneticVector(reading: MagneticVector) {
      const now = Date.now();
      if (now - lastMagneticFieldRefresh.current >= MAGNETIC_FIELD_REFRESH_INTERVAL_MS) {
        lastMagneticFieldRefresh.current = now;
        setVector(reading);
      }
    }

    function startMagnetometer(useForHeading: boolean) {
      Magnetometer.isAvailableAsync()
        .then((available) => {
          if (!mounted) {
            return;
          }
          if (!available) {
            if (useForHeading) {
              setSensorSource("demo");
            }
            return;
          }

          if (useForHeading) {
            setSensorSource("magnetometer");
          }
          Magnetometer.setUpdateInterval(useForHeading ? COMPASS_SENSOR_INTERVAL_MS : MAGNETIC_FIELD_REFRESH_INTERVAL_MS);
          magnetometerSubscription = Magnetometer.addListener((reading) => {
            updateMagneticVector(reading);
            if (useForHeading) {
              updateHeading(preciseHeadingFromMagnetometer(reading));
            }
          });
        })
        .catch(() => {
          if (mounted && useForHeading) {
            setSensorSource("demo");
          }
        });
    }

    DeviceMotion.isAvailableAsync()
      .then((available) => {
        if (!mounted) {
          return;
        }
        if (!available) {
          startMagnetometer(true);
          return;
        }

        setSensorSource("motion");
        DeviceMotion.setUpdateInterval(COMPASS_SENSOR_INTERVAL_MS);
        motionSubscription = DeviceMotion.addListener((reading) => {
          if (reading.rotation) {
            const tilt = clampedCompassGimbalTilt(reading.rotation);
            tiltPitch.setValue(tilt.pitchDegrees);
            tiltRoll.setValue(tilt.rollDegrees);
            updateHeading(headingFromDeviceMotionRotation(reading.rotation));
          }
        });

        startMagnetometer(false);
      })
      .catch(() => {
        if (mounted) {
          startMagnetometer(true);
        }
      });

    return () => {
      mounted = false;
      motionSubscription?.remove();
      magnetometerSubscription?.remove();
    };
  }, [animateCompassBodyToHeading, tiltPitch, tiltRoll]);

  return {
    compassBodyTransform,
    heading,
    sensorSource,
    vector,
  };
}

const styles = StyleSheet.create({
  shell: {
    flex: 1,
    backgroundColor: "#090d08",
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
  titleSection: {
    alignItems: "center",
    marginBottom: 2,
  },
  title: {
    color: "#ffe6b0",
    fontSize: 30,
    fontWeight: "900",
    letterSpacing: 1,
    textAlign: "center",
  },
  subtitle: {
    color: "#95cfca",
    fontSize: 14,
    letterSpacing: 0.45,
    marginTop: 3,
    marginBottom: 5,
    textAlign: "center",
  },
  panelLabel: {
    color: "#9fb8b2",
    fontSize: 12,
    fontWeight: "900",
    letterSpacing: 0,
    textTransform: "uppercase",
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
  compassStage: {
    alignSelf: "center",
    aspectRatio: 1,
    maxWidth: 220,
    position: "relative",
    overflow: "hidden",
    width: "90%",
    borderRadius: 999,
  },
  compassWrap: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 999,
    overflow: "hidden",
  },
  fixedNorthNeedleLayer: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 2,
  },
  metricGrid: {
    flexDirection: "row",
    gap: 8,
    flexWrap: "wrap",
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
  authPanel: {
    backgroundColor: "rgba(10, 25, 26, 0.9)",
    borderColor: "#254542",
    borderRadius: 8,
    borderWidth: 1,
    gap: 12,
    padding: 14,
  },
  authHeader: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
  },
  authTitle: {
    color: "#fbfff8",
    fontSize: 22,
    fontWeight: "900",
    letterSpacing: 0,
    marginTop: 4,
  },
  authSubtitle: {
    color: "#93cbc7",
    fontSize: 12,
    fontWeight: "700",
    marginTop: 6,
  },
  authStateBadge: {
    backgroundColor: "#14232f",
    borderColor: "#34485e",
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  authStateBadgeActive: {
    backgroundColor: "#0d302d",
    borderColor: "#1fbba4",
  },
  authStateText: {
    color: "#adc0cf",
    fontSize: 12,
    fontWeight: "900",
  },
  authStateTextActive: {
    color: "#adfff1",
  },
  adminCard: {
    backgroundColor: "#0d2a2f",
    borderColor: "#1fbba4",
    borderRadius: 8,
    borderWidth: 1,
    padding: 12,
  },
  adminEmail: {
    color: "#f6fffb",
    fontSize: 17,
    fontWeight: "900",
    letterSpacing: 0,
  },
  adminRole: {
    color: "#71ead8",
    fontSize: 13,
    fontWeight: "900",
    marginTop: 5,
  },
  authError: {
    color: "#ffb1a8",
    fontSize: 13,
    fontWeight: "800",
    lineHeight: 18,
  },
  authAction: {
    alignItems: "center",
    backgroundColor: "#13dec0",
    borderRadius: 8,
    justifyContent: "center",
    minHeight: 60,
    paddingHorizontal: 14,
  },
  authActionDisabled: {
    backgroundColor: "#25414b",
  },
  authActionPressed: {
    backgroundColor: "#8dffec",
  },
  authActionText: {
    color: "#031514",
    fontSize: 19,
    fontWeight: "900",
  },
  authActionTextDisabled: {
    color: "#9eb4bd",
  },
  featurePanel: {
    backgroundColor: "rgba(7, 20, 21, 0.74)",
    borderColor: "#1b3837",
    borderRadius: 8,
    borderWidth: 1,
    gap: 12,
    padding: 14,
  },
  featureTabs: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 8,
  },
  featureTab: {
    backgroundColor: "#101b27",
    borderColor: "#2a415c",
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    minWidth: "48%",
    minHeight: 56,
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  featureTabActive: {
    borderColor: "#7cf2e3",
    backgroundColor: "#13253e",
  },
  featureTabPressed: {
    opacity: 0.78,
  },
  featureSectionTitle: {
    color: "#f4fbff",
    fontSize: 16,
    fontWeight: "900",
    marginBottom: 6,
  },
  featureSectionBody: {
    color: "#a9bfd2",
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 18,
  },
  featureError: {
    color: "#ffb1a8",
  },
  listBlock: {
    gap: 8,
    marginTop: 8,
  },
  listItem: {
    backgroundColor: "#101b27",
    borderColor: "#2a415c",
    borderRadius: 8,
    borderWidth: 1,
    gap: 4,
    padding: 10,
  },
  listTitle: {
    color: "#f4fbff",
    fontSize: 14,
    fontWeight: "900",
  },
  listMeta: {
    color: "#8fc6c4",
    fontSize: 12,
  },
  listBody: {
    color: "#9eb4c4",
    fontSize: 12,
    lineHeight: 17,
  },
  actionLink: {
    alignSelf: "flex-start",
    marginTop: 4,
  },
  actionLinkText: {
    color: "#8ff5ff",
    fontSize: 12,
    fontWeight: "900",
  },
  actionLinksRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 6,
    flexWrap: "wrap",
  },
  termList: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    marginTop: 8,
  },
  termItem: {
    backgroundColor: "#152b35",
    borderColor: "#2a4a61",
    borderRadius: 6,
    borderWidth: 1,
    color: "#a9bfd2",
    fontSize: 12,
    fontWeight: "900",
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  featureLabel: {
    color: "#f4fbff",
    fontSize: 15,
    fontWeight: "900",
  },
});
