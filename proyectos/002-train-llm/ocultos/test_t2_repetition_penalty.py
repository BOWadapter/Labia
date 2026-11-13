"""Hidden acceptance tests for t2-repetition-penalty (LabIA project 002). Not shown to the agents."""

from __future__ import annotations

import sys
from typing import Any

import pytest
import torch

import src.post_training.evaluation as evaluation
import src.post_training.inference as inference
from src.inference.sampling import apply_repetition_penalty
from src.post_training.rollout import generate_with_logprobs


class _Sentinel(Exception):
    pass


def test_ctrl_rule_applied_once_per_seen_token() -> None:
    logits = torch.tensor([[2.0, -2.0, 3.0, -1.0]])
    context = torch.tensor([[0, 1, 1, 0]])
    original = logits.clone()
    out = apply_repetition_penalty(logits, context, 2.0)
    assert torch.allclose(out, torch.tensor([[1.0, -4.0, 3.0, -1.0]]))
    assert torch.equal(logits, original)


def test_rows_are_independent_and_one_is_identity() -> None:
    logits = torch.tensor([[4.0, 4.0], [4.0, 4.0]])
    context = torch.tensor([[0], [1]])
    assert torch.allclose(apply_repetition_penalty(logits, context, 4.0), torch.tensor([[1.0, 4.0], [4.0, 1.0]]))
    assert torch.allclose(apply_repetition_penalty(logits, context, 1.0), logits)


@pytest.mark.parametrize("penalty", [0.0, -1.0])
def test_non_positive_penalty_is_rejected(penalty: float) -> None:
    with pytest.raises(ValueError):
        apply_repetition_penalty(torch.zeros(1, 3), torch.tensor([[0]]), penalty)


class _Favors3(torch.nn.Module):
    """Every position prefers token 3, then token 4."""

    context_length = 32

    def __init__(self) -> None:
        super().__init__()
        self.w = torch.nn.Parameter(torch.zeros(1))

    def forward(self, idx: torch.Tensor) -> torch.Tensor:
        logits = torch.zeros(idx.size(0), idx.size(1), 10)
        logits[..., 3] = 5.0
        logits[..., 4] = 4.0
        return logits


def test_generation_penalizes_the_prompt_and_generated_tokens() -> None:
    prompt = torch.tensor([[3, 1]])
    plain = generate_with_logprobs(_Favors3(), prompt, 2, top_k=1, stop_tokens=(9,), pad_id=9)
    assert plain.sequences[0, 2:].tolist() == [3, 3]
    penal = generate_with_logprobs(_Favors3(), prompt, 2, top_k=1, stop_tokens=(9,), pad_id=9, repetition_penalty=10.0)
    # 3 is in the prompt (5 / 10 = 0.5 < 4), then 4 was generated (4 / 10 = 0.4 < 0.5)
    assert penal.sequences[0, 2:].tolist() == [4, 3]


def test_batched_generate_forwards_the_penalty(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def capture(*args: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        raise _Sentinel

    monkeypatch.setattr(evaluation, "generate_with_logprobs", capture)
    with pytest.raises(_Sentinel):
        evaluation.batched_generate(_Favors3(), [[1, 2]], 3, device="cpu", repetition_penalty=1.3)
    assert seen["repetition_penalty"] == 1.3


def test_generate_reply_forwards_the_penalty(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def capture(*args: Any, **kwargs: Any) -> list[str]:
        seen.update(kwargs)
        return ["ok"]

    monkeypatch.setattr(inference, "batched_generate", capture)
    monkeypatch.setattr(inference, "encode_prompt", lambda messages: [1, 2])
    assert inference.generate_reply(_Favors3(), "hi", device="cpu", repetition_penalty=1.7) == "ok"
    assert seen["repetition_penalty"] == 1.7


@pytest.mark.parametrize(("argv", "expected"), [([], 1.0), (["--repetition_penalty", "1.25"], 1.25)])
def test_chat_cli_option(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                         argv: list[str], expected: float) -> None:
    import scripts.chat as chat

    seen: dict[str, Any] = {}

    def fake_reply(model: Any, text: str, **kwargs: Any) -> str:
        seen.update(kwargs)
        return "reply"

    monkeypatch.setattr(chat, "resolve_device", lambda device: "cpu")
    monkeypatch.setattr(chat, "load_model_from_ckpt", lambda *a, **k: torch.nn.Linear(1, 1))
    monkeypatch.setattr(chat, "generate_reply", fake_reply)
    monkeypatch.setattr(sys, "argv", ["chat.py", "--ckpt", "m.pt", "--prompt", "hi", *argv])
    chat.main()
    capsys.readouterr()
    assert seen["repetition_penalty"] == expected
