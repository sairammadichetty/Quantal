"""Unit tests for calculate_text_credits.

Each test shows the expected value broken down step-by-step so the
working is easy to cross-check against the brief.
"""

from __future__ import annotations

import pytest

from app.core.credit_logic import calculate_text_credits


def test_empty_message_is_base_cost():
    # Just the base cost — no chars, no words, nothing else fires.
    assert calculate_text_credits("") == 1.0


def test_single_short_word_floors_at_one():
    # "Hi" (2 chars, 1 word of len 2)
    # base 1.0 + chars 2*0.05=0.1 + short-word 0.1 - unique 2.0 = -0.8 -> floor 1.0
    # Third-vowel check: index 2 is out of range, no bonus.
    # Not a palindrome ("hi" != "ih").
    assert calculate_text_credits("Hi") == 1.0


def test_mid_and_long_words_floors_to_minimum():
    # "Lease Agreement" (15 chars, "Lease"=mid, "Agreement"=long)
    # 1.0 + 15*0.05 + 0.2 + 0.3 = 2.25
    # 3rd-char indices 2,5,8,11,14 -> 'a',' ','r','m','t' -> 'a' is a vowel +0.3
    # 2 unique words -> -2.0
    # 2.25 + 0.3 - 2.0 = 0.55 -> floor 1.0
    assert calculate_text_credits("Lease Agreement") == 1.0


def test_repeated_words_skip_unique_bonus_and_do_not_floor():
    # "apple apple apple" — 17 chars, three identical mid-length words
    # 1 + 17*0.05 + 3*0.2 = 2.45
    # 3rd-char indices 2,5,8,11,14 -> 'p',' ','p',' ','p' (no vowels)
    # Not all unique -> no bonus. Not a palindrome.
    assert calculate_text_credits("apple apple apple") == 2.45


def test_third_vowel_counting_every_third_char():
    # "abcdefghi": indices 2,5,8 -> 'c','f','i' -> only 'i' is a vowel
    # 1.0 + 9*0.05 + 0.3 (long) + 0.3 (vowel) - 2.0 = 0.05 -> floor 1.0
    assert calculate_text_credits("abcdefghi") == 1.0


def test_length_penalty_above_100_chars():
    # 101 'a's. All 33 third-position chars are vowels.
    # 1 + 101*0.05 + 0.3 + 33*0.3 + 5.0 - 2.0 = 19.25
    # Palindrome -> *2 = 38.5
    assert calculate_text_credits("a" * 101) == 38.5


def test_unique_word_bonus_only_when_all_unique():
    repeated = calculate_text_credits("apple apple")
    unique = calculate_text_credits("apple banana")
    assert unique < repeated


def test_unique_word_bonus_is_case_sensitive():
    # "Apple" and "apple" are different words for the unique check.
    case_sensitive_unique = calculate_text_credits("Apple apple")
    true_duplicate = calculate_text_credits("apple apple")
    assert case_sensitive_unique < true_duplicate

    # "Apple apple": 1 + 11*0.05 + 2*0.2 - 2.0 = -0.05 -> floor 1.0
    assert case_sensitive_unique == 1.0


def test_floor_is_applied_before_palindrome_doubling():
    # "aba" would otherwise go negative after the unique-word bonus.
    # We floor to 1.0 first, then the palindrome rule doubles -> 2.0.
    # Flooring at the end instead would give 1.0 and make the palindrome
    # rule meaningless here.
    assert calculate_text_credits("aba") == 2.0

    assert calculate_text_credits("abc") == 1.0


def test_palindrome_doubles_final_value():
    # "aba": 1 + 0.15 + 0.1 + 0.3 - 2 = -0.45 -> floor 1.0 -> *2 = 2.0
    assert calculate_text_credits("aba") == 2.0


def test_palindrome_with_punctuation_and_spaces():
    # Not asserting an exact value here — just that the palindrome is
    # strictly more expensive than its non-palindrome twin.
    pal = calculate_text_credits("A man, a plan, a canal: Panama")
    non_pal = calculate_text_credits("A man, a plan, a canal: Havana")
    assert pal > non_pal


def test_pure_punctuation_is_not_a_palindrome():
    # Cleaned string is empty -> we must NOT double.
    # 1 + 3*0.05 = 1.15
    assert calculate_text_credits("!!!") == 1.15


def test_word_regex_ignores_standalone_dashes_and_apostrophes():
    # "- - -": no actual words, just punctuation.
    # 1 + 5*0.05 = 1.25
    assert calculate_text_credits("- - -") == 1.25


def test_word_regex_accepts_apostrophe_and_hyphen_inside_words():
    # "it's": 1 word of length 4 (mid).
    # 1 + 4*0.05 + 0.2 - 2 = -0.6 -> floor 1.0
    assert calculate_text_credits("it's") == 1.0


def test_decimal_precision_no_float_drift():
    # "abc": 1 + 0.15 + 0.1 - 2 = -0.75 -> floor 1.0
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
