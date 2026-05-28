from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from talkingboats.config import DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT
from talkingboats.security import assert_public_safe

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
PUBLIC_EXCLUDED_CHANNELS = ("WX",)
TOPIC_PLOT_PATH = "/analysis/topic_clusters.html"
PUBLIC_AUDIO_EXAMPLE_LIMIT = DEFAULT_PUBLIC_AUDIO_EXPORT_LIMIT
MAX_BERTOPIC_TOPICS = 18
TOPIC_COLOR_PALETTE = (
    "#40e0bf",
    "#6ab8ff",
    "#f0b85a",
    "#ff7777",
    "#8bd867",
    "#f58fb2",
    "#a5b4fc",
    "#f7cf5d",
    "#34d399",
    "#fb7185",
    "#38bdf8",
    "#c084fc",
    "#f97316",
    "#22d3ee",
    "#e879f9",
    "#84cc16",
    "#facc15",
    "#60a5fa",
)
TOPIC_OUTLIER_COLOR = "#596761"

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]{2,}|\b\d{2,4}\b")
STOPWORDS = {
    "the",
    "and",
    "for",
    "you",
    "are",
    "that",
    "this",
    "with",
    "from",
    "have",
    "has",
    "was",
    "were",
    "will",
    "would",
    "can",
    "could",
    "should",
    "your",
    "our",
    "its",
    "there",
    "here",
    "copy",
    "radio",
    "over",
    "out",
    "all",
    "just",
    "into",
    "about",
    "after",
    "before",
    "been",
    "but",
    "not",
    "yes",
    "yeah",
    "okay",
    "thank",
    "thanks",
    "ok",
    "uh",
    "um",
    "them",
    "they",
    "she",
    "her",
    "him",
    "his",
    "then",
    "than",
    "now",
    "did",
    "does",
    "doing",
    "had",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "zero",
    "ten",
    "to",
    "in",
    "on",
    "of",
    "at",
    "a",
    "an",
    "is",
    "it",
    "be",
    "by",
    "as",
    "if",
    "or",
    "we",
    "i",
    "me",
    "my",
    "us",
    "do",
    "go",
    "going",
    "get",
    "got",
}

PHRASE_BUCKETS = {
    "communication_markers": re.compile(
        r"\b(roger|copy|over|out|standing by|go ahead|negative|affirmative|"
        r"say again|switch|working channel)\b",
        re.IGNORECASE,
    ),
    "movement": re.compile(
        r"\b(northbound|southbound|inbound|outbound|making|turning|passing|crossing|"
        r"docking|undocking|departing|arriving|transiting)\b",
        re.IGNORECASE,
    ),
    "places": re.compile(
        r"\b(west waterway|east waterway|elliott bay|pier \d+|terminal \d+|"
        r"harbor island|duwamish|locks|shilshole|smith cove|colman dock|"
        r"bainbridge|vashon|mile rock)\b",
        re.IGNORECASE,
    ),
    "vessel_types": re.compile(
        r"\b(tug|barge|ferry|container ship|cruise ship|pilot|pleasure craft|"
        r"sailboat|tow|ship|vessel)\b",
        re.IGNORECASE,
    ),
}

KNOWN_ENTITY_PATTERNS = (
    ("Seattle Traffic", "shore_station", re.compile(r"\bSeattle Traffic\b", re.IGNORECASE)),
    ("Coast Guard", "shore_station", re.compile(r"\b(?:USCG|Coast Guard)\b", re.IGNORECASE)),
    ("Pilot Station", "shore_station", re.compile(r"\bPilot Station\b", re.IGNORECASE)),
)
VESSEL_NAME_RE = re.compile(
    r"\b(?:(?:MSC|COSCO)\s+[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)?|"
    r"(?:Tug|Ferry|Clipper|Cape|Emerald|Walla|Admiral|Ocean|Spirit|Reliance|"
    r"Anthem|Commander|Virginia|Yukon)\s+[A-Z][A-Za-z0-9]+"
    r"(?:\s+[A-Z][A-Za-z0-9]+)?)\b"
)
NON_ENTITY_PHRASES = {
    "Elliott Bay",
    "West Waterway",
    "East Waterway",
    "Pier",
    "Terminal",
    "Good Morning",
    "Good Afternoon",
    "Thank You",
}

