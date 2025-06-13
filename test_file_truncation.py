#!/usr/bin/env python3
"""Test to verify that coordinator.py and sensor.py have the correct truncation function."""

import os
import re

def check_truncation_function(file_path):
    """Check if the file has the correct truncation function."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check if truncate_description function exists
        function_pattern = r'def truncate_description\(.*?\):'
        function_match = re.search(function_pattern, content)
        
        if not function_match:
            return False, "truncate_description function not found"
        
        # Check if the function has max_length=61 parameter
        if 'max_length=61' not in content:
            return False, "Function doesn't use max_length=61"
        
        # Check if the function returns text[:max_length] + "..."
        if 'text[:max_length] + "..."' not in content:
            return False, "Function doesn't use correct truncation logic"
        
        return True, "Truncation function is correct"
        
    except Exception as e:
        return False, f"Error reading file: {e}"

def main():
    """Check both coordinator.py and sensor.py files."""
    files_to_check = [
        'custom_components/datacenter_assistant/coordinator.py',
        'custom_components/datacenter_assistant/sensor.py'
    ]
    
    print("Checking truncation function in datacenter assistant files:")
    print("=" * 60)
    
    all_correct = True
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            is_correct, message = check_truncation_function(file_path)
            status = "✅ PASS" if is_correct else "❌ FAIL"
            print(f"{file_path}: {status}")
            print(f"  {message}")
            all_correct = all_correct and is_correct
        else:
            print(f"{file_path}: ❌ FAIL")
            print(f"  File not found")
            all_correct = False
        print()
    
    print("=" * 60)
    print(f"Overall result: {'✅ ALL FILES CORRECT' if all_correct else '❌ SOME FILES NEED FIXING'}")
    
    return all_correct

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
