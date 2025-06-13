#!/usr/bin/env python3
"""
Test script to get detailed upgrade information for VCF 5.2.1.0
"""

import asyncio
import aiohttp
import json

# VCF Configuration
VCF_URL = "https://192.168.101.62"
VCF_USERNAME = "administrator@vsphere.local"
VCF_PASSWORD = "VMware1!"

async def test_upgrade_details():
    """Get detailed upgrade information for 5.2.1.0."""
    
    # Get token
    async with aiohttp.ClientSession() as session:
        # Login
        login_url = f"{VCF_URL}/v1/tokens"
        login_data = {
            "username": VCF_USERNAME,
            "password": VCF_PASSWORD
        }
        
        async with session.post(login_url, json=login_data, ssl=False) as resp:
            if resp.status != 200:
                print(f"❌ Login failed: {resp.status}")
                return
            
            login_response = await resp.json()
            token = login_response.get("accessToken")
            print(f"✅ Got token: {token[:50]}...")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Get domains
        domains_url = f"{VCF_URL}/v1/domains"
        async with session.get(domains_url, headers=headers, ssl=False) as resp:
            domains_response = await resp.json()
            domain = domains_response["elements"][0]
            domain_id = domain["id"]
            domain_name = domain["name"]
            print(f"✅ Using domain: {domain_name} ({domain_id})")
        
        # Test upgradables with 5.2.1.0
        target_version = "5.2.1.0"
        upgradables_url = f"{VCF_URL}/v1/domains/{domain_id}/upgradables"
        params = {"targetVersion": target_version}
        
        print(f"\n🔍 Getting upgradables for version {target_version}...")
        async with session.get(upgradables_url, headers=headers, params=params, ssl=False) as resp:
            if resp.status == 200:
                upgradables_response = await resp.json()
                print(f"📊 Upgradables Response:")
                print(json.dumps(upgradables_response, indent=2))
                
                elements = upgradables_response.get("elements", [])
                print(f"\n📈 Found {len(elements)} upgradable items:")
                
                for i, element in enumerate(elements, 1):
                    print(f"\n  Upgrade {i}:")
                    print(f"    ID: {element.get('id', 'N/A')}")
                    print(f"    Type: {element.get('type', 'N/A')}")
                    print(f"    Source Version: {element.get('sourceVersion', 'N/A')}")
                    print(f"    Target Version: {element.get('targetVersion', 'N/A')}")
                    print(f"    Description: {element.get('description', 'N/A')}")
                    
                    if 'bundleRepoPath' in element:
                        print(f"    Bundle Path: {element.get('bundleRepoPath', 'N/A')}")
                    
                    if 'preInstallCheckResultList' in element:
                        print(f"    Precheck Results: {len(element.get('preInstallCheckResultList', []))} items")
            else:
                error_text = await resp.text()
                print(f"❌ Failed to get upgradables: {resp.status} - {error_text}")
        
        # Test releases for target version
        print(f"\n🎯 Getting releases for version {target_version}...")
        releases_url = f"{VCF_URL}/v1/releases"
        async with session.get(releases_url, headers=headers, ssl=False) as resp:
            if resp.status == 200:
                releases_response = await resp.json()
                elements = releases_response.get("elements", [])
                
                target_release = None
                for release in elements:
                    if release.get("versionNumber") == target_version:
                        target_release = release
                        break
                
                if target_release:
                    print(f"📦 Found target release: {target_version}")
                    print(f"    Release Date: {target_release.get('releaseDate', 'N/A')}")
                    print(f"    Description: {target_release.get('versionDescription', 'N/A')}")
                    
                    if 'componentVersions' in target_release:
                        component_versions = target_release.get('componentVersions', [])
                        print(f"    Component Versions: {len(component_versions)} components")
                        for comp in component_versions[:5]:  # Show first 5
                            print(f"      - {comp.get('type', 'N/A')}: {comp.get('version', 'N/A')}")
                else:
                    print(f"⚠️  No release found for version {target_version}")
                    print(f"📋 Available versions:")
                    for release in elements[:5]:  # Show first 5
                        print(f"    - {release.get('versionNumber', 'N/A')} ({release.get('releaseDate', 'N/A')})")

if __name__ == "__main__":
    asyncio.run(test_upgrade_details())
