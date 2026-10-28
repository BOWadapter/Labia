# AGENTS.md — train-llm-from-scratch

Derived from the repository's own CONTRIBUTING.md (FareedKhan-dev/train-llm-from-scratch,
MIT). LabIA project 002 copies this file to the repository root for the `always_on`
strategy and leaves it out for `none`.

## Checks before you finish

- `python -m pytest -q -m "not slow"` (CPU only)
- `ruff check .`
- `mypy`

## Conventions

1. Type everything new. Tensor arguments use jaxtyping shapes such as
   `Float[Tensor, "batch seq vocab"]`; `tests/conftest.py` checks them at runtime.
2. Configs are typed dataclasses. A new hyperparameter is a field in
   `config/post_training_config.py` (choices as `Literal[...]`) and a key in the matching
   `configs/*.json`. The loader rejects unknown keys and wrong types.
3. Tests need no GPU: tiny models and generated data. Test a property rather than a
   hard-coded number.
4. Add or update tests for the behavior you change, and the docs if a command or flag
   changes.
5. Keep the classic model in `src/models/` simple; new architecture ideas go in
   `src/models/modern/` or behind a flag.
6. Commit messages: `feat(area): what is new`, `fix(area): what was wrong`, `docs: ...`.
