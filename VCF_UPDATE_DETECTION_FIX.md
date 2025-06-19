# VCF Update Availability Detection Fix

## Problem

After the object-oriented refactoring in commit `49084dbf42d76b20116f8472abb409e826c2e2d2`, the VCF update availability detection stopped working. Updates that were previously detected correctly were no longer being found.

## Root Cause Analysis

The issue was in the `_check_domain_updates` method in `coordinator.py`. The sequence of operations was incorrect:

### Before Fix (Broken)
```python
# Get current version from API
current_version = releases_data.get("elements", [{}])[0].get("version")

# Call find_applicable_releases BEFORE setting current_version on domain object
applicable_releases = domain.find_applicable_releases(future_releases_data.get("elements", []))

# Set update info AFTER trying to find applicable releases
domain.set_update_info(current_version, "updates_available", applicable_releases[0])
```

### The Problem
The `VCFDomain.find_applicable_releases()` method starts with:
```python
def find_applicable_releases(self, future_releases):
    if not self.current_version:
        return []  # Returns empty list immediately!
```

Since `domain.current_version` was `None` when `find_applicable_releases()` was called, it always returned an empty list, making it appear as if no updates were available.

## Solution

Fixed the sequence by setting the `current_version` on the domain object **before** calling `find_applicable_releases()`:

### After Fix (Working)
```python
# Get current version from API
current_version = releases_data.get("elements", [{}])[0].get("version")

# Set current version on domain BEFORE calling find_applicable_releases
domain.current_version = current_version

# Now find_applicable_releases can properly compare versions
applicable_releases = domain.find_applicable_releases(future_releases_data.get("elements", []))

# Set complete update info
domain.set_update_info(current_version, "updates_available", applicable_releases[0])
```

## Files Modified

1. **`coordinator.py`**: Fixed the sequence in `_check_domain_updates()` method
2. **`vcf_api.py`**: Enhanced logging in `find_applicable_releases()` for better debugging

## Additional Improvements

- Added comprehensive debug logging to track the update detection process
- Added warnings when current_version is not set
- Added logging to show how many future releases were retrieved and evaluated
- Added version comparison logging for better troubleshooting

## Verification

The fix ensures that:
1. Domain objects have their current_version set before update detection
2. The update detection logic works identically to the original working version
3. Better logging is available for troubleshooting future issues

This restores the update availability detection functionality to the same level as commit `85962a27a36e17e99d16d5a5b8df39a0b5ce511b`.
