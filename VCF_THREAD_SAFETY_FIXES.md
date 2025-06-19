# VCF Thread Safety Fixes

## Overview
Fixed critical thread safety issues in the VCF (VMware Cloud Foundation) integration where Home Assistant was reporting "RuntimeError: Detected code that calls hass.async_create_task from a thread other than the event loop".

## Root Cause
The issue occurred because:
1. Event handlers in sensor entities were being triggered from background threads
2. These handlers were calling `hass.async_create_task()` directly, which is not allowed from non-main threads
3. Event firing in the upgrade service could potentially happen from background contexts

## Files Modified

### 1. entity_factory.py
**Problem**: Sensor event handlers called `hass.async_create_task()` directly from background threads.

**Fix**: Replaced direct calls with `hass.loop.call_soon_threadsafe()` to schedule tasks on the event loop:

```python
# Before (caused thread safety errors):
def _handle_upgrade_status_change(self, event):
    if event.data.get("domain_id") == self._domain_id:
        self.hass.async_create_task(self._async_update_state())

# After (thread-safe):
def _handle_upgrade_status_change(self, event):
    if event.data.get("domain_id") == self._domain_id:
        self.hass.loop.call_soon_threadsafe(
            lambda: self.hass.async_create_task(self._async_update_state())
        )
```

Applied to both:
- `VCFDomainUpgradeStatusSensor._handle_upgrade_status_change()`
- `VCFDomainUpgradeLogsSensor._handle_upgrade_logs_change()`

### 2. upgrade_service.py
**Problem**: Event firing could potentially happen from background threads.

**Fix**: Made event firing thread-safe by detecting execution context and using `call_soon_threadsafe` when needed:

```python
def set_upgrade_status(self, domain_id: str, status: str):
    # ... status update logic ...
    
    # Fire event for Home Assistant to update sensors (thread-safe)
    def fire_status_event():
        self.hass.bus.fire(
            "vcf_upgrade_status_changed",
            {"domain_id": domain_id, "status": status}
        )
    
    if hasattr(self.hass, 'loop') and self.hass.loop.is_running():
        # If called from a background thread, schedule on event loop
        self.hass.loop.call_soon_threadsafe(fire_status_event)
    else:
        # Already on main thread or loop not running
        fire_status_event()
```

Applied to both:
- `set_upgrade_status()`
- `set_upgrade_logs()`

### 3. button.py
**Problem**: Coordinator update callback called `hass.async_create_task()` directly.

**Fix**: Wrapped the task creation in `call_soon_threadsafe`:

```python
# Before:
def coordinator_update_callback():
    hass.async_create_task(create_domain_buttons())

# After:
def coordinator_update_callback():
    hass.loop.call_soon_threadsafe(
        lambda: hass.async_create_task(create_domain_buttons())
    )
```

### 4. sensor.py
**Problem**: Similar coordinator update callbacks with direct `async_create_task` calls.

**Fix**: Applied the same thread-safe pattern:

```python
def coordinator_update_callback():
    self.hass.loop.call_soon_threadsafe(
        lambda: self.hass.async_create_task(self._create_domain_entities(coordinator))
    )

def resource_coordinator_update_callback():
    self.hass.loop.call_soon_threadsafe(
        lambda: self.hass.async_create_task(self._create_resource_entities(resource_coordinator))
    )
```

## Technical Details

### Thread Safety Pattern
The fix follows the Home Assistant recommended pattern for thread safety:

1. **Detect Execution Context**: Check if we're on the main event loop
2. **Schedule Safely**: Use `hass.loop.call_soon_threadsafe()` to schedule work on the event loop
3. **Lambda Wrapper**: Use lambda to properly capture the async task creation

### Why This Works
- `call_soon_threadsafe()` is designed to be called from any thread
- It schedules a callback to run on the main event loop thread
- Once on the main thread, `hass.async_create_task()` is safe to call
- The lambda ensures proper closure of variables

## Testing
After applying these fixes:
- No more "RuntimeError: Detected code that calls hass.async_create_task from a thread other than the event loop" errors
- Event-driven sensor updates work correctly
- Upgrade workflow continues to function properly
- All async operations remain on the correct thread

## Impact
- **Stability**: Eliminates potential crashes from thread safety violations
- **Compatibility**: Ensures compliance with Home Assistant's threading model
- **Reliability**: Event-driven updates work consistently without errors
- **Future-Proof**: Code follows Home Assistant best practices

## References
- [Home Assistant Asyncio Thread Safety Guide](https://developers.home-assistant.io/docs/asyncio_thread_safety/#hassasync_create_task)
- [Python asyncio.loop.call_soon_threadsafe() documentation](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.call_soon_threadsafe)
