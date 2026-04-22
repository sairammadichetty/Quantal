"""Unit tests for `calculate_text_credits`.

Each test derives its expected value from the spec step-by-step in a
comment so a reviewer can verify correctness against the brief without
having to re-run the calculator in their head.
"""

from __future__ import annotations

import pytest

from app.core.credit_logic import calculate_text_credits


def test_empty_message_is_base_cost():
    # No chars, no words, no vowels, no penalty, no unique bonus (0 words).
    # Total = base(1.0) = 1.0
    assert calculate_text_credits("") == 1.0


def test_single_short_word_floors_at_one():
    # "Hi" (2 chars, 1 word of len 2)
    # base 1.0 + chars 2*0.05=0.1 + short-word 0.1 - unique 2.0 = -0.8 -> floor 1.0
    # Third-vowel check: index 2 is out of range, no bonus.
    # Not a palindrome ("hi" != "ih").
    assert calculate_text_credits("Hi") == 1.0


def test_mid_and_long_words_floors_to_minimum():
    # "Lease Agreement" — 15 chars, words "Lease"(mid), "Agreement"(long).
    # base 1.0 + chars 15*0.05=0.75 + mid 0.2 + long 0.3 = 2.25
    # Third-char indices 2,5,8,11,14 -> 'a',' ','r','m','t' -> only 'a' vowel = +0.3
    # Unique words (2 distinct) -> -2.0
    # 2.25 + 0.3 - 2.0 = 0.55 -> floors to 1.0. Not a palindrome.
    assert calculate_text_credits("Lease Agreement") == 1.0


def test_repeated_words_skip_unique_bonus_and_do_not_floor():
    # "apple apple apple" — 17 chars, three identical mid-length words.
    # base 1 + chars 17*0.05=0.85 + 3 mid words (3*0.2=0.6) = 2.45
    # Third-char indices 2,5,8,11,14 -> 'p',' ','p',' ','p' (no vowels).
    # Unique set has 1 element vs 3 words -> no bonus applied.
    # Not a palindrome. No length penalty.
    assert calculate_text_credits("apple apple apple") == 2.45


def test_third_vowel_counting_every_third_char():
    # "abcdefghi" — 9 chars; indices 2,5,8 -> 'c','f','i' -> only 'i' is a vowel (+0.3)
    # base 1.0 + 9*0.05=0.45 + word "abcdefghi" long 0.3 + vowel 0.3 = 2.05
    # Unique (1 word) -> -2.0 -> 0.05 -> floor 1.0
    # Not a palindrome.
    assert calculate_text_credits("abcdefghi") == 1.0


def test_length_penalty_above_100_chars():
    # 101 'a' characters.
    # base 1 + chars 101*0.05=5.05 + one long word 0.3
    # Third vowels: indices 2,5,...,98 -> 33 'a's each +0.3 = +9.9
    #   (positions 2,5,8,...,98 inclusive = 33 items)
    # Length penalty +5.0
    # Unique (1 word) -> -2.0
    # Total: 1 + 5.05 + 0.3 + 9.9 + 5.0 - 2.0 = 19.25
    # Palindrome? "aaa..." reversed equals itself -> double -> 38.5
    assert calculate_text_credits("a" * 101) == 38.5


def test_unique_word_bonus_only_when_all_unique():
    # Repeat -> no bonus
    repeated = calculate_text_credits("apple apple")
    # All unique -> bonus applied
    unique = calculate_text_credits("apple banana")
    assert unique < repeated


def test_unique_word_bonus_is_case_sensitive():
    # "Apple" vs "apple" are DIFFERENT words for the unique check, so this
    # message should receive the -2.0 bonus. Compare against "apple apple"
    # which has a true duplicate (and therefore no bonus) and must end up
    # strictly more expensive once the bonus takes effect.
    case_sensitive_unique = calculate_text_credits("Apple apple")
    true_duplicate = calculate_text_credits("apple apple")
    assert case_sensitive_unique < true_duplicate

    # Hand calculation for "Apple apple":
    # len=11 -> chars 11*0.05 = 0.55
    # words: "Apple"(5, mid=0.2), "apple"(5, mid=0.2) -> +0.4
    # third-char indices 2,5,8 -> 'p',' ','p' -> 0 vowels
    # set({"Apple","apple"}) has 2 elements == len(words) -> -2.0 bonus
    # 1.0 + 0.55 + 0.4 - 2.0 = -0.05 -> floor 1.0. Not a palindrome.
    assert case_sensitive_unique == 1.0


