from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import queue
import subprocess
import sys
import threading
import urllib.request
import wave
from array import array
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ALLOWED_CHANNELS = ("WX", "05A", "13", "14", "16", "22A", "66A", "68", "69", "71", "72", "74")
Channel = str
CONTENT_TYPES_BY_SUFFIX = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}


@dataclass(frozen=True)
class EdgeCaptureConfig:
    channel: Channel
    sample_rate_hz: int = 24_000
    frame_ms: int = 100
    threshold_rms: int = 8_000
    min_clip_seconds: float = 0.7
    max_clip_seconds: float = 45.0
    pre_roll_seconds: float = 0.7
    post_roll_seconds: float = 1.2

    def __post_init__(self) -> None:
        if self.channel not in ALLOWED_CHANNELS:
            raise ValueError(f"channel must be one of {', '.join(ALLOWED_CHANNELS)}")
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.frame_ms <= 0:
            raise ValueError("frame_ms must be positive")
        if (self.sample_rate_hz * self.frame_ms) % 1000 != 0:
            raise ValueError("sample_rate_hz * frame_ms must produce whole frames")
        if self.threshold_rms <= 0:
            raise ValueError("threshold_rms must be positive")
        if self.min_clip_seconds <= 0:
            raise ValueError("min_clip_seconds must be positive")
        if self.max_clip_seconds < self.min_clip_seconds:
            raise ValueError("max_clip_seconds must be at least min_clip_seconds")
        if self.pre_roll_seconds < 0 or self.post_roll_seconds < 0:
            raise ValueError("pre/post roll seconds must be non-negative")

    @property
    def frame_seconds(self) -> float:
        return self.frame_ms / 1000

    @property
    def frame_bytes(self) -> int:
        return int(self.sample_rate_hz * self.frame_seconds) * 2

    @property
    def pre_roll_frames(self) -> int:
        return round(self.pre_roll_seconds / self.frame_seconds)

    @property
    def post_roll_frames(self) -> int:
        return round(self.post_roll_seconds / self.frame_seconds)

    @property
    def min_clip_frames(self) -> int:
        return max(1, math.ceil(self.min_clip_seconds / self.frame_seconds))

    @property
    def max_clip_frames(self) -> int:
        return max(self.min_clip_frames, math.floor(self.max_clip_seconds / self.frame_seconds))


@dataclass(frozen=True)
class EdgeClip:
    channel: Channel
    started_at: datetime
    ended_at: datetime
    sample_rate_hz: int
    pcm_i16le: bytes
    peak_amplitude: int
    rms_amplitude: float

    @property
    def duration_seconds(self) -> float:
        samples = len(self.pcm_i16le) // 2
        return round(samples / self.sample_rate_hz, 3)


@dataclass(frozen=True)
class SpooledClip:
    audio_path: Path
    metadata_path: Path


