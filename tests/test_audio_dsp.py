from talkingboats.audio_dsp import (
    WARM_VOICE_PROFILE,
    build_ffmpeg_dsp_command,
    dsp_profile_for_name,
)


def test_warm_voice_profile_keeps_marine_voice_band_and_noise_reduction() -> None:
    graph = WARM_VOICE_PROFILE.filter_graph

    assert graph.startswith("highpass=f=180,lowpass=f=3600")
    assert "afftdn=" in graph
    assert "anlmdn=" in graph
    assert "equalizer=f=180" in graph
    assert "equalizer=f=2500" in graph
    assert "acompressor=" in graph
    assert graph.endswith("alimiter=limit=0.78")


def test_build_ffmpeg_dsp_command_outputs_streamable_mp3() -> None:
    command = build_ffmpeg_dsp_command(
        "ffmpeg",
        "http://pi.test/talkingboats-13.mp3",
        WARM_VOICE_PROFILE,
    )

    assert command[:3] == ["ffmpeg", "-hide_banner", "-loglevel"]
    assert command[command.index("-i") - 1] == "-re"
    assert command[command.index("-i") + 1] == "http://pi.test/talkingboats-13.mp3"
    assert command[command.index("-af") + 1] == WARM_VOICE_PROFILE.filter_graph
    assert command[command.index("-codec:a") + 1] == "libmp3lame"
    assert command[command.index("-b:a") + 1] == WARM_VOICE_PROFILE.bitrate
    assert command[-3:] == ["-f", "mp3", "pipe:1"]


def test_unknown_dsp_profile_is_rejected() -> None:
    try:
        dsp_profile_for_name("maximum-bass")
    except ValueError as exc:
        assert "unknown DSP profile" in str(exc)
    else:
        raise AssertionError("unknown DSP profile should fail fast")
