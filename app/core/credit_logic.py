import re
import math

def calculate_text_credits(message: str) -> float:
    """
    Calculates credits based on text rules for Orbital Copilot.
    """
    if not message:
        return 1.0

    # 1. Base Cost
    total_credits = 1.0

    # 2. Character Count (0.05 per char)
    total_credits += len(message) * 0.05

    # 3. Word Length Multipliers
    # Rule: sequence of letters plus ' and -
    words = re.findall(r"[a-zA-Z'-]+", message)
    
    for word in words:
        length = len(word)
        if 1 <= length <= 3:
            total_credits += 0.1
        elif 4 <= length <= 7:
            total_credits += 0.2
        elif length >= 8:
            total_credits += 0.3

    # 4. Third Vowels (3rd, 6th, 9th...)
    # We use slicing [2::3] to get every 3rd character (index 2, 5, 8...)
    vowels = set("aeiouAEIOU")
    third_chars = message[2::3]
    for char in third_chars:
        if char in vowels:
            total_credits += 0.3

    # 5. Length Penalty (> 100 chars)
    if len(message) > 100:
        total_credits += 5.0

    # 6. Unique Word Bonus (-2 credits)
    # Case-sensitive check
    if len(words) > 0 and len(set(words)) == len(words):
        total_credits -= 2.0

    # Ensure minimum cost is 1.0 before palindrome doubling
    total_credits = max(1.0, total_credits)

    # 7. Palindromes (Double the total)
    # Clean: lowercase and remove non-alphanumeric
    clean_text = "".join(char.lower() for char in message if char.isalnum())
    if clean_text and clean_text == clean_text[::-1]:
        total_credits *= 2

    # Return rounded to 2 decimal places for financial precision
    return round(total_credits, 2)