class ContinuousWavRecorder:
    def __init__(
        self,
        *,
        output_dir: Path,
        channel: Channel,
        stream_started_at: datetime,
        sample_rate_hz: int,
        segment_seconds: float,
        retention_seconds: float | None,
        on_segment_complete: Callable[[Path, Path], None] | None = None,
    ) -> None:
        if channel not in ALLOWED_CHANNELS:
            raise ValueError(f"channel must be one of {', '.join(ALLOWED_CHANNELS)}")
        if stream_started_at.tzinfo is None:
            raise ValueError("stream_started_at must include a timezone")
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if segment_seconds <= 0:
            raise ValueError("segment_seconds must be positive")
        if retention_seconds is not None and retention_seconds <= 0:
            raise ValueError("retention_seconds must be positive")
        self.output_dir = output_dir
        self.channel = channel
        self.stream_started_at = stream_started_at.astimezone(UTC)
        self.sample_rate_hz = sample_rate_hz
        self.segment_samples = max(1, round(segment_seconds * sample_rate_hz))
        self.retention_seconds = retention_seconds
        self.on_segment_complete = on_segment_complete
        self.total_samples = 0
        self.segment_started_at: datetime | None = None
        self.segment_samples_written = 0
        self.segment_path: Path | None = None
        self.segment_tmp_path: Path | None = None
        self.segment_writer: wave.Wave_write | None = None
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, pcm_i16le: bytes) -> None:
        usable_bytes = len(pcm_i16le) - (len(pcm_i16le) % 2)
        offset = 0
        while offset < usable_bytes:
            if self.segment_writer is None:
                self._open_segment()
            remaining_samples = self.segment_samples - self.segment_samples_written
            remaining_bytes = remaining_samples * 2
            chunk = pcm_i16le[offset : min(usable_bytes, offset + remaining_bytes)]
            assert self.segment_writer is not None
            self.segment_writer.writeframesraw(chunk)
            samples_written = len(chunk) // 2
            self.segment_samples_written += samples_written
            self.total_samples += samples_written
            offset += len(chunk)
            if self.segment_samples_written >= self.segment_samples:
                self._close_segment()

    def close(self) -> None:
        if self.segment_writer is not None:
            self._close_segment()

    def _open_segment(self) -> None:
        started_at = self.stream_started_at + timedelta(
            seconds=self.total_samples / self.sample_rate_hz
        )
        stem = f"continuous-channel-{self.channel}-{_recording_stamp(started_at)}"
        self.segment_started_at = started_at
        self.segment_path = self.output_dir / f"{stem}.wav"
        self.segment_tmp_path = self.segment_path.with_suffix(".wav.tmp")
        self.segment_writer = wave.open(str(self.segment_tmp_path), "wb")  # noqa: SIM115
        self.segment_writer.setnchannels(1)
        self.segment_writer.setsampwidth(2)
        self.segment_writer.setframerate(self.sample_rate_hz)
        self.segment_samples_written = 0

    def _close_segment(self) -> None:
        assert self.segment_writer is not None
        assert self.segment_started_at is not None
        assert self.segment_path is not None
        assert self.segment_tmp_path is not None
        self.segment_writer.close()
        ended_at = self.segment_started_at + timedelta(
            seconds=self.segment_samples_written / self.sample_rate_hz
        )
        self.segment_tmp_path.replace(self.segment_path)
        metadata_path = self.segment_path.with_suffix(".json")
        tmp_metadata_path = metadata_path.with_suffix(".json.tmp")
        metadata = {
            "channel": self.channel,
            "started_at": _format_utc(self.segment_started_at),
            "ended_at": _format_utc(ended_at),
            "duration_seconds": round(self.segment_samples_written / self.sample_rate_hz, 3),
            "sample_rate_hz": self.sample_rate_hz,
            "content_type": "audio/wav",
            "audio_file": self.segment_path.name,
            "recording_kind": "continuous",
        }
        tmp_metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_metadata_path.replace(metadata_path)
        if self.on_segment_complete is not None:
            self.on_segment_complete(self.segment_path, metadata_path)
        self.segment_started_at = None
        self.segment_samples_written = 0
        self.segment_path = None
        self.segment_tmp_path = None
        self.segment_writer = None
        self.prune_expired(datetime.now(UTC))

    def prune_expired(self, now: datetime) -> None:
        if self.retention_seconds is None:
            return
        if now.tzinfo is None:
            raise ValueError("now must include a timezone")
        cutoff = now.astimezone(UTC).timestamp() - self.retention_seconds
        patterns = (
            f"continuous-channel-{self.channel}-*.wav",
            f"continuous-channel-{self.channel}-*.json",
            f"continuous-channel-{self.channel}-*.tmp",
        )
        for pattern in patterns:
            for path in self.output_dir.glob(pattern):
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                except FileNotFoundError:
                    continue


@dataclass(frozen=True)
class SegmentUploadRequest:
    channel: str
    audio_path: Path
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float
    content_type: str
    idempotency_key: str


@dataclass(frozen=True)
class SegmentUploadResult:
    bucket: str
    key: str
    bytes_uploaded: int
    content_type: str


