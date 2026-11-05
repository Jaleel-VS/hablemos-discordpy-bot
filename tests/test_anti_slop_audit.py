"""Tests for the anti-slop baseline audit wrapper."""
from __future__ import annotations

from collections import Counter

from scripts import anti_slop_audit


def test_scan_counts_rule_codes_from_flake8_output(monkeypatch) -> None:
    class Result:
        stdout = (
            "cogs/a.py:1:1: ASP001 safety comment required\n"
            "db/b.py:2:1: ASP009 unsafe dictionary\n"
        )
        stderr = ""

    monkeypatch.setattr(anti_slop_audit.subprocess, "run", lambda *args, **kwargs: Result())

    count, rules, output = anti_slop_audit.scan()

    assert count == 2
    assert rules == Counter({"ASP001": 1, "ASP009": 1})
    assert "db/b.py" in output


