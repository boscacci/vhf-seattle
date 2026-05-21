import json
from pathlib import Path

from talkingboats.ais_history import (
    AisHistoryConfig,
    build_ais_tracks,
    build_erddap_url,
    load_ais_rows,
    write_tracks_json,
)


def test_build_erddap_url_targets_year_dataset_and_bbox() -> None:
    config = AisHistoryConfig(
        start="2024-07-01T00:00:00Z",
        end="2024-07-08T00:00:00Z",
        min_lat=47.565,
        max_lat=47.665,
        min_lon=-122.44,
        max_lon=-122.315,
    )

    url = build_erddap_url(config)

    assert "AIS2024_AIS.csv" in url
    assert "MMSI,time,Lat,Lon,SOG,COG,VesselName,VesselType" in url
    assert "time%3E%3D2024-07-01T00%3A00%3A00Z" in url
    assert "Lon%3C%3D-122.315" in url


def test_load_rows_skips_erddap_units_row_and_builds_tracks(tmp_path: Path) -> None:
    csv_path = tmp_path / "ais.csv"
    csv_path.write_text(
        "\n".join(
            [
                "MMSI,time,Lat,Lon,SOG,COG,VesselName,VesselType",
                ",UTC,,,,,,",
                "3671,2024-07-01T00:00:00Z,47.600,-122.400,5.0,90.0,FUN BOAT,37",
                "3671,2024-07-01T00:05:00Z,47.605,-122.390,6.0,91.0,FUN BOAT,37",
                "3669,2024-07-01T00:00:00Z,47.610,-122.380,8.0,180.0,TUG TEST,32",
                "3669,2024-07-01T00:05:00Z,47.615,-122.375,7.0,181.0,TUG TEST,32",
                "bad,2024-07-01T00:05:00Z,not-a-lat,-122.375,7.0,181.0,BAD,32",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = load_ais_rows(csv_path)
    tracks = build_ais_tracks(rows, max_tracks=10, min_points=2)

    assert len(rows) == 4
    assert {track["track_id"] for track in tracks} == {"real-ais-3671", "real-ais-3669"}
    fun_track = next(track for track in tracks if track["track_id"] == "real-ais-3671")
    tug_track = next(track for track in tracks if track["track_id"] == "real-ais-3669")
    assert fun_track["channel_hint"] == "68"
    assert fun_track["vessel_type"] == "pleasure-craft"
    assert tug_track["channel_hint"] == "14"
    assert tug_track["vessel_type"] == "tug"
    assert fun_track["points"][0]["observed_at"] == "2024-07-01T00:00:00Z"


def test_write_tracks_json_and_patch_manifest(tmp_path: Path) -> None:
    tracks = [
        {
            "track_id": "real-ais-3671",
            "mmsi": "3671",
            "name": "FUN BOAT",
            "vessel_type": "pleasure-craft",
            "channel_hint": "68",
            "points": [
                {
                    "observed_at": "2024-07-01T00:00:00Z",
                    "lat": 47.6,
                    "lon": -122.4,
                    "speed_knots": 5.0,
                    "course_degrees": 90.0,
                }
            ],
        }
    ]
    output_path = tmp_path / "tracks.json"
    manifest_path = tmp_path / "private_manifest.json"
    manifest_path.write_text(json.dumps({"clips": []}), encoding="utf-8")

    write_tracks_json(tracks, output_path, private_manifest_path=manifest_path)

    assert json.loads(output_path.read_text(encoding="utf-8"))["ais_tracks"] == tracks
    patched = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert patched["ais_tracks"] == tracks