class SegmentUploadWorker:
    def __init__(
        self,
        *,
        api_url: str,
        ingest_token: str,
        delete_after_upload: bool = False,
        uploader: Callable[..., Any] | None = None,
        queue_size: int = 4,
    ) -> None:
        if not api_url:
            raise ValueError("api_url is required")
        if not ingest_token:
            raise ValueError("ingest_token is required")
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        self.api_url = api_url
        self.ingest_token = ingest_token
        self.delete_after_upload = delete_after_upload
        self.uploader = uploader or _default_upload_clip
        self._queue: queue.Queue[tuple[Path, Path] | None] = queue.Queue(maxsize=queue_size)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="talkingboats-segment-uploader")
        self._thread.start()

    def enqueue(self, audio_path: Path, metadata_path: Path) -> bool:
        try:
            self._queue.put_nowait((audio_path, metadata_path))
        except queue.Full:
            _log_event(
                "edge_capture_record_upload_dropped",
                audio_file=audio_path.name,
                reason="queue_full",
            )
            return False
        return True

    def upload(self, audio_path: Path, metadata_path: Path) -> Any:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        started_at = _parse_utc(metadata["started_at"])
        ended_at = _parse_utc(metadata["ended_at"]) if metadata.get("ended_at") else None
        request = SegmentUploadRequest(
            channel=metadata["channel"],
            audio_path=audio_path,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=metadata.get("duration_seconds"),
            content_type=metadata.get("content_type"),
            idempotency_key=_continuous_idempotency_key(
                channel=metadata["channel"],
                started_at=started_at,
                audio_path=audio_path,
            ),
        )
        result = self.upload_request(request)
        if self.delete_after_upload:
            metadata_path.unlink(missing_ok=True)
        return result

    def upload_request(self, request: SegmentUploadRequest) -> Any:
        result = self.uploader(self.api_url, self.ingest_token, request)
        _log_event(
            "edge_capture_record_uploaded",
            channel=request.channel,
            audio_file=request.audio_path.name,
            key=getattr(result, "key", None),
            bytes_uploaded=getattr(result, "bytes_uploaded", None),
            content_type=getattr(result, "content_type", None),
        )
        if self.delete_after_upload:
            request.audio_path.unlink(missing_ok=True)
        return result

    def close(self) -> None:
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join(timeout=30)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                audio_path, metadata_path = item
                try:
                    self.upload(audio_path, metadata_path)
                except Exception as exc:  # noqa: BLE001 - keep capture alive.
                    _log_event(
                        "edge_capture_record_upload_failed",
                        audio_file=audio_path.name,
                        error=f"{type(exc).__name__}: {exc}",
                    )
            finally:
                self._queue.task_done()


@dataclass(frozen=True)
class ThermalPolicy:
    max_temp_c: float = 72.0
    resume_temp_c: float = 66.0
    max_load_per_cpu: float = 0.85

    def __post_init__(self) -> None:
        if self.max_temp_c <= 0:
            raise ValueError("max_temp_c must be positive")
        if self.resume_temp_c <= 0:
            raise ValueError("resume_temp_c must be positive")
        if self.resume_temp_c >= self.max_temp_c:
            raise ValueError("resume_temp_c must be lower than max_temp_c")
        if self.max_load_per_cpu <= 0:
            raise ValueError("max_load_per_cpu must be positive")


@dataclass(frozen=True)
class FrameMetrics:
    rms: float
    peak: int