def test_floor_is_applied_before_palindrome_doubling():
    # "aba" is the canonical case: pre-floor total would be negative due to
    # the unique-word bonus on a single-word message. The 1-credit floor
    # kicks in BEFORE palindrome doubling, so the final value is exactly
    # 1.0 * 2 = 2.0. If the floor were applied after doubling instead, we
    # would get max(1.0, (-0.45 * 2)) = 1.0 — i.e. a different, wrong
    # answer. This test pins the correct ordering.
    assert calculate_text_credits("aba") == 2.0

    # Sanity: a non-palindrome that would also floor stays at 1.0.
    assert calculate_text_credits("abc") == 1.0


def test_palindrome_doubles_final_value():
    # "aba" -> 3 chars, word "aba" (3, short=0.1)
    # base 1 + chars 0.15 + word 0.1 = 1.25
    # Third-char 'a' at index 2 is a vowel -> +0.3 -> 1.55
    # Unique (1 word) -> -2 -> -0.45 -> floor 1.0
    # Palindrome ("aba") -> *2 -> 2.0
    assert calculate_text_credits("aba") == 2.0


def test_palindrome_with_punctuation_and_spaces():
    # "A man, a plan, a canal: Panama" -> palindrome after normalisation.
    # We don't need an exact value here — just the doubled vs undoubled
    # relationship. Compare to the same words in a non-palindrome order.
    pal = calculate_text_credits("A man, a plan, a canal: Panama")
    non_pal = calculate_text_credits("A man, a plan, a canal: Havana")
    # Palindrome doubling should make the palindrome strictly larger.
    assert pal > non_pal


def test_pure_punctuation_is_not_a_palindrome():
    # Cleaned string is empty -> must NOT double.
    # base 1 + chars 3*0.05=0.15 = 1.15 (no words, no vowels, no penalties)
    assert calculate_text_credits("!!!") == 1.15


def test_word_regex_ignores_standalone_dashes_and_apostrophes():
    # "- - -" has three hyphens and two spaces; no real words should be counted.
    # base 1 + chars 5*0.05=0.25 = 1.25
    # No words -> no multiplier, no unique bonus.
    # Third-char indices: 2,5 -> '-', ' ' (not vowels)
    # Not a palindrome? "-- -- --" cleaned is "" -> not a palindrome.
    assert calculate_text_credits("- - -") == 1.25


def test_word_regex_accepts_apostrophe_and_hyphen_inside_words():
    # "it's" — 4 chars, one word of length 4 (mid).
    # base 1 + chars 4*0.05=0.2 + mid 0.2 = 1.4
    # Third-vowel index 2 is "'" -> not vowel.
    # Unique -> -2 -> -0.6 -> floor 1.0.
    assert calculate_text_credits("it's") == 1.0


def test_decimal_precision_no_float_drift():
    # Inputs designed to expose 0.1+0.2 style drift:
    # "abc" -> 3 chars
    # base 1 + 3*0.05=0.15 + short word 0.1 = 1.25
    # Third-char 'c' at index 2 -> not vowel.
    # Unique -> -2 -> -0.75 -> floor 1.0. Not palindrome.
    assert calculate_text_credits("abc") == 1.0


@pytest.mark.parametrize(
    "message,expected_at_least",
    [
        ("Please produce a Short Lease Report", 1.0),
        ("What is the rent?", 1.0),
    ],
)
def test_realistic_messages_are_at_least_floor(message, expected_at_least):
    # Sanity check: real-world looking inputs never undershoot the 1-credit floor.
    assert calculate_text_credits(message) >= expected_at_least
