# VCF Upgrade Service Infinite Loop Fix

## Problem Identified
The VCF upgrade service was stuck in an infinite loop because:

1. **Incorrect Component Data Extraction**: The code was trying to get `name` and `version` fields from component data, but the API returns `description` and `toVersion` instead.

2. **Infinite Loop with HOST Components**: The system was counting HOST components as "processed" but they remained in AVAILABLE status, causing the upgrade cycle to repeat indefinitely.

## Root Cause Analysis

From the API response logs, the component structure is:
```json
{
  "description": "VMware ESXi Server Update Bundle",
  "vendor": "VMware",
  "releasedDate": "2024-10-09T12:00:00Z", 
  "toVersion": "8.0.3-24280767",
  "fromVersion": "8.0.3-24022510",
  "imageType": "PATCH",
  "id": "435b7342-9ec6-4692-8ca8-dcc396633313",
  "type": "HOST"
}
```

But the code was expecting:
- `name` field (doesn't exist - should use `description`)
- `version` field (doesn't exist - should use `toVersion`)

## Fixes Applied

### 1. Fixed Component Data Extraction

**Before:**
```python
component_name = component_data.get("name", "unknown")
component_version = component_data.get("version", "unknown")
```

**After:**
```python
component_name = component_data.get("description", "unknown")  # Use description as name
component_version = component_data.get("toVersion", component_data.get("version", "unknown"))  # Use toVersion or fallback
```

### 2. Added HOST-Only Detection Logic

Added logic to detect when only HOST upgrades remain available:

```python
# Check if we only have HOST components left (which we skip)
non_host_upgrades = []
for upgrade in available_upgrades:
    # ... check component type ...
    if component_type and "HOST" not in component_type:
        non_host_upgrades.append(upgrade)

if not non_host_upgrades:
    _LOGGER.info(f"Domain {domain_id}: Only HOST upgrades remain, and HOST upgrades are not implemented. Considering upgrade complete.")
    break
```

### 3. Separated HOST vs Non-HOST Processing Tracking

**Before:**
```python
processed_count = 0
# ... process upgrades ...
processed_count += 1  # for all components including HOST
```

**After:**
```python
processed_count = 0
non_host_processed = 0
# ... process upgrades ...
if component_type in ["SDDC_MANAGER", "NSX_T_MANAGER", "VCENTER"]:
    processed_count += 1
    non_host_processed += 1
elif "HOST" in component_type:
    # Don't count HOST components as processed to avoid infinite loop
    continue
```

### 4. Improved Cycle Completion Logic

**Before:**
```python
if processed_count == 0:
    # Wait and retry
    await asyncio.sleep(60)
```

**After:**
```python
if non_host_processed == 0:
    if processed_count == 0:
        # Nothing processed at all - wait and try again
        await asyncio.sleep(60)
    else:
        # Only HOST upgrades were found - exit the loop
        break
```

## Expected Behavior After Fix

1. **Component Info**: Will now correctly show component descriptions and versions:
   ```
   Processing component - Type: HOST, Name: VMware ESXi Server Update Bundle, Version: 8.0.3-24280767
   ```

2. **HOST Handling**: Will properly skip HOST components without counting them as processed

3. **Loop Termination**: Will exit the upgrade loop when only HOST components remain instead of looping forever

4. **Status Messages**: Will clearly indicate when only HOST upgrades remain and the upgrade is considered complete

## Log Output Changes

**Before (Infinite Loop):**
```
Domain xxx: Completed upgrade cycle 1, processed 1 upgrades
Domain xxx: Completed upgrade cycle 2, processed 1 upgrades  
Domain xxx: Completed upgrade cycle 3, processed 1 upgrades
... (continues forever)
```

**After (Proper Termination):**
```
Domain xxx: Processing component - Type: HOST, Name: VMware ESXi Server Update Bundle, Version: 8.0.3-24280767
Domain xxx: Skipping ESX host upgrade for component VMware ESXi Server Update Bundle (HOST upgrades not implemented)
Domain xxx: Completed upgrade cycle 1, processed 0 upgrades (0 non-HOST)
Domain xxx: Only HOST upgrades remain, exiting upgrade loop
```

## Files Modified
- `custom_components/datacenter_assistant/upgrade_service.py`
  - Fixed component data field mapping
  - Added HOST-only detection logic  
  - Separated HOST vs non-HOST processing tracking
  - Improved cycle completion logic

This fix resolves the infinite loop issue and allows the upgrade process to properly complete when only HOST components remain.