def detect_activity_clips(
    chunks: Iterable[bytes],
    *,
    started_at: datetime,
    config: EdgeCaptureConfig,
) -> Iterator[EdgeClip]:
    if started_at.tzinfo is None:
        raise ValueError("started_at must include a timezone")

    frame_bytes = config.frame_bytes
    leftover = b""
    frame_index = 0
    pre_roll: deque[tuple[int, bytes]] = deque(maxlen=config.pre_roll_frames)
    active_frames: list[bytes] = []
    active_start_index: int | None = None
    trailing_silence_frames = 0

    def finish_clip() -> EdgeClip | None:
        nonlocal active_frames, active_start_index, trailing_silence_frames
        if active_start_index is None:
            return None
        frames = active_frames
        start_index = active_start_index
        active_frames = []
        active_start_index = None
        trailing_silence_frames = 0
        if len(frames) < config.min_clip_frames:
            return None
        pcm = b"".join(frames)
        started = started_at.astimezone(UTC) + timedelta(seconds=start_index * config.frame_seconds)
        ended = started + timedelta(seconds=len(frames) * config.frame_seconds)
        metrics = pcm_metrics_i16le(pcm)
        return EdgeClip(
            channel=config.channel,
            started_at=started,
            ended_at=ended,
            sample_rate_hz=config.sample_rate_hz,
            pcm_i16le=pcm,
            peak_amplitude=metrics.peak,
            rms_amplitude=round(metrics.rms, 3),
        )

    def process_frame(frame: bytes) -> EdgeClip | None:
        nonlocal active_start_index, trailing_silence_frames, active_frames
        metrics = pcm_metrics_i16le(frame)
        is_active = metrics.rms >= config.threshold_rms

        if active_start_index is None:
            if is_active:
                active_start_index = frame_index - len(pre_roll)
                active_frames = [data for _, data in pre_roll]
                active_frames.append(frame)
                trailing_silence_frames = 0
            else:
                pre_roll.append((frame_index, frame))
            return None

        active_frames.append(frame)
        if is_active:
            trailing_silence_frames = 0
        else:
            trailing_silence_frames += 1

        if len(active_frames) >= config.max_clip_frames:
            return finish_clip()
        if trailing_silence_frames >= config.post_roll_frames:
            return finish_clip()
        return None

    for chunk in chunks:
        if not chunk:
            continue
        data = leftover + chunk
        complete_bytes = len(data) - (len(data) % frame_bytes)
        for offset in range(0, complete_bytes, frame_bytes):
            clip = process_frame(data[offset : offset + frame_bytes])
            frame_index += 1
            if clip is not None:
                pre_roll.clear()
                yield clip
        leftover = data[complete_bytes:]

    if active_start_index is not None:
        clip = finish_clip()
        if clip is not None:
            yield clip


def pcm_metrics_i16le(pcm: bytes) -> FrameMetrics:
    usable_bytes = len(pcm) - (len(pcm) % 2)
    if usable_bytes <= 0:
        return FrameMetrics(rms=0.0, peak=0)
    samples = array("h")
    samples.frombytes(pcm[:usable_bytes])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return FrameMetrics(rms=0.0, peak=0)
    peak = max(abs(sample) for sample in samples)
    square_sum = sum(sample * sample for sample in samples)
    rms = math.sqrt(square_sum / len(samples))
    return FrameMetrics(rms=rms, peak=peak)


