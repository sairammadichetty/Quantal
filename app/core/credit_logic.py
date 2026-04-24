"""Text-based credit calculation for messages without a report_id."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

_BASE_COST = Decimal("1.0")
_PER_CHAR_COST = Decimal("0.05")
_SHORT_WORD_COST = Decimal("0.1")  # 1-3 chars
_MID_WORD_COST = Decimal("0.2")  # 4-7 chars
_LONG_WORD_COST = Decimal("0.3")  # 8+ chars
_THIRD_VOWEL_COST = Decimal("0.3")
_LENGTH_PENALTY = Decimal("5.0")
_LENGTH_PENALTY_THRESHOLD = 100
_UNIQUE_WORD_BONUS = Decimal("2.0")
_MIN_COST = Decimal("1.0")
_VOWELS = frozenset("aeiouAEIOU")

# A word must contain at least one letter; this rejects stray "-" / "'" tokens
# that a naive [A-Za-z'-]+ would otherwise charge for.
_WORD_RE = re.compile(r"[A-Za-z'-]*[A-Za-z][A-Za-z'-]*")


def calculate_text_credits(message: str) -> float:
    """Return the credit cost for a plain-text message, rounded to 2dp.

    Internal maths uses Decimal to avoid float drift (0.1 + 0.2 != 0.3).
    """
    # Rule 1 - Base cost - `Decimal(0)` is safe for an empty string: base cost below still
    # applies, matching the brief.
    total = _BASE_COST

    # Rule 2 — character count (0.05 per char, includes whitespace &
    # punctuation). `len(str)` counts Unicode code points, which matches
    # the task's intuitive notion of "character".
    total += _PER_CHAR_COST * len(message)

    # Rule 3 — word length multipliers. See `_WORD_RE` for our word def.
    words = _WORD_RE.findall(message)
    for word in words:
        length = len(word)
        if length <= 3:
            total += _SHORT_WORD_COST
        elif length <= 7:
            total += _MID_WORD_COST
        else:
            total += _LONG_WORD_COST

    # Rule 4 — every 3rd character (indices 2, 5, 8, ...) that is a vowel
    # adds 0.3. Slicing `[2::3]` is both the cleanest and the fastest way
    # to express this.
    for char in message[2::3]:
        if char in _VOWELS:
            total += _THIRD_VOWEL_COST

    # Rule 5 — length penalty (strict `> 100`).
    if len(message) > _LENGTH_PENALTY_THRESHOLD:
        total += _LENGTH_PENALTY

    # Skip the unique-word check on word-less messages, otherwise set() == list()
    # trivially matches and we'd hand out a bonus for pure punctuation.
    if words and len(set(words)) == len(words):
        total -= _UNIQUE_WORD_BONUS

    # Floor before the palindrome doubling. A stricter reading of the brief
    # would floor only at the end, but then palindromes like "aba" never
    # actually double (see README for the reasoning).
    if total < _MIN_COST:
        total = _MIN_COST

    # Rule 7 — palindrome detection. Strip to alphanumerics, lower-case,
    # and compare with its reverse. An empty cleaned string is NOT a
    # palindrome (otherwise any pure-punctuation message would double).
    cleaned = "".join(ch.lower() for ch in message if ch.isalnum())
    if cleaned and cleaned == cleaned[::-1]:
        total *= 2

    # Quantise to 2dp using banker's-free half-up rounding, which matches
    # the intuitive "round a half upwards" people expect for money.
    quantised = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(quantised)