EDUCATION_RESOURCES = [
    {
        "title": "VTS radio procedures",
        "source": "USCG Navigation Center",
        "url": "https://navcen.uscg.gov/vessel-traffic-services-radio-procedures",
        "category": "VTS",
        "local_relevance": (
            "Explains the radio procedure vocabulary behind calls to Seattle Traffic and "
            "the structured movement reports heard on VHF 14."
        ),
    },
    {
        "title": "VTS Puget Sound User Manual",
        "source": "USCG Sector Puget Sound",
        "url": (
            "https://navcen.uscg.gov/sites/default/files/pdf/VTS%20User%20Guides/"
            "VTS_PS_UsersManual_%282024%29.pdf"
        ),
        "category": "VTS",
        "local_relevance": (
            "The best local reference for Puget Sound reporting points, watch practices, "
            "and Seattle Traffic channel conventions."
        ),
    },
    {
        "title": "U.S. VHF marine channel information",
        "source": "USCG Navigation Center",
        "url": "https://www.navcen.uscg.gov/us-vhf-channel-information",
        "category": "Channels",
        "local_relevance": (
            "Official channel-use context for bridge-to-bridge, calling, liaison, and "
            "non-commercial traffic heard around Elliott Bay."
        ),
    },
    {
        "title": "U.S. Coast Pilot 10",
        "source": "NOAA Office of Coast Survey",
        "url": "https://nauticalcharts.noaa.gov/publications/coast-pilot/",
        "category": "Local geography",
        "local_relevance": (
            "Authoritative navigation text for Elliott Bay, Smith Cove, Harbor Island, "
            "the Duwamish Waterway, and Seattle waterfront piers."
        ),
    },
    {
        "title": "Marine weather broadcasts",
        "source": "National Weather Service",
        "url": "https://www.weather.gov/marine/uscg_broadcasts",
        "category": "Weather radio",
        "local_relevance": (
            "Background on weather broadcasts and Coast Guard broadcast practices that "
            "can appear alongside working-channel radio traffic."
        ),
    },
    {
        "title": "Puget Sound Harbor Safety Plan",
        "source": "Puget Sound Harbor Safety Committee",
        "url": (
            "https://www.seattle.gov/documents/Departments/PSCSC/ExamsAndRegisters/"
            "Puget_Sound_Harbor_Safety_Plan_2015.pdf"
        ),
        "category": "Harbor safety",
        "local_relevance": (
            "Local safety-practice context for Elliott Bay, Smith Cove, and VTS radio "
            "watch expectations."
        ),
    },
    {
        "title": "Moorage in Elliott Bay & Duwamish Waterway",
        "source": "Port of Seattle",
        "url": "https://www.portseattle.org/page/moorage-elliott-bay-duwamish-waterway",
        "category": "Local geography",
        "local_relevance": (
            "Helps decode pier, terminal, and waterway place names that recur in "
            "transcripts around Harbor Island and the Seattle waterfront."
        ),
    },
    {
        "title": "Order a pilot",
        "source": "Puget Sound Pilots",
        "url": "https://pspilots.org/order-a-pilot/",
        "category": "Pilotage",
        "local_relevance": (
            "Practical context for pilot-station and pilot-transfer language heard "
            "around commercial vessel movements."
        ),
    },
]