def write_spooled_clip(clip: EdgeClip, output_dir: Path) -> SpooledClip:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _clip_stem(clip)
    audio_path = output_dir / f"{stem}.wav"
    metadata_path = output_dir / f"{stem}.json"

    tmp_audio = audio_path.with_suffix(".wav.tmp")
    with wave.open(str(tmp_audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(clip.sample_rate_hz)
        wav.writeframes(clip.pcm_i16le)
    tmp_audio.replace(audio_path)

    metadata = {
        "channel": clip.channel,
        "started_at": _format_utc(clip.started_at),
        "ended_at": _format_utc(clip.ended_at),
        "duration_seconds": clip.duration_seconds,
        "sample_rate_hz": clip.sample_rate_hz,
        "content_type": "audio/wav",
        "audio_file": audio_path.name,
        "peak_amplitude": clip.peak_amplitude,
        "rms_amplitude": clip.rms_amplitude,
    }
    tmp_metadata = metadata_path.with_suffix(".json.tmp")
    tmp_metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_metadata.replace(metadata_path)
    return SpooledClip(audio_path=audio_path, metadata_path=metadata_path)


def encode_mp3(wav_path: Path, *, bitrate: str = "64k") -> Path:
    mp3_path = wav_path.with_suffix(".mp3")
    tmp_mp3 = mp3_path.with_suffix(".tmp.mp3")
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(wav_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            bitrate,
            str(tmp_mp3),
        ],
        check=True,
    )
    tmp_mp3.replace(mp3_path)
    return mp3_path


def infer_audio_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in CONTENT_TYPES_BY_SUFFIX:
        raise ValueError(f"unsupported audio extension: {suffix or '<none>'}")
    return CONTENT_TYPES_BY_SUFFIX[suffix]


def should_pause_processing(
    *,
    temp_c: float | None,
    load_1m: float | None,
    cpu_count: int | None,
    policy: ThermalPolicy,
    already_paused: bool,
) -> bool:
    cpu_total = max(1, cpu_count or 1)
    load_per_cpu = (load_1m / cpu_total) if load_1m is not None else 0.0
    if load_per_cpu >= policy.max_load_per_cpu:
        return True
    if temp_c is None:
        return False
    if already_paused:
        return temp_c >= policy.resume_temp_c
    return temp_c >= policy.max_temp_c


def read_cpu_temp_c() -> float | None:
    thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        raw = thermal_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return int(raw) / 1000
    except ValueError:
        return None


def read_load_1m() -> float | None:
    try:
        return os.getloadavg()[0]
    except OSError:
        return None


def stdin_chunks(chunk_size: int) -> Iterator[bytes]:
    while True:
        chunk = sys.stdin.buffer.read(chunk_size)
        if not chunk:
            break
        yield chunk


def tee_chunks(
    chunks: Iterable[bytes],
    *,
    config: EdgeCaptureConfig | None = None,
) -> Iterator[bytes]:
    if config is not None:
        for original, rendered in _squelched_pcm_chunk_stream(chunks, config=config):
            sys.stdout.buffer.write(rendered)
            sys.stdout.buffer.flush()
            yield original
        return
    for chunk in chunks:
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
        yield chunk


def squelched_pcm_chunks(
    chunks: Iterable[bytes],
    *,
    config: EdgeCaptureConfig,
) -> Iterator[bytes]:
    for _, rendered in _squelched_pcm_chunk_stream(chunks, config=config):
        yield rendered


def _squelched_pcm_chunk_stream(
    chunks: Iterable[bytes],
    *,
    config: EdgeCaptureConfig,
) -> Iterator[tuple[bytes, bytes]]:
    frame_bytes = config.frame_bytes
    leftover = b""
    hangover_frames = 0

    for chunk in chunks:
        if not chunk:
            continue
        data = leftover + chunk
        complete_bytes = len(data) - (len(data) % frame_bytes)
        rendered = bytearray()
        for offset in range(0, complete_bytes, frame_bytes):
            frame = data[offset : offset + frame_bytes]
            metrics = pcm_metrics_i16le(frame)
            if metrics.rms >= config.threshold_rms:
                hangover_frames = config.post_roll_frames
                rendered.extend(frame)
            elif hangover_frames > 0:
                hangover_frames -= 1
                rendered.extend(frame)
            else:
                rendered.extend(b"\0" * len(frame))
        leftover = data[complete_bytes:]
        if rendered:
            yield chunk, bytes(rendered)

    if leftover:
        metrics = pcm_metrics_i16le(leftover)
        if metrics.rms >= config.threshold_rms or hangover_frames > 0:
            yield leftover, leftover
        else:
            yield leftover, b"\0" * len(leftover)


def record_chunks(
    chunks: Iterable[bytes],
    recorder: ContinuousWavRecorder,
) -> Iterator[bytes]:
    try:
        for chunk in chunks:
            recorder.write(chunk)
            yield chunk
    finally:
        recorder.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect radio activity from rtl_fm PCM and spool bounded clips on the Pi."
    )
    parser.add_argument("--channel", choices=ALLOWED_CHANNELS, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("/opt/talkingboats/spool/clips"))
    parser.add_argument("--sample-rate-hz", type=int, default=24_000)
    parser.add_argument("--frame-ms", type=int, default=100)
    parser.add_argument("--threshold-rms", type=int, default=8_000)
    parser.add_argument("--min-clip-seconds", type=float, default=0.7)
    parser.add_argument("--max-clip-seconds", type=float, default=45.0)
    parser.add_argument("--pre-roll-seconds", type=float, default=0.7)
    parser.add_argument("--post-roll-seconds", type=float, default=1.2)
    parser.add_argument("--chunk-size", type=int, default=24_000)
    parser.add_argument("--tee-stdout", action="store_true")
    parser.add_argument("--squelch-stdout", action="store_true")
    parser.add_argument("--record-dir", type=Path)
    parser.add_argument("--record-segment-seconds", type=float, default=300.0)
    parser.add_argument("--record-retention-seconds", type=float, default=86_400.0)
    parser.add_argument("--no-record-retention", action="store_true")
    parser.add_argument("--record-upload", action="store_true")
    parser.add_argument("--record-delete-after-upload", action="store_true")
    parser.add_argument("--record-upload-queue-size", type=int, default=4)
    parser.add_argument("--encode-mp3", action="store_true")
    parser.add_argument("--mp3-bitrate", default="64k")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--api-url", default=os.getenv("TALKINGBOATS_PRIVATE_API"))
    parser.add_argument("--ingest-token", default=os.getenv("TALKINGBOATS_INGEST_TOKEN"))
    parser.add_argument("--delete-after-upload", action="store_true")
    parser.add_argument("--max-temp-c", type=float, default=72.0)
    parser.add_argument("--resume-temp-c", type=float, default=66.0)
    parser.add_argument("--max-load-per-cpu", type=float, default=0.85)
    args = parser.parse_args()

    if args.upload and (not args.api_url or not args.ingest_token):
        parser.error("--upload requires --api-url/--ingest-token or environment equivalents")
    if args.record_upload and (not args.api_url or not args.ingest_token):
        parser.error(
            "--record-upload requires --api-url/--ingest-token or environment equivalents"
        )

    config = EdgeCaptureConfig(
        channel=args.channel,
        sample_rate_hz=args.sample_rate_hz,
        frame_ms=args.frame_ms,
        threshold_rms=args.threshold_rms,
        min_clip_seconds=args.min_clip_seconds,
        max_clip_seconds=args.max_clip_seconds,
        pre_roll_seconds=args.pre_roll_seconds,
        post_roll_seconds=args.post_roll_seconds,
    )
    policy = ThermalPolicy(
        max_temp_c=args.max_temp_c,
        resume_temp_c=args.resume_temp_c,
        max_load_per_cpu=args.max_load_per_cpu,
    )
    chunks: Iterable[bytes] = stdin_chunks(args.chunk_size)
    started_at = datetime.now(UTC)
    upload_worker = None
    if args.record_upload:
        upload_worker = SegmentUploadWorker(
            api_url=args.api_url,
            ingest_token=args.ingest_token,
            delete_after_upload=args.record_delete_after_upload,
            queue_size=args.record_upload_queue_size,
        )
        upload_worker.start()
    activity_uploader = (
        SegmentUploadWorker(api_url=args.api_url, ingest_token=args.ingest_token)
        if args.upload
        else None
    )
    recorder = None
    if args.record_dir is not None:
        recorder = ContinuousWavRecorder(
            output_dir=args.record_dir,
            channel=args.channel,
            stream_started_at=started_at,
            sample_rate_hz=args.sample_rate_hz,
            segment_seconds=args.record_segment_seconds,
            retention_seconds=None
            if args.no_record_retention
            else args.record_retention_seconds,
            on_segment_complete=upload_worker.enqueue if upload_worker else None,
        )
        chunks = record_chunks(chunks, recorder)
    if args.tee_stdout:
        chunks = tee_chunks(chunks, config=config if args.squelch_stdout else None)

    paused = False
    clips_written = 0
    _log_event(
        "edge_capture_start",
        channel=args.channel,
        output_dir=str(args.output_dir),
        record_dir=str(args.record_dir) if args.record_dir else None,
        record_retention_seconds=None
        if args.no_record_retention
        else args.record_retention_seconds,
        record_segment_seconds=args.record_segment_seconds if args.record_dir else None,
        record_upload=args.record_upload,
        tee_stdout=args.tee_stdout,
        squelch_stdout=args.squelch_stdout,
        upload=args.upload,
    )

    try:
        for clip in detect_activity_clips(chunks, started_at=started_at, config=config):
            spooled = write_spooled_clip(clip, args.output_dir)
            clips_written += 1
            temp_c = read_cpu_temp_c()
            load_1m = read_load_1m()
            paused = should_pause_processing(
                temp_c=temp_c,
                load_1m=load_1m,
                cpu_count=os.cpu_count(),
                policy=policy,
                already_paused=paused,
            )
            upload_path = spooled.audio_path
            if paused:
                _log_event(
                    "edge_capture_deferred",
                    channel=clip.channel,
                    duration_seconds=clip.duration_seconds,
                    audio_file=spooled.audio_path.name,
                    reason="thermal_or_load",
                    temp_c=temp_c,
                    load_1m=load_1m,
                )
                continue
            if args.encode_mp3:
                upload_path = encode_mp3(spooled.audio_path, bitrate=args.mp3_bitrate)
            _log_event(
                "edge_capture_clip",
                channel=clip.channel,
                duration_seconds=clip.duration_seconds,
                audio_file=upload_path.name,
                clips_written=clips_written,
                temp_c=temp_c,
                load_1m=load_1m,
            )
            if args.upload:
                assert activity_uploader is not None
                result = activity_uploader.upload_request(
                    build_activity_upload_request(clip, upload_path),
                )
                _log_event(
                    "edge_capture_uploaded",
                    channel=clip.channel,
                    key=result.key,
                    bytes_uploaded=result.bytes_uploaded,
                    content_type=result.content_type,
                )
                if args.delete_after_upload:
                    upload_path.unlink(missing_ok=True)
                    spooled.audio_path.unlink(missing_ok=True)
                    spooled.metadata_path.unlink(missing_ok=True)
    finally:
        if upload_worker is not None:
            upload_worker.close()

    _log_event("edge_capture_stop", channel=args.channel, clips_written=clips_written)


