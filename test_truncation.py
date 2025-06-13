#!/usr/bin/env python3

import sys
import os

# Add the custom_components directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'custom_components', 'datacenter_assistant'))

from coordinator import truncate_description
from sensor import truncate_description as sensor_truncate_description

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
        result_coordinator = truncate_description(input_text)
        result_sensor = sensor_truncate_description(input_text)
        
        print(f"Test {i}:")
        print(f"  Input: {repr(input_text)}")
        print(f"  Length: {len(input_text) if isinstance(input_text, str) else 'N/A'}")
        print(f"  Expected: {repr(expected)}")
        print(f"  Coordinator result: {repr(result_coordinator)}")
        print(f"  Sensor result: {repr(result_sensor)}")
        print(f"  Result length: {len(result_coordinator) if isinstance(result_coordinator, str) else 'N/A'}")
        
        # Check if results match expected
        coordinator_ok = result_coordinator == expected
        sensor_ok = result_sensor == expected
        
        print(f"  Coordinator ✓: {coordinator_ok}")
        print(f"  Sensor ✓: {sensor_ok}")
        print()
        
        if not (coordinator_ok and sensor_ok):
            print(f"❌ Test {i} FAILED!")
            return False
    
    print("✅ All tests passed!")
    return True

if __name__ == "__main__":
    test_truncation()