EDUCATION_GUIDE = [
    {
        "title": "Seattle Traffic is the coordinator",
        "signals": "Seattle Traffic, VHF 14, sail plan, destination, pilot on board",
        "what_it_explains": (
            "Calls to Seattle Traffic are usually vessels checking in with the local VTS "
            "picture, updating a sail plan, naming a destination, or reporting a material "
            "change in movement."
        ),
        "why_it_matters": (
            "VHF 14 is the Puget Sound VTS working channel for the Seattle side of the "
            "system. When a ship says its name, location, course, speed, destination, or "
            "pilot status, it is helping traffic coordinators keep a shared mental chart "
            "for dense commercial water."
        ),
    },
    {
        "title": "Channel 13 is the cockpit-to-cockpit layer",
        "signals": "bridge-to-bridge, one whistle, crossing, passing, tug, pilot station",
        "what_it_explains": (
            "Short exchanges on 13 are often two vessels agreeing on an immediate maneuver: "
            "who will pass where, who will hold up, and whether a tug or pilot boat has room "
            "to work."
        ),
        "why_it_matters": (
            "Channel 13 is for intership navigation safety. The clipped style is deliberate: "
            "nearby bridge teams need a clear intent statement, not a long conversation."
        ),
    },
    {
        "title": "The place names are job sites and pinch points",
        "signals": "Elliott Bay, West Waterway, East Waterway, Smith Cove, Pier 91, Harbor Island",
        "what_it_explains": (
            "Many transcript place names are not sightseeing landmarks. They are entrances, "
            "berths, turns, terminals, and work areas that explain what the vessel is doing "
            "next."
        ),
        "why_it_matters": (
            "Pier 91 and Smith Cove point toward cruise and commercial terminal moves; the "
            "East and West Waterways frame Harbor Island and the Duwamish industrial route; "
            "Elliott Bay is the shared approach where ferries, tugs, pilots, cruise ships, "
            "and container traffic compress into the same radio scene."
        ),
    },
    {
        "title": "The jargon is compressed on purpose",
        "signals": "roger, copy, say again, over, out, standing by, go ahead",
        "what_it_explains": (
            "Radio words are receipts and turn-taking tools. They tell the other station "
            "whether a message was received, whether a repeat is needed, and whose turn it "
            "is to transmit."
        ),
        "why_it_matters": (
            "Marine VHF is shared airspace. Standard phrases keep the channel short, reduce "
            "ambiguity in noisy audio, and leave room for safety-critical traffic."
        ),
    },
    {
        "title": "Pilot and tug talk is work coordination",
        "signals": "pilot station, tug assist, container ship, cruise ship, berth, knots",
        "what_it_explains": (
            "Mentions of pilots, tugs, knots, and berth names usually describe a ship move "
            "being built in stages: pilot boarding, tug hookup, speed control, berth approach, "
            "or departure timing."
        ),
        "why_it_matters": (
            "Large vessels do not improvise their way into Elliott Bay terminals. Pilots, "
            "tugs, VTS, and bridge teams keep each phase explicit so everyone nearby can "
            "predict the next maneuver."
        ),
    },
    {
        "title": "Treat vessel names as clues, not gospel",
        "signals": "MSC Gabriella, COSCO Jetta, Tug Osprey, Cape San Juan, ASR confusion",
        "what_it_explains": (
            "The dashboard surfaces suspected names because ship names, company prefixes, "
            "and call signs are useful lexical signals, but automatic speech recognition can "
            "turn maritime names into nearby everyday words."
        ),
        "why_it_matters": (
            "A phrase like Costco Jetta may really be COSCO Jetta. The analysis should help "
            "you investigate likely vessels and entities without pretending the transcript "
            "is an official vessel log."
        ),
    },
]


@dataclass(frozen=True)
class TranscriptClip:
    key: str
    channel: str
    started_at: str
    ended_at: str | None
    duration_seconds: float | None
    content_type: str
    transcript: str