def _clip_stem(clip: EdgeClip) -> str:
    stamp = clip.started_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    digest = hashlib.sha256(clip.pcm_i16le).hexdigest()[:16]
    return f"channel-{clip.channel}-{stamp}-{digest}"


def _recording_stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def build_activity_upload_request(clip: EdgeClip, audio_path: Path) -> SegmentUploadRequest:
    return SegmentUploadRequest(
        channel=clip.channel,
        audio_path=audio_path,
        started_at=clip.started_at,
        ended_at=clip.ended_at,
        duration_seconds=clip.duration_seconds,
        content_type=infer_audio_content_type(audio_path),
        idempotency_key=_activity_idempotency_key(
            channel=clip.channel,
            started_at=clip.started_at,
            audio_path=audio_path,
        ),
    )


def _activity_idempotency_key(
    *,
    channel: str,
    started_at: datetime,
    audio_path: Path,
) -> str:
    stamp = _format_utc(started_at)
    digest = _file_sha256(audio_path)
    return f"activity-v1:{channel}:{stamp}:{digest}"


def _continuous_idempotency_key(
    *,
    channel: str,
    started_at: datetime,
    audio_path: Path,
) -> str:
    stamp = _format_utc(started_at)
    digest = _file_sha256(audio_path)
    return f"continuous-v1:{channel}:{stamp}:{digest}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return parsed.astimezone(UTC)


