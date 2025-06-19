# VCF Upgrade Flow Documentation

## Overview
The DataCenter Assistant provides a comprehensive upgrade workflow for VMware Cloud Foundation (VCF) domains. This document explains how the automated upgrade process works from initiation to completion.

## Upgrade Entities

### Button Entity: Domain Upgrade Trigger
- **Entity Name**: `button.vcf_domain{X}_start_upgrade`
- **Purpose**: Initiates the upgrade process for a specific domain
- **Behavior**:
  - If no update available: Shows message "No updates available for this domain"
  - If update available: Shows message "Starting upgrade process..." and begins workflow

### Status Entity: Upgrade Progress Tracking
- **Entity Name**: `sensor.vcf_domain{X}_upgrade_status`
- **Purpose**: Tracks the current state of the upgrade process
- **States**:
  - `waiting_for_initiation` - Default state, no upgrade in progress
  - `targeting_new_vcf_version` - Setting target version for upgrade
  - `downloading_bundle` - Downloading update bundle
  - `precheck_running` - Running pre-upgrade validation
  - `precheck_failed` - Pre-upgrade checks failed
  - `upgrade_in_progress` - Upgrade actively running
  - `waiting_for_acknowledgment` - Requires user acknowledgment to continue
  - `upgrade_completed` - Upgrade finished successfully
  - `upgrade_failed` - Upgrade encountered an error

### Log Entity: Upgrade Messages
- **Entity Name**: `sensor.vcf_domain{X}_upgrade_logs`
- **Purpose**: Provides real-time upgrade messages for dashboard display
- **Format**: Markdown-formatted messages for dashboard cards
- **Default Value**: "## No Messages\nNo upgrade activity at this time."

## Upgrade Workflow Steps

### Phase 1: Initiation
```
User Clicks Upgrade Button → Check Update Availability → Begin Workflow
```

1. **Button Press Handler**
   - Validates update availability
   - Sets status to `targeting_new_vcf_version`
   - Updates logs with "Starting upgrade process for domain {name}"

### Phase 2: Target Version Setup
```
Status: targeting_new_vcf_version
API Call: PATCH /v1/releases/domains/{domainID}
```

**Request Body:**
```json
{
  "releaseId": "{target_release_id}",
  "operation": "TARGET"
}
```

**Success Response**: HTTP 202 (Accepted)
- Updates status based on response
- Logs: "Successfully targeted version {version} for upgrade"

### Phase 3: Bundle Download
```
Status: downloading_bundle
API Call: PATCH /v1/bundles/{bundleId}
```

**Request Body:**
```json
{
  "operation": "DOWNLOAD"
}
```

**Monitoring**: Poll bundle status until download completes
- Logs progress updates
- Handles download failures with retry logic

### Phase 4: Pre-upgrade Validation
```
Status: precheck_running
API Call: POST /v1/domains/{domainId}/upgrades/precheck
```

**Request Body:**
```json
{
  "releaseId": "{target_release_id}",
  "skipKnownHostCheck": false
}
```

**Validation Results**:
- **Success**: Status → `upgrade_in_progress`
- **Failure**: Status → `precheck_failed`, logs error details

### Phase 5: Upgrade Execution
```
Status: upgrade_in_progress
API Call: POST /v1/domains/{domainId}/upgrades
```

**Request Body:**
```json
{
  "releaseId": "{target_release_id}",
  "skipKnownHostCheck": false
}
```

**Progress Monitoring**:
- Continuous polling of upgrade status
- Real-time log updates
- Detection of alert conditions

### Phase 6: Alert Handling
```
Status: waiting_for_acknowledgment
Service: acknowledge_upgrade_alerts
```

**When Alerts Occur**:
- Status changes to `waiting_for_acknowledgment`
- Logs display alert details
- User can call acknowledgment service to continue

**Alert Acknowledgment**:
```
Service Call: datacenter_assistant.acknowledge_upgrade_alerts
API Call: POST /v1/domains/{domainId}/upgrades/acknowledge
```

### Phase 7: Completion
```
Status: upgrade_completed | upgrade_failed
```

**Success Path**:
- Status → `upgrade_completed`
- Logs → "Upgrade completed successfully"
- Entity states updated with new version info

**Failure Path**:
- Status → `upgrade_failed`
- Logs → Detailed error information
- Rollback procedures (if applicable)

## API Endpoints Used

| Phase | Method | Endpoint | Purpose |
|-------|---------|----------|---------|
| Target | PATCH | `/v1/releases/domains/{domainID}` | Set target version |
| Download | PATCH | `/v1/bundles/{bundleId}` | Download bundle |
| Precheck | POST | `/v1/domains/{domainId}/upgrades/precheck` | Validate readiness |
| Upgrade | POST | `/v1/domains/{domainId}/upgrades` | Start upgrade |
| Monitor | GET | `/v1/domains/{domainId}/upgrades/{upgradeId}` | Check progress |
| Acknowledge | POST | `/v1/domains/{domainId}/upgrades/acknowledge` | Handle alerts |

## Error Handling

### Retry Logic
- **Network Failures**: Exponential backoff with max 3 retries
- **Token Expiry**: Automatic token refresh and retry
- **API Rate Limits**: Respect rate limiting headers

### Failure Recovery
- **Precheck Failures**: Stop process, provide detailed error logs
- **Download Failures**: Retry download up to 3 times
- **Upgrade Failures**: Log error details, maintain failed status

### User Notifications
- **Critical Errors**: Persistent notifications in Home Assistant
- **Progress Updates**: Real-time log entity updates
- **Completion Status**: Final status notifications

## Dashboard Integration

### Recommended Card Setup
```yaml
type: entities
title: VCF Domain 1 Upgrade
entities:
  - entity: sensor.vcf_domain1_upgrade_status
    name: Status
  - entity: button.vcf_domain1_start_upgrade
    name: Start Upgrade
  - entity: sensor.vcf_domain1_upgrade_logs
    name: Messages
```

### Automation Examples
```yaml
# Notify when upgrade completes
- alias: "VCF Upgrade Complete"
  trigger:
    platform: state
    entity_id: sensor.vcf_domain1_upgrade_status
    to: 'upgrade_completed'
  action:
    service: notify.mobile_app
    data:
      message: "VCF Domain 1 upgrade completed successfully!"
```

## Monitoring and Observability

### Key Metrics
- Upgrade duration tracking
- Success/failure rates
- Alert frequency
- Component-specific upgrade times

### Logging Strategy
- **DEBUG**: API request/response details
- **INFO**: Workflow state transitions
- **WARNING**: Recoverable errors and retries
- **ERROR**: Critical failures requiring intervention

### Health Checks
- Regular validation of upgrade service availability
- Token validity monitoring
- API endpoint connectivity tests
