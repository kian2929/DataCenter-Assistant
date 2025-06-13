#!/usr/bin/env python3
"""Test to find all description fields in the codebase and verify they use truncation."""

import os
import re

def find_description_fields(file_path):
    """Find all description fields in a Python file."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Look for common description field patterns
        patterns = [
            r'"description"\s*:\s*([^,\n]+)',  # "description": value
            r"'description'\s*:\s*([^,\n]+)",  # 'description': value
            r'description\s*=\s*([^,\n]+)',   # description = value
        ]
        
        description_usages = []
        
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                value = match.group(1).strip()
                
                # Check if the value uses truncate_description function
                uses_truncation = 'truncate_description' in value
                description_usages.append({
                    'line': line_num,
                    'value': value,
                    'uses_truncation': uses_truncation,
                    'match_text': match.group(0)
                })
        
        return description_usages
        
    except Exception as e:
        return f"Error reading file: {e}"

def main():
    """Check description fields in all Python files."""
    files_to_check = [
        'custom_components/datacenter_assistant/coordinator.py',
        'custom_components/datacenter_assistant/sensor.py',
        'custom_components/datacenter_assistant/binary_sensor.py',
        'custom_components/datacenter_assistant/button.py'
    ]
    
    print("Checking description field usage in datacenter assistant files:")
    print("=" * 80)
    
    all_good = True
    
    for file_path in files_to_check:
        if not os.path.exists(file_path):
            print(f"{file_path}: ❌ File not found")
            all_good = False
            continue
            
        print(f"\n📁 {file_path}:")
        description_fields = find_description_fields(file_path)
        
        if isinstance(description_fields, str):  # Error message
            print(f"  ❌ {description_fields}")
            all_good = False
            continue
        
        if not description_fields:
            print("  ℹ️  No description fields found")
            continue
        
        for field in description_fields:
            status = "✅" if field['uses_truncation'] else "⚠️"
            print(f"  Line {field['line']}: {status} {field['match_text']}")
            if not field['uses_truncation']:
                print(f"    Value: {field['value']}")
                # Check if it's a simple string that might need truncation
                if ('"' in field['value'] or "'" in field['value']) and 'truncate_description' not in field['value']:
                    print("    ⚠️  This might need truncation if it's a long description")
                    all_good = False
    
    print("\n" + "=" * 80)
    print(f"Overall result: {'✅ ALL DESCRIPTION FIELDS CHECKED' if all_good else '⚠️ SOME FIELDS MAY NEED ATTENTION'}")
    
    return all_good

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
