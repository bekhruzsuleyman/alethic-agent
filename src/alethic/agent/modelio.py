"""Load the model without PyYAML: the config is a flat `key: value` file, so a small reader is enough."""
from __future__ import annotations

import re


def _value(raw: str):
    raw = raw.strip()
    if raw == "":
        return None
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            pass
    return raw


def read_flat_yaml(text: str) -> dict:
    """Parse `key: value` lines with `#` comments, ints, floats, booleans and quoted strings."""
    out = {}
    for line in text.splitlines():
        line = re.sub(r"(^|\s)#.*$", "", line).rstrip()
        if not line.strip():
            continue
        key, sep, rest = line.partition(":")
        if not sep:
            raise ValueError("cannot read config line: %r" % line)
        out[key.strip()] = _value(rest)
    return out


def read_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        import yaml
    except ImportError:
        return read_flat_yaml(text)
    return yaml.safe_load(text) or {}


MODELS = {
    "sft3c": {
        "label": "SFT-3c",
        "filename": "model-sft3c.pt",
        "hf_repo": "bekhruzsuleyman/alethic-300m",
        "hf_file": "runs/sft3c/best/model.pt",
        "base_mode": False,
        "note": "tool-use agent (default)",
    },
    "base": {
        "label": "Base",
        "filename": "model-base.pt",
        "hf_repo": "bekhruzsuleyman/alethic-300m",
        "hf_file": "runs/gqa_p3/latest/state.pt",
        "base_mode": True,
        "note": "Phase 3 pretrained base model (raw completion)",
    },
}


def load_model(weights: str, config: str, device: str = "cpu"):
    import torch

    from alethic.model.transformer import ModelConfig, Transformer

    model = Transformer(ModelConfig.from_dict(read_config(config))).to(device)
    ckpt = torch.load(weights, map_location=device, weights_only=True)
    state = ckpt["model"] if isinstance(ckpt, dict) and "model" in ckpt else ckpt
    if any(k.startswith("_orig_mod.") for k in state):
        state = {k.removeprefix("_orig_mod."): v for k, v in state.items()}
    model.load_state_dict(state)
    return model.eval()
