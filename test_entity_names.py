#!/usr/bin/env python3
"""Test script to verify entity names and no-update handling."""

import sys
import os

# Add the custom component to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components', 'datacenter_assistant'))

def test_entity_names():
    """Test that entity names are correctly formatted."""
    print("=== Testing Entity Names ===")
    
    # Mock coordinator data with no updates
    class MockCoordinator:
        def __init__(self):
            self.data = {
                "domain_updates": {
                    "domain-123": {
                        "domain_name": "Test Domain",
                        "domain_prefix": "domain1",
                        "current_version": "4.5.0",
                        "update_status": "up_to_date",
                        "next_version": None,
                        "component_updates": {}  # No updates available
                    }
                }
            }
    
    coordinator = MockCoordinator()
    
    # Test VCFDomainUpdateStatusSensor
    try:
        from sensor import VCFDomainUpdateStatusSensor
        status_sensor = VCFDomainUpdateStatusSensor(coordinator, "domain-123", "Test Domain", "domain1")
        print(f"✓ VCFDomainUpdateStatusSensor name: '{status_sensor._attr_name}'")
        print(f"✓ VCFDomainUpdateStatusSensor unique_id: '{status_sensor._attr_unique_id}'")
        print(f"✓ VCFDomainUpdateStatusSensor state (no updates): '{status_sensor.state}'")
        
        # Test attributes with no updates
        attrs = status_sensor.extra_state_attributes
        print(f"✓ VCFDomainUpdateStatusSensor attributes: {attrs}")
    except Exception as e:
        print(f"✗ VCFDomainUpdateStatusSensor test failed: {e}")
    
    # Test VCFDomainComponentsSensor  
    try:
        from sensor import VCFDomainComponentsSensor
        components_sensor = VCFDomainComponentsSensor(coordinator, "domain-123", "Test Domain", "domain1")
        print(f"✓ VCFDomainComponentsSensor name: '{components_sensor._attr_name}'")
        print(f"✓ VCFDomainComponentsSensor unique_id: '{components_sensor._attr_unique_id}'")
        print(f"✓ VCFDomainComponentsSensor state (no updates): '{components_sensor.state}'")
        
        # Test attributes with no updates
        attrs = components_sensor.extra_state_attributes
        print(f"✓ VCFDomainComponentsSensor attributes: {attrs}")
    except Exception as e:
        print(f"✗ VCFDomainComponentsSensor test failed: {e}")

if __name__ == "__main__":
    test_entity_names()
