# VCF Lifecycle Management - Implementation Summary

## Overview
This Home Assistant integration manages VMware Cloud Foundation (VCF) component lifecycle, including NSX, vCenter, SDDC Manager, etc. It follows the workflow described in `flow.txt` to discover domains, check for updates, and manage the upgrade process.

## What Was Fixed and Improved

### 1. **Coordinator Logic - Following flow.txt Workflow**
- **Domain Discovery**: Now properly implements the flow.txt workflow:
  - Gets domains with `GET /v1/domains` and filters for `status="ACTIVE"`
  - Enumerates domains with prefixes (`domain1_`, `domain2_`, etc.)
  - Fails setup if no active domains found (as required)
  
- **SDDC Manager Mapping**: 
  - Uses `GET /v1/sddc-managers` to match SDDC managers to domains
  - Captures SDDC manager ID, FQDN, and version for each domain

- **Update Detection Workflow**: For each domain:
  - Gets current VCF version with `GET /v1/releases?domainId={domainID}`
  - Gets bundles with `GET /v1/bundles`
  - Filters for bundles with "VMware Cloud Foundation (version)" in description
  - If no VCF bundles found, reports "up to date"
  - If bundles found, considers the oldest by `releaseDate` (as per flow.txt)
  - Extracts version information following the variable naming convention:
    - `nextVersion_versionDescription`
    - `nextVersion_versionNumber`
    - `nextVersion_releaseDate`
    - `nextVersion_bundlesToDownload`

- **Component Update Detection**:
  - Uses `GET /v1/upgradables/domains/{domainId}/?targetVersion=<nextVersion_versionNumber>`
  - For each component, gets bundle details with `GET /v1/bundles/{componentBundleID}`
  - Stores component updates as `nextVersion_componentUpdates`

### 2. **New Sensor Architecture**
**Replaced old sensors with domain-aware sensors:**

- **VCFOverallStatusSensor**: Shows overall system status across all domains
- **VCFDomainCountSensor**: Shows count and details of active domains
- **VCFDomainUpdateStatusSensor**: Individual sensor per domain showing:
  - Update status ("updates_available", "up_to_date", "error")
  - Current and next version information
  - Component update details following flow.txt format
- **VCFDomainComponentsSensor**: Shows components available for update per domain

### 3. **Enhanced Binary Sensors**
- **VCFConnectionBinarySensor**: Shows VCF connection status
- **VCFUpdatesAvailableBinarySensor**: Shows if any domain has updates available

### 4. **Manual Trigger Button**
- **VCFManualUpdateCheckButton**: Allows manual triggering of the update check process (as required by flow.txt)

### 5. **Authentication Improvements**
- **Proactive Token Refresh**: Refreshes token 10 minutes before expiry
- **Automatic Retry**: Retries API calls with fresh token on 401 errors
- **Token Expiry Tracking**: Properly tracks and logs token expiration times

## Data Structure

The coordinator now returns data in this format:
```json
{
  "domains": [
    {
      "id": "domain-id",
      "name": "Management Domain",
      "status": "ACTIVE",
      "prefix": "domain1_",
      "sddc_manager_id": "sddc-id",
      "sddc_manager_fqdn": "sddc.example.com"
    }
  ],
  "domain_updates": {
    "domain-id": {
      "domain_name": "Management Domain",
      "domain_prefix": "domain1_",
      "current_version": "5.1.0",
      "update_status": "updates_available",
      "next_version": {
        "versionDescription": "VMware Cloud Foundation (5.2.0)",
        "versionNumber": "5.2.0",
        "releaseDate": "2024-01-15",
        "bundleId": "bundle-123",
        "bundlesToDownload": ["bundle-123"]
      },
      "component_updates": {
        "componentUpdate1": {
          "id": "bundle-456",
          "description": "NSX Manager 4.1.2",
          "version": "4.1.2",
          "componentType": "NSX_MANAGER"
        }
      }
    }
  }
}
```

## Entity Naming Convention

Following flow.txt requirements, entities are created per domain:
- `sensor.vcf_management_domain_updates` - Update status for Management Domain
- `sensor.vcf_management_domain_components` - Components in Management Domain
- `sensor.vcf_overall_status` - Overall system status
- `binary_sensor.vcf_connection` - Connection status
- `binary_sensor.vcf_updates_available` - Any updates available
- `button.vcf_manual_update_check` - Manual update check trigger

## Home Assistant Attributes

Each domain update sensor exposes attributes following flow.txt naming:
- `nextVersion_versionNumber`: Next VCF version available
- `nextVersion_versionDescription`: Description of the update
- `nextVersion_releaseDate`: Release date of the update
- `nextVersion_componentUpdates_componentUpdate1_description`: Component 1 description
- `nextVersion_componentUpdates_componentUpdate1_version`: Component 1 version

## Usage

1. **Setup**: Configure the integration with VCF URL, username, and password
2. **Monitoring**: Use the sensors to monitor update status across domains
3. **Manual Check**: Use the "VCF Manual Update Check" button to trigger immediate checking
4. **Automation**: Create Home Assistant automations based on update availability

## Services Available

- `datacenter_assistant.refresh_token` - Manually refresh authentication token
- `datacenter_assistant.trigger_upgrade` - Start upgrade process (implementation TBD)
- `datacenter_assistant.download_bundle` - Download update bundles

## Next Steps (As mentioned in flow.txt)

The actual upgrade workflow is marked as "TBD" in flow.txt. The current implementation provides:
1. ✅ Domain discovery and validation
2. ✅ Update detection and reporting
3. ✅ Manual trigger capability
4. ✅ Proper API authentication and token management
5. ⏳ Actual upgrade execution (to be implemented)

The foundation is now solid for implementing the upgrade execution workflow when requirements are finalized.
