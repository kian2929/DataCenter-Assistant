# VCF Upgrade Implementation Summary

This implementation adds complete VCF (VMware Cloud Foundation) upgrade functionality to the DataCenter Assistant Home Assistant integration, following the specifications in `to_implement.txt`.

## New Components Implemented

### 1. VCF Upgrade Service (`upgrade_service.py`)
- **VCFUpgradeService**: Core service that handles the complete VCF upgrade workflow
- Implements all steps from targeting new versions to final validation
- Supports SDDC Manager, NSX-T, and vCenter upgrades (ESX host upgrades skipped as specified)
- Includes proper error handling, logging, and state management
- Handles API unavailability during SDDC Manager upgrades
- Fires Home Assistant events for real-time sensor updates

### 2. New Button Entities
- **VCFDomainUpgradeButton**: Starts VCF upgrade for each domain
  - Named as "VCF {domain_name} Start Upgrade"
  - Checks for available updates before starting
  - Shows appropriate messages when no updates are available
- **VCFDomainAcknowledgeButton**: Acknowledges alerts during upgrade
  - Named as "VCF {domain_name} Acknowledge Alerts"
  - Allows continuation of upgrade process when warnings/errors are present

### 3. New Sensor Entities
- **VCFDomainUpgradeStatusSensor**: Tracks upgrade status for each domain
  - Named as "VCF {domain_prefix} Upgrade Status"
  - States include:
    - `waiting_for_initiation` (default)
    - `targeting_new_vcf_version`
    - `downloading_bundles`
    - `running_prechecks`
    - `waiting_acknowledgement`
    - `starting_upgrades`
    - `upgrading_sddcmanager`
    - `upgrading_nsx`
    - `upgrading_vcenter`
    - `final_validation`
    - `successfully_completed`
    - `failed`

- **VCFDomainUpgradeLogsSensor**: Provides dynamic markdown messages
  - Named as "VCF {domain_prefix} Upgrade Logs"
  - Stores full logs in attributes for dashboard card display
  - Default value: "No Messages"
  - Updates in real-time during upgrade process

### 4. Home Assistant Services
- **start_domain_upgrade**: Service to start domain upgrade programmatically
- **acknowledge_upgrade_alerts**: Service to acknowledge alerts via automation

## Upgrade Workflow Implementation

The implementation follows the exact workflow specified in `to_implement.txt`:

### Step 1: Target VCF Version
- Uses `PATCH /v1/releases/domains/{domainID}` with target version
- Updates status to "targeting_new_vcf_version"

### Step 2: Download Bundles
- Downloads all bundles from `next_release["patchBundles"]`
- Uses `PATCH /v1/bundles/{id}` with `downloadNow: true`
- Monitors download status with `GET /v1/bundles/{id}`
- Updates status to "downloading_bundles"

### Step 3: Run Pre-checks
- Two-phase check-set query process
- Maps resource types to target versions using BOM data
- Executes pre-checks with `POST /v1/system/check-sets`
- Handles warnings/errors with user acknowledgement
- Updates status to "running_prechecks" and "waiting_acknowledgement" if needed

### Step 4: Component Upgrades
- Dynamically detects available upgrades with `GET /v1/upgradables/domains/{domainId}`
- Supports different upgrade mechanisms:
  - **SDDC Manager**: Handles API unavailability during upgrade
  - **NSX-T**: Complex upgrade with manager and host cluster specs
  - **vCenter**: In-place upgrade with proper resource mapping
- Updates status appropriately for each component type

### Step 5: Final Validation
- Uses `POST /v1/releases/domains/{domainID}/validations`
- Checks for "COMPLETED" execution status
- Updates to "successfully_completed" on success

## Dynamic Entity Creation

The implementation uses dynamic entity creation to handle domains discovered at runtime:

- Buttons and sensors are created automatically when domains are detected
- Uses coordinator listeners to detect new domains
- Proper cleanup and state management
- Unique entity IDs based on domain prefixes

## Real-time Updates

- Upgrade service fires Home Assistant events on status/log changes
- Sensors listen for these events and update automatically
- No polling required for upgrade status updates
- Immediate feedback in the UI

## Error Handling

- Comprehensive error handling at every step
- Proper logging for debugging
- Failed upgrades set status to "failed" with error details
- Timeout handling for long-running operations
- API unavailability handling during SDDC Manager upgrades

## Integration Points

- Seamlessly integrates with existing VCF coordinator
- Uses existing VCF API client for authentication and requests
- Follows existing patterns for entity creation and management
- Maintains compatibility with current sensor structure

## Usage

1. **Via Buttons**: Use the "VCF {domain} Start Upgrade" button in Home Assistant
2. **Via Services**: Call `datacenter_assistant.start_domain_upgrade` service
3. **Monitor Progress**: Watch the upgrade status and logs sensors
4. **Handle Alerts**: Use the acknowledge button or service when needed

The implementation is complete and ready for testing with a live VCF environment.
