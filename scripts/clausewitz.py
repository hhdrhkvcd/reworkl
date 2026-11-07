"""Small, dependency-free Clausewitz reader for mod consistency checks.

Keeps duplicate keys, ordered anonymous values and locations. It is not an
engine/schema validator; it checks structure and lets validation inspect refs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterator


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int
    line: int
    quoted: bool = False


@dataclass
class Entry:
    key: str | None
    value: str | list[Entry]
    op: str = "="
    line: int = 1
    start: int = 0
    end: int = 0
    prefix: str = ""

    def children(self, key: str | None = None) -> list[Entry]:
        if not isinstance(self.value, list):
            return []
        return [e for e in self.value if key is None or e.key == key]

    def scalar(self, key: str, default: str = "") -> str:
        items = self.children(key)
        return str(items[-1].value) if items and isinstance(items[-1].value, str) else default

    def walk(self) -> Iterator[Entry]:
        yield self
        for child in self.children():
            yield from child.walk()


class ParseError(ValueError):
    pass


TOKEN = re.compile(r'\s+|\#[^\n]*|"(?:\\.|[^"\\])*"|[{}]|[!<>=?]=?|[^\s{}"#<>=!?]+')
OPERATORS = {"=", "<", ">", "<=", ">=", "!=", "?="}


def parse(text: str, name: str = "<string>") -> Entry:
    text = text.lstrip("\ufeff")
    tokens: list[Token] = []
    cursor = 0
    line = 1
    for m in TOKEN.finditer(text):
        if m.start() != cursor:
            raise ParseError(f"{name}:{line}: invalid character or unclosed string")
        raw = m.group()
        if not raw.isspace() and not raw.startswith("#"):
            value = raw
            if raw.startswith('"'):
                value = raw[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            tokens.append(Token(value, m.start(), m.end(), line, raw.startswith('"')))
        line += raw.count("\n")
        cursor = m.end()
    if cursor != len(text):
        raise ParseError(f"{name}:{line}: unclosed string")

    i = 0

    def block(nested: bool = False) -> list[Entry]:
        nonlocal i
        result = []
        while i < len(tokens):
            token = tokens[i]
            if token.value == "}" and not token.quoted:
                if not nested:
                    raise ParseError(f"{name}:{token.line}: unexpected closing brace")
                i += 1
                return result
            if token.value == "{" and not token.quoted:
                i += 1
                value = block(True)
                result.append(Entry(None, value, line=token.line, start=token.start, end=tokens[i - 1].end))
                continue
            if token.value in OPERATORS and not token.quoted:
                raise ParseError(f"{name}:{token.line}: expected key or value, got {token.value!r}")
            i += 1
            if i < len(tokens) and tokens[i].value in OPERATORS and not tokens[i].quoted:
                op = tokens[i].value
                i += 1
                if i >= len(tokens) or (tokens[i].value == "}" and not tokens[i].quoted):
                    raise ParseError(f"{name}:{token.line}: missing value for {token.value}")
                v = tokens[i]
                prefix = ""
                # Colour syntax: color = rgb { 1 2 3 } (and hsv / hsv360).
                if not v.quoted and v.value.lower() in {"rgb", "hsv", "hsv360"} and i + 1 < len(tokens) and tokens[i + 1].value == "{":
                    prefix = v.value
                    i += 1
                    v = tokens[i]
                i += 1
                if v.value == "{" and not v.quoted:
                    value = block(True)
                elif v.value in OPERATORS and not v.quoted:
                    raise ParseError(f"{name}:{v.line}: unexpected operator")
                else:
                    value = v.value
                result.append(Entry(token.value, value, op, token.line, token.start, tokens[i - 1].end, prefix))
            else:
                result.append(Entry(None, token.value, line=token.line, start=token.start, end=token.end))
        if nested:
            raise ParseError(f"{name}: unclosed block")
        return result

    return Entry(None, block(), start=0, end=len(text))


def load(path: Path) -> Entry:
    return parse(path.read_text(encoding="utf-8-sig"), str(path))
