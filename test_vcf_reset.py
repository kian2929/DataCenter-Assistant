#!/usr/bin/env python3
"""
VCF State Investigation and Reset
Check current state and try to reset to baseline
"""

import asyncio
import aiohttp
import json

# VCF Configuration
VCF_URL = "https://192.168.101.62"
VCF_USERNAME = "administrator@vsphere.local"
VCF_PASSWORD = "VMware1!"

async def investigate_and_reset():
    """Investigate VCF state and try to reset if needed."""
    
    async with aiohttp.ClientSession() as session:
        # Authenticate
        login_data = {"username": VCF_USERNAME, "password": VCF_PASSWORD}
        async with session.post(f"{VCF_URL}/v1/tokens", json=login_data, ssl=False) as resp:
            token = (await resp.json()).get("accessToken")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Get domain info
        async with session.get(f"{VCF_URL}/v1/domains", headers=headers, ssl=False) as resp:
            domain = (await resp.json())["elements"][0]
            domain_id = domain["id"]
            domain_name = domain["name"]
        
        print(f"🏢 Domain: {domain_name}")
        print(f"🆔 ID: {domain_id}")
        
        # Check detailed domain state
        print(f"\n🔍 Investigating current domain state...")
        domain_detail_url = f"{VCF_URL}/v1/domains/{domain_id}"
        async with session.get(domain_detail_url, headers=headers, ssl=False) as resp:
            if resp.status == 200:
                domain_detail = await resp.json()
                
                print(f"📊 Domain Details:")
                print(f"   Name: {domain_detail.get('name')}")
                print(f"   Type: {domain_detail.get('type')}")
                print(f"   Status: {domain_detail.get('status')}")
                
                # Check domain manager info
                dm = domain_detail.get('domainManager', {})
                print(f"   Domain Manager:")
                print(f"     Version: {dm.get('version', 'Unknown')}")
                print(f"     FQDN: {dm.get('fqdn', 'Unknown')}")
                print(f"     Status: {dm.get('status', 'Unknown')}")
                
                # Check if there's a target version set
                target_version = domain_detail.get('targetVersion')
                if target_version:
                    print(f"   🎯 Target Version: {target_version}")
                else:
                    print(f"   🎯 Target Version: None (clean state)")
                
                # Check clusters
                clusters = domain_detail.get('clusters', [])
                print(f"   Clusters: {len(clusters)}")
                for cluster in clusters[:2]:  # Show first 2
                    print(f"     - {cluster.get('name')}: {cluster.get('status')}")
        
        # Check all active tasks
        print(f"\n🔍 Checking all active tasks...")
        tasks_url = f"{VCF_URL}/v1/tasks"
        async with session.get(tasks_url, headers=headers, ssl=False) as resp:
            if resp.status == 200:
                tasks = await resp.json()
                all_tasks = tasks.get("elements", [])
                
                # Filter for active tasks
                active_tasks = [
                    task for task in all_tasks 
                    if task.get("status") in ["IN_PROGRESS", "PENDING", "RUNNING"]
                ]
                
                print(f"📋 Total tasks: {len(all_tasks)}")
                print(f"⚡ Active tasks: {len(active_tasks)}")
                
                if active_tasks:
                    print(f"🔄 Active Tasks:")
                    for task in active_tasks[:5]:  # Show first 5
                        task_id = task.get("id", "Unknown")[:8]
                        task_type = task.get("type", "Unknown")
                        status = task.get("status", "Unknown")
                        creation_time = task.get("creationTimestamp", "Unknown")
                        print(f"     {task_id}... {task_type}: {status} ({creation_time})")
                        
                        # Check if task is related to our domain
                        resources = task.get("resources", [])
                        for resource in resources:
                            if resource.get("resourceId") == domain_id:
                                print(f"       ⚠️  This task affects our domain!")
                
                # Filter for recent failed tasks
                failed_tasks = [
                    task for task in all_tasks 
                    if task.get("status") in ["FAILED", "ERROR"]
                ]
                
                if failed_tasks:
                    print(f"\n❌ Recent Failed Tasks:")
                    for task in failed_tasks[:3]:  # Show first 3
                        task_id = task.get("id", "Unknown")[:8]
                        task_type = task.get("type", "Unknown")
                        status = task.get("status", "Unknown")
                        print(f"     {task_id}... {task_type}: {status}")
        
        # Try to clear any target version if set
        print(f"\n🔄 Attempting to clear target version (if any)...")
        clear_url = f"{VCF_URL}/v1/domains/{domain_id}/version"
        
        # First try to get current target
        async with session.get(clear_url, headers=headers, ssl=False) as resp:
            if resp.status == 200:
                version_info = await resp.json()
                print(f"📋 Current version info: {version_info}")
        
        # Try to clear target version by setting it to current version
        print(f"\n🧹 Attempting to reset to baseline state...")
        
        # Let's try the current version 5.2.0.0
        reset_data = {"targetVersion": "5.2.0.0"}
        async with session.patch(clear_url, headers=headers, json=reset_data, ssl=False) as resp:
            reset_response = await resp.text()
            
            if resp.status in [200, 202]:
                print(f"✅ Successfully reset target version to 5.2.0.0")
            elif resp.status == 400 and "SAME_SOURCE_AND_TARGET" in reset_response:
                print(f"✅ System is already at baseline (5.2.0.0)")
            else:
                print(f"⚠️  Reset attempt: {resp.status}")
                print(f"   Response: {reset_response[:200]}")
        
        # Now test if we can check upgradables again
        print(f"\n🔧 Testing upgradables after reset...")
        upgradables_url = f"{VCF_URL}/v1/domains/{domain_id}/upgradables"
        
        async with session.get(upgradables_url, headers=headers, ssl=False) as resp:
            if resp.status == 200:
                upgradables = await resp.json()
                upgrade_count = len(upgradables.get("elements", []))
                print(f"✅ Upgradables API working: {upgrade_count} upgrades")
                
                # Now try setting a valid target version again
                print(f"\n🎯 Re-testing target version 5.2.1.0...")
                test_data = {"targetVersion": "5.2.1.0"}
                
                async with session.patch(clear_url, headers=headers, json=test_data, ssl=False) as resp:
                    test_response = await resp.text()
                    
                    if resp.status in [200, 202]:
                        print(f"✅ SUCCESS! Target version 5.2.1.0 accepted after reset!")
                        
                        # Check upgradables with this version
                        params = {"targetVersion": "5.2.1.0"}
                        async with session.get(upgradables_url, headers=headers, params=params, ssl=False) as resp:
                            if resp.status == 200:
                                upgradables = await resp.json()
                                upgrade_count = len(upgradables.get("elements", []))
                                print(f"✅ Found {upgrade_count} upgrades for 5.2.1.0")
                                
                                print(f"\n🎉 INTEGRATION TEST RESULT:")
                                print(f"   ✅ VCF upgrade integration is working correctly!")
                                print(f"   ✅ Can set target version 5.2.1.0")
                                print(f"   ✅ Can detect available upgrades")
                                print(f"   ✅ Ready for full upgrade orchestration")
                                
                                return True
                            else:
                                print(f"⚠️  Upgradables check failed: {resp.status}")
                    else:
                        print(f"❌ Still failing to set 5.2.1.0: {resp.status}")
                        print(f"   {test_response[:200]}")
            else:
                error_text = await resp.text()
                print(f"❌ Upgradables still failing: {resp.status}")
                print(f"   {error_text[:200]}")
        
        return False

if __name__ == "__main__":
    print("🔍 VCF STATE INVESTIGATION AND RESET")
    print("🔄 Attempting to reset VCF to clean state")
    print("=" * 50)
    
    result = asyncio.run(investigate_and_reset())
    
    print("\n" + "=" * 50)
    if result:
        print("🎉 SUCCESS: VCF integration working after reset!")
    else:
        print("⚠️  The VCF system may need manual intervention")
    print("=" * 50)
