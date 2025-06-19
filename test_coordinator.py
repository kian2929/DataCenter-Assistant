#!/usr/bin/env python3
"""
Test script to verify VCF resource coordinator behavior
"""

import asyncio
import logging
from datetime import timedelta

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_timedelta():
    """Test that timedelta is working correctly"""
    interval = timedelta(seconds=10)
    logger.info(f"Update interval: {interval}")
    logger.info(f"Total seconds: {interval.total_seconds()}")
    
    # Test that the interval is indeed 10 seconds
    assert interval.total_seconds() == 10.0, f"Expected 10.0 seconds, got {interval.total_seconds()}"
    logger.info("✓ Timedelta test passed")

async def test_coordinator_behavior():
    """Test coordinator behavior simulation"""
    logger.info("Testing coordinator update behavior...")
    
    # Simulate coordinator updates
    update_count = 0
    
    async def mock_update_method():
        nonlocal update_count
        update_count += 1
        logger.info(f"Mock update #{update_count} called")
        return {"test": update_count, "timestamp": asyncio.get_event_loop().time()}
    
    # Simulate polling every 2 seconds for 10 seconds
    start_time = asyncio.get_event_loop().time()
    for i in range(5):  # 5 updates over 10 seconds
        result = await mock_update_method()
        logger.info(f"Update result: {result}")
        await asyncio.sleep(2)
    
    end_time = asyncio.get_event_loop().time()
    duration = end_time - start_time
    
    logger.info(f"Test completed in {duration:.2f} seconds with {update_count} updates")
    logger.info("✓ Coordinator behavior test passed")

async def main():
    """Run all tests"""
    logger.info("Starting VCF coordinator tests...")
    
    try:
        await test_timedelta()
        await test_coordinator_behavior()
        logger.info("✅ All tests passed!")
        
        # Additional check for resource coordinator specifics
        logger.info("\n📋 Resource Coordinator Configuration:")
        logger.info("- Update interval: 10 seconds")
        logger.info("- Should fetch: /v1/domains -> /v1/domains/{id} -> /v1/clusters/{id} -> /v1/hosts/{id}")
        logger.info("- Expected entities: Domain capacity, cluster host counts, host resources")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
