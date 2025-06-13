#!/usr/bin/env python3
"""
Quick test of the precheck monitoring to understand the response structure.
"""

import asyncio
import aiohttp
import json

# VCF Configuration
VCF_URL = "https://192.168.101.62"
VCF_USERNAME = "administrator@vsphere.local"
VCF_PASSWORD = "VMware1!"

async def test_precheck_monitoring():
    """Test the precheck monitoring API response structure."""
    
    async with aiohttp.ClientSession() as session:
        # Get token
        login_url = f"{VCF_URL}/v1/tokens"
        auth_data = {"username": VCF_USERNAME, "password": VCF_PASSWORD}
        
        async with session.post(login_url, json=auth_data, ssl=False) as resp:
            if resp.status != 200:
                print(f"❌ Auth failed: {resp.status}")
                return
            
            data = await resp.json()
            token = data.get("accessToken")
            print(f"✅ Got token: {token[:20]}...")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Get domains
        async with session.get(f"{VCF_URL}/v1/domains", headers=headers, ssl=False) as resp:
            data = await resp.json()
            domain = data["elements"][0]
            domain_id = domain["id"]
            print(f"✅ Using domain: {domain['name']} ({domain_id})")
        
        # Start precheck query
        query_url = f"{VCF_URL}/v1/system/check-sets/queries"
        query_data = {
            "checkSetType": "UPGRADE",
            "domains": [{"domainId": domain_id}]
        }
        
        async with session.post(query_url, headers=headers, json=query_data, ssl=False) as resp:
            if resp.status != 200:
                print(f"❌ Query failed: {resp.status}")
                return
                
            query_response = await resp.json()
            query_id = query_response.get("queryId")
            resources = query_response.get("resources", [])
            print(f"✅ Query ID: {query_id}")
            print(f"✅ Resources: {len(resources)}")
        
        # Start precheck
        checkset_url = f"{VCF_URL}/v1/system/check-sets"
        checkset_data = {
            "queryId": query_id,
            "resources": [
                {
                    "resourceId": resource.get("resourceId"),
                    "type": resource.get("resourceType"),
                    "targetVersion": "5.2.0.0"
                } for resource in resources
            ],
            "targetVersion": "5.2.0.0"
        }
        
        async with session.post(checkset_url, headers=headers, json=checkset_data, ssl=False) as resp:
            if resp.status not in [200, 201, 202]:
                print(f"❌ Precheck start failed: {resp.status}")
                return
                
            checkset_response = await resp.json()
            precheck_id = checkset_response.get("id")
            print(f"✅ Precheck ID: {precheck_id}")
        
        # Monitor precheck status
        check_url = f"{VCF_URL}/v1/system/check-sets/{precheck_id}"
        
        print("\n🔍 Monitoring precheck status...")
        for i in range(5):  # Check 5 times
            await asyncio.sleep(2)
            
            async with session.get(check_url, headers=headers, ssl=False) as resp:
                if resp.status != 200:
                    print(f"❌ Status check failed: {resp.status}")
                    continue
                
                status_response = await resp.json()
                print(f"\n📊 Precheck Status Check #{i+1}:")
                print(f"   Full response: {json.dumps(status_response, indent=2)}")
                
                execution_status = status_response.get("executionStatus")
                print(f"   Execution Status: {execution_status}")
                
                # Check for different possible status fields
                possible_status_fields = ["status", "state", "currentStatus", "overallStatus"]
                for field in possible_status_fields:
                    if field in status_response:
                        print(f"   {field}: {status_response[field]}")

if __name__ == "__main__":
    asyncio.run(test_precheck_monitoring())
