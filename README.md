# DataCenter Assistant - VMware VCF Integration for Home Assistant

A custom Home Assistant integration for managing VMware Cloud Foundation (VCF) lifecycle operations.

## Features

- **VCF Bundle Management**: View and download available VCF bundles
- **Update Status Monitoring**: Monitor upgrade status across VCF components  
- **Automated Token Management**: Automatic VCF API token refresh
- **Component Status**: Track individual VCF component upgrade statuses
- **Manual Controls**: Buttons for manual token refresh, update execution, and bundle downloads

## Entities Created

### Sensors
- `sensor.vcf_upgrade_status` - Overall upgrade status (up_to_date, upgrades_available, not_connected)
- `sensor.vcf_upgrade_distribution` - Distribution of upgrade statuses across components
- `sensor.vcf_upgrade_components` - Individual component upgrade statuses
- `sensor.vcf_available_updates` - Available VCF bundles for download

### Binary Sensors  
- `binary_sensor.vcf_upgrades_available` - True if any upgrades are available

### Buttons
- `button.vcf_refresh_token` - Manually refresh VCF authentication token
- `button.vcf_execute_updates` - Execute available updates (only enabled when updates are available)
- `button.vcf_download_bundle` - Download available VCF bundles

## Services

- `datacenter_assistant.refresh_token` - Refresh VCF authentication token
- `datacenter_assistant.trigger_upgrade` - Trigger upgrade for specific component
- `datacenter_assistant.download_bundle` - Download specific VCF bundle

## Installation

1. Copy the `custom_components/datacenter_assistant` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Configuration → Integrations → Add Integration
4. Search for "DataCenter Assistant"
5. Enter your VCF connection details:
   - **VCF URL**: Your VCF SDDC Manager URL (e.g., https://vcf.domain.com)
   - **VCF Username**: Admin username for VCF
   - **VCF Password**: Admin password for VCF

## Configuration

The integration will automatically:
- Authenticate with VCF and obtain access tokens
- Refresh tokens before they expire
- Poll for bundle and upgrade information every 15 minutes

## API Endpoints Used

- `POST /v1/tokens` - Authentication
- `GET /v1/bundles` - Retrieve available bundles
- `PATCH /v1/bundles/{id}` - Download bundles
- `POST /v1/system/updates/{type}/{fqdn}/start` - Execute upgrades

## Requirements

- Home Assistant 2023.1 or later
- VMware Cloud Foundation 4.3 or later
- Network access from Home Assistant to VCF SDDC Manager

## Troubleshooting

Check the Home Assistant logs for any connection or authentication issues:
- Integration uses `custom_components.datacenter_assistant` logger
- Most common issues are related to network connectivity or VCF credentials

## Development

This integration was developed for VCF lifecycle management and monitoring within Home Assistant automation workflows.
