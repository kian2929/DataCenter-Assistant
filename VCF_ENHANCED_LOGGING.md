# VCF Upgrade Service Enhanced Logging

## Overview
Added comprehensive logging to the VCF upgrade service to provide better visibility into the upgrade process, especially during the component upgrade phase where the original logging was insufficient.

## Enhanced Logging Areas

### 1. Upgrade Workflow Main Steps
- Added start/end logging for each major phase:
  - Target version setting
  - Bundle downloads
  - Pre-checks
  - Component upgrades
  - Final validation
  - Completion/failure

### 2. Component Upgrade Cycle Tracking
- **Cycle Counting**: Each upgrade cycle is numbered for tracking
- **Element Counting**: Shows total elements found vs available for upgrade
- **Status Breakdown**: Logs status of all elements when no upgrades are available
- **Progress Tracking**: Shows which upgrade is being processed (e.g., "Processing upgrade 2/5")

### 3. Bundle and Component Processing
- **Bundle Details**: Logs bundle ID, status, and component information
- **Component Information**: Shows component type, name, and version
- **Processing Decisions**: Logs whether each component will be upgraded or skipped
- **Error Handling**: Detailed error messages for failed bundle fetches or upgrades

### 4. SDDC Manager Upgrade Monitoring
- **Upgrade Start**: Logs when upgrade request is sent with data payload
- **Status Checks**: Numbers each status check and logs current status
- **API Availability**: Monitors API availability during SDDC Manager upgrade
- **Recovery Logic**: Logs when API comes back online and stabilization period

### 5. HOST Component Handling
- **Proper Classification**: Now correctly identifies "HOST" components (was causing warnings)
- **Skip Logging**: Clearly explains why HOST upgrades are skipped
- **Progress Counting**: Marks HOST components as "processed" to prevent infinite loops

## Key Improvements

### Before
```
2025-06-19 23:35:52.097 WARNING (MainThread) [custom_components.datacenter_assistant.upgrade_service] Unknown component type: HOST
```

### After
```
2025-06-19 23:35:52.097 INFO (MainThread) [custom_components.datacenter_assistant.upgrade_service] Domain 5d73e7e4-5ef6-4a69-ab9b-1237484054dd: Processing component - Type: HOST, Name: esx-01.example.com, Version: 8.0.2-22380479
2025-06-19 23:35:52.097 INFO (MainThread) [custom_components.datacenter_assistant.upgrade_service] Domain 5d73e7e4-5ef6-4a69-ab9b-1237484054dd: Skipping ESX host upgrade for component esx-01.example.com (HOST upgrades not implemented)
```

## New Log Messages

### Upgrade Cycle Information
- `Domain {id}: Starting upgrade cycle {n}`
- `Domain {id}: Found {n} total upgradable elements`
- `Domain {id}: Found {n} available upgrades`
- `Domain {id}: Completed upgrade cycle {n}, processed {n} upgrades`

### Component Processing
- `Domain {id}: Processing upgrade {i}/{total}`
- `Domain {id}: Processing component - Type: {type}, Name: {name}, Version: {version}`
- `Domain {id}: Starting {component} upgrade with bundle {bundle_id}`

### Status Monitoring
- `Domain {id}: {Component} upgrade status check #{n}`
- `Domain {id}: {Component} upgrade status: {status}`
- `Domain {id}: API temporarily unavailable during {component} upgrade`
- `Domain {id}: API is back online after {component} upgrade`

### Completion and Error Handling
- `Domain {id}: All upgrades completed successfully`
- `Domain {id}: No upgrades processed this cycle, waiting 60 seconds...`
- `Domain {id}: Upgrade workflow completed successfully!`

## Benefits

1. **Troubleshooting**: Easy to identify where the upgrade process stops or fails
2. **Progress Tracking**: Clear understanding of upgrade progress and current activity
3. **Performance Monitoring**: Track how long each phase takes
4. **Error Diagnosis**: Detailed error messages with context
5. **Cycle Detection**: Identify infinite loops or stuck processes
6. **Component Visibility**: See exactly which components are being processed

## Log Levels Used

- **DEBUG**: Detailed technical information (API requests/responses, detailed status)
- **INFO**: General progress and important status changes
- **WARNING**: Non-fatal issues (unknown component types, API temporarily unavailable)
- **ERROR**: Actual failures that affect the upgrade process

## Usage

With these enhanced logs, you can now:
1. See exactly which components are being processed
2. Track upgrade cycles and detect if the process is stuck
3. Monitor SDDC Manager upgrade progress even when API is unavailable
4. Understand why certain components are skipped
5. Identify the root cause of upgrade failures
6. Monitor the overall health of the upgrade process

The logs will help identify if the upgrade is progressing normally, stuck in a loop, or encountering specific component issues.
