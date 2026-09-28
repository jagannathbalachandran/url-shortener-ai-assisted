"""Tests for SecureCodeGenerator."""

from __future__ import annotations

import pytest

from shortener.codegen import BASE62_ALPHABET, SecureCodeGenerator
from shortener.models import CODE_LENGTH


def test_generate_returns_code_of_expected_length() -> None:
    generator = SecureCodeGenerator()

    code = generator.generate()

    assert len(code) == CODE_LENGTH


def test_generate_uses_only_base62_alphabet() -> None:
    generator = SecureCodeGenerator()

    code = generator.generate()

    assert all(ch in BASE62_ALPHABET for ch in code)


def test_generate_draws_one_secure_choice_per_character(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _fake_choice(alphabet: str) -> str:
        calls.append(alphabet)
        return "x"

    monkeypatch.setattr("shortener.codegen.secrets.choice", _fake_choice)
    generator = SecureCodeGenerator(length=4, alphabet="ab")

    code = generator.generate()

    assert code == "xxxx"
    assert calls == ["ab"] * 4
