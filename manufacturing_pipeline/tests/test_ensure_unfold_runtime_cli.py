import sys

from manufacturing_pipeline.tools import ensure_unfold_runtime


def test_parse_args_accepts_force_reinstall(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["ensure_unfold_runtime.py", "--force-reinstall"],
    )

    args = ensure_unfold_runtime.parse_args()

    assert args.force_reinstall is True
