# VCF SDDC Manager Upgrade State Preservation Fix

## Problem
During SDDC Manager upgrades, the VCF API becomes temporarily unavailable (as expected), but this causes all Home Assistant sensors to update with "unknown" or "unavailable" values, leading to confusing state changes like:
- VCF Overall Status changing from "upgrading" to "up_to_date" 
- VCF Connection showing as disconnected
- Domain statuses becoming unknown
- Host counts changing to 0

This happens because the coordinators continue trying to fetch data during the API outage and update sensors with empty/error responses.

## Solution
Implemented a state preservation system that maintains the last known good state during expected API outages:

### 1. Event-Driven API Outage Tracking
- **upgrade_service.py**: SDDC Manager upgrade process now fires events:
  - `vcf_api_outage_expected` when SDDC Manager upgrade starts
  - `vcf_api_restored` when API connectivity is restored

### 2. Coordinator State Preservation
- **coordinator.py**: Enhanced `VCFCoordinatorManager` with:
  - Event listeners for API outage notifications
  - State preservation logic that returns last successful data during outages
  - Timeout mechanism (1 hour) to prevent indefinite state preservation
  - Separate tracking for both upgrade and resource coordinators

### 3. Connection Sensor Enhancement  
- **binary_sensor.py**: Enhanced `VCFConnectionBinarySensor` with:
  - Event listeners for API outage notifications
  - Preservation of connection state during expected outages
  - Clear attributes indicating when preserved state is being used

### 4. Improved SDDC Manager Upgrade Monitoring
- **upgrade_service.py**: Enhanced `_upgrade_sddc_manager()` with:
  - Better API connectivity checking during upgrade
  - Event firing for coordinator notifications
  - Periodic connectivity tests every 5 minutes
  - Proper cleanup on upgrade completion or failure

## Key Features
- **Intelligent State Preservation**: Only preserves state during known SDDC Manager upgrades
- **Event-Driven Architecture**: Uses Home Assistant event bus for real-time communication
- **Timeout Protection**: Automatically resumes normal operation after 1 hour
- **Transparent Operation**: Attributes clearly indicate when preserved state is being used
- **Fallback Detection**: Can detect ongoing upgrades even without events as a fallback

## Result
During SDDC Manager upgrades:
- Sensors maintain their last known state instead of showing "unknown"
- VCF Connection sensor stays "connected" with clear indication of API outage
- Overall status remains accurate (e.g., stays "upgrading" instead of changing to "up_to_date")
- Users see consistent, logical state progression throughout the upgrade process

## Files Modified
1. `coordinator.py` - Added state preservation logic and event listeners
2. `upgrade_service.py` - Enhanced SDDC Manager upgrade monitoring and event firing
3. `binary_sensor.py` - Enhanced connection sensor with state preservation
