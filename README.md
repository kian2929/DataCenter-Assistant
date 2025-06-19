# DataCenter Assistant - Home Assistant Integration

A comprehensive Home Assistant custom integration for monitoring and managing VMware vSphere Cloud Foundation (VCF) environments. This integration provides real-time monitoring, update management, and automated operations for your VCF infrastructure directly from your Home Assistant dashboard.

## Features

### 🔍 **VCF Monitoring**
- **Domain Monitoring**: Track status and health of all VCF domains
- **Resource Monitoring**: Monitor cluster capacity, host counts, and resource utilization
- **Version Tracking**: Keep track of current VCF versions across all domains
- **Update Detection**: Automatically detect available VCF updates and applicable releases

### 🔄 **Update Management**
- **Automated Update Checks**: Periodic checking for VCF updates
- **Update Status Tracking**: Monitor upgrade progress and status
- **Bundle Management**: Download and manage VCF upgrade bundles
- **Pre-check Operations**: Run pre-upgrade checks before applying updates

### 🎛️ **Control & Automation**
- **Manual Controls**: Buttons to trigger upgrades and refresh tokens
- **Service Integration**: Exposed services for advanced automation
- **Status Notifications**: Real-time status updates and logs
- **Dynamic Entity Creation**: Automatically creates entities based on your VCF configuration

## Architecture

### Core Components

#### 1. **VCF API Client** (`vcf_api.py`)
Central API client that handles all VCF operations:
- **Authentication Management**: Automatic token refresh and expiry handling
- **API Request Handling**: Centralized HTTP client with error handling and retry logic  
- **Domain Management**: VCF domain data models with business logic
- **Version Compatibility**: Smart version comparison for upgrade applicability

#### 2. **Data Coordinator** (`coordinator.py`)
Manages data fetching and caching:
- **VCFCoordinatorManager**: Main coordinator for VCF operations
- **Upgrade Data Fetching**: Retrieves domain and update information
- **SDDC Manager Mapping**: Maps SDDC managers to their domains
- **Update Detection**: Checks for available updates across all domains
- **Resource Monitoring**: Tracks cluster and host resources

#### 3. **Entity Factory** (`entity_factory.py`)
Dynamic entity creation system:
- **Domain-Specific Entities**: Creates entities for each VCF domain
- **Update Status Sensors**: Tracks upgrade progress and status
- **Capacity Monitoring**: Monitors domain and cluster capacity
- **Resource Utilization**: Tracks host and cluster resource usage

#### 4. **Sensor Platform** (`sensor.py`)
Home Assistant sensor entities:
- **Overall Status Sensors**: VCF environment health overview
- **Domain Count Sensors**: Track number of active domains
- **Dynamic Entity Management**: Handles creation/removal of domain-specific entities
- **Resource Monitoring**: Cluster and host resource sensors

#### 5. **Binary Sensors** (`binary_sensor.py`)
Boolean state monitoring:
- **Update Availability**: Binary sensors for update detection
- **Domain Health**: Active/inactive status monitoring
- **System Status**: Overall VCF system health indicators

#### 6. **Button Controls** (`button.py`)
Interactive control entities:
- **Upgrade Triggers**: Buttons to initiate VCF upgrades
- **Token Refresh**: Manual token refresh capabilities
- **Bundle Downloads**: Trigger bundle downloads manually

#### 7. **Configuration Flow** (`config_flow.py`)
Home Assistant configuration integration:
- **Setup Wizard**: Guided configuration of VCF credentials
- **Input Validation**: Validates VCF URL, username, and password
- **Error Handling**: Provides clear error messages for configuration issues

### Supporting Modules

#### **Utilities** (`utils.py`)
Helper functions for:
- Version string parsing and comparison
- Text truncation and formatting
- Resource icon determination
- Safe name conversion for entities

#### **Base Sensors** (`base_sensors.py`)
Base classes providing:
- Common sensor functionality
- Standardized attribute handling
- Consistent entity behavior
- Error state management

## Installation

### HACS Installation (Recommended)
1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots menu and select "Custom repositories"
4. Add `https://github.com/kian2929/DataCenter-Assistant` as a custom repository
5. Select "Integration" as the category
6. Click "Add"
7. Find "DataCenter Assistant" in HACS and install it
8. Restart Home Assistant

### Manual Installation
1. Copy the `custom_components/datacenter_assistant` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant
3. Go to Configuration → Integrations
4. Click "Add Integration" and search for "DataCenter Assistant"

## Configuration

### Initial Setup
1. Navigate to **Configuration** → **Integrations**
2. Click **Add Integration**
3. Search for **DataCenter Assistant**
4. Enter your VCF credentials:
   - **VCF URL**: Your VCF SDDC Manager URL (e.g., `https://your-vcf-fqdn`)
   - **Username**: VCF administrator username
   - **Password**: VCF administrator password

### Credential Requirements
- User must have sufficient privileges to:
  - Read domain information
  - Access release and bundle data
  - Perform upgrade operations (if using upgrade features)
  - Refresh authentication tokens

## Entities Created

The integration dynamically creates entities based on your VCF configuration:

### Global Entities
- `sensor.vcf_overall_status` - Overall VCF environment status
- `sensor.vcf_domain_count` - Number of active domains

### Per-Domain Entities (Dynamic)
For each VCF domain, the following entities are created:

