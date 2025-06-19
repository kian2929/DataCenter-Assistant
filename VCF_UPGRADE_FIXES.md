# VCF Upgrade Issues Fixed

## Issue 1: Thread Safety Problems

**Problem**: The sensor event handlers were calling `async_schedule_update_ha_state()` from threads other than the Home Assistant event loop, causing RuntimeError exceptions.

**Root Cause**: The upgrade service fires Home Assistant events using `hass.bus.fire()`, which can be called from any thread. However, the sensor event handlers that respond to these events were directly calling Home Assistant async methods from the wrong thread context.

**Solution**: 
1. Modified event handlers to use `hass.async_create_task()` to schedule state updates on the correct event loop
2. Created separate async methods (`_async_update_state()` and `_async_update_logs_state()`) to handle the actual state updates

**Files Fixed**:
- `entity_factory.py`: Updated `VCFDomainUpgradeStatusSensor` and `VCFDomainUpgradeLogsSensor` event handlers

## Issue 2: API Response Handling

**Problem**: The VCF API was returning non-JSON responses (likely HTML error pages) for PATCH operations, causing JSON decode errors.

**Root Cause**: The `/v1/releases/domains/{domainId}` PATCH endpoint was returning an unexpected content type instead of JSON.

**Solution**:
1. Enhanced the VCF API client to handle both JSON and non-JSON responses
2. Added proper error handling for PATCH/PUT/DELETE operations that might return empty responses
3. Added comprehensive logging to help debug API issues
4. Added defensive programming with type checking throughout the upgrade service

**Files Fixed**:
- `vcf_api.py`: Enhanced `api_request()` method to handle ContentTypeError exceptions
- `upgrade_service.py`: Added type checking and better error messages for API responses

## Issue 3: Type Safety and Defensive Programming

**Problem**: The code assumed API responses would always be dictionaries, but sometimes they could be strings or other types.

**Solution**: 
1. Added `isinstance()` checks throughout the upgrade service
2. Added proper error handling for unexpected response formats
3. Enhanced logging to show actual API request/response details
4. Added fallback behavior for malformed responses

**Files Fixed**:
- `upgrade_service.py`: Added comprehensive type checking for all API response handling

## Key Improvements

### Thread-Safe Event Handling
```python
def _handle_upgrade_status_change(self, event):
    """Handle upgrade status change events."""
    if event.data.get("domain_id") == self._domain_id:
        # Schedule update on the Home Assistant event loop
        self.hass.async_create_task(self._async_update_state())

async def _async_update_state(self):
    """Async method to update entity state."""
    self.async_schedule_update_ha_state()
```

### Robust API Response Handling
```python
# Try to parse as JSON, but handle empty responses for PATCH/PUT/DELETE
try:
    return await resp.json()
except aiohttp.ContentTypeError:
    if method.upper() in ['PATCH', 'PUT', 'DELETE'] and resp.status in [200, 202, 204]:
        return {"status": "success", "message": f"Operation completed with status {resp.status}"}
    else:
        raise
```

### Type-Safe Response Processing
```python
if isinstance(upgradables_response, dict):
    available_upgrades = [
        upgrade for upgrade in upgradables_response.get("elements", [])
        if isinstance(upgrade, dict) and upgrade.get("status") == "AVAILABLE"
    ]
else:
    raise Exception("Unexpected response format from upgradables endpoint")
```

## Result

The VCF upgrade functionality now:
1. ✅ Handles sensor updates without thread safety errors
2. ✅ Properly processes API responses even when they're not JSON
3. ✅ Provides detailed error messages for debugging
4. ✅ Gracefully handles unexpected response formats
5. ✅ Maintains type safety throughout the upgrade workflow

The upgrade process can now start successfully and will provide better error reporting if API issues occur.
