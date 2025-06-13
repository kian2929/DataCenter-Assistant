#!/usr/bin/env python3
"""
Test script to validate VCF API flow.txt logic against real VCF environment.
"""

import asyncio
import aiohttp
import json
import re
from typing import Dict, List, Any

# VCF Configuration
VCF_URL = "https://192.168.101.62"
VCF_USERNAME = "administrator@vsphere.local"
VCF_PASSWORD = "VMware1!"

async def get_vcf_token(session: aiohttp.ClientSession) -> str:
    """Get VCF authentication token."""
    print("🔐 Getting VCF authentication token...")
    
    login_url = f"{VCF_URL}/v1/tokens"
    auth_data = {
        "username": VCF_USERNAME,
        "password": VCF_PASSWORD
    }
    
    async with session.post(login_url, json=auth_data, ssl=False) as resp:
        if resp.status != 200:
            raise Exception(f"Authentication failed: {resp.status}")
        
        token_data = await resp.json()
        token = token_data.get("accessToken") or token_data.get("access_token")
        
        if not token:
            raise Exception("Could not extract token from response")
        
        print("✅ Authentication successful")
        return token

async def test_vcf_flow():
    """Test the complete VCF flow.txt workflow."""
    print("🚀 Starting VCF API Flow Test")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        try:
            # Step 1: Get authentication token
            token = await get_vcf_token(session)
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            }
            
            # Step 2: Get domains (only ACTIVE ones)
            print("\n📋 Step 1: Getting domains (ACTIVE only)")
            domains_url = f"{VCF_URL}/v1/domains"
            
            async with session.get(domains_url, headers=headers, ssl=False) as resp:
                if resp.status != 200:
                    raise Exception(f"Domains API failed: {resp.status}")
                domains_data = await resp.json()
            
            # Filter active domains and assign prefixes
            active_domains = []
            domain_counter = 1
            
            print(f"   Found {len(domains_data.get('elements', []))} total domains")
            
            for domain in domains_data.get("elements", []):
                if domain.get("status") == "ACTIVE":
                    domain_info = {
                        "id": domain.get("id"),
                        "name": domain.get("name"),
                        "status": domain.get("status"),
                        "prefix": f"domain{domain_counter}_"
                    }
                    active_domains.append(domain_info)
                    print(f"   ✅ Active Domain {domain_counter}: {domain.get('name')} ({domain.get('id')})")
                    domain_counter += 1
                else:
                    print(f"   ⏭️  Skipping {domain.get('name')} - Status: {domain.get('status')}")
            
            if not active_domains:
                print("❌ No active domains found - setup would fail")
                return
            
            print(f"   📊 Total active domains: {len(active_domains)}")
            
            # Step 3: Get SDDC managers
            print("\n🖥️  Step 2: Getting SDDC managers")
            sddc_url = f"{VCF_URL}/v1/sddc-managers"
            
            async with session.get(sddc_url, headers=headers, ssl=False) as resp:
                if resp.status != 200:
                    raise Exception(f"SDDC Managers API failed: {resp.status}")
                sddc_data = await resp.json()
            
            # Map SDDC managers to domains
            for domain in active_domains:
                for sddc in sddc_data.get("elements", []):
                    if sddc.get("domain", {}).get("id") == domain["id"]:
                        domain["sddc_manager_id"] = sddc.get("id")
                        domain["sddc_manager_fqdn"] = sddc.get("fqdn")
                        domain["sddc_manager_version"] = sddc.get("version")
                        print(f"   ✅ {domain['prefix']}sddc_manager: {sddc.get('fqdn')} (v{sddc.get('version')})")
                        break
            
            # Step 4: For each domain, check for updates
            print("\n🔄 Step 3: Checking for updates per domain")
            
            for domain in active_domains:
                print(f"\n   🏢 Processing {domain['name']} ({domain['prefix']})")
                
                # Get current VCF version
                print(f"      📊 Getting current VCF version...")
                releases_url = f"{VCF_URL}/v1/releases"
                params = {"domainId": domain["id"]}
                
                async with session.get(releases_url, headers=headers, params=params, ssl=False) as resp:
                    if resp.status != 200:
                        print(f"      ❌ Failed to get releases: {resp.status}")
                        continue
                    releases_data = await resp.json()
                
                current_version = None
                if releases_data.get("elements"):
                    current_version = releases_data["elements"][0].get("version")
                    print(f"      ✅ Current VCF version: {current_version}")
                
                # Get bundles and filter for VCF updates
                print(f"      📦 Getting bundles...")
                bundles_url = f"{VCF_URL}/v1/bundles"
                
                async with session.get(bundles_url, headers=headers, ssl=False) as resp:
                    if resp.status != 200:
                        print(f"      ❌ Failed to get bundles: {resp.status}")
                        continue
                    bundles_data = await resp.json()
                
                print(f"      📊 Found {len(bundles_data.get('elements', []))} total bundles")
                
                # Filter for VCF upgrade bundles with improved regex
                vcf_bundles = []
                bundle_count = 0
                
                for bundle in bundles_data.get("elements", []):
                    description = bundle.get("description", "")
                    bundle_count += 1
                    
                    # Look for VCF upgrade bundles with improved pattern
                    if re.search(r"VMware Cloud Foundation\s+\d+\.\d+", description, re.IGNORECASE):
                        # Extract version from description with improved regex
                        version_pattern = r"VMware Cloud Foundation\s+(\d+\.\d+\.\d+(?:\.\d+)?)"
                        match = re.search(version_pattern, description, re.IGNORECASE)
                        if match:
                            version = match.group(1)
                            # Normalize version to 4 parts (add .0 if missing)
                            version_parts = version.split('.')
                            if len(version_parts) == 3:
                                version = f"{version}.0"
                            vcf_bundles.append({
                                "bundle": bundle,
                                "version": version,
                                "description": description
                            })
                            print(f"      ✅ VCF Bundle {bundle.get('id', 'N/A')}: {description[:80]}... (Version: {version})")
                        else:
                            print(f"      ❌ No version match for: {description[:80]}...")
                    elif "configuration drift bundle for VMware Cloud Foundation" in description.lower():
                        # Handle configuration drift bundles as fallback
                        version_pattern = r"VMware Cloud Foundation\s+(\d+\.\d+\.\d+(?:\.\d+)?)"
                        match = re.search(version_pattern, description, re.IGNORECASE)
                        if match:
                            version = match.group(1)
                            # Normalize version to 4 parts (add .0 if missing)
                            version_parts = version.split('.')
                            if len(version_parts) == 3:
                                version = f"{version}.0"
                            vcf_bundles.append({
                                "bundle": bundle,
                                "version": version,
                                "description": description
                            })
                            print(f"      ✅ VCF Bundle (fallback) {bundle.get('id', 'N/A')}: {description[:80]}... (Version: {version})")
                
                if not vcf_bundles:
                    print(f"      ℹ️  No VCF update bundles found - would report 'up_to_date'")
                    continue
                
                # Extract versions and sort them properly to find the next logical upgrade
                print(f"      🔍 Analyzing upgrade path from current version: {current_version}")
                version_bundles = []
                for bundle_info in vcf_bundles:
                    bundle = bundle_info["bundle"]
                    version = bundle_info["version"]
                    
                    # Convert to tuple for proper version comparison
                    version_tuple = tuple(map(int, version.split('.')))
                    version_bundles.append((version_tuple, version, bundle))
                
                # Sort by version number (not release date) to ensure proper upgrade path
                version_bundles.sort(key=lambda x: x[0])
                
                print(f"      📊 Available versions in order:")
                for version_tuple, version_str, bundle in version_bundles:
                    print(f"         - {version_str} (Bundle: {bundle.get('id', 'N/A')})")
                
                # Find the next version after current version
                target_bundle = None
                target_version = None
                
                if current_version:
                    current_parts = current_version.split('.')
                    if len(current_parts) == 3:
                        current_version_normalized = f"{current_version}.0"
                    else:
                        current_version_normalized = current_version
                    current_tuple = tuple(map(int, current_version_normalized.split('.')))
                    
                    print(f"      🎯 Looking for next version after: {current_version_normalized}")
                    
                    # Find the first version that's higher than current
                    for version_tuple, version_str, bundle in version_bundles:
                        if version_tuple > current_tuple:
                            target_bundle = bundle
                            target_version = version_str
                            print(f"      ✅ Selected next upgrade: {current_version_normalized} -> {target_version}")
                            print(f"         (Following proper upgrade path - no version skipping)")
                            break
                    
                    if not target_bundle:
                        print(f"      ℹ️  No higher version available - system is up to date")
                        continue
                else:
                    # If no current version, take the lowest available version
                    if version_bundles:
                        target_bundle = version_bundles[0][2]
                        target_version = version_bundles[0][1]
                        print(f"      ⚠️  No current version detected, selecting lowest available: {target_version}")
                
                if target_bundle and target_version:
                    print(f"      🎯 Target update bundle: {target_bundle.get('id')} (v{target_version})")
                    print(f"      📅 Release date: {target_bundle.get('releaseDate')}")
                    
                    # Look for configuration drift bundle for this version
                    config_drift_bundles = []
                    for bundle_info in vcf_bundles:
                        bundle = bundle_info["bundle"]
                        desc = bundle.get("description", "")
                        if "configuration drift bundle" in desc.lower() and target_version in desc:
                            config_drift_bundles.append(bundle.get("id"))
                            print(f"      📦 Found config drift bundle: {bundle.get('id')} (will be downloaded with upgrade)")
                    
                    bundles_to_download = [target_bundle.get("id")]
                    if config_drift_bundles:
                        bundles_to_download.extend(config_drift_bundles)
                    
                    print(f"      📋 Total bundles to download: {len(bundles_to_download)}")
                    for i, bundle_id in enumerate(bundles_to_download, 1):
                        bundle_type = "Config Drift" if bundle_id in config_drift_bundles else "Upgrade"
                        print(f"         {i}. {bundle_id} ({bundle_type})")
                else:
                    print(f"      ❌ No valid target bundle found")
                    continue
                
                    # Get upgradable components
                    print(f"      🔧 Getting upgradable components for target version {target_version}...")
                    upgradables_url = f"{VCF_URL}/v1/upgradables/domains/{domain['id']}"
                    params = {"targetVersion": target_version} if target_version else {}
                    
                    try:
                        async with session.get(upgradables_url, headers=headers, params=params, ssl=False) as resp:
                            if resp.status == 200:
                                upgradables_data = await resp.json()
                                components = upgradables_data.get("elements", [])
                                print(f"      ✅ Found {len(components)} upgradable components")
                                
                                # Get details for each component bundle
                                component_count = 0
                                for component in components:
                                    component_bundle_id = component.get("bundleId")
                                    component_type = component.get("componentType", "Unknown")
                                    
                                    if component_bundle_id:
                                        bundle_detail_url = f"{VCF_URL}/v1/bundles/{component_bundle_id}"
                                        try:
                                            async with session.get(bundle_detail_url, headers=headers, ssl=False) as bundle_resp:
                                                if bundle_resp.status == 200:
                                                    bundle_detail = await bundle_resp.json()
                                                    component_count += 1
                                                    print(f"         🔧 Component {component_count}: {component_type}")
                                                    print(f"            📦 Bundle: {bundle_detail.get('description', 'N/A')[:60]}...")
                                                    print(f"            🏷️  Version: {bundle_detail.get('version', 'N/A')}")
                                        except Exception as e:
                                            print(f"         ❌ Error getting bundle {component_bundle_id}: {e}")
                            else:
                                print(f"      ⚠️  Upgradables API returned {resp.status} - might not be available yet")
                                resp_text = await resp.text()
                                print(f"         Response: {resp_text[:200]}...")
                    except Exception as e:
                        print(f"      ❌ Error calling upgradables API: {e}")
                
                print(f"   ✅ Completed processing {domain['name']}")
            
            print("\n🎉 VCF API Flow Test Completed Successfully!")
            
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_vcf_flow())