def generate_lexical_analysis(
    *,
    db_path: Path,
    output_dir: Path,
    page_size: int = 500,
    limit: int | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    clips = list(load_transcribed_clips(db_path, page_size=page_size, limit=limit))
    generated_at_text = _format_utc(generated_at or datetime.now(UTC))
    payload = _build_payload(clips, generated_at=generated_at_text)

    analysis_dir = output_dir / "analysis"
    topic_payload = _build_topics(
        clips,
        html_output_path=analysis_dir / "topic_clusters.html",
    )
    payload["topics"] = topic_payload
    assert_public_safe(payload)

    lexical_path = analysis_dir / "lexical.json"
    _atomic_write_text(
        lexical_path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    write_cached_lexical_analysis(
        db_path,
        payload=payload,
        source_fingerprint=_source_fingerprint(clips),
    )
    return payload


def load_transcribed_clips(
    db_path: Path,
    *,
    page_size: int,
    limit: int | None,
) -> Iterable[TranscriptClip]:
    offset = 0
    remaining = limit
    excluded = ",".join("?" for _ in PUBLIC_EXCLUDED_CHANNELS)
    with sqlite3.connect(db_path) as connection:
        while remaining is None or remaining > 0:
            batch_size = page_size if remaining is None else min(page_size, remaining)
            rows = connection.execute(
                f"""
                SELECT
                    key,
                    channel,
                    started_at,
                    ended_at,
                    duration_seconds,
                    content_type,
                    transcript
                FROM uploaded_clips
                WHERE status = 'transcribed'
                    AND transcript IS NOT NULL
                    AND trim(transcript) != ''
                    AND channel NOT IN ({excluded})
                ORDER BY started_at ASC, id ASC
                LIMIT ? OFFSET ?
                """,
                (*PUBLIC_EXCLUDED_CHANNELS, batch_size, offset),
            ).fetchall()
            if not rows:
                break
            for (
                key,
                channel,
                started_at,
                ended_at,
                duration_seconds,
                content_type,
                transcript,
            ) in rows:
                yield TranscriptClip(
                    key=str(key),
                    channel=str(channel),
                    started_at=str(started_at),
                    ended_at=str(ended_at) if ended_at else None,
                    duration_seconds=(
                        float(duration_seconds) if duration_seconds is not None else None
                    ),
                    content_type=str(content_type),
                    transcript=_public_text(str(transcript)),
                )
            offset += len(rows)
            if remaining is not None:
                remaining -= len(rows)


def write_cached_lexical_analysis(
    db_path: Path,
    *,
    payload: dict[str, Any],
    source_fingerprint: str,
) -> None:
    assert_public_safe(payload)
    payload_json = json.dumps(payload, sort_keys=True)
    generated_at = str(payload.get("generated_at") or _format_utc(datetime.now(UTC)))
    now = _format_utc(datetime.now(UTC))
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS lexical_analysis_cache (
                cache_key TEXT PRIMARY KEY,
                source_fingerprint TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO lexical_analysis_cache (
                cache_key,
                source_fingerprint,
                payload_json,
                generated_at,
                updated_at
            )
            VALUES ('latest', ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                source_fingerprint = excluded.source_fingerprint,
                payload_json = excluded.payload_json,
                generated_at = excluded.generated_at,
                updated_at = excluded.updated_at
            """,
            (source_fingerprint, payload_json, generated_at, now),
        )


def read_cached_lexical_analysis(db_path: Path | None) -> dict[str, Any]:
    if db_path is None or not db_path.exists():
        return missing_lexical_analysis()
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM lexical_analysis_cache
                WHERE cache_key = 'latest'
                """
            ).fetchone()
    except sqlite3.OperationalError:
        return missing_lexical_analysis()
    if not row:
        return missing_lexical_analysis()
    payload = json.loads(row[0])
    assert_public_safe(payload)
    return payload


def missing_lexical_analysis() -> dict[str, Any]:
    return {
        "status": "missing",
        "generated_at": None,
        "source_clip_count": 0,
        "source_min_started_at": None,
        "source_max_started_at": None,
        "channels": {},
        "frequency": {
            "by_channel": {},
            "by_hour_pacific": {},
            "by_day_pacific": {},
        },
        "terms": {
            "unigrams": [],
            "bigrams": [],
            "trigrams": [],
            "semantic_buckets": _empty_buckets(),
            "by_channel": {},
        },
        "entities": [],
        "topics": {
            "status": "missing",
            "reason": "no cached lexical analysis has been generated",
            "plot_url": TOPIC_PLOT_PATH,
            "items": [],
        },
        "education_guide": EDUCATION_GUIDE,
        "education": EDUCATION_RESOURCES,
    }


def _build_payload(clips: list[TranscriptClip], *, generated_at: str) -> dict[str, Any]:
    channel_counts: Counter[str] = Counter()
    hour_counts: Counter[str] = Counter()
    day_counts: Counter[str] = Counter()
    unigrams: Counter[str] = Counter()
    bigrams: Counter[str] = Counter()
    trigrams: Counter[str] = Counter()
    buckets: dict[str, Counter[str]] = {name: Counter() for name in PHRASE_BUCKETS}
    by_channel_terms: dict[str, Counter[str]] = defaultdict(Counter)

    started_values = []
    for clip in clips:
        channel_counts[clip.channel] += 1
        started_values.append(clip.started_at)
        local_time = _parse_utc(clip.started_at).astimezone(PACIFIC_TZ)
        hour_counts[f"{local_time.hour:02d}:00"] += 1
        day_counts[local_time.date().isoformat()] += 1
        tokens = _tokens(clip.transcript)
        unigrams.update(token for token in tokens if _countable_token(token))
        by_channel_terms[clip.channel].update(token for token in tokens if _countable_token(token))
        bigrams.update(_ngrams(tokens, 2))
        trigrams.update(_ngrams(tokens, 3))
        for name, pattern in PHRASE_BUCKETS.items():
            buckets[name].update(_bucket_hits(pattern, clip.transcript))

    source_min = min(started_values) if started_values else None
    source_max = max(started_values) if started_values else None
    payload = {
        "status": "ok",
        "generated_at": generated_at,
        "source_clip_count": len(clips),
        "source_min_started_at": source_min,
        "source_max_started_at": source_max,
        "channels": dict(
            sorted(channel_counts.items(), key=lambda item: _channel_sort_key(item[0]))
        ),
        "frequency": {
            "by_channel": dict(
                sorted(channel_counts.items(), key=lambda item: _channel_sort_key(item[0]))
            ),
            "by_hour_pacific": dict(sorted(hour_counts.items())),
            "by_day_pacific": dict(sorted(day_counts.items())),
        },
        "terms": {
            "unigrams": _counter_items(unigrams, limit=50),
            "bigrams": _counter_items(bigrams, limit=40),
            "trigrams": _counter_items(trigrams, limit=40),
            "semantic_buckets": {
                name: _counter_items(counts, limit=30) for name, counts in buckets.items()
            },
            "by_channel": {
                channel: _counter_items(counts, limit=24)
                for channel, counts in sorted(
                    by_channel_terms.items(),
                    key=lambda item: _channel_sort_key(item[0]),
                )
            },
        },
        "entities": _extract_entities(
            clips,
            public_audio_keys=_public_audio_keys(clips, limit=PUBLIC_AUDIO_EXAMPLE_LIMIT),
        ),
        "topics": {
            "status": "pending",
            "plot_url": TOPIC_PLOT_PATH,
            "items": [],
        },
        "education_guide": EDUCATION_GUIDE,
        "education": EDUCATION_RESOURCES,
    }
    return payload


def _build_topics(
    clips: list[TranscriptClip],
    *,
    html_output_path: Path,
    min_topic_documents: int = 40,
) -> dict[str, Any]:
    documents = [clip.transcript for clip in clips if clip.transcript.strip()]
    if len(documents) < min_topic_documents:
        _write_placeholder_topic_html(
            html_output_path,
            "Not enough transcript documents for BERTopic yet.",
        )
        return {
            "status": "skipped",
            "reason": "not enough documents for BERTopic",
            "plot_url": TOPIC_PLOT_PATH,
            "items": [],
        }
    try:
        from bertopic import BERTopic
        from plotly import graph_objects as go
        from sentence_transformers import SentenceTransformer
        from umap import UMAP
    except ImportError as exc:
        _write_placeholder_topic_html(
            html_output_path,
            f"BERTopic dependencies are not installed: {exc.name or type(exc).__name__}.",
        )
        return {
            "status": "skipped",
            "reason": f"BERTopic unavailable: {exc.name or type(exc).__name__}",
            "plot_url": TOPIC_PLOT_PATH,
            "items": [],
        }

    try:
        embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        embeddings = embedder.encode(documents, show_progress_bar=True)
        umap_model = UMAP(n_components=3, metric="cosine", random_state=42)
        topic_model = BERTopic(
            language="english",
            n_gram_range=(1, 2),
            top_n_words=12,
            min_topic_size=8,
            nr_topics=MAX_BERTOPIC_TOPICS,
            calculate_probabilities=False,
            umap_model=umap_model,
        )
        topics, _ = topic_model.fit_transform(documents, embeddings=embeddings)
        coordinates = umap_model.fit_transform(embeddings)
        marker_colors = [_topic_color(topic_id) for topic_id in topics]
        figure = go.Figure(
            data=[
                go.Scatter3d(
                    x=coordinates[:, 0],
                    y=coordinates[:, 1],
                    z=coordinates[:, 2],
                    mode="markers",
                    marker={
                        "size": 5,
                        "color": marker_colors,
                        "colorscale": "Turbo",
                        "opacity": 0.88,
                        "line": {"color": "rgba(7,17,15,0.45)", "width": 1},
                    },
                    text=[_short_text(doc, limit=160) for doc in documents],
                    customdata=[_topic_label(topic_id) for topic_id in topics],
                    hovertemplate="%{customdata}<br>%{text}<extra></extra>",
                )
            ],
            layout={
                "paper_bgcolor": "#07110f",
                "plot_bgcolor": "#07110f",
                "font": {"color": "#f2f7f4"},
                "dragmode": "orbit",
                "autosize": True,
                "scene": {
                    "camera": {"eye": {"x": 1.45, "y": 1.55, "z": 1.05}},
                    "bgcolor": "#07110f",
                    "xaxis": {
                        "showticklabels": False,
                        "title": "UMAP 1",
                        "gridcolor": "rgba(242,247,244,0.16)",
                        "zerolinecolor": "rgba(242,247,244,0.22)",
                    },
                    "yaxis": {
                        "showticklabels": False,
                        "title": "UMAP 2",
                        "gridcolor": "rgba(242,247,244,0.16)",
                        "zerolinecolor": "rgba(242,247,244,0.22)",
                    },
                    "zaxis": {
                        "showticklabels": False,
                        "title": "UMAP 3",
                        "gridcolor": "rgba(242,247,244,0.16)",
                        "zerolinecolor": "rgba(242,247,244,0.22)",
                    },
                },
                "margin": {"l": 0, "r": 0, "t": 8, "b": 0},
            },
        )
        _atomic_write_text(
            html_output_path,
            _mobile_topic_plot_html(
                figure.to_html(
                    full_html=True,
                    include_plotlyjs="cdn",
                    config={
                        "responsive": True,
                        "scrollZoom": True,
                        "displaylogo": False,
                        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                    },
                )
            ),
        )
        return {
            "status": "ok",
            "reason": None,
            "plot_url": TOPIC_PLOT_PATH,
            "items": _topic_items(
                topic_model,
                topics,
                documents,
                max_items=MAX_BERTOPIC_TOPICS,
            ),
        }
    except Exception as exc:  # noqa: BLE001 - keep analysis useful without model artifacts.
        _write_placeholder_topic_html(
            html_output_path,
            f"BERTopic analysis could not complete: {type(exc).__name__}.",
        )
        return {
            "status": "skipped",
            "reason": f"BERTopic failed: {type(exc).__name__}: {exc}",
            "plot_url": TOPIC_PLOT_PATH,
            "items": [],
        }


def _topic_color(topic_id: int) -> str:
    if topic_id == -1:
        return TOPIC_OUTLIER_COLOR
    return TOPIC_COLOR_PALETTE[int(topic_id) % len(TOPIC_COLOR_PALETTE)]


def _topic_label(topic_id: int) -> str:
    if topic_id == -1:
        return "Outliers"
    return f"Topic {topic_id}"


def _mobile_topic_plot_html(html_text: str) -> str:
    mobile_css = """
<style>
  html, body { min-height: 100%; margin: 0; background: #07110f; overflow: hidden; }
  .plotly-graph-div { width: 100vw !important; height: 100dvh !important; touch-action: none; }
  .modebar { transform: scale(1.08); transform-origin: top right; }
</style>
"""
    if "</head>" in html_text:
        return html_text.replace("</head>", f"{mobile_css}</head>", 1)
    return f"{mobile_css}{html_text}"


def _topic_items(
    topic_model: Any,
    topics: Sequence[int],
    documents: Sequence[str],
    *,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    counts = Counter(topics)
    items = []
    for topic_id, count in counts.most_common():
        if max_items is not None and len(items) >= max_items:
            break
        if topic_id == -1:
            label = "Outliers"
            words: list[str] = []
        else:
            label = f"Topic {topic_id}"
            words = [word for word, _score in topic_model.get_topic(topic_id)[:12]]
        examples = [
            {"text": _short_text(document, limit=260)}
            for document, assigned_topic in zip(documents, topics, strict=True)
            if assigned_topic == topic_id
        ][:3]
        items.append(
            {
                "id": int(topic_id),
                "label": label,
                "count": int(count),
                "top_words": words,
                "examples": examples,
            }
        )
    return items


def _write_placeholder_topic_html(path: Path, message: str) -> None:
    body = html.escape(message)
    _atomic_write_text(
        path,
        f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Elliott Bay VHF Topic Clusters</title>
    <style>
      html, body {{
        min-height: 100%;
        margin: 0;
        color: #f2f7f4;
        background: #07110f;
        font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      }}
      main {{
        display: grid;
        min-height: 100vh;
        place-items: center;
        padding: 24px;
        text-align: center;
      }}
      p {{
        max-width: 560px;
        color: #9fb1aa;
        line-height: 1.55;
      }}
    </style>
  </head>
  <body>
    <main>
      <div>
        <h1>Topic Clusters</h1>
        <p>{body}</p>
      </div>
    </main>
  </body>
</html>
""",
    )


def _extract_entities(
    clips: list[TranscriptClip],
    *,
    public_audio_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    entities: dict[str, dict[str, Any]] = {}
    playable_keys = public_audio_keys or set()

    def add(name: str, kind: str, clip: TranscriptClip) -> None:
        clean_name = " ".join(name.split())
        if clean_name in NON_ENTITY_PHRASES or len(clean_name) < 4:
            return
        item = entities.setdefault(
            clean_name,
            {
                "name": clean_name,
                "kind": kind,
                "count": 0,
                "channels": Counter(),
                "examples": [],
            },
        )
        item["count"] += 1
        item["channels"][clip.channel] += 1
        if len(item["examples"]) < 3:
            example = {
                "channel": clip.channel,
                "started_at": clip.started_at,
                "duration_seconds": clip.duration_seconds,
                "text": clip.transcript,
            }
            if clip.key in playable_keys:
                example["audio_public_filename"] = _public_audio_filename(clip)
            item["examples"].append(example)

    for clip in sorted(
        clips,
        key=lambda item: (item.key in playable_keys, item.started_at),
        reverse=True,
    ):
        for name, kind, pattern in KNOWN_ENTITY_PATTERNS:
            if pattern.search(clip.transcript):
                add(name, kind, clip)
        for match in VESSEL_NAME_RE.finditer(clip.transcript):
            add(match.group(0), "vessel", clip)

    ranked = []
    for item in entities.values():
        count = int(item["count"])
        confidence = _entity_confidence(kind=str(item["kind"]), count=count)
        ranked.append(
            {
                "name": item["name"],
                "kind": item["kind"],
                "count": count,
                "confidence": confidence,
                "channels": dict(
                    sorted(
                        item["channels"].items(),
                        key=lambda entry: _channel_sort_key(entry[0]),
                    )
                ),
                "examples": item["examples"],
            }
        )
    return sorted(
        ranked,
        key=lambda item: (item["count"], item["confidence"], item["name"]),
        reverse=True,
    )


def _public_audio_keys(clips: list[TranscriptClip], *, limit: int) -> set[str]:
    recent_public_clips = sorted(clips, key=lambda item: item.started_at, reverse=True)[:limit]
    return {clip.key for clip in recent_public_clips}


def _entity_confidence(*, kind: str, count: int) -> float:
    base = 0.8 if kind == "shore_station" else 0.62
    return round(min(0.99, base + min(count, 5) * 0.07), 2)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def _countable_token(token: str) -> bool:
    return token not in STOPWORDS and any(character.isalpha() for character in token)


def _ngrams(tokens: list[str], length: int) -> Iterable[str]:
    for index in range(len(tokens) - length + 1):
        gram = tokens[index : index + length]
        if any(token in STOPWORDS for token in gram):
            continue
        if not any(character.isalpha() for token in gram for character in token):
            continue
        yield " ".join(gram)


def _bucket_hits(pattern: re.Pattern[str], text: str) -> Iterable[str]:
    for match in pattern.finditer(text):
        yield " ".join(match.group(0).lower().split())


def _counter_items(counter: Counter[str], *, limit: int) -> list[dict[str, int | str]]:
    return [
        {"term": term, "count": int(count)}
        for term, count in counter.most_common(limit)
    ]


def _source_fingerprint(clips: list[TranscriptClip]) -> str:
    digest = hashlib.sha256()
    for clip in clips:
        digest.update(clip.key.encode("utf-8"))
        digest.update(b"\0")
        digest.update(clip.channel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(clip.started_at.encode("utf-8"))
        digest.update(b"\0")
        digest.update(clip.transcript.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _public_audio_filename(clip: TranscriptClip) -> str:
    started_at = _parse_utc(clip.started_at)
    stamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    channel = "".join(character.lower() for character in clip.channel if character.isalnum())
    digest = f"sha{hashlib.sha256(clip.key.encode('utf-8')).hexdigest()[:12]}"
    return f"{stamp}-vhf-{channel}-{digest}{_suffix_for_content_type(clip.content_type)}"


def _suffix_for_content_type(content_type: str) -> str:
    return {
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/aac": ".aac",
        "audio/flac": ".flac",
        "audio/m4a": ".m4a",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
    }.get(content_type, ".audio")


def _empty_buckets() -> dict[str, list[Any]]:
    return {name: [] for name in PHRASE_BUCKETS}


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("clip timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _channel_sort_key(channel: str) -> tuple[int, str]:
    digits = "".join(character for character in channel if character.isdigit())
    return (int(digits) if digits else 9999, channel)


def _short_text(text: str, *, limit: int) -> str:
    cleaned = " ".join(_public_text(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _public_text(text: str) -> str:
    cleaned = " ".join(text.split())
    cleaned = re.sub(r"\braw/channel=[^\s]+", "[redacted]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bX-Amz-[^\s]+", "[redacted]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"https?://(?:10\.|127\.0\.0\.1|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.)"
        r"[^\s]+",
        "[redacted]",
        cleaned,
    )
    cleaned = re.sub(r"\b\d{12}\b", "[redacted]", cleaned)
    return cleaned


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        tmp_path = Path(handle.name)
        handle.write(text)
    tmp_path.replace(path)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Elliott Bay VHF transcripts and cache public lexical artifacts."
    )
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/public-site"))
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    if not args.db_path.exists():
        parser.error(f"database does not exist: {args.db_path}")
    payload = generate_lexical_analysis(
        db_path=args.db_path,
        output_dir=args.output_dir,
        page_size=args.page_size,
        limit=args.limit,
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "source_clip_count": payload["source_clip_count"],
            }
        )
    )


if __name__ == "__main__":
    main()
