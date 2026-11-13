"""Hidden acceptance tests for t1-label-smoothing (LabIA project 002). Not shown to the agents."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import torch
import torch.nn.functional as F

from config.loader import load_config
from config.post_training_config import ConfigError, SFTConfig
from src.post_training.sft import sft_loss

RAIZ = Path(__file__).resolve().parents[1]


def _batch() -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    gen = torch.Generator().manual_seed(0)
    logits = torch.randn(2, 6, 9, generator=gen)
    tokens = torch.randint(0, 9, (2, 6), generator=gen)
    mask = torch.tensor([[0, 0, 1, 1, 1, 0], [0, 1, 1, 0, 1, 1]])
    return logits, tokens, mask


def _reference(logits: torch.Tensor, tokens: torch.Tensor, mask: torch.Tensor, eps: float) -> torch.Tensor:
    logits, targets, m = logits[:, :-1, :], tokens[:, 1:], mask[:, 1:].float()
    ce = F.cross_entropy(logits.reshape(-1, logits.size(-1)), targets.reshape(-1), reduction="none", label_smoothing=eps)
    return (ce.view(targets.shape) * m).sum() / m.sum()


def test_default_is_zero_and_valid_values_are_accepted() -> None:
    assert SFTConfig().label_smoothing == 0.0
    assert SFTConfig(label_smoothing=0.3).label_smoothing == 0.3


@pytest.mark.parametrize("value", [-0.01, 1.0, 1.5])
def test_out_of_range_is_rejected(value: float) -> None:
    with pytest.raises(ConfigError):
        SFTConfig(label_smoothing=value)


def test_loading_from_json_checks_the_value() -> None:
    sft_json = str(RAIZ / "configs" / "sft.json")
    assert load_config(SFTConfig, sft_json, {"label_smoothing": 0.2}).label_smoothing == 0.2
    with pytest.raises(ConfigError):
        load_config(SFTConfig, sft_json, {"label_smoothing": 1.0})


def test_zero_keeps_the_original_loss() -> None:
    logits, tokens, mask = _batch()
    expected = _reference(logits, tokens, mask, 0.0)
    assert torch.allclose(sft_loss(logits, tokens, mask), expected, atol=1e-6)
    assert torch.allclose(sft_loss(logits, tokens, mask, label_smoothing=0.0), expected, atol=1e-6)


@pytest.mark.parametrize("eps", [0.1, 0.5])
def test_smoothing_matches_torch_cross_entropy(eps: float) -> None:
    logits, tokens, mask = _batch()
    got = sft_loss(logits, tokens, mask, label_smoothing=eps)
    assert torch.allclose(got, _reference(logits, tokens, mask, eps), atol=1e-5)
    assert not torch.allclose(got, _reference(logits, tokens, mask, 0.0), atol=1e-4)


def test_training_script_passes_the_value_to_every_loss_call() -> None:
    tree = ast.parse((RAIZ / "scripts" / "train_sft.py").read_text(encoding="utf-8"))
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == "sft_loss"
    ]
    assert calls
    for call in calls:
        assert len(call.args) >= 4 or any(k.arg == "label_smoothing" for k in call.keywords)
