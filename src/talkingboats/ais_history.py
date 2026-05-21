from __future__ import annotations

import argparse
import csv
import json
import math
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

ERDDAP_BASE_URL = "https://data.pmel.noaa.gov/pmel/erddap/tabledap"
AIS_COLUMNS = ("MMSI", "time", "Lat", "Lon", "SOG", "COG", "VesselName", "VesselType")

VESSEL_TYPES = {
    "30": "fishing",
    "31": "tug",
    "32": "tug",
    "36": "sailing",
    "37": "pleasure-craft",
    "52": "tug",
    "60": "passenger",
    "70": "cargo",
    "71": "cargo",
    "72": "cargo",
    "73": "cargo",
    "74": "cargo",
    "79": "cargo",
    "80": "tanker",
}


@dataclass(frozen=True)
class AisHistoryConfig:
    start: str
    end: str
    min_lat: float = 47.565
    max_lat: float = 47.665
    min_lon: float = -122.44
    max_lon: float = -122.315

    @property
    def year(self) -> int:
        start_year = int(self.start[:4])
        end_year = int(self.end[:4])
        if start_year != end_year:
            raise ValueError("start and end must be in the same ERDDAP AIS dataset year")
        return start_year


def build_erddap_url(config: AisHistoryConfig) -> str:
    dataset = f"AIS{config.year}_AIS.csv"
    query = ",".join(AIS_COLUMNS)
    constraints = [
        f"time>={config.start}",
        f"time<{config.end}",
        f"Lat>={config.min_lat}",
        f"Lat<={config.max_lat}",
        f"Lon>={config.min_lon}",
        f"Lon<={config.max_lon}",
    ]
    return (
        f"{ERDDAP_BASE_URL}/{dataset}?"
        f"{quote(query, safe=',')}&"
        f"{'&'.join(quote(constraint, safe='') for constraint in constraints)}"
    )


def fetch_ais_csv(config: AisHistoryConfig, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    url = build_erddap_url(config)
    with urllib.request.urlopen(url, timeout=240) as response:
        output_path.write_bytes(response.read())
    return url


def load_ais_rows(csv_path: Path) -> list[dict[str, Any]]:
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("time") == "UTC" or not row.get("MMSI"):
                continue
            try:
                rows.append(
                    {
                        "mmsi": row["MMSI"].strip(),
                        "observed_at": row["time"].strip(),
                        "lat": float(row["Lat"]),
                        "lon": float(row["Lon"]),
                        "speed_knots": _optional_float(row.get("SOG")),
                        "course_degrees": _optional_float(row.get("COG")),
                        "name": row.get("VesselName", "").strip() or row["MMSI"].strip(),
                        "vessel_type_code": row.get("VesselType", "").strip(),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def build_ais_tracks(
    rows: list[dict[str, Any]],
    *,
    max_tracks: int = 16,
    min_points: int = 2,
    max_points_per_track: int = 48,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["mmsi"]].append(row)

    candidates = []
    for mmsi, points in grouped.items():
        sorted_points = sorted(points, key=lambda point: point["observed_at"])
        if len(sorted_points) < min_points:
            continue
        distance_nm = _track_distance_nm(sorted_points)
        max_speed = max((point.get("speed_knots") or 0.0 for point in sorted_points), default=0.0)
        if distance_nm < 0.05 and max_speed < 0.5:
            continue
        candidates.append(
            {
                "mmsi": mmsi,
                "points": sorted_points,
                "distance_nm": distance_nm,
                "max_speed": max_speed,
            }
        )

    candidates.sort(
        key=lambda item: (item["distance_nm"], item["max_speed"], len(item["points"])),
        reverse=True,
    )
    tracks = []
    for candidate in candidates[:max_tracks]:
        points = _sample_points(candidate["points"], max_points_per_track)
        type_code = _mode(point["vessel_type_code"] for point in points)
        vessel_type = VESSEL_TYPES.get(type_code, "unknown")
        tracks.append(
            {
                "track_id": f"real-ais-{candidate['mmsi']}",
                "mmsi": candidate["mmsi"],
                "name": _mode(point["name"] for point in points) or candidate["mmsi"],
                "vessel_type": vessel_type,
                "channel_hint": _channel_hint(type_code),
                "points": [
                    {
                        "observed_at": point["observed_at"],
                        "lat": point["lat"],
                        "lon": point["lon"],
                        "speed_knots": point.get("speed_knots"),
                        "course_degrees": point.get("course_degrees"),
                    }
                    for point in points
                ],
            }
        )
    return tracks


def write_tracks_json(
    tracks: list[dict[str, Any]],
    output_path: Path,
    *,
    private_manifest_path: Path | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"ais_tracks": tracks}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if private_manifest_path:
        manifest = json.loads(private_manifest_path.read_text(encoding="utf-8"))
        manifest["ais_tracks"] = tracks
        private_manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _sample_points(points: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(points) <= limit:
        return points
    indexes = {
        round(index * (len(points) - 1) / (limit - 1))
        for index in range(limit)
    }
    return [points[index] for index in sorted(indexes)]


def _track_distance_nm(points: list[dict[str, Any]]) -> float:
    distance = 0.0
    for index in range(1, len(points)):
        distance += _haversine_nm(points[index - 1], points[index])
    return distance


def _haversine_nm(a: dict[str, Any], b: dict[str, Any]) -> float:
    radius_nm = 3440.065
    lat1 = math.radians(a["lat"])
    lat2 = math.radians(b["lat"])
    d_lat = lat2 - lat1
    d_lon = math.radians(b["lon"] - a["lon"])
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * radius_nm * math.asin(math.sqrt(h))


def _mode(values) -> str:
    cleaned = [value for value in values if value]
    if not cleaned:
        return ""
    return Counter(cleaned).most_common(1)[0][0]


def _optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _channel_hint(type_code: str) -> str:
    return "68" if type_code in {"36", "37"} else "14"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a bbox-filtered historical AIS slice from NOAA PMEL ERDDAP."
    )
    parser.add_argument("--start", default="2024-07-01T00:00:00Z")
    parser.add_argument("--end", default="2024-07-08T00:00:00Z")
    parser.add_argument("--raw-csv", type=Path, required=True)
    parser.add_argument("--tracks-json", type=Path, required=True)
    parser.add_argument("--private-manifest", type=Path)
    parser.add_argument("--max-tracks", type=int, default=16)
    parser.add_argument("--min-points", type=int, default=2)
    parser.add_argument("--max-points-per-track", type=int, default=48)
    parser.add_argument("--use-existing", action="store_true")
    args = parser.parse_args()

    config = AisHistoryConfig(start=args.start, end=args.end)
    if not args.use_existing or not args.raw_csv.exists():
        url = fetch_ais_csv(config, args.raw_csv)
        print(f"Fetched {url}")

    rows = load_ais_rows(args.raw_csv)
    tracks = build_ais_tracks(
        rows,
        max_tracks=args.max_tracks,
        min_points=args.min_points,
        max_points_per_track=args.max_points_per_track,
    )
    write_tracks_json(tracks, args.tracks_json, private_manifest_path=args.private_manifest)
    print(
        json.dumps(
            {
                "raw_csv": str(args.raw_csv),
                "rows": len(rows),
                "tracks": len(tracks),
                "tracks_json": str(args.tracks_json),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
