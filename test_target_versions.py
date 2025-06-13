#!/usr/bin/env python3
"""
Test different target versions to find valid upgrade paths
"""

import asyncio
import aiohttp
import json

# VCF Configuration
VCF_URL = "https://192.168.101.62"
VCF_USERNAME = "administrator@vsphere.local"
VCF_PASSWORD = "VMware1!"

async def test_target_versions():
    """Test different target versions to find valid upgrade paths."""
    
    async with aiohttp.ClientSession() as session:
        # Login
        login_url = f"{VCF_URL}/v1/tokens"
        login_data = {
            "username": VCF_USERNAME,
            "password": VCF_PASSWORD
        }
        
        async with session.post(login_url, json=login_data, ssl=False) as resp:
            login_response = await resp.json()
            token = login_response.get("accessToken")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Get domain
        domains_url = f"{VCF_URL}/v1/domains"
        async with session.get(domains_url, headers=headers, ssl=False) as resp:
            domains_response = await resp.json()
            domain = domains_response["elements"][0]
            domain_id = domain["id"]
            domain_name = domain["name"]
            print(f"✅ Domain: {domain_name} ({domain_id})")
        
        # Test different target versions
        test_versions = [
            "5.2.0.1",
            "5.2.1",
            "5.2.1.0",
            "5.2.2",
            "5.2.2.0",
            "5.3.0",
            "5.3.0.0"
        ]
        
        print(f"\n🧪 Testing different target versions...")
        print("=" * 60)
        
        for target_version in test_versions:
            print(f"\n🎯 Testing version: {target_version}")
            
            # Test target version API
            target_url = f"{VCF_URL}/v1/domains/{domain_id}/version"
            patch_data = {"targetVersion": target_version}
            
            async with session.patch(target_url, headers=headers, json=patch_data, ssl=False) as resp:
                if resp.status in [200, 202]:
                    print(f"  ✅ Target Version API: Accepted")
                    
                    # Test upgradables for this version
                    upgradables_url = f"{VCF_URL}/v1/domains/{domain_id}/upgradables"
                    params = {"targetVersion": target_version}
                    
                    async with session.get(upgradables_url, headers=headers, params=params, ssl=False) as resp:
                        if resp.status == 200:
                            upgradables_response = await resp.json()
                            upgrades_count = len(upgradables_response.get("elements", []))
                            print(f"  ✅ Upgradables API: {upgrades_count} upgrades available")
                            
                            if upgrades_count > 0:
                                print(f"  🎉 VALID UPGRADE TARGET: {target_version}")
                                # Show first upgrade details
                                upgrade = upgradables_response.get("elements", [{}])[0]
                                print(f"    - Type: {upgrade.get('type', 'N/A')}")
                                print(f"    - Source: {upgrade.get('sourceVersion', 'N/A')}")
                                print(f"    - Target: {upgrade.get('targetVersion', 'N/A')}")
                                
                                # Test validation API
                                validation_url = f"{VCF_URL}/v1/releases/domains/{domain_id}/validations"
                                validation_data = {"targetVersion": target_version}
                                
                                async with session.post(validation_url, headers=headers, json=validation_data, ssl=False) as resp:
                                    if resp.status in [200, 201, 202]:
                                        print(f"  ✅ Validation API: Started successfully")
                                    else:
                                        validation_error = await resp.text()
                                        print(f"  ❌ Validation API: Error {resp.status}")
                                        if "SAME_SOURCE_AND_TARGET" not in validation_error:
                                            print(f"    {validation_error[:100]}")
                        else:
                            upgradables_error = await resp.text()
                            print(f"  ❌ Upgradables API: Error {resp.status}")
                            if "VCF_RUNTIME_ERROR" in upgradables_error:
                                print(f"    Runtime error - invalid version")
                            else:
                                print(f"    {upgradables_error[:100]}")
                else:
                    target_error = await resp.text()
                    print(f"  ❌ Target Version API: Error {resp.status}")
                    if "SAME_SOURCE_AND_TARGET" in target_error:
                        print(f"    Same as current version")
                    else:
                        print(f"    {target_error[:100]}")
        
        print(f"\n📊 Test Summary:")
        print("=" * 60)
        print("Tested various target versions to find valid upgrade paths.")
        print("Look for versions marked as 'VALID UPGRADE TARGET' above.")

if __name__ == "__main__":
    asyncio.run(test_target_versions())
