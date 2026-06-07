from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from talkingboats.audio_dsp import build_ffmpeg_dsp_command, dsp_profile_for_name
from talkingboats.channel_metadata import CHANNEL_METADATA, VOICE_NET_BALANCED_CHANNELS

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIP_CONSOLE_DIR = REPO_ROOT / "public-site"
DEFAULT_PERFORMANCE_HISTORY_DB_PATH = REPO_ROOT / "data" / "performance_telemetry.sqlite3"
SHELL_ASSET_TYPES = {
    "index.html": "text/html",
    "assets/app.js": "application/javascript",
    "assets/styles.css": "text/css",
    "public_manifest.json": "application/json",
}
PERFORMANCE_DISK_PATHS = (
    ("system", Path("/")),
    ("home", Path("/home/rob")),
    ("talkingboats spool", Path("/opt/talkingboats")),
)
TAILNET_DEV_API_HOSTS = ("optiplex.tailbea63b.ts.net",)
PERFORMANCE_DEV_HOSTS = (
    "vhf-dev.robertboscacci.com",
    "localhost",
    "127.0.0.1",
    "testserver",
    "",
    *TAILNET_DEV_API_HOSTS,
)
PERFORMANCE_DEV_ORIGIN_HOSTS = TAILNET_DEV_API_HOSTS
OPTIPLEX_PERFORMANCE_ROLE = "OptiPlex ASR Box"
PI_PERFORMANCE_ROLE = "Raspberry Pi Decoder"
PERFORMANCE_PUBLIC_ROLES = (OPTIPLEX_PERFORMANCE_ROLE, PI_PERFORMANCE_ROLE)
PERFORMANCE_ROLE_ALIASES = {
    "OptiPlex live proxy": OPTIPLEX_PERFORMANCE_ROLE,
    "Raspberry Pi edge radio": PI_PERFORMANCE_ROLE,
}
PERFORMANCE_PUBLIC_STATUSES = {"ok", "watch", "high", "unknown"}
TAILSCALE_IDENTITY_HEADER = "tailscale-user-login"
TAILNET_DEV_PROXY_HEADER = "x-talkingboats-tailnet-dev"
TAILNET_OPERATOR_LOCAL_HOSTS = {
    "",
    "localhost",
    "127.0.0.1",
    "testserver",
    *TAILNET_DEV_API_HOSTS,
}
PERFORMANCE_SAMPLE_INTERVAL_SECONDS = 5.0
PERFORMANCE_MEMORY_HISTORY_SECONDS = 6 * 60 * 60
PERFORMANCE_PERSIST_INTERVAL_SECONDS = 60.0
PERFORMANCE_PERSIST_HISTORY_SECONDS = 24 * 60 * 60
PERFORMANCE_PUBLIC_HISTORY_LIMIT = 6_000
PI_PERFORMANCE_SCRIPT = r"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


def threshold_status(value, watch_at, high_at):
    if value >= high_at:
        return "high"
    if value >= watch_at:
        return "watch"
    return "ok"


def worst_status(statuses):
    rank = {"unknown": 0, "ok": 1, "watch": 2, "high": 3}
    return max(statuses or ["unknown"], key=lambda status: rank.get(status, 0))


def load_snapshot():
    cpu_count = os.cpu_count() or 1
    try:
        one_minute, five_minute, fifteen_minute = os.getloadavg()
    except OSError:
        return {"status": "unknown"}
    per_cpu = one_minute / cpu_count
    return {
        "oneMinute": round(one_minute, 2),
        "fiveMinute": round(five_minute, 2),
        "fifteenMinute": round(fifteen_minute, 2),
        "perCpu": round(per_cpu, 2),
        "status": threshold_status(per_cpu, watch_at=0.75, high_at=1.0),
    }


def cpu_times():
    try:
        fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
    except OSError:
        return None
    values = [int(value) for value in fields[:8]]
    idle = values[3] + values[4]
    return sum(values), idle


def cpu_snapshot():
    first = cpu_times()
    if first is None:
        return {"status": "unknown"}
    time.sleep(0.1)
    second = cpu_times()
    if second is None:
        return {"status": "unknown"}
    total_delta = second[0] - first[0]
    idle_delta = second[1] - first[1]
    if total_delta <= 0:
        return {"status": "unknown"}
    utilization = max(0.0, min(100.0, (1 - (idle_delta / total_delta)) * 100))
    return {
        "utilizationPercent": round(utilization, 1),
        "status": threshold_status(utilization, watch_at=75.0, high_at=90.0),
    }


def meminfo():
    values = {}
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        name, separator, raw_value = line.partition(":")
        if not separator:
            continue
        parts = raw_value.strip().split()
        if not parts:
            continue
        try:
            values[name] = int(parts[0]) * 1024
        except ValueError:
            continue
    return values


def memory_snapshot():
    values = meminfo()
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return {"status": "unknown"}
    used_percent = ((total - available) / total) * 100
    return {
        "totalBytes": total,
        "availableBytes": available,
        "usedPercent": round(used_percent, 1),
        "status": threshold_status(used_percent, watch_at=75.0, high_at=90.0),
    }


def disk_snapshots():
    disks = []
    seen_devices = set()
    for label, path in (("system", Path("/")), ("talkingboats spool", Path("/opt/talkingboats"))):
        if not path.exists():
            continue
        try:
            device = path.stat().st_dev
        except OSError:
            continue
        if device in seen_devices:
            continue
        seen_devices.add(device)
        usage = shutil.disk_usage(path)
        used_percent = (usage.used / usage.total) * 100 if usage.total else 0.0
        disks.append(
            {
                "label": label,
                "totalBytes": usage.total,
                "freeBytes": usage.free,
                "usedPercent": round(used_percent, 1),
                "status": threshold_status(used_percent, watch_at=80.0, high_at=90.0),
            }
        )
    return disks