def _default_upload_clip(api_url: str, ingest_token: str, request: Any) -> Any:
    api_url = api_url.rstrip("/")
    payload = {
        "channel": request.channel,
        "started_at": _format_utc(request.started_at),
        "content_type": request.content_type,
        "idempotency_key": request.idempotency_key,
        "duration_seconds": request.duration_seconds,
    }
    if request.ended_at is not None:
        payload["ended_at"] = _format_utc(request.ended_at)
    presign_request = urllib.request.Request(
        f"{api_url}/api/ingest/clips/presign",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-TalkingBoats-Ingest-Token": ingest_token,
        },
        method="POST",
    )
    with urllib.request.urlopen(presign_request, timeout=30) as response:
        presign = json.loads(response.read().decode("utf-8"))

    audio_bytes = request.audio_path.read_bytes()
    put_headers = dict(presign.get("required_headers", {}))
    put_request = urllib.request.Request(
        presign["upload_url"],
        data=audio_bytes,
        headers=put_headers,
        method="PUT",
    )
    with urllib.request.urlopen(put_request, timeout=120):
        pass
    return SegmentUploadResult(
        bucket=presign["bucket"],
        key=presign["key"],
        bytes_uploaded=len(audio_bytes),
        content_type=request.content_type,
    )


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _log_event(event: str, **fields: object) -> None:
    payload = {"event": event, **fields}
    print(json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
