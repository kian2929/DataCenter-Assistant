# VCF Pre-check Request Body Fix v2

## Issue
The pre-check request body was missing some resources (particularly CLUSTER) because they weren't being properly included from the initial response when they didn't appear in the detailed response.

## Root Cause
The issue was that when storing resources from the initial response, I wasn't preserving their `checkSets` data. So when a resource like CLUSTER didn't appear in the detailed response (because it has no BOM mapping), it would fall back to the initial response data but without any check sets.

## Fix Applied

### 1. Enhanced Initial Resource Storage
Modified the initial resource processing to store check sets data:

```python
# Store the complete resource data for later processing
resources_data.append({
    "resourceType": resource_type,
    "resourceId": resource_id,
    "resourceName": resource_name,
    "domain": resource.get("domain"),
    "checkSets": resource.get("checkSets", [])  # Store check sets from initial response
})
```

### 2. Improved Logging
Added comprehensive logging to track:
- Check sets count for each resource in initial response
- Which response (detailed vs initial) is being used for each resource
- Final resource count and check sets in the request body
- Warning messages for invalid data

### 3. Enhanced Debug Information
Added detailed logging for:
- Resource processing from both responses
- Check sets validation and processing
- Final request structure verification

## Expected Behavior
Now when running pre-checks:
1. Initial query finds all resources (e.g., NSXT_MANAGER, VCENTER, ESX, CLUSTER)
2. Detailed query returns resources with BOM mappings (e.g., NSXT_MANAGER, VCENTER, ESX)
3. Final request includes ALL resources:
   - Resources with detailed data use that
   - Resources without detailed data (like CLUSTER) use their initial response data
   - All resources retain their check sets appropriately

## Files Modified
- `custom_components/datacenter_assistant/upgrade_service.py`
  - Enhanced initial resource storage to preserve check sets
  - Improved logging throughout the pre-check process
  - Added validation and warning messages

## Verification
The fix ensures that:
- All resources found in the initial query are included in the final pre-check request
- Resources without BOM mappings (like CLUSTER) are properly included with their check sets
- Comprehensive logging allows for easy debugging of the pre-check process
- The request body structure matches VCF API expectations
