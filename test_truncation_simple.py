#!/usr/bin/env python3

def truncate_description(text, max_length=64):
    """Truncate description text to 61 characters + '...' if needed."""
    if not text or not isinstance(text, str):
        return text
    if len(text) <= 61:
        return text
    return text[:61] + "..."

def test_truncation():
    """Test the truncate_description function."""
    
    # Test cases
    test_cases = [
        ("Short text", "Short text"),  # Should not be truncated
        ("This is exactly 61 characters long - it should not truncate", "This is exactly 61 characters long - it should not truncate"),  # Exactly 61 chars
        ("This is a very long description that exceeds 61 characters and should be truncated with ellipsis", "This is a very long description that exceeds 61 characte..."),  # Should be truncated
        ("", ""),  # Empty string
        (None, None),  # None value
        (123, 123),  # Non-string value
    ]
    
    print("Testing truncate_description function...")
    print("=" * 50)
    
    for i, (input_text, expected) in enumerate(test_cases, 1):
        result = truncate_description(input_text)
        
        print(f"Test {i}:")
        print(f"  Input: {repr(input_text)}")
        print(f"  Length: {len(input_text) if isinstance(input_text, str) else 'N/A'}")
        print(f"  Expected: {repr(expected)}")
        print(f"  Result: {repr(result)}")
        print(f"  Result length: {len(result) if isinstance(result, str) else 'N/A'}")
        
        # Check if results match expected
        result_ok = result == expected
        
        print(f"  Status: {'✓' if result_ok else '❌'}")
        print()
        
        if not result_ok:
            print(f"❌ Test {i} FAILED!")
            return False
    
    print("✅ All tests passed!")
    return True

if __name__ == "__main__":
    test_truncation()
