"""Tiny isolated numerical probe of the actual adapter configuration and CT2 conversion."""

import json
import tempfile
from pathlib import Path

import torch
from ctranslate2.converters import TransformersConverter
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from transformers import PreTrainedTokenizerFast, WhisperConfig, WhisperForConditionalGeneration

from talkingboats.asr_experiments import DEFAULT_CONFIG, configure_adapter, model_digest

torch.manual_seed(42)
torch.set_num_threads(1)
config = WhisperConfig(
    d_model=16,
    encoder_layers=1,
    decoder_layers=1,
    encoder_attention_heads=2,
    decoder_attention_heads=2,
    encoder_ffn_dim=32,
    decoder_ffn_dim=32,
    vocab_size=32,
    num_mel_bins=80,
    max_source_positions=16,
    max_target_positions=16,
    pad_token_id=0,
    bos_token_id=1,
    eos_token_id=2,
    decoder_start_token_id=1,
    suppress_tokens=[],
    begin_suppress_tokens=[],
)
model = configure_adapter(WhisperForConditionalGeneration(config), {**DEFAULT_CONFIG, "dropout": 0})
inputs = torch.randn(1, 80, 32)
labels = torch.tensor([[1, 3, 4, 2]])
loss = model(input_features=inputs, labels=labels).loss
loss.backward()
assert torch.isfinite(loss)
assert all(not p.requires_grad for n, p in model.named_parameters() if ".encoder." in n)
assert all("lora_" in n for n, p in model.named_parameters() if p.requires_grad)
assert any(
    p.grad is not None and torch.count_nonzero(p.grad)
    for n, p in model.named_parameters()
    if p.requires_grad
)
optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=0.01)
optimizer.step()
after = model(input_features=inputs, labels=labels).loss
assert after < loss
with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    merged = model.merge_and_unload()
    merged.save_pretrained(directory / "hf")
    tokenizer = Tokenizer(WordLevel({f"token{i}": i for i in range(32)}, unk_token="token0"))
    PreTrainedTokenizerFast(tokenizer_object=tokenizer).save_pretrained(directory / "hf")
    TransformersConverter(str(directory / "hf")).convert(
        str(directory / "ct2"), quantization="int8"
    )
    digest = model_digest(directory / "ct2")
    assert len(digest) == 64
print(
    json.dumps(
        {
            "event": "asr_training_probe_passed",
            "encoder_frozen": True,
            "loss_before": float(loss.detach()),
            "loss_after": float(after.detach()),
            "ct2_int8_conversion": True,
        }
    )
)
