"""Hidden acceptance tests for t3-inverse-sqrt (LabIA project 002). Not shown to the agents."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import get_args

import pytest

import config.post_training_config as post_training_config
import src.optim.schedules as schedules
from config.loader import load_config
from config.post_training_config import PretrainConfig
from src.optim import inverse_sqrt_lr, lr_at
from src.post_training.cli import parse_config

RAIZ = Path(__file__).resolve().parents[1]
KW = {"warmup_steps": 100, "max_steps": 1000, "lr": 1e-3, "min_lr": 1e-5}


def test_warmup_is_the_shared_one() -> None:
    for step in (0, 1, 50, 99):
        assert inverse_sqrt_lr(step, **KW) == pytest.approx(schedules.cosine_lr(step, **KW))


def test_decay_follows_the_inverse_square_root() -> None:
    assert inverse_sqrt_lr(100, **KW) == pytest.approx(1e-3)
    assert inverse_sqrt_lr(400, **KW) == pytest.approx(5e-4)
    assert inverse_sqrt_lr(900, **KW) == pytest.approx(1e-3 / 3)
    assert inverse_sqrt_lr(5000, **KW) == pytest.approx(1e-3 * math.sqrt(100 / 5000))


def test_never_below_min_lr_and_max_steps_ignored() -> None:
    assert inverse_sqrt_lr(10**9, **KW) == pytest.approx(1e-5)
    assert inverse_sqrt_lr(2000, **{**KW, "max_steps": 10}) == inverse_sqrt_lr(2000, **KW)


def test_no_warmup_starts_at_lr() -> None:
    kw = {**KW, "warmup_steps": 0}
    assert inverse_sqrt_lr(0, **kw) == pytest.approx(1e-3)
    assert inverse_sqrt_lr(4, **kw) == pytest.approx(5e-4)


def test_selectable_by_name() -> None:
    assert lr_at("inverse_sqrt", 400, **KW) == pytest.approx(inverse_sqrt_lr(400, **KW))
    assert "inverse_sqrt" in get_args(schedules.Schedule)
    assert "inverse_sqrt" in get_args(post_training_config.Schedule)


def test_configuration_and_cli_accept_it(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_config(PretrainConfig, str(RAIZ / "configs" / "pretrain.json"), {"lr_schedule": "inverse_sqrt"})
    assert cfg.lr_schedule == "inverse_sqrt"
    monkeypatch.setattr(sys, "argv", ["pretrain_base.py", "--lr_schedule", "inverse_sqrt"])
    parsed, _ = parse_config(PretrainConfig)
    assert parsed.lr_schedule == "inverse_sqrt"
