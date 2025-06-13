# Home Assistant Attribute Name Optimization

## Problem
Long attribute names in Home Assistant were wrapping to multiple lines, making the UI unreadable with too many attributes visible.

Example problematic names:
- `nextVersion_componentUpdates_vCenter_description` (47 characters)
- `nextVersion_versionDescription` (30 characters) 
- `domains_with_updates` (18 characters)

## Solution
Shortened all attribute names while maintaining clarity and understanding.

## Attribute Name Changes

### VCFDomainUpdateStatusSensor
| Old Name | New Name | Savings |
|----------|----------|---------|
| `domain_name` | `domain` | 5 chars |
| `domain_prefix` | `prefix` | 7 chars |
| `current_version` | `curr_ver` | 7 chars |
| `update_status` | `status` | 3 chars |
| `nextVersion_versionNumber` | `next_ver` | 17 chars |
| `nextVersion_versionDescription` | `next_desc` | 21 chars |
| `nextVersion_releaseDate` | `next_date` | 14 chars |
| `nextVersion_bundlesToDownload` | `next_bundles` | 17 chars |
| `nextVersion_componentUpdates_{comp}_description` | `{comp}_desc` | ~31 chars |
| `nextVersion_componentUpdates_{comp}_version` | `{comp}_ver` | ~28 chars |
| `nextVersion_componentUpdates_{comp}_id` | `{comp}_id` | ~24 chars |

### VCFDomainComponentsSensor
| Old Name | New Name | Savings |
|----------|----------|---------|
| `domain_name` | `domain` | 5 chars |
| `component_count` | `count` | 10 chars |
| `components.description` | `components.desc` | 7 chars |
| `components.version` | `components.ver` | 4 chars |
| `components.component_type` | `components.type` | 10 chars |

### VCFOverallStatusSensor  
| Old Name | New Name | Savings |
|----------|----------|---------|
| `total_domains` | `total` | 8 chars |
| `domains_with_updates` | `with_updates` | 8 chars |
| `domains_up_to_date` | `up_to_date` | 8 chars |
| `domains_with_errors` | `errors` | 13 chars |

### VCFDomainCountSensor
| Old Name | New Name | Savings |
|----------|----------|---------|
| `update_status` | `upd_status` | 3 chars |
| `current_version` | `curr_ver` | 7 chars |
| `sddc_manager_fqdn` | `sddc_fqdn` | 8 chars |

## Results

### Before Optimization:
```
nextVersion_componentUpdates_vCenter_description: vCenter upgrade...
nextVersion_componentUpdates_vCenter_version: 8.0.2.00300
nextVersion_componentUpdates_NSX_description: NSX upgrade with...
nextVersion_versionDescription: VMware Cloud Foundation...
```

### After Optimization:
```
vCenter_desc: vCenter upgrade...
vCenter_ver: 8.0.2.00300
NSX_desc: NSX upgrade with...
next_desc: VMware Cloud Foundation...
```

## Benefits
- ✅ Attribute names now fit on single lines
- ✅ More attributes visible without scrolling
- ✅ Better use of Home Assistant screen space
- ✅ Maintained clarity and understanding
- ✅ Consistent abbreviation patterns
- ✅ Maximum attribute name length reduced from 47 to 16 characters
