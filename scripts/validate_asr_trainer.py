"""Exercise the complete trainer/merge/converter on a tiny isolated Whisper fixture."""

import json
import math
import shutil
import tempfile
import wave
from array import array
from pathlib import Path

from faster_whisper.utils import download_model
from transformers import WhisperConfig, WhisperForConditionalGeneration, WhisperProcessor

from talkingboats.asr_experiments import DEFAULT_CONFIG, train_candidate

snapshot = Path(download_model("turbo", local_files_only=True))
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    source = root / "fixture-model"
    source.mkdir()
    for name in [
        "tokenizer.json",
        "tokenizer_config.json",
        "preprocessor_config.json",
        "vocab.json",
        "merges.txt",
        "special_tokens_map.json",
        "added_tokens.json",
    ]:
        if (snapshot / name).exists():
            shutil.copyfile(snapshot / name, source / name)
    processor = WhisperProcessor.from_pretrained(source)
    processor.tokenizer.pad_token = processor.tokenizer.eos_token
    processor.save_pretrained(source)
    model_config = WhisperConfig(
        d_model=16,
        encoder_layers=1,
        decoder_layers=1,
        encoder_attention_heads=2,
        decoder_attention_heads=2,
        encoder_ffn_dim=32,
        decoder_ffn_dim=32,
        vocab_size=len(processor.tokenizer),
        num_mel_bins=processor.feature_extractor.feature_size,
        max_source_positions=1500,
        max_target_positions=448,
        pad_token_id=processor.tokenizer.pad_token_id,
        bos_token_id=processor.tokenizer.bos_token_id,
        eos_token_id=processor.tokenizer.eos_token_id,
        decoder_start_token_id=50258,
        suppress_tokens=[],
        begin_suppress_tokens=[],
    )
    WhisperForConditionalGeneration(model_config).save_pretrained(source)
    audio = root / "fixture.wav"
    samples = array(
        "h", [int(1000 * math.sin(2 * math.pi * 500 * i / 16000)) for i in range(16000)]
    )
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(samples.tobytes())
    run = root / "run"
    run.mkdir()
    config = {
        **DEFAULT_CONFIG,
        "base_model": str(source),
        "epochs": 1,
        "gradient_accumulation_steps": 1,
    }
    row = {"audio_path": str(audio), "text": "radio test"}
    result = train_candidate(config, run, [row], [row], lambda *args, **kwargs: None)
    assert (result / "model.bin").exists() and (run / "model_identity.json").exists()
    print(
        json.dumps(
            {
                "event": "asr_complete_trainer_probe_passed",
                "isolated_fixture": True,
                "merge_and_int8_conversion": True,
            }
        )
    )
