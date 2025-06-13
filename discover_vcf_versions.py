#!/usr/bin/env python3
"""
Test script to discover available VCF versions and find a valid upgrade target
"""

import asyncio
import aiohttp
import json

# VCF Configuration  
VCF_URL = "https://192.168.101.62"
VCF_USERNAME = "administrator@vsphere.local"
VCF_PASSWORD = "VMware1!"

async def discover_versions():
    """Discover available VCF versions."""
    
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
            print(f"✅ Got token")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Get current domain info
        domains_url = f"{VCF_URL}/v1/domains"
        async with session.get(domains_url, headers=headers, ssl=False) as resp:
            domains_response = await resp.json()
            domain = domains_response["elements"][0]
            domain_id = domain["id"]
            domain_name = domain["name"]
            
            # Get current VCF version from domain
            vcf_version = "Unknown"
            if 'domainManager' in domain:
                vcf_version = domain['domainManager'].get('version', 'Unknown')
            
            print(f"✅ Domain: {domain_name} ({domain_id})")
            print(f"✅ Current VCF Version: {vcf_version}")
        
        # Get all available releases
        print(f"\n📦 Getting all available releases...")
        releases_url = f"{VCF_URL}/v1/releases"
        async with session.get(releases_url, headers=headers, ssl=False) as resp:
            if resp.status == 200:
                releases_response = await resp.json()
                elements = releases_response.get("elements", [])
                
                print(f"📊 Found {len(elements)} releases:")
                for i, release in enumerate(elements, 1):
                    version = release.get("versionNumber", "N/A")
                    date = release.get("releaseDate", "N/A")
                    desc = release.get("versionDescription", "No description")[:100]
                    print(f"  {i:2}. Version: {version:15} Date: {date:12} - {desc}")
                
                # Try to find a newer version than current
                print(f"\n🔍 Looking for versions newer than {vcf_version}...")
                
                test_versions = []
                for release in elements:
                    rel_version = release.get("versionNumber")
                    if rel_version and rel_version != vcf_version:
                        test_versions.append(rel_version)
                
                # Test a few versions for upgradability
                for test_version in test_versions[:3]:
                    print(f"\n🧪 Testing upgradables for version {test_version}...")
                    
                    upgradables_url = f"{VCF_URL}/v1/domains/{domain_id}/upgradables"
                    params = {"targetVersion": test_version}
                    
                    async with session.get(upgradables_url, headers=headers, params=params, ssl=False) as resp:
                        if resp.status == 200:
                            upgradables_response = await resp.json()
                            upgrades_count = len(upgradables_response.get("elements", []))
                            print(f"  ✅ Version {test_version}: {upgrades_count} upgrades available")
                            
                            if upgrades_count > 0:
                                print(f"    🎯 Found valid upgrade target: {test_version}")
                                # Show upgrade details
                                for upgrade in upgradables_response.get("elements", [])[:2]:
                                    print(f"      - {upgrade.get('type', 'N/A')}: {upgrade.get('sourceVersion', 'N/A')} → {upgrade.get('targetVersion', 'N/A')}")
                        else:
                            error_text = await resp.text()
                            print(f"  ❌ Version {test_version}: Error {resp.status}")
                            if "VCF_RUNTIME_ERROR" in error_text:
                                print(f"    Runtime error - version may not be valid for upgrade")
                            else:
                                print(f"    {error_text[:100]}")
            else:
                print(f"❌ Failed to get releases: {resp.status}")
        
        # Also check bundles for version info
        print(f"\n📚 Checking bundles for version information...")
        bundles_url = f"{VCF_URL}/v1/bundles"
        async with session.get(bundles_url, headers=headers, ssl=False) as resp:
            if resp.status == 200:
                bundles_response = await resp.json()
                bundles = bundles_response.get("elements", [])
                print(f"📦 Found {len(bundles)} VCF bundles:")
                
                for bundle in bundles[:10]:  # Show first 10
                    bundle_id = bundle.get("id", "N/A")
                    version = bundle.get("version", "N/A")
                    desc = bundle.get("description", "No description")[:80]
                    print(f"  - {bundle_id[:8]}... v{version} - {desc}")
            else:
                print(f"❌ Failed to get bundles: {resp.status}")

if __name__ == "__main__":
    asyncio.run(discover_versions())
