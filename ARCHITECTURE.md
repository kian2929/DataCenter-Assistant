# DataCenter Assistant - Architecture Overview

## What It Does
The DataCenter Assistant is a Home Assistant integration that monitors and manages VMware Cloud Foundation (VCF) infrastructure. It tracks your VCF domains, detects available updates, monitors resource usage, and allows you to trigger upgrades directly from Home Assistant.

## How It Works

### Main Components

```
VCF Infrastructure → API Client → Data Coordinators → Home Assistant Entities
```

#### 1. **VCF API Client** (`vcf_api.py`)
- Handles authentication with your VCF environment
- Automatically refreshes expired tokens
- Makes all API calls to VCF endpoints

#### 2. **Data Coordinators** (`coordinator.py`)
- **Upgrade Coordinator**: Checks for VCF updates every 15 minutes
- **Resource Coordinator**: Monitors CPU/memory/storage every 10 seconds
- Caches data to avoid overwhelming your VCF system

#### 3. **Dynamic Entities** (`sensor.py`)
Creates Home Assistant entities based on your infrastructure:
- **Domain entities**: Overall status, version info, update availability
- **Resource entities**: Capacity usage, host counts, individual host metrics
- **Control entities**: Buttons to trigger upgrades and actions

#### 4. **Services** (Actions you can trigger)
- Refresh authentication tokens
- Download update bundles
- Start domain upgrades
- Acknowledge upgrade alerts

### Key Features

#### Smart Update Detection
- Compares your current VCF version with available updates
- Only shows compatible upgrade paths
- Tracks update status throughout the upgrade process

#### Automatic Token Management
- Monitors token expiration (refreshes before it expires)
- Handles authentication failures gracefully
- Updates stored credentials automatically

#### Resource Monitoring
- Real-time tracking of compute resources
- Host-level CPU, memory, and storage metrics
- Cluster and domain capacity summaries

## File Structure

```
custom_components/datacenter_assistant/
├── __init__.py           # Main integration setup
├── config_flow.py        # Configuration UI
├── coordinator.py        # Data fetching logic
├── vcf_api.py           # VCF API communication
├── sensor.py            # Entity creation
├── services.yaml        # Available actions
├── utils.py             # Helper functions
└── manifest.json        # Integration metadata
```

## Setup Process

1. **Configuration**: Enter VCF URL, username, and password
2. **Authentication**: Integration connects to VCF and gets access token
3. **Discovery**: Scans your VCF environment for domains and resources
4. **Entity Creation**: Creates Home Assistant entities for monitoring
5. **Data Collection**: Starts regular polling for updates and resource data

## Integration Flow

### Initial Setup
```
User Config → VCF Authentication → Domain Discovery → Entity Creation
```

### Ongoing Operation
```
Scheduled Updates → API Calls → Data Processing → Entity State Updates
```

### User Actions
```
Service Call → API Request → VCF Action → Status Update
```

## What You See in Home Assistant

### Entities Created
- `sensor.vcf_domain1_update_status` - Shows if updates are available
- `sensor.vcf_domain1_current_version` - Current VCF version
- `sensor.vcf_host_server01_cpu_usage` - Individual host metrics
- `button.vcf_domain1_start_upgrade` - Trigger upgrades

### Available Services
- `datacenter_assistant.refresh_token`
- `datacenter_assistant.start_domain_upgrade`
- `datacenter_assistant.download_bundle`

## Error Handling

The integration includes robust error handling:
- **Token Expiry**: Automatically refreshes authentication
- **API Failures**: Retries with exponential backoff
- **Network Issues**: Graceful degradation with status indicators
- **Invalid Data**: Validates responses before processing

## Development Status

Currently implemented:
- ✅ VCF authentication and token management
- ✅ Domain discovery and monitoring
- ✅ Resource usage tracking
- ✅ Basic upgrade services

In development (see `to_implement.txt`):
- 🔄 Automated upgrade workflows
- 🔄 Upgrade progress tracking
- 🔄 Real-time upgrade logs
- 🔄 Alert acknowledgment system
