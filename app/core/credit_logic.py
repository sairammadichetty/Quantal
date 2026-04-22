"""Text-based credit calculation for messages without a valid report_id.

Every rule in the brief is implemented here as a small, commented step so
a reviewer can diff the code against the spec line-by-line.

Implementation notes:

- We use `decimal.Decimal` internally to avoid binary-float drift
  (e.g. `0.1 + 0.2 == 0.30000000000000004`). The final value is quantised
  to 2 decimal places before being cast to `float` at the boundary. For
  this task 2dp is plenty; if Product ever requires more precision we can
  expose the unrounded `Decimal` directly.

- "Word" is defined by the brief as "any continual sequence of letters,
  plus ' and -". We interpret that as: a token made of letters/'/-
  that *contains at least one letter*. That excludes stray tokens like
  "-" or "'-" that the naive `[a-zA-Z'-]+` regex would otherwise count
  (and charge for).

- Rule ordering matters and is subtle. The brief says:
    • Unique Word Bonus: "subtract 2 ... (minimum should still be 1 credit)"
    • Palindromes:       "double ... after all other rules have been applied"
  We therefore floor at 1.0 *before* palindrome doubling. A strict reading
  of "minimum cost should still be 1 credit" as a final-floor would
  produce different values for some inputs; we chose the reading that
  keeps the palindrome rule meaningful (doubling a 1.0 floor to 2.0).
  This is called out in the README.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

# Module-level constants: easier to see/edit, and they make the tests
# readable when they want to reference the same values.
_BASE_COST = Decimal("1.0")
_PER_CHAR_COST = Decimal("0.05")
_SHORT_WORD_COST = Decimal("0.1")   # 1-3 chars
_MID_WORD_COST = Decimal("0.2")     # 4-7 chars
_LONG_WORD_COST = Decimal("0.3")    # 8+ chars
_THIRD_VOWEL_COST = Decimal("0.3")
_LENGTH_PENALTY = Decimal("5.0")
_LENGTH_PENALTY_THRESHOLD = 100
_UNIQUE_WORD_BONUS = Decimal("2.0")
_MIN_COST = Decimal("1.0")
_VOWELS = frozenset("aeiouAEIOU")

# "Word" = at least one letter, optionally interspersed with ' and -.
# This deliberately rejects tokens like "-" or "''" that the naive
# `[a-zA-Z'-]+` pattern would match.
_WORD_RE = re.compile(r"[A-Za-z'-]*[A-Za-z][A-Za-z'-]*")


def calculate_text_credits(message: str) -> float:
    """Compute the credit cost for a plain-text (non-report) message.

    Returns a `float` quantised to 2dp for convenient JSON serialisation.
    All internal maths is done with `Decimal` to keep intermediate values
    exact.
    """
    # `Decimal(0)` is safe for an empty string: base cost below still
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

    # Rule 6 — unique word bonus (case-sensitive). Skip the check when
    # there are no words, otherwise `set()==list()` trivially matches and
    # we'd hand out a bonus for punctuation-only messages.
    if words and len(set(words)) == len(words):
        total -= _UNIQUE_WORD_BONUS

    # Floor at the minimum cost *before* the palindrome doubling so that
    # the palindrome rule operates on a sensible value. See module
    # docstring for the rationale.
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