#### Sensors
- `sensor.vcf_domain{X}_update_status` - Current update/upgrade status
- `sensor.vcf_domain{X}_capacity` - Domain resource capacity information
- `sensor.vcf_domain{X}_upgrade_logs` - Upgrade progress logs (Markdown formatted)

#### Binary Sensors  
- `binary_sensor.vcf_domain{X}_update_available` - Whether updates are available

#### Buttons
- `button.vcf_domain{X}_start_upgrade` - Trigger domain upgrade process
- `button.vcf_domain{X}_refresh_token` - Manually refresh authentication token

### Resource Monitoring Entities
- `sensor.vcf_cluster_{cluster_name}_host_count` - Number of hosts in cluster
- `sensor.vcf_host_{host_name}_resources` - Individual host resource utilization

## Services

The integration exposes the following services for advanced automation:

### `datacenter_assistant.refresh_token`
Manually refresh the VCF authentication token.
```yaml
service: datacenter_assistant.refresh_token
```

### `datacenter_assistant.trigger_upgrade`
Trigger an upgrade for a specific VCF component.
```yaml
service: datacenter_assistant.trigger_upgrade
data:
  component_type: "vcenter"  # vcenter, esxi, nsx, etc.
  fqdn: "vcenter.domain.local"
```

### `datacenter_assistant.download_bundle`
Download a specific VCF upgrade bundle.
```yaml
service: datacenter_assistant.download_bundle
data:
  bundle_id: "bundle-12345"
```

## Automation Examples

### Automatic Update Notifications
```yaml
automation:
  - alias: "VCF Update Available Notification"
    trigger:
      - platform: state
        entity_id: binary_sensor.vcf_domain1_update_available
        to: 'on'
    action:
      - service: notify.mobile_app
        data:
          message: "VCF Domain 1 has updates available!"
          title: "VCF Update Available"
```

### Scheduled Token Refresh
```yaml
automation:
  - alias: "Daily VCF Token Refresh"
    trigger:
      - platform: time
        at: "02:00:00"
    action:
      - service: datacenter_assistant.refresh_token
```

### Upgrade Progress Monitoring
```yaml
automation:
  - alias: "VCF Upgrade Status Change"
    trigger:
      - platform: state
        entity_id: sensor.vcf_domain1_update_status
    action:
      - service: notify.slack
        data:
          message: "VCF Domain 1 upgrade status: {{ states('sensor.vcf_domain1_update_status') }}"
```

## Dashboard Integration

### Lovelace Card Example
```yaml
type: entities
title: VCF Environment Status
entities:
  - sensor.vcf_overall_status
  - sensor.vcf_domain_count
  - binary_sensor.vcf_domain1_update_available
  - sensor.vcf_domain1_update_status
  - button.vcf_domain1_start_upgrade
```

### Markdown Card for Upgrade Logs
```yaml
type: markdown
title: VCF Upgrade Logs
content: >
  {{ states('sensor.vcf_domain1_upgrade_logs') }}
```

## Troubleshooting

### Common Issues

#### Authentication Failures
- **Issue**: Sensors show "unknown" or authentication errors
- **Solution**: Check VCF credentials and network connectivity
- **Action**: Use the `refresh_token` service or restart the integration

#### Missing Entities
- **Issue**: Expected domain entities not appearing  
- **Solution**: Ensure domains are in "ACTIVE" status in VCF
- **Action**: Check Home Assistant logs for initialization errors

#### Update Detection Issues
- **Issue**: Updates not being detected
- **Solution**: Verify user permissions for release and bundle APIs
- **Action**: Check VCF API connectivity and token validity

### Logging
Enable debug logging for troubleshooting:
```yaml
logger:
  default: warning
  logs:
    custom_components.datacenter_assistant: debug
```

### Support Files
- `manifest.json` - Integration metadata and requirements
- `services.yaml` - Service definitions and schemas
- `translations/` - Localization files (English/German)

## API Reference

The integration interacts with VCF APIs including:
- `/v1/domains` - Domain information
- `/v1/releases` - Version and release data  
- `/v1/bundles` - Upgrade bundle management
- `/v1/tokens` - Authentication management
- `/v1/sddc-managers` - SDDC Manager information

## Development Status

### Implemented Features ✅
- VCF domain monitoring
- Update detection and tracking  
- Token management and refresh
- Basic upgrade triggering
- Resource monitoring
- Dynamic entity creation

### Planned Features 🚧
- Complete automated upgrade workflow
- Pre-check execution and monitoring
- Bundle download progress tracking
- Enhanced upgrade status reporting
- Rollback capabilities
- Advanced automation triggers

See `to_implement.txt` for detailed development roadmap.

## Contributing

Contributions are welcome! Areas for contribution:
- Bug fixes and improvements
- Feature enhancements
- Documentation updates
- Localization/translations
- Testing and validation

## License

This project is licensed under the Apache License 2.0 - see the repository for details.

## Support

For issues, feature requests, or questions:
- GitHub Issues: [Create an issue](https://github.com/kian2929/DataCenter-Assistant/issues)
- Home Assistant Community: Search for "DataCenter Assistant"

---

**Note**: This integration requires a VMware vSphere Cloud Foundation environment and appropriate administrator credentials. Ensure proper network connectivity between Home Assistant and your VCF infrastructure.