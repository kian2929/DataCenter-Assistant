# VCF Upgrade Flow Implementation

## Overview
This document describes the implementation of the comprehensive VCF (VMware Cloud Foundation) upgrade orchestration system as specified in flow2.txt.

## New Entities

### Buttons
1. **VCF domainX Upgrade** - Triggers the upgrade process for a specific domain
2. **VCF domainX Acknowledge Alerts** - Acknowledges warnings during upgrade process

### Sensors  
1. **VCF domainX Status** - Original domain status (enhanced to show "update_process_started")
2. **VCF domainX Components To Update** - Original components sensor
3. **VCF domainX Upgrade Status** - NEW: Tracks upgrade progress through all phases
4. **VCF domainX Update Logs** - NEW: Provides markdown-formatted upgrade logs

### Switches
1. **VCF domainX Ignore Alerts** - Controls whether to ignore warnings during upgrades

## Upgrade Flow States

The **VCF domainX Upgrade Status** sensor progresses through these states:

1. `waiting_for_initiation` - Default state, no upgrade in progress
2. `update_process_started` - Upgrade button was pressed
3. `downloading_bundles` - Downloading component bundles
4. `setting_new_vcf_version_target` - Setting target VCF version
5. `initializing_prechecks` - Initializing upgrade prechecks
6. `running_prechecks` - Running prechecks
7. `evaluating_prechecks` - Evaluating precheck results (40 min timeout)
8. `prechecks_done` - Prechecks completed
9. `waiting_for_alert_acknowledgement` - Waiting for user to acknowledge warnings
10. `alerts_were_acknowledged` - User acknowledged alerts, continuing
11. `starting_upgrades` - Beginning component upgrades
12. `successfully_completed` - Upgrade completed successfully
13. `failed` - Upgrade failed at any point

## Key Features

### Bundle Downloads
- Downloads all component bundles including fallback bundles
- Uses concurrent downloads for efficiency
- Updates logs with progress for each component

### Precheck System
- Implements full precheck workflow per VCF API
- 40-minute timeout for precheck evaluation
- Extracts and displays errors/warnings in markdown format
- Respects "Ignore Alerts" setting or waits for manual acknowledgment

### Alert Handling
- **VCF domainX Ignore Alerts** switch controls automatic alert bypass
- **VCF domainX Acknowledge Alerts** button for manual warning acknowledgment
- Process pauses indefinitely until alerts are handled

### Logging System
- Rich markdown logs with timestamps and icons (✅❌⚠️ℹ️)
- Real-time status updates
- Error details and progress tracking
- Suitable for dashboard display

### Error Handling
- Comprehensive error handling at each phase
- Timeout management (40 min prechecks, 3 hour component upgrades)
- Automatic failure state on any error or timeout
- Detailed error messages in logs

## API Integration

The system integrates with VCF APIs following the official documentation:

### Bundle Downloads
```
PATCH /v1/bundles/{bundleID}
Body: {"downloadNow": true}
```

### Target Version Setting
```
PATCH /v1/releases/domains/{domainID}
Body: {"targetVersion": "5.2.1.0"}
```

### Precheck Workflow
```
GET /v1/system/check-sets/queries
POST /v1/system/check-sets
GET /v1/system/check-sets/{id} (monitoring)
```

### Final Validation
```
POST /v1/releases/domains/{domainID}/validations
Body: {"targetVersion": "5.2.1.0"}
```

## Home Assistant Integration

### Notifications
- Persistent notifications for key events
- Success/failure notifications
- Error details for troubleshooting

### State Management
- Orchestrator instances stored in hass.data
- Cross-entity communication via shared state
- Automatic cleanup after completion

### Entity Naming
- Consistent naming: `VCF domain1 [Function]`
- Unique IDs prevent conflicts
- Domain-specific entity creation

## Usage Workflow

1. **Check Updates**: Existing sensors show available updates
2. **Configure Alerts**: Set "Ignore Alerts" switch as desired
3. **Start Upgrade**: Press "VCF domainX Upgrade" button
4. **Monitor Progress**: Watch "Upgrade Status" and "Update Logs" sensors
5. **Handle Alerts**: If warnings appear, either acknowledge or enable ignore setting
6. **Wait for Completion**: Process runs autonomously to completion

## Technical Implementation

### Files Created/Modified
- `upgrade_orchestrator.py` - Main orchestration logic
- `switch.py` - New switch platform for ignore alerts
- `button.py` - Extended with upgrade buttons
- `sensor.py` - Extended with upgrade status/logs sensors
- `manifest.json` - Added switch platform

### Key Classes
- `VCFUpgradeOrchestrator` - Core upgrade logic
- `VCFDomainUpgradeStatusSensor` - Status tracking
- `VCFDomainUpgradeLogsSensor` - Log display
- `VCFDomainIgnoreAlertsSwitch` - Alert control
- `VCFDomainUpgradeButton` - Trigger upgrade
- `VCFDomainAcknowledgeAlertsButton` - Handle warnings

## Future Enhancements

The current implementation provides a solid foundation but could be extended with:

1. **Component-Specific Upgrades**: Individual component upgrade controls
2. **Rollback Functionality**: Ability to rollback failed upgrades  
3. **Scheduling**: Automated upgrade scheduling
4. **Progress Bars**: Visual progress indicators
5. **Email Notifications**: External notification options
6. **Backup Integration**: Pre-upgrade backup verification

## Testing and Validation

This implementation follows the flow2.txt specification and includes:
- Comprehensive error handling
- Timeout management
- State persistence
- User interaction points
- Detailed logging

The system is designed to handle real-world VCF environments with proper error recovery and user feedback mechanisms.