def thermal_snapshot():
    temperature = None
    try:
        raw_temp = Path("/sys/class/thermal/thermal_zone0/temp").read_text(encoding="utf-8")
        temperature = round(int(raw_temp.strip()) / 1000, 1)
    except (OSError, ValueError):
        try:
            result = subprocess.run(
                ["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=1
            )
            marker = result.stdout.strip().partition("=")[2].replace("'C", "")
            temperature = round(float(marker), 1)
        except (FileNotFoundError, subprocess.SubprocessError, ValueError):
            temperature = None
    throttled = "unknown"
    try:
        result = subprocess.run(
            ["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=1
        )
        throttled = result.stdout.strip().partition("=")[2] or "unknown"
    except (FileNotFoundError, subprocess.SubprocessError):
        throttled = "unknown"
    status = "unknown"
    if temperature is not None:
        status = threshold_status(temperature, watch_at=70.0, high_at=85.0)
    if throttled not in {"", "0x0", "unknown"}:
        status = worst_status([status, "watch"])
    return {"temperatureC": temperature, "throttled": throttled, "status": status}


load = load_snapshot()
cpu = cpu_snapshot()
memory = memory_snapshot()
disks = disk_snapshots()
thermal = thermal_snapshot()
statuses = [
    load.get("status", "unknown"),
    cpu.get("status", "unknown"),
    memory.get("status", "unknown"),
]
statuses.extend(disk.get("status", "unknown") for disk in disks)
statuses.append(thermal.get("status", "unknown"))
print(
    json.dumps(
        {
            "role": "Raspberry Pi Decoder",
            "reachable": True,
            "status": worst_status([str(status) for status in statuses]),
            "cpuCount": os.cpu_count() or 1,
            "cpu": cpu,
            "load": load,
            "memory": memory,
            "disks": disks,
            "thermal": thermal,
        },
        sort_keys=True,
    )
)
"""


@dataclass(frozen=True)
class ChannelPreset:
    id: str
    channel: str
    label: str
    frequency_hz: int
    description: str
    squelch: int = 0
    audio_filter_enabled: bool = True

    @property
    def frequency_mhz(self) -> str:
        return f"{self.frequency_hz / 1_000_000:.3f}"

    def to_config(self) -> dict[str, str]:
        return {
            "id": self.id,
            "channel": self.channel,
            "label": self.label,
            "frequencyMhz": self.frequency_mhz,
            "description": self.description,
        }


_CHANNEL_PRESET_IDS = {
    "05A": "vts_05a",
    "06": "intership_06",
    "09": "calling_09",
    "10": "commercial_10",
    "13": "bridge_13",
    "14": "vts_14",
    "16": "safety_16",
    "22A": "uscg_22a",
    "65A": "portops_65a",
    "66A": "portops_66a",
    "67": "commercial_67",
    "68": "recreation_68",
    "69": "noncommercial_69",
    "71": "noncommercial_71",
    "72": "ship_72",
    "73": "portops_73",
    "74": "portops_74",
    "77": "ship_77",
    "78A": "noncommercial_78a",
}
_CHANNEL_DESCRIPTIONS = {
    "05A": "Puget Sound traffic and port coordination.",
    "06": "Intership safety calls.",
    "09": "Calling and commercial traffic.",
    "10": "Commercial working traffic.",
    "13": "Navigation safety between commercial vessels.",
    "14": "Vessel traffic and harbor movements.",
    "16": "Safety hailing and distress watch.",
    "22A": "Coast Guard working broadcasts after hailing.",
    "65A": "Port operations and harbor coordination.",
    "66A": "Port operations and harbor coordination.",
    "67": "Commercial and bridge coordination.",
    "68": "Local recreational vessel traffic.",
    "69": "Non-commercial vessel traffic.",
    "71": "Non-commercial vessel traffic.",
    "72": "Ship-to-ship working traffic.",
    "73": "Port operations and harbor coordination.",
    "74": "Port operations and harbor coordination.",
    "77": "Ship-to-ship working traffic.",
    "78A": "Non-commercial vessel traffic.",
}
DEFAULT_CHANNELS = tuple(
    ChannelPreset(
        id=_CHANNEL_PRESET_IDS[channel],
        channel=metadata.channel,
        label=metadata.label,
        frequency_hz=metadata.frequency_hz,
        description=_CHANNEL_DESCRIPTIONS[channel],
    )
    for channel in VOICE_NET_BALANCED_CHANNELS
    if (metadata := CHANNEL_METADATA.get(channel)) is not None
)


def _default_channel_stream_urls() -> dict[str, tuple[str, ...]]:
    channels = {
        channel: (f"http://192.168.1.114:8000/talkingboats-{channel.lower()}.mp3",)
        for channel in VOICE_NET_BALANCED_CHANNELS
    }
    channels["14"] = (
        "http://192.168.1.114:8000/talkingboats-live.mp3",
        "http://192.168.1.114:8000/talkingboats-14.mp3",
    )
    return channels


@dataclass(frozen=True)
class ProxySettings:
    stream_url: str = "http://192.168.1.114:8000/talkingboats-live.mp3"
    stream_urls: tuple[str, ...] = (
        "http://192.168.1.114:8000/talkingboats-live.mp3",
        "http://192.168.1.114:8000/talkingboats-14.mp3",
    )
    channel_stream_urls: dict[str, tuple[str, ...]] = field(
        default_factory=_default_channel_stream_urls
    )
    receiver_status_url: str = "http://192.168.1.114:8050/current-status.json"
    transcript_url: str = "http://127.0.0.1:8055/api/live-transcript"
    private_api_url: str = "http://192.168.1.247:8034"
    ais_catcher_base_url: str = "http://192.168.1.114:8100"
    ais_catcher_dev_hosts: tuple[str, ...] = PERFORMANCE_DEV_HOSTS
    ais_catcher_dev_origin_hosts: tuple[str, ...] = PERFORMANCE_DEV_ORIGIN_HOSTS
    active_channel_id: str = "recreation_68"
    retune_ssh_target: str = "192.168.1.114"
    pi_env_path: str = "/etc/talkingboats/live-radio.env"
    ffmpeg_path: str = "ffmpeg"
    restart_transcriber_service: bool = True
    enable_debug_endpoints: bool = False
    tailnet_dev_routes_enabled: bool = False
    performance_background_enabled: bool = True
    performance_sample_interval_seconds: float = PERFORMANCE_SAMPLE_INTERVAL_SECONDS
    performance_memory_history_seconds: int = PERFORMANCE_MEMORY_HISTORY_SECONDS
    performance_persist_interval_seconds: float = PERFORMANCE_PERSIST_INTERVAL_SECONDS
    performance_persist_history_seconds: int = PERFORMANCE_PERSIST_HISTORY_SECONDS
    performance_history_db_path: str = str(DEFAULT_PERFORMANCE_HISTORY_DB_PATH)
    public_site_dir: str = str(REPO_ROOT / "outputs/public-site")
    performance_dev_hosts: tuple[str, ...] = PERFORMANCE_DEV_HOSTS
    performance_dev_origin_hosts: tuple[str, ...] = PERFORMANCE_DEV_ORIGIN_HOSTS
    cors_origins: tuple[str, ...] = (
        "https://vhf.robertboscacci.com",
        "https://vhf-dev.robertboscacci.com",
    )

    @classmethod
    def from_env(cls) -> ProxySettings:
        stream_url = os.environ.get("TALKINGBOATS_PROXY_STREAM_URL", cls.stream_url)
        stream_urls = _env_csv("TALKINGBOATS_PROXY_STREAM_URLS") or (stream_url, *cls.stream_urls)
        stream_urls = _dedupe(stream_urls)
        channel_stream_urls = _env_channel_stream_urls("TALKINGBOATS_PROXY_CHANNEL_STREAM_URLS")
        if not channel_stream_urls:
            channel_stream_urls = _default_channel_stream_urls()
            channel_stream_urls["14"] = stream_urls
        return cls(
            stream_url=stream_url,
            stream_urls=stream_urls,
            channel_stream_urls=channel_stream_urls,
            receiver_status_url=os.environ.get(
                "TALKINGBOATS_PROXY_RECEIVER_STATUS_URL",
                cls.receiver_status_url,
            ),
            transcript_url=os.environ.get(
                "TALKINGBOATS_PROXY_TRANSCRIPT_URL",
                cls.transcript_url,
            ),
            private_api_url=os.environ.get(
                "TALKINGBOATS_PROXY_PRIVATE_API_URL",
                cls.private_api_url,
            ),
            ais_catcher_base_url=os.environ.get(
                "TALKINGBOATS_PROXY_AIS_CATCHER_BASE_URL",
                cls.ais_catcher_base_url,
            ),
            ais_catcher_dev_hosts=_env_csv("TALKINGBOATS_PROXY_AIS_CATCHER_DEV_HOSTS")
            or cls.ais_catcher_dev_hosts,
            ais_catcher_dev_origin_hosts=_env_csv("TALKINGBOATS_PROXY_AIS_CATCHER_DEV_ORIGIN_HOSTS")
            or cls.ais_catcher_dev_origin_hosts,
            active_channel_id=os.environ.get(
                "TALKINGBOATS_PROXY_ACTIVE_CHANNEL_ID",
                cls.active_channel_id,
            ),
            retune_ssh_target=os.environ.get(
                "TALKINGBOATS_PROXY_RETUNE_SSH_TARGET",
                cls.retune_ssh_target,
            ),
            ffmpeg_path=os.environ.get("TALKINGBOATS_PROXY_FFMPEG_PATH", cls.ffmpeg_path),
            restart_transcriber_service=_env_bool("TALKINGBOATS_PROXY_RESTART_TRANSCRIBER", True),
            enable_debug_endpoints=_env_bool("TALKINGBOATS_PROXY_ENABLE_DEBUG_ENDPOINTS", False),
            tailnet_dev_routes_enabled=_env_bool(
                "TALKINGBOATS_PROXY_TAILNET_DEV_ROUTES_ENABLED",
                cls.tailnet_dev_routes_enabled,
            ),
            performance_background_enabled=_env_bool(
                "TALKINGBOATS_PROXY_PERFORMANCE_BACKGROUND_ENABLED",
                cls.performance_background_enabled,
            ),
            performance_sample_interval_seconds=_env_float(
                "TALKINGBOATS_PROXY_PERFORMANCE_SAMPLE_INTERVAL_SECONDS",
                cls.performance_sample_interval_seconds,
            ),
            performance_memory_history_seconds=_env_int(
                "TALKINGBOATS_PROXY_PERFORMANCE_MEMORY_HISTORY_SECONDS",
                cls.performance_memory_history_seconds,
            ),
            performance_persist_interval_seconds=_env_float(
                "TALKINGBOATS_PROXY_PERFORMANCE_PERSIST_INTERVAL_SECONDS",
                cls.performance_persist_interval_seconds,
            ),
            performance_persist_history_seconds=_env_int(
                "TALKINGBOATS_PROXY_PERFORMANCE_PERSIST_HISTORY_SECONDS",
                cls.performance_persist_history_seconds,
            ),
            performance_history_db_path=os.environ.get(
                "TALKINGBOATS_PROXY_PERFORMANCE_HISTORY_DB_PATH",
                cls.performance_history_db_path,
            ),
            public_site_dir=os.environ.get(
                "TALKINGBOATS_PROXY_PUBLIC_SITE_DIR",
                os.environ.get("TALKINGBOATS_PUBLIC_SITE_DIR", cls.public_site_dir),
            ),
            performance_dev_hosts=_env_csv("TALKINGBOATS_PROXY_PERFORMANCE_DEV_HOSTS")
            or cls.performance_dev_hosts,
            performance_dev_origin_hosts=_env_csv("TALKINGBOATS_PROXY_PERFORMANCE_DEV_ORIGIN_HOSTS")
            or cls.performance_dev_origin_hosts,
            cors_origins=_env_csv("TALKINGBOATS_PROXY_CORS_ORIGINS") or cls.cors_origins,
        )


@dataclass(frozen=True)
class RetuneResult:
    restarted_transcriber: bool = False


class RetuneRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64)


ClientFactory = Callable[[], httpx.AsyncClient]
Retuner = Callable[[ChannelPreset, ProxySettings], RetuneResult]
PerformanceCollector = Callable[[ProxySettings], dict[str, object]]


class PerformanceHistoryStore:
    def __init__(
        self,
        *,
        db_path: Path | None = DEFAULT_PERFORMANCE_HISTORY_DB_PATH,
        memory_history_seconds: int = PERFORMANCE_MEMORY_HISTORY_SECONDS,
        persist_interval_seconds: float = PERFORMANCE_PERSIST_INTERVAL_SECONDS,
        persist_history_seconds: int = PERFORMANCE_PERSIST_HISTORY_SECONDS,
    ) -> None:
        self._db_path = db_path
        self._memory_history_seconds = memory_history_seconds
        self._persist_interval_seconds = persist_interval_seconds
        self._persist_history_seconds = persist_history_seconds
        self._samples: dict[str, deque[dict[str, object]]] = {}
        self._last_persist_epoch: dict[str, float] = {}
        self._latest_payload: dict[str, object] | None = None
        self._sampler_task: asyncio.Task[None] | None = None
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: ProxySettings) -> PerformanceHistoryStore:
        db_path = Path(settings.performance_history_db_path).expanduser()
        return cls(
            db_path=db_path if settings.performance_history_db_path else None,
            memory_history_seconds=settings.performance_memory_history_seconds,
            persist_interval_seconds=settings.performance_persist_interval_seconds,
            persist_history_seconds=settings.performance_persist_history_seconds,
        )

    def running(self) -> bool:
        return self._sampler_task is not None and not self._sampler_task.done()

    def start_background_sampler(
        self,
        settings: ProxySettings,
        collector: PerformanceCollector,
    ) -> None:
        if self.running() or settings.performance_sample_interval_seconds <= 0:
            return
        self._sampler_task = asyncio.create_task(self._sample_loop(settings, collector))

    async def stop_background_sampler(self) -> None:
        task = self._sampler_task
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._sampler_task = None

    async def _sample_loop(
        self,
        settings: ProxySettings,
        collector: PerformanceCollector,
    ) -> None:
        while True:
            try:
                await self.capture_async(settings, collector)
            except Exception as exc:  # pragma: no cover - defensive runtime logging
                print(
                    json.dumps(
                        {
                            "event": "performance_sampler_failed",
                            "error_type": type(exc).__name__,
                        }
                    )
                )
            await asyncio.sleep(settings.performance_sample_interval_seconds)

    async def payload_for_request(
        self,
        settings: ProxySettings,
        collector: PerformanceCollector,
    ) -> dict[str, object]:
        if self.running():
            latest = self.latest_payload()
            if latest is not None:
                return latest
        return await self.capture_async(settings, collector)

    async def capture_async(
        self,
        settings: ProxySettings,
        collector: PerformanceCollector,
    ) -> dict[str, object]:
        return await asyncio.to_thread(self.capture, settings, collector)

    def capture(
        self,
        settings: ProxySettings,
        collector: PerformanceCollector,
    ) -> dict[str, object]:
        return self.record(collector(settings))

    def latest_payload(self) -> dict[str, object] | None:
        with self._lock:
            if self._latest_payload is None:
                return None
            return dict(self._latest_payload)

    def record(self, payload: dict[str, object]) -> dict[str, object]:
        if not isinstance(payload, dict):
            payload = {}
        generated_at = _public_generated_at(payload.get("generatedAt"))
        generated_epoch = _performance_sample_epoch(generated_at)
        hosts = _raw_performance_hosts(payload)
        public_hosts: list[dict[str, object]] = []
        with self._lock:
            for index, host in enumerate(hosts):
                key = _performance_history_key(host, index)
                role = _performance_history_role(host, index)
                samples = self._samples.setdefault(key, deque())
                sample = _performance_history_sample(generated_at, generated_epoch, host)
                samples.append(sample)
                self._trim_memory_samples(samples, generated_epoch)
                self._persist_sample_if_due(key, role, sample)
                host_with_history = dict(host)
                host_with_history["history"] = self._combined_history(key, samples, generated_epoch)
                public_hosts.append(host_with_history)
        payload_with_history = dict(payload)
        if public_hosts:
            payload_with_history["hosts"] = public_hosts
            payload_with_history["host"] = public_hosts[0]
        self._latest_payload = payload_with_history
        return payload_with_history

    def _trim_memory_samples(
        self,
        samples: deque[dict[str, object]],
        generated_epoch: float,
    ) -> None:
        cutoff = generated_epoch - self._memory_history_seconds
        while samples and _sample_epoch(samples[0]) < cutoff:
            samples.popleft()

    def _persist_sample_if_due(
        self,
        host_key: str,
        role: str,
        sample: dict[str, object],
    ) -> None:
        if self._db_path is None or self._persist_interval_seconds <= 0:
            return
        generated_epoch = _sample_epoch(sample)
        last_persisted = self._last_persist_epoch.get(host_key)
        if (
            last_persisted is not None
            and generated_epoch - last_persisted < self._persist_interval_seconds
        ):
            return
        self._ensure_database()
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO performance_telemetry_samples (
                    generated_at,
                    generated_epoch,
                    host_key,
                    host_role,
                    cpu_utilization_percent,
                    memory_used_percent,
                    thermal_temperature_c
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample["generatedAt"],
                    generated_epoch,
                    host_key,
                    role,
                    sample.get("cpuUtilizationPercent"),
                    sample.get("memoryUsedPercent"),
                    sample.get("thermalTemperatureC"),
                ),
            )
            cutoff = generated_epoch - self._persist_history_seconds
            connection.execute(
                "DELETE FROM performance_telemetry_samples WHERE generated_epoch < ?",
                (cutoff,),
            )
        self._last_persist_epoch[host_key] = generated_epoch

    def _combined_history(
        self,
        host_key: str,
        memory_samples: deque[dict[str, object]],
        generated_epoch: float,
    ) -> list[dict[str, object]]:
        combined: dict[str, dict[str, object]] = {}
        for sample in self._load_persisted_history(host_key, generated_epoch):
            combined[str(sample["generatedAt"])] = sample
        for sample in memory_samples:
            combined[str(sample["generatedAt"])] = dict(sample)
        return sorted(combined.values(), key=_sample_epoch)[-PERFORMANCE_PUBLIC_HISTORY_LIMIT:]

    def _load_persisted_history(
        self,
        host_key: str,
        generated_epoch: float,
    ) -> list[dict[str, object]]:
        if self._db_path is None or not self._db_path.exists():
            return []
        cutoff = generated_epoch - self._persist_history_seconds
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    generated_at,
                    generated_epoch,
                    cpu_utilization_percent,
                    memory_used_percent,
                    thermal_temperature_c
                FROM performance_telemetry_samples
                WHERE host_key = ? AND generated_epoch >= ?
                ORDER BY generated_epoch
                """,
                (host_key, cutoff),
            ).fetchall()
        history = []
        for generated_at, epoch, cpu, memory, thermal in rows:
            sample: dict[str, object] = {
                "generatedAt": generated_at,
                "_epoch": float(epoch),
            }
            if cpu is not None:
                sample["cpuUtilizationPercent"] = float(cpu)
            if memory is not None:
                sample["memoryUsedPercent"] = float(memory)
            if thermal is not None:
                sample["thermalTemperatureC"] = float(thermal)
            history.append(sample)
        return history

    def _ensure_database(self) -> None:
        if self._db_path is None:
            return
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS performance_telemetry_samples (
                    id INTEGER PRIMARY KEY,
                    generated_at TEXT NOT NULL,
                    generated_epoch REAL NOT NULL,
                    host_key TEXT NOT NULL,
                    host_role TEXT NOT NULL,
                    cpu_utilization_percent REAL,
                    memory_used_percent REAL,
                    thermal_temperature_c REAL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_performance_telemetry_host_epoch
                ON performance_telemetry_samples (host_key, generated_epoch)
                """
            )


def create_app(
    settings: ProxySettings | None = None,
    *,
    client_factory: ClientFactory | None = None,
    retuner: Retuner | None = None,
    performance_collector: PerformanceCollector | None = None,
) -> FastAPI:
    settings = settings or ProxySettings.from_env()
    client_factory = client_factory or _default_client
    retuner = retuner or retune_pi
    performance_collector = performance_collector or collect_performance_snapshot
    performance_history = PerformanceHistoryStore.from_settings(settings)
    retune_lock = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        if settings.performance_background_enabled:
            performance_history.start_background_sampler(settings, performance_collector)
        try:
            yield
        finally:
            await performance_history.stop_background_sampler()

    app = FastAPI(
        title="Talking Boats Tailnet Radio Proxy",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.performance_history = performance_history
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/clips/recent")
    async def recent_clips(request: Request) -> Response:
        return await _proxy_private_api(request, "/api/clips/recent", settings, client_factory)

    @app.get("/api/clips/playback")
    async def clip_playback(request: Request) -> Response:
        return await _proxy_private_api(request, "/api/clips/playback", settings, client_factory)

    @app.get("/api/clips/audio")
    async def clip_audio(request: Request) -> Response:
        return await _proxy_private_api(request, "/api/clips/audio", settings, client_factory)

    if settings.tailnet_dev_routes_enabled:

        @app.post("/api/clips/corrections")
        async def clip_correction(request: Request) -> Response:
            _require_tailnet_operator(request)
            return await _proxy_private_api(
                request,
                "/api/clips/corrections",
                settings,
                client_factory,
                forward_content_type=True,
            )

        @app.post("/api/clips/features")
        async def clip_feature(request: Request) -> Response:
            _require_tailnet_operator(request)
            return await _proxy_private_api(
                request,
                "/api/clips/features",
                settings,
                client_factory,
                forward_content_type=True,
            )

        @app.get("/api/clips/corrections/export")
        async def clip_corrections_export(request: Request) -> Response:
            _require_tailnet_operator(request)
            return await _proxy_private_api(
                request,
                "/api/clips/corrections/export",
                settings,
                client_factory,
            )

        @app.get("/api/asr-feedback/status")
        async def asr_feedback_status(request: Request) -> Response:
            _require_tailnet_operator(request)
            return await _proxy_private_api(
                request,
                "/api/asr-feedback/status",
                settings,
                client_factory,
            )

    @app.get("/api/analysis/lexical")
    async def lexical_analysis(request: Request) -> Response:
        return await _proxy_private_api(request, "/api/analysis/lexical", settings, client_factory)

    @app.get("/api/clips/search")
    async def clip_search(request: Request) -> Response:
        return await _proxy_private_api(request, "/api/clips/search", settings, client_factory)

    @app.api_route(
        "/ais-catcher",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    @app.api_route(
        "/ais-catcher/{proxy_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    async def ais_catcher_viewer(request: Request, proxy_path: str = "") -> Response:
        return await _proxy_ais_catcher(request, proxy_path, settings, client_factory)

    @app.get("/api/live/current.mp3")
    async def current_live_stream(dsp: str | None = None) -> StreamingResponse:
        stream_url = await _select_live_stream(settings.stream_urls, client_factory)
        return StreamingResponse(
            _audio_iterator_for_stream(stream_url, dsp, settings, client_factory),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/live/channels")
    async def live_channels() -> dict[str, object]:
        return {
            "defaultChannel": "14",
            "channels": _public_live_channels(settings),
        }

    @app.get("/api/live/performance")
    async def live_performance(request: Request) -> dict[str, object]:
        if not settings.tailnet_dev_routes_enabled:
            raise HTTPException(status_code=404, detail="performance dashboard is dev-only")
        if not _performance_host_allowed(request, settings):
            raise HTTPException(status_code=404, detail="performance dashboard is dev-only")
        snapshot = await performance_history.payload_for_request(settings, performance_collector)
        return _public_performance_payload(snapshot)

    @app.get("/api/live/{channel}/current.mp3")
    async def channel_live_stream(channel: str, dsp: str | None = None) -> StreamingResponse:
        stream_urls = _stream_urls_for_channel(settings, channel)
        stream_url = await _select_live_stream(stream_urls, client_factory)
        return StreamingResponse(
            _audio_iterator_for_stream(stream_url, dsp, settings, client_factory),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/live/status")
    async def live_status() -> dict[str, object]:
        preset = (
            await _preset_from_receiver_status(settings, client_factory)
            or await _preset_from_available_stream(settings.stream_urls, client_factory)
            or _find_channel(settings.active_channel_id)
        )
        return _live_status_payload(preset)

    @app.get("/api/live/{channel}/status")
    async def channel_live_status(channel: str) -> dict[str, object]:
        _stream_urls_for_channel(settings, channel)
        preset = _find_channel_by_number(channel)
        return _live_status_payload(preset)

    if settings.enable_debug_endpoints:

        @app.get("/api/live-transcript")
        async def live_transcript() -> dict[str, Any]:
            async with client_factory() as client:
                response = await client.get(settings.transcript_url)
            if response.status_code >= 500:
                raise HTTPException(status_code=502, detail="transcriber unavailable")
            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()

        @app.post("/api/channel")
        async def retune_channel(request: RetuneRequest) -> dict[str, Any]:
            if retune_lock.locked():
                raise HTTPException(status_code=409, detail="retune already in progress")
            preset = _find_channel(request.id)
            async with retune_lock:
                try:
                    result = await _run_retuner(retuner, preset, settings)
                except subprocess.CalledProcessError as exc:
                    detail = (exc.stderr or exc.stdout or str(exc)).strip()
                    raise HTTPException(status_code=502, detail=detail or "retune failed") from exc
                except subprocess.TimeoutExpired as exc:
                    raise HTTPException(status_code=504, detail="retune timed out") from exc
            return {
                "activeChannelId": preset.id,
                "channel": preset.channel,
                "label": preset.label,
                "frequencyMhz": preset.frequency_mhz,
                "restartedTranscriber": result.restarted_transcriber,
            }

        @app.get("/talkingboats-live.mp3")
        async def live_stream() -> StreamingResponse:
            stream_url = await _select_live_stream(settings.stream_urls, client_factory)
            return StreamingResponse(
                _iter_upstream_audio(stream_url, client_factory),
                media_type="audio/mpeg",
                headers={"Cache-Control": "no-store"},
            )

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    @app.get("/clips", include_in_schema=False)
    @app.get("/clips/", include_in_schema=False)
    @app.get("/hall-of-fame", include_in_schema=False)
    @app.get("/hall-of-fame/", include_in_schema=False)
    @app.get("/search", include_in_schema=False)
    @app.get("/search/", include_in_schema=False)
    @app.get("/live", include_in_schema=False)
    @app.get("/live/", include_in_schema=False)
    @app.get("/ais", include_in_schema=False)
    @app.get("/ais/", include_in_schema=False)
    @app.get("/map", include_in_schema=False)
    @app.get("/map/", include_in_schema=False)
    @app.get("/analysis", include_in_schema=False)
    @app.get("/analysis/", include_in_schema=False)
    @app.get("/about", include_in_schema=False)
    @app.get("/about/", include_in_schema=False)
    @app.get("/performance", include_in_schema=False)
    @app.get("/performance/", include_in_schema=False)
    @app.get("/operator", include_in_schema=False)
    @app.get("/operator/", include_in_schema=False)
    async def clip_console_index() -> Response:
        return _shell_asset_response("index.html")

    @app.get("/assets/app.js", include_in_schema=False)
    async def clip_console_app_js() -> Response:
        return _shell_asset_response("assets/app.js")

    @app.get("/assets/styles.css", include_in_schema=False)
    async def clip_console_styles() -> Response:
        return _shell_asset_response("assets/styles.css")

    @app.get("/public_manifest.json", include_in_schema=False)
    async def clip_console_manifest() -> Response:
        return _generated_public_site_asset_response(
            settings,
            "public_manifest.json",
            media_type="application/json",
        )

    @app.get("/analysis/topic_clusters.html", include_in_schema=False)
    async def topic_clusters_html() -> Response:
        return _generated_public_site_asset_response(
            settings,
            "analysis/topic_clusters.html",
            media_type="text/html",
        )

    app.mount("/", StaticFiles(directory=CLIP_CONSOLE_DIR, html=True), name="clip-console")
    return app


def _find_channel(channel_id: str) -> ChannelPreset:
    for channel in DEFAULT_CHANNELS:
        if channel.id == channel_id:
            return channel
    raise HTTPException(status_code=404, detail="unknown channel")


def _find_channel_by_number(channel_number: str) -> ChannelPreset:
    normalized = channel_number.upper()
    for channel in DEFAULT_CHANNELS:
        if channel.channel.upper() == normalized:
            return channel
    raise HTTPException(status_code=404, detail="unknown channel")


def _public_live_channels(settings: ProxySettings) -> list[dict[str, str]]:
    channels = []
    for channel_number in settings.channel_stream_urls:
        try:
            preset = _find_channel_by_number(channel_number)
        except HTTPException:
            continue
        channels.append(
            {
                "channel": preset.channel,
                "label": preset.label,
                "frequencyMhz": preset.frequency_mhz,
                "streamPath": f"/api/live/{preset.channel}/current.mp3",
                "statusPath": f"/api/live/{preset.channel}/status",
            }
        )
    return channels


def _stream_urls_for_channel(settings: ProxySettings, channel_number: str) -> tuple[str, ...]:
    preset = _find_channel_by_number(channel_number)
    stream_urls = settings.channel_stream_urls.get(preset.channel)
    if not stream_urls:
        raise HTTPException(status_code=404, detail="live stream not configured")
    return stream_urls


def _live_status_payload(preset: ChannelPreset) -> dict[str, object]:
    return {
        "activeChannelId": preset.id,
        "channel": preset.channel,
        "label": preset.label,
        "frequencyMhz": preset.frequency_mhz,
        "streamDelaySeconds": {"minimum": 1, "maximum": 5},
    }


def _performance_host_allowed(request: Request, settings: ProxySettings) -> bool:
    return _dev_host_allowed(
        request,
        dev_hosts=settings.performance_dev_hosts,
        dev_origin_hosts=settings.performance_dev_origin_hosts,
    )


def _ais_catcher_host_allowed(request: Request, settings: ProxySettings) -> bool:
    return _dev_host_allowed(
        request,
        dev_hosts=settings.ais_catcher_dev_hosts,
        dev_origin_hosts=settings.ais_catcher_dev_origin_hosts,
    )


def _dev_host_allowed(
    request: Request,
    *,
    dev_hosts: tuple[str, ...],
    dev_origin_hosts: tuple[str, ...],
) -> bool:
    host = request.headers.get("host", "")
    hostname = host.rsplit("@", 1)[-1].split(":", 1)[0].lower()
    if hostname in {allowed.lower() for allowed in dev_hosts}:
        return True
    environment = request.headers.get("x-talkingboats-environment", "").lower()
    origin_hosts = {allowed.lower() for allowed in dev_origin_hosts}
    return environment == "dev" and hostname in origin_hosts


def _require_tailnet_operator(request: Request) -> None:
    if _tailnet_operator_allowed(request):
        return
    raise HTTPException(status_code=403, detail="tailnet operator access required")


def _tailnet_operator_allowed(request: Request) -> bool:
    if request.headers.get(TAILNET_DEV_PROXY_HEADER) == "1":
        return True
    if request.headers.get(TAILSCALE_IDENTITY_HEADER):
        return True
    host = request.headers.get("host", "")
    hostname = host.rsplit("@", 1)[-1].split(":", 1)[0].lower()
    return hostname in TAILNET_OPERATOR_LOCAL_HOSTS


def _public_performance_payload(payload: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload, dict):
        payload = {}
    hosts = _raw_performance_hosts(payload)
    public_hosts = [
        _public_performance_host(host, index)
        for index, host in enumerate(hosts)
        if isinstance(host, dict)
    ]
    status = _public_status(payload.get("status"))
    if status == "unknown":
        status = _worst_status([str(host.get("status", "unknown")) for host in public_hosts])
    return {
        "status": status,
        "generatedAt": _public_generated_at(payload.get("generatedAt")),
        "host": public_hosts[0] if public_hosts else {},
        "hosts": public_hosts,
    }


def _raw_performance_hosts(payload: dict[str, object]) -> list[dict[str, object]]:
    raw_hosts = payload.get("hosts")
    hosts = raw_hosts if isinstance(raw_hosts, list) else []
    if not hosts and isinstance(payload.get("host"), dict):
        hosts = [payload["host"]]
    return [host for host in hosts if isinstance(host, dict)]


def _public_performance_host(host: dict[str, object], index: int) -> dict[str, object]:
    role = (
        PERFORMANCE_PUBLIC_ROLES[index]
        if index < len(PERFORMANCE_PUBLIC_ROLES)
        else f"Telemetry host {index + 1}"
    )
    public_host: dict[str, object] = {
        "role": role,
        "status": _public_status(host.get("status")),
        "cpu": _public_metric(host.get("cpu"), ("utilizationPercent",)),
        "load": _public_metric(
            host.get("load"), ("oneMinute", "fiveMinute", "fifteenMinute", "perCpu")
        ),
        "memory": _public_metric(
            host.get("memory"), ("totalBytes", "availableBytes", "usedPercent")
        ),
        "disks": _public_disks(host.get("disks")),
        "thermal": _public_thermal(host.get("thermal")),
    }
    history = _public_performance_history(host.get("history"))
    if history:
        public_host["history"] = history
    if isinstance(host.get("reachable"), bool):
        public_host["reachable"] = host["reachable"]
    cpu_count = _public_number(host.get("cpuCount"))
    if cpu_count is not None:
        public_host["cpuCount"] = int(cpu_count)
    return public_host


def _public_metric(value: object, numeric_fields: tuple[str, ...]) -> dict[str, object]:
    metric: dict[str, object] = {"status": "unknown"}
    if not isinstance(value, dict):
        return metric
    metric["status"] = _public_status(value.get("status"))
    for field_name in numeric_fields:
        number = _public_number(value.get(field_name))
        if number is not None:
            metric[field_name] = number
    return metric


def _public_disks(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    disks = []
    for disk in value:
        if not isinstance(disk, dict):
            continue
        disks.append(_public_metric(disk, ("totalBytes", "freeBytes", "usedPercent")))
    return disks


def _public_thermal(value: object) -> dict[str, object]:
    thermal = _public_metric(value, ("temperatureC",))
    throttled = value.get("throttled") if isinstance(value, dict) else None
    thermal["throttled"] = _public_throttled_label(throttled)
    return thermal


def _performance_history_key(host: dict[str, object], index: int) -> str:
    role = _performance_history_role(host, index)
    if role != f"Telemetry host {index + 1}":
        return f"{index}:{role}"
    return f"{index}:host"


def _performance_history_role(host: dict[str, object], index: int) -> str:
    role = host.get("role")
    if isinstance(role, str) and 0 < len(role) <= 80 and "://" not in role:
        return _public_performance_role(role)
    if index < len(PERFORMANCE_PUBLIC_ROLES):
        return PERFORMANCE_PUBLIC_ROLES[index]
    return f"Telemetry host {index + 1}"


def _public_performance_role(role: str) -> str:
    return PERFORMANCE_ROLE_ALIASES.get(role, role)


def _performance_history_sample(
    generated_at: str,
    generated_epoch: float,
    host: dict[str, object],
) -> dict[str, object]:
    sample: dict[str, object] = {"generatedAt": generated_at, "_epoch": generated_epoch}
    cpu = host.get("cpu") if isinstance(host.get("cpu"), dict) else {}
    memory = host.get("memory") if isinstance(host.get("memory"), dict) else {}
    thermal = host.get("thermal") if isinstance(host.get("thermal"), dict) else {}
    cpu_utilization = _public_number(cpu.get("utilizationPercent"))
    memory_used = _public_number(memory.get("usedPercent"))
    thermal_temperature = _public_number(thermal.get("temperatureC"))
    if cpu_utilization is not None:
        sample["cpuUtilizationPercent"] = cpu_utilization
    if memory_used is not None:
        sample["memoryUsedPercent"] = memory_used
    if thermal_temperature is not None:
        sample["thermalTemperatureC"] = thermal_temperature
    return sample


def _public_performance_history(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    history = []
    for sample in value[-PERFORMANCE_PUBLIC_HISTORY_LIMIT:]:
        if not isinstance(sample, dict):
            continue
        public_sample = {"generatedAt": _public_generated_at(sample.get("generatedAt"))}
        for source_field in (
            "cpuUtilizationPercent",
            "memoryUsedPercent",
            "thermalTemperatureC",
        ):
            number = _public_number(sample.get(source_field))
            if number is not None:
                public_sample[source_field] = number
        history.append(public_sample)
    return history


def _performance_sample_epoch(generated_at: str) -> float:
    try:
        return datetime.fromisoformat(generated_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return time.time()


def _sample_epoch(sample: dict[str, object]) -> float:
    epoch = _public_number(sample.get("_epoch"))
    if epoch is not None:
        return float(epoch)
    generated_at = sample.get("generatedAt")
    if isinstance(generated_at, str):
        return _performance_sample_epoch(generated_at)
    return time.time()


def _public_generated_at(value: object) -> str:
    if isinstance(value, str) and len(value) <= 64 and "://" not in value:
        return value
    return _format_utc(datetime.now(UTC))


def _public_status(value: object) -> str:
    if isinstance(value, str) and value in PERFORMANCE_PUBLIC_STATUSES:
        return value
    return "unknown"


def _public_number(value: object) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(float(value)):
        return None
    return value


def _public_throttled_label(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    if value in {"unknown", "unavailable"}:
        return value
    if len(value) < 3 or not value.startswith("0x"):
        return "unknown"
    if all(character in "0123456789abcdefABCDEF" for character in value[2:]):
        return value
    return "unknown"


def collect_performance_snapshot(settings: ProxySettings) -> dict[str, object]:
    optiplex = _local_performance_host_snapshot()
    pi = _pi_performance_snapshot(settings)
    statuses = [
        str(optiplex.get("status", "unknown")),
        str(pi.get("status", "unknown")),
    ]
    return {
        "status": _worst_status(statuses),
        "generatedAt": _format_utc(datetime.now(UTC)),
        "host": optiplex,
        "hosts": [optiplex, pi],
    }


def _local_performance_host_snapshot() -> dict[str, object]:
    load = _load_snapshot()
    cpu = _cpu_utilization_snapshot()
    memory = _memory_snapshot()
    disks = _disk_snapshots()
    thermal = _local_thermal_snapshot()
    statuses = [
        str(load.get("status", "unknown")),
        str(cpu.get("status", "unknown")),
        str(memory.get("status", "unknown")),
        *(str(disk.get("status", "unknown")) for disk in disks),
        str(thermal.get("status", "unknown")),
    ]
    return {
        "status": _worst_status(statuses),
        "role": OPTIPLEX_PERFORMANCE_ROLE,
        "reachable": True,
        "cpuCount": os.cpu_count() or 1,
        "cpu": cpu,
        "load": load,
        "memory": memory,
        "disks": disks,
        "thermal": thermal,
    }


def _load_snapshot() -> dict[str, object]:
    cpu_count = os.cpu_count() or 1
    try:
        one_minute, five_minute, fifteen_minute = os.getloadavg()
    except OSError:
        return {"status": "unknown"}
    per_cpu = one_minute / cpu_count
    return {
        "oneMinute": round(one_minute, 2),
        "fiveMinute": round(five_minute, 2),
        "fifteenMinute": round(fifteen_minute, 2),
        "perCpu": round(per_cpu, 2),
        "status": _threshold_status(per_cpu, watch_at=0.75, high_at=1.0),
    }


def _cpu_utilization_snapshot() -> dict[str, object]:
    first = _read_cpu_times()
    if first is None:
        return {"status": "unknown"}
    time.sleep(0.1)
    second = _read_cpu_times()
    if second is None:
        return {"status": "unknown"}
    total_delta = second[0] - first[0]
    idle_delta = second[1] - first[1]
    if total_delta <= 0:
        return {"status": "unknown"}
    utilization = max(0.0, min(100.0, (1 - (idle_delta / total_delta)) * 100))
    return {
        "utilizationPercent": round(utilization, 1),
        "status": _threshold_status(utilization, watch_at=75.0, high_at=90.0),
    }


def _read_cpu_times() -> tuple[int, int] | None:
    try:
        first_line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
    except (IndexError, OSError):
        return None
    fields = first_line.split()
    if not fields or fields[0] != "cpu":
        return None
    try:
        values = [int(value) for value in fields[1:9]]
    except ValueError:
        return None
    if len(values) < 5:
        return None
    idle = values[3] + values[4]
    return sum(values), idle


def _memory_snapshot() -> dict[str, object]:
    meminfo = _read_meminfo()
    total = meminfo.get("MemTotal")
    available = meminfo.get("MemAvailable")
    if not total or available is None:
        return {"status": "unknown"}
    used = max(0, total - available)
    used_percent = (used / total) * 100
    return {
        "totalBytes": total,
        "availableBytes": available,
        "usedPercent": round(used_percent, 1),
        "status": _threshold_status(used_percent, watch_at=75.0, high_at=90.0),
    }


def _read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        name, separator, raw_value = line.partition(":")
        if not separator:
            continue
        parts = raw_value.strip().split()
        if not parts:
            continue
        try:
            values[name] = int(parts[0]) * 1024
        except ValueError:
            continue
    return values


def _disk_snapshots() -> list[dict[str, object]]:
    disks = []
    seen_devices: set[int] = set()
    for label, path in PERFORMANCE_DISK_PATHS:
        if not path.exists():
            continue
        try:
            device = path.stat().st_dev
        except OSError:
            continue
        if device in seen_devices:
            continue
        seen_devices.add(device)
        usage = shutil.disk_usage(path)
        used_percent = (usage.used / usage.total) * 100 if usage.total else 0.0
        disks.append(
            {
                "label": label,
                "totalBytes": usage.total,
                "freeBytes": usage.free,
                "usedPercent": round(used_percent, 1),
                "status": _threshold_status(used_percent, watch_at=80.0, high_at=90.0),
            }
        )
    return disks


def _local_thermal_snapshot() -> dict[str, object]:
    thermal_dir = Path("/sys/class/thermal")
    temperatures: list[float] = []
    try:
        temp_paths = sorted(thermal_dir.glob("thermal_zone*/temp"))
    except OSError:
        temp_paths = []
    for temp_path in temp_paths:
        try:
            raw_value = temp_path.read_text(encoding="utf-8").strip()
            temperature = float(raw_value)
        except (OSError, ValueError):
            continue
        if abs(temperature) > 1000:
            temperature /= 1000
        temperatures.append(temperature)
    if not temperatures:
        return {"status": "unknown", "throttled": "unknown"}
    temperature = max(temperatures)
    return {
        "temperatureC": round(temperature, 1),
        "throttled": "unknown",
        "status": _threshold_status(temperature, watch_at=70.0, high_at=85.0),
    }


def _pi_performance_snapshot(settings: ProxySettings) -> dict[str, object]:
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=2",
                settings.retune_ssh_target,
                "python3",
                "-",
            ],
            check=False,
            capture_output=True,
            input=PI_PERFORMANCE_SCRIPT,
            text=True,
            timeout=4,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return _unknown_pi_performance_snapshot()
    if result.returncode != 0:
        return _unknown_pi_performance_snapshot()
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _unknown_pi_performance_snapshot()
    if not isinstance(payload, dict):
        return _unknown_pi_performance_snapshot()
    payload["role"] = _public_performance_role(str(payload.get("role") or PI_PERFORMANCE_ROLE))
    payload["reachable"] = True
    payload.setdefault("status", "unknown")
    payload.setdefault("cpuCount", 1)
    payload.setdefault("cpu", {"status": "unknown"})
    payload.setdefault("load", {"status": "unknown"})
    payload.setdefault("memory", {"status": "unknown"})
    payload.setdefault("disks", [])
    payload.setdefault("thermal", {"status": "unknown"})
    return payload


def _unknown_pi_performance_snapshot() -> dict[str, object]:
    return {
        "role": PI_PERFORMANCE_ROLE,
        "reachable": False,
        "status": "unknown",
        "cpuCount": 1,
        "cpu": {"status": "unknown"},
        "load": {"status": "unknown"},
        "memory": {"status": "unknown"},
        "disks": [],
        "thermal": {"status": "unknown"},
    }


def _threshold_status(value: float, *, watch_at: float, high_at: float) -> str:
    if value >= high_at:
        return "high"
    if value >= watch_at:
        return "watch"
    return "ok"


def _worst_status(statuses: list[str]) -> str:
    rank = {"unknown": 0, "ok": 1, "watch": 2, "high": 3}
    if not statuses:
        return "unknown"
    return max(statuses, key=lambda status: rank.get(status, 0))


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _shell_asset_response(relative_path: str) -> Response:
    path = (CLIP_CONSOLE_DIR / relative_path).resolve()
    try:
        path.relative_to(CLIP_CONSOLE_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="asset not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return Response(
        content=path.read_bytes(),
        headers={"Cache-Control": "no-store", "Pragma": "no-cache", "Expires": "0"},
        media_type=SHELL_ASSET_TYPES.get(relative_path, "application/octet-stream"),
    )


def _generated_public_site_asset_response(
    settings: ProxySettings,
    relative_path: str,
    *,
    media_type: str,
) -> Response:
    root = Path(settings.public_site_dir).resolve()
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="asset not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return Response(
        content=path.read_bytes(),
        headers={"Cache-Control": "no-store", "Pragma": "no-cache", "Expires": "0"},
        media_type=media_type,
    )


def _preset_for_stream_url(stream_url: str) -> ChannelPreset | None:
    normalized = stream_url.lower()
    stream_channel_markers = {
        preset.id: (
            f"-{preset.channel.lower()}.",
            f"/{preset.channel.lower()}.",
            f"channel={preset.channel.lower()}",
        )
        for preset in DEFAULT_CHANNELS
    }
    for channel_id, markers in stream_channel_markers.items():
        if any(marker in normalized for marker in markers):
            return _find_channel(channel_id)
    return None


def retune_pi(preset: ChannelPreset, settings: ProxySettings) -> RetuneResult:
    script = _build_pi_retune_script(preset, settings)
    subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            settings.retune_ssh_target,
            "sudo",
            "python3",
            "-",
        ],
        input=script,
        text=True,
        capture_output=True,
        timeout=45,
        check=True,
    )
    restarted = False
    if settings.restart_transcriber_service:
        subprocess.run(
            ["systemctl", "--user", "restart", "talkingboats-live-transcriber.service"],
            text=True,
            capture_output=True,
            timeout=20,
            check=True,
        )
        restarted = True
    return RetuneResult(restarted_transcriber=restarted)


def _build_pi_retune_script(preset: ChannelPreset, settings: ProxySettings) -> str:
    payload = {
        "env_path": settings.pi_env_path,
        "updates": {
            "TALKINGBOATS_LIVE_CHANNEL": preset.channel,
            "TALKINGBOATS_LIVE_FREQUENCY_HZ": str(preset.frequency_hz),
            "TALKINGBOATS_LIVE_LABEL": preset.label,
            "TALKINGBOATS_LIVE_SQUELCH": str(preset.squelch),
            "TALKINGBOATS_AUDIO_FILTER_ENABLED": str(preset.audio_filter_enabled).lower(),
        },
    }
    return f"""
import json
import subprocess
from pathlib import Path

payload = {json.dumps(payload)}
env_path = Path(payload["env_path"])
updates = payload["updates"]
lines = env_path.read_text().splitlines()
seen = set()
out = []

def quote(value):
    return "'" + value.replace("'", "'\\\\''") + "'"

for line in lines:
    if "=" not in line or line.lstrip().startswith("#"):
        out.append(line)
        continue
    key = line.split("=", 1)[0]
    if key in updates:
        out.append(f"{{key}}={{quote(updates[key])}}")
        seen.add(key)
    else:
        out.append(line)

for key, value in updates.items():
    if key not in seen:
        out.append(f"{{key}}={{quote(value)}}")

env_path.write_text("\\n".join(out) + "\\n")
env_path.chmod(0o600)
subprocess.run(["systemctl", "restart", "talkingboats-edge-live-radio-stream.service"], check=True)
"""


async def _iter_upstream_audio(
    stream_url: str,
    client_factory: ClientFactory,
) -> AsyncIterator[bytes]:
    async with client_factory() as client, client.stream("GET", stream_url) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes(chunk_size=1024):
            if chunk:
                yield chunk


def _audio_iterator_for_stream(
    stream_url: str,
    dsp: str | None,
    settings: ProxySettings,
    client_factory: ClientFactory,
) -> AsyncIterator[bytes]:
    if not dsp:
        return _iter_upstream_audio(stream_url, client_factory)
    try:
        profile = dsp_profile_for_name(dsp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _iter_dsp_audio(stream_url, settings.ffmpeg_path, profile.name)


async def _iter_dsp_audio(
    stream_url: str,
    ffmpeg_path: str,
    profile_name: str,
) -> AsyncIterator[bytes]:
    profile = dsp_profile_for_name(profile_name)
    command = build_ffmpeg_dsp_command(ffmpeg_path, stream_url, profile)
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=502, detail=f"ffmpeg not found: {ffmpeg_path}") from exc

    stderr_task = asyncio.create_task(_drain_stream(process.stderr))
    try:
        if process.stdout is None:
            raise HTTPException(status_code=502, detail="ffmpeg stdout unavailable")
        while True:
            chunk = await process.stdout.read(1024)
            if not chunk:
                break
            yield chunk
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()
        await stderr_task


async def _drain_stream(stream: asyncio.StreamReader | None) -> None:
    if stream is None:
        return
    while await stream.read(4096):
        pass


async def _select_live_stream(
    stream_urls: tuple[str, ...],
    client_factory: ClientFactory,
) -> str:
    last_error = "no live stream candidates configured"
    async with client_factory() as client:
        for url in stream_urls:
            try:
                async with client.stream("GET", url) as response:
                    if response.status_code < 400:
                        return url
                    last_error = f"{url} returned HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                last_error = f"{url} failed: {type(exc).__name__}"
    raise HTTPException(status_code=502, detail=last_error)


async def _preset_from_available_stream(
    stream_urls: tuple[str, ...],
    client_factory: ClientFactory,
) -> ChannelPreset | None:
    try:
        stream_url = await _select_live_stream(stream_urls, client_factory)
    except HTTPException:
        return None
    return _preset_for_stream_url(stream_url)


async def _preset_from_receiver_status(
    settings: ProxySettings,
    client_factory: ClientFactory,
) -> ChannelPreset | None:
    async with client_factory() as client:
        try:
            response = await client.get(settings.receiver_status_url, timeout=2)
        except httpx.HTTPError:
            return None
    if response.status_code >= 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None

    channel = str(payload.get("channel") or "")
    frequency_hz = _int_or_none(payload.get("frequencyHz"))
    label = str(payload.get("label") or "")
    for preset in DEFAULT_CHANNELS:
        if channel == preset.channel or frequency_hz == preset.frequency_hz:
            return preset
    if channel and frequency_hz and label:
        return ChannelPreset(
            id=f"receiver_{channel.lower()}",
            channel=channel,
            label=label,
            frequency_hz=frequency_hz,
            description="Current receiver slot.",
        )
    return None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _proxy_private_api(
    request: Request,
    path: str,
    settings: ProxySettings,
    client_factory: ClientFactory,
    *,
    forward_content_type: bool = False,
) -> Response:
    target_url = f"{settings.private_api_url.rstrip('/')}{path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"
    async with client_factory() as client:
        upstream = await client.request(
            request.method,
            target_url,
            content=await request.body(),
            headers=_private_api_request_headers(request, forward_content_type),
        )
    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() in {"cache-control", "content-type"}
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


def _private_api_request_headers(
    request: Request,
    forward_content_type: bool,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if forward_content_type and (content_type := request.headers.get("content-type")):
        headers["content-type"] = content_type
    return headers


async def _proxy_ais_catcher(
    request: Request,
    proxy_path: str,
    settings: ProxySettings,
    client_factory: ClientFactory,
) -> Response:
    target_url = _ais_catcher_target_url(
        settings.ais_catcher_base_url,
        proxy_path,
        request.url.query,
    )
    async with client_factory() as client:
        try:
            upstream = await client.request(
                request.method,
                target_url,
                headers=_ais_catcher_request_headers(request),
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="AIS-catcher viewer unavailable") from exc

    content = upstream.content
    content_type = upstream.headers.get("content-type", "")
    if "text/html" in content_type.lower() and upstream.status_code < 400:
        content = _rewrite_ais_catcher_html(content, upstream.encoding or "utf-8")

    response_headers = _ais_catcher_response_headers(upstream, settings.ais_catcher_base_url)
    return Response(
        content=content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


def _ais_catcher_target_url(base_url: str, proxy_path: str, query: str) -> str:
    base = base_url.rstrip("/")
    suffix = proxy_path.lstrip("/")
    target_url = f"{base}/{suffix}" if suffix else f"{base}/"
    if query:
        target_url = f"{target_url}?{query}"
    return target_url


def _ais_catcher_request_headers(request: Request) -> dict[str, str]:
    allowed_headers = {"accept", "accept-language", "range", "user-agent"}
    return {
        name: value for name, value in request.headers.items() if name.lower() in allowed_headers
    }


def _ais_catcher_response_headers(upstream: httpx.Response, base_url: str) -> dict[str, str]:
    allowed_headers = {"content-type", "etag", "last-modified", "location"}
    response_headers = {
        name: value for name, value in upstream.headers.items() if name.lower() in allowed_headers
    }
    location = response_headers.get("location") or response_headers.get("Location")
    if location:
        response_headers["Location"] = _rewrite_ais_catcher_location(location, base_url)
        response_headers.pop("location", None)
    response_headers["Cache-Control"] = "no-store"
    response_headers["Pragma"] = "no-cache"
    response_headers["Expires"] = "0"
    return response_headers


def _rewrite_ais_catcher_html(content: bytes, encoding: str) -> bytes:
    text = content.decode(encoding, errors="replace")
    text = re.sub(
        r'((?:href|src|action)=["\'])/(?!/)',
        r"\1/ais-catcher/",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"url\(/(?!/)", "url(/ais-catcher/", text, flags=re.IGNORECASE)
    if "<base " not in text.lower():
        text = re.sub(
            r"(<head\b[^>]*>)",
            r'\1\n    <base href="/ais-catcher/" />',
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    return text.encode(encoding)


def _rewrite_ais_catcher_location(location: str, base_url: str) -> str:
    if location.startswith("/ais-catcher"):
        return location
    if location.startswith("/"):
        return f"/ais-catcher{location}"
    parsed_location = urlsplit(location)
    parsed_base = urlsplit(base_url)
    if parsed_location.scheme and parsed_location.netloc == parsed_base.netloc:
        path = parsed_location.path or "/"
        query = f"?{parsed_location.query}" if parsed_location.query else ""
        return f"/ais-catcher{path}{query}"
    return location


async def _run_retuner(
    retuner: Retuner,
    preset: ChannelPreset,
    settings: ProxySettings,
) -> RetuneResult:
    done = threading.Event()
    result: RetuneResult | None = None
    error: BaseException | None = None

    def run() -> None:
        nonlocal error, result
        try:
            result = retuner(preset, settings)
        except BaseException as exc:  # noqa: BLE001 - propagate operator command failures unchanged.
            error = exc
        else:
            error = None
        finally:
            done.set()

    threading.Thread(target=run, name="talkingboats-retuner", daemon=True).start()
    while not done.is_set():
        await asyncio.sleep(0.05)
    if error is not None:
        raise error
    if result is None:
        raise RuntimeError("retune finished without a result")
    return result


def _default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0),
        follow_redirects=False,
    )


def _env_channel_stream_urls(name: str) -> dict[str, tuple[str, ...]]:
    value = os.getenv(name)
    if not value:
        return {}
    channels: dict[str, tuple[str, ...]] = {}
    for entry in value.split(";"):
        channel, separator, urls = entry.partition("=")
        channel = channel.strip().upper()
        if not separator or not channel:
            continue
        stream_urls = tuple(url.strip() for url in urls.split(",") if url.strip())
        if stream_urls:
            channels[channel] = _dedupe(stream_urls)
    return channels


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_csv(name: str) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen = set()
    deduped = []
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return tuple(deduped)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Talking Boats tailnet radio proxy.")
    parser.add_argument("--host", default=os.environ.get("TALKINGBOATS_PROXY_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("TALKINGBOATS_PROXY_PORT", "8095")),
    )
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
