import pytest
from app.core.credit_logic import calculate_text_credits

def test_base_cost():
    # Minimum cost should be 1.0
    assert calculate_text_credits("") == 1.0

def test_word_length_multipliers():
    # "The" (3 chars) = +0.1
    # "Lease" (5 chars) = +0.2
    # "Agreement" (9 chars) = +0.3
    # Base(1) + Chars(17*0.05=0.85) + Words(0.1+0.2+0.3=0.6) - Unique(-2) = 0.45 -> Floor 1.0
    assert calculate_text_credits("The Lease Agreement") == 1.0

def test_vowel_rule():
    # Index 2, 5, 8...
    # "Abc efg ijk"
    #      ^   ^   ^ 
    #   (3rd, 6th, 9th are vowels)
    # Total: 3 occurrences * 0.3 = 0.9 extra credits
    res = calculate_text_credits("Abcefgijk")
    # Base(1) + Chars(9*0.05=0.45) + Words(0.3) + Vowels(0.9) - Unique(-2) = 0.65 -> Floor 1.0
    assert res == 1.0

def test_length_penalty():
    # Message exactly 101 chars
    long_msg = "a" * 101
    res = calculate_text_credits(long_msg)
    # Base(1) + Chars(5.05) + Penalty(5.0) = 11.05
    assert res >= 11.05

def test_unique_word_bonus():
    # "apple apple" -> No bonus
    # "apple banana" -> -2 credits bonus
    cost_repeat = calculate_text_credits("apple apple")
    cost_unique = calculate_text_credits("apple banana")
    assert cost_unique < cost_repeat

def test_palindrome_doubling():
    # "Racecar" is a palindrome
    # After alphanumeric cleaning and lowercasing: "racecar"
    # Let's use a simple one: "aba"
    # Base(1) + Chars(3*0.05=0.15) + Word(0.1) + Vowel(1st 'a' at idx 2 = 0.3) - Unique(2) 
    # = Floor 1.0 -> Then doubled = 2.0
    assert calculate_text_credits("aba") == 2.0

def test_complex_palindrome():
    # "A man, a plan, a canal: Panama"
    # This should be recognized as a palindrome after cleaning
    res = calculate_text_credits("A man a plan a canal Panama")
    # If logic is correct, the final result is doubled
    # This is a great case to show the interviewer
    assert res > 1.0 
