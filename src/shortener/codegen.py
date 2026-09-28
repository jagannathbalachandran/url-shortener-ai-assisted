"""Short code generation for links."""

from __future__ import annotations

import secrets
from typing import Protocol

from shortener.models import CODE_LENGTH

BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


class CodeGenerator(Protocol):
    """Produces short codes for new links."""

    def generate(self) -> str:
        """Return a new short code."""
        ...


class SecureCodeGenerator:
    """Generates random base62 codes using a cryptographically secure RNG."""

    def __init__(
        self, length: int = CODE_LENGTH, alphabet: str = BASE62_ALPHABET
    ) -> None:
        self._length = length
        self._alphabet = alphabet

    def generate(self) -> str:
        """Return a new `length`-char code drawn from `alphabet` via `secrets`."""
        return "".join(secrets.choice(self._alphabet) for _ in range(self._length))
