# VCF Pre-Check Request Body Fix

## Problem Identified
The VCF pre-check request body was missing resources (specifically CLUSTER) because the code was incorrectly filtering out resources that don't have target versions in the BOM (Bill of Materials).

## Root Cause Analysis

### Original Flow Issues:
1. **Step 1**: Initial query returns 4 resources: SDDC_MANAGER, NSX_T_MANAGER, CLUSTER, VCENTER
2. **Step 2**: BOM mapping only finds target versions for 3 resources (no CLUSTER version)
3. **Step 3**: Detailed query only includes the 3 resources with target versions
4. **Step 4**: Final execution only includes the 3 resources from detailed response

### Expected vs Actual Behavior:
- **Expected**: All 4 resources should be included in final request body
- **Actual**: Only 3 resources (missing CLUSTER) were included

### Comparison:
**Expected API Call Body** (from user's example):
```json
{
  "resources": [
    {"resourceType": "VCENTER", ...},
    {"resourceType": "SDDC_MANAGER", ...},
    {"resourceType": "CLUSTER", ...},    // <- Missing in original code
    {"resourceType": "NSX_T_MANAGER", ...}
  ],
  "queryId": "...",
  "metadata": {"targetVersion": "5.2.1.0"}
}
```

**Actual Generated Body** (from logs):
```json
{
  "resources": [
    {"resourceType": "VCENTER", ...},
    {"resourceType": "SDDC_MANAGER", ...},
    {"resourceType": "NSX_T_MANAGER", ...}
    // CLUSTER missing!
  ],
  "queryId": "...",
  "metadata": {"targetVersion": "5.2.1.0"}
}
```

## Fixes Applied

### 1. Fixed Resource Target Version Mapping
**Before**: Only included resources with BOM target versions
```python
if target_resource_version:
    resources_with_versions.append({
        "resourceType": resource_type,
        "resourceTargetVersion": target_resource_version
    })
else:
    _LOGGER.warning(f"No target version found for resource type {resource_type}")
```

**After**: Include all resources, add target version only if available
```python
resource_spec = {"resourceType": resource_type}

if target_resource_version:
    resource_spec["resourceTargetVersion"] = target_resource_version
    _LOGGER.info(f"Mapped {resource_type} to version {target_resource_version}")
else:
    _LOGGER.info(f"Including {resource_type} without target version")

resources_with_versions.append(resource_spec)
```

### 2. Fixed Final Check-Sets Data Building
**Before**: Only used resources from detailed response (incomplete)
```python
# Only processed resources from detailed response
for resource in second_response_resources:
    # Process only resources with target versions
```

**After**: Use ALL resources from initial response, supplement with detailed response
```python
# Create map of detailed response for lookup
detailed_resources_map = {}
for resource in second_response_resources:
    detailed_resources_map[resource_type] = resource

# Process ALL resources from initial response
for initial_resource in resources_data:
    # Use detailed response if available, otherwise use initial response
    if resource_type in detailed_resources_map:
        resource_to_use = detailed_resources_map[resource_type]
    else:
        resource_to_use = initial_resource
```

## Technical Details

### Resource Type Handling
- **SDDC_MANAGER, NSX_T_MANAGER, VCENTER**: Have BOM target versions, included in detailed response
- **CLUSTER**: No BOM target version, excluded from detailed response, but still needs check sets from initial response

### Check Sets Source Priority
1. **First Priority**: Use check sets from detailed response (has target version context)
2. **Fallback**: Use check sets from initial response (for resources without target versions)

### Logging Improvements
- Clear indication of which data source is used for each resource
- Shows whether resources have target versions or not
- Tracks the final resource count to match expected behavior

## Expected Results

### Resource Inclusion
- **Before**: 3 resources in final request
- **After**: 4 resources in final request (includes CLUSTER)

### Log Output Changes
**Before**:
```
Domain xxx: 3 resources mapped to target versions
Domain xxx: Processing 3 resources from detailed response
Domain xxx: Prepared check-sets for 3 resources
```

**After**:
```
Domain xxx: 4 resources prepared for detailed query
Domain xxx: Building final check-sets data using all 4 initial resources
Domain xxx: Processing resource 3 - Type: CLUSTER, ID: ..., Name: ...
Domain xxx: Using initial response data for CLUSTER (not in detailed response)
Domain xxx: Prepared check-sets for 4 resources
```

### API Request Body
The final request body will now include all resources with their appropriate check sets:
- Resources with target versions use detailed response check sets
- Resources without target versions (like CLUSTER) use initial response check sets
- All resources include proper domain information and resource details

## Files Modified
- `custom_components/datacenter_assistant/upgrade_service.py`
  - Fixed resource target version mapping logic
  - Enhanced final check-sets data building to include all resources
  - Improved logging for better troubleshooting

This fix ensures that pre-checks include all necessary resources, matching the expected VCF API behavior and preventing incomplete assessments.
