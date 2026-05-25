from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DspProfile:
    name: str
    filter_graph: str
    bitrate: str = "64k"


WARM_VOICE_PROFILE = DspProfile(
    name="warm_voice",
    filter_graph=",".join(
        (
            "highpass=f=180",
            "lowpass=f=3600",
            "afftdn=nr=18:nf=-42:tn=1:gs=8",
            "anlmdn=s=0.00004:p=0.002:r=0.006:m=11",
            "adeclick",
            "equalizer=f=180:t=q:w=0.9:g=2",
            "equalizer=f=750:t=q:w=1.0:g=1.5",
            "equalizer=f=2500:t=q:w=1.0:g=2.2",
            "equalizer=f=4200:t=q:w=1.4:g=-3",
            "acompressor=threshold=0.08:ratio=2.4:attack=8:release=180:makeup=1.8",
            "alimiter=limit=0.78",
        )
    ),
)

DSP_PROFILES = {
    WARM_VOICE_PROFILE.name: WARM_VOICE_PROFILE,
}


def dsp_profile_for_name(name: str) -> DspProfile:
    try:
        return DSP_PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"unknown DSP profile: {name}") from exc


def build_ffmpeg_dsp_command(
    ffmpeg_path: str,
    stream_url: str,
    profile: DspProfile,
) -> list[str]:
    return [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-re",
        "-i",
        stream_url,
        "-af",
        profile.filter_graph,
        "-codec:a",
        "libmp3lame",
        "-b:a",
        profile.bitrate,
        "-content_type",
        "audio/mpeg",
        "-f",
        "mp3",
        "pipe:1",
    ]
