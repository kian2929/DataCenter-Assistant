#!/usr/bin/env python3
"""Standalone test script to verify description truncation functionality."""

def truncate_description(text, max_length=61):
    """Truncate description to max_length characters, adding '...' if truncated."""
    if text is None:
        return ""
    text = str(text)
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

def test_truncation():
    """Test various truncation scenarios."""
    
    # Test cases
    test_cases = [
        # (input, expected_output, description)
        ("Short text", "Short text", "Short text should not be truncated"),
        ("This is exactly 61 characters long - it should not truncate!", "This is exactly 61 characters long - it should not truncate!", "Exactly 61 chars should not be truncated"),
        ("This is a very long description that exceeds 61 characters and should be truncated with ellipsis", "This is a very long description that exceeds 61 characters an...", "Long text should be truncated"),
        ("", "", "Empty string should remain empty"),
        (None, "", "None should become empty string"),
        ("A" * 100, "A" * 61 + "...", "Very long string should be truncated to 61 + ..."),
    ]
    
    print("Testing truncate_description function:")
    print("=" * 70)
    
    all_passed = True
    
    for i, (input_text, expected, description) in enumerate(test_cases, 1):
        result = truncate_description(input_text)
        passed = result == expected
        all_passed = all_passed and passed
        
        print(f"Test {i}: {description}")
        print(f"  Input: {repr(input_text)}")
        if input_text is not None:
            print(f"  Input length: {len(str(input_text))}")
        print(f"  Expected: {repr(expected)} (length: {len(expected)})")
        print(f"  Got: {repr(result)} (length: {len(result)})")
        print(f"  Status: {'✅ PASS' if passed else '❌ FAIL'}")
        print()
    
    print("=" * 70)
    print(f"Overall result: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    # Test with real-world example
    print("\n🔍 Real-world example:")
    long_description = "This VMware vCenter Server upgrade bundle contains critical security updates, performance improvements, and new features for managing virtual infrastructure. It includes enhanced vSphere management capabilities, improved resource allocation algorithms, and updated security protocols to protect against the latest threats."
    truncated = truncate_description(long_description)
    print(f"Original length: {len(long_description)}")
    print(f"Truncated length: {len(truncated)}")
    print(f"Original: {long_description}")
    print(f"Truncated: {truncated}")
    
    return all_passed

if __name__ == "__main__":
    success = test_truncation()
    exit(0 if success else 1)
