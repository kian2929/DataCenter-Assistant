#!/usr/bin/env python3
"""
Test script to systematically validate the VCF flow.txt workflow
This script tests each step of the workflow against the actual VCF API
"""

import asyncio
import aiohttp
import json
import re
from datetime import datetime
import ssl
import sys

# VCF Configuration
VCF_URL = "https://192.168.101.62"
VCF_USERNAME = "administrator@vsphere.local"
VCF_PASSWORD = "VMware1!"

class VCFFlowTester:
    def __init__(self):
        self.token = None
        self.session = None
        self.domains = []
        self.domain_data = {}
        
    async def __aenter__(self):
        # Create SSL context that ignores certificate verification
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self.session = aiohttp.ClientSession(connector=connector)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def authenticate(self):
        """Step 0: Authenticate and get token"""
        print("=" * 60)
        print("STEP 0: Authentication")
        print("=" * 60)
        
        login_url = f"{VCF_URL}/v1/tokens"
        auth_data = {
            "username": VCF_USERNAME,
            "password": VCF_PASSWORD
        }
        
        print(f"🔐 Authenticating to: {login_url}")
        print(f"👤 Username: {VCF_USERNAME}")
        
        try:
            async with self.session.post(login_url, json=auth_data) as resp:
                print(f"📡 Response Status: {resp.status}")
                
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"❌ Authentication failed: {error_text}")
                    return False
                    
                token_data = await resp.json()
                print(f"📋 Response keys: {list(token_data.keys())}")
                
                # Try different possible token field names
                self.token = (token_data.get("accessToken") or 
                             token_data.get("access_token") or 
                             token_data.get("token"))
                
                if self.token:
                    print(f"✅ Authentication successful")
                    print(f"🔑 Token (first 20 chars): {self.token[:20]}...")
                    return True
                else:
                    print(f"❌ Could not extract token from response: {token_data}")
                    return False
                    
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False

    async def get_domains(self):
        """Step 1: Get Domain Information - only consider ACTIVE domains"""
        print("\n" + "=" * 60)
        print("STEP 1: Get Domain Information")
        print("=" * 60)
        
        domains_url = f"{VCF_URL}/v1/domains"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }
        
        print(f"🌐 Getting domains from: {domains_url}")
        
        try:
            async with self.session.get(domains_url, headers=headers) as resp:
                print(f"📡 Response Status: {resp.status}")
                
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"❌ Failed to get domains: {error_text}")
                    return False
                    
                domains_data = await resp.json()
                print(f"📋 Response structure: {list(domains_data.keys())}")
                
                elements = domains_data.get("elements", [])
                print(f"📊 Total domains found: {len(elements)}")
                
                # Process domains according to flow.txt
                domain_counter = 1
                self.domains = []
                
                for domain in elements:
                    print(f"\n🏢 Domain {domain_counter}:")
                    print(f"   ID: {domain.get('id')}")
                    print(f"   Name: {domain.get('name')}")
                    print(f"   Status: {domain.get('status')}")
                    print(f"   Type: {domain.get('type')}")
                    
                    # Only consider ACTIVE domains as per flow.txt
                    if domain.get("status") == "ACTIVE":
                        domain_info = {
                            "id": domain.get("id"),
                            "name": domain.get("name"),
                            "status": domain.get("status"),
                            "type": domain.get("type"),
                            "prefix": f"domain{domain_counter}_"
                        }
                        self.domains.append(domain_info)
                        print(f"   ✅ Added as {domain_info['prefix']}")
                        domain_counter += 1
                    else:
                        print(f"   ⏭️  Skipping (not ACTIVE)")
                
                if not self.domains:
                    print("❌ No active domains found - setup should fail as per flow.txt")
                    return False
                else:
                    print(f"\n✅ Found {len(self.domains)} active domain(s)")
                    return True
                    
        except Exception as e:
            print(f"❌ Error getting domains: {e}")
            return False

    async def get_sddc_managers(self):
        """Step 2: Get SDDC Manager Information and map to domains"""
        print("\n" + "=" * 60)
        print("STEP 2: Get SDDC Manager Information")
        print("=" * 60)
        
        sddc_url = f"{VCF_URL}/v1/sddc-managers"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }
        
        print(f"🖥️  Getting SDDC managers from: {sddc_url}")
        
        try:
            async with self.session.get(sddc_url, headers=headers) as resp:
                print(f"📡 Response Status: {resp.status}")
                
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"❌ Failed to get SDDC managers: {error_text}")
                    return False
                    
                sddc_data = await resp.json()
                print(f"📋 Response structure: {list(sddc_data.keys())}")
                
                sddc_elements = sddc_data.get("elements", [])
                print(f"📊 Total SDDC managers found: {len(sddc_elements)}")
                
                # Map SDDC managers to domains
                for sddc in sddc_elements:
                    print(f"\n🖥️  SDDC Manager:")
                    print(f"   ID: {sddc.get('id')}")
                    print(f"   FQDN: {sddc.get('fqdn')}")
                    print(f"   Version: {sddc.get('version')}")
                    domain_info = sddc.get('domain', {})
                    print(f"   Domain ID: {domain_info.get('id')}")
                    print(f"   Domain Name: {domain_info.get('name')}")
                    
                    # Match with our active domains
                    for domain in self.domains:
                        if domain['id'] == domain_info.get('id'):
                            domain['sddc_manager_id'] = sddc.get('id')
                            domain['sddc_manager_fqdn'] = sddc.get('fqdn')
                            domain['sddc_manager_version'] = sddc.get('version')
                            print(f"   ✅ Mapped to {domain['prefix']}{domain['name']}")
                            break
                
                print(f"\n✅ SDDC Manager mapping completed")
                return True
                
        except Exception as e:
            print(f"❌ Error getting SDDC managers: {e}")
            return False

    async def check_domain_updates(self):
        """Step 3: Check for updates for each domain following flow.txt"""
        print("\n" + "=" * 60)
        print("STEP 3: Check Domain Updates (Following flow.txt)")
        print("=" * 60)
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }
        
        for domain in self.domains:
            print(f"\n🔍 Checking updates for {domain['prefix']}{domain['name']}")
            print("-" * 50)
            
            domain_id = domain['id']
            domain_name = domain['name']
            
            try:
                # Get current VCF version for this domain
                print(f"📋 Getting current VCF version...")
                releases_url = f"{VCF_URL}/v1/releases"
                params = {"domainId": domain_id}
                
                async with self.session.get(releases_url, headers=headers, params=params) as resp:
                    print(f"   📡 Releases API Status: {resp.status}")
                    
                    if resp.status != 200:
                        error_text = await resp.text()
                        print(f"   ❌ Failed to get releases: {error_text}")
                        continue
                        
                    releases_data = await resp.json()
                    print(f"   📊 Releases found: {len(releases_data.get('elements', []))}")
                    
                    current_version = None
                    if releases_data.get("elements"):
                        current_version = releases_data["elements"][0].get("version")
                        print(f"   📌 Current VCF Version: {current_version}")
                    else:
                        print(f"   ⚠️  No current version found")
                
                # Get bundles to check for VCF updates
                print(f"📦 Getting bundles for VCF updates...")
                bundles_url = f"{VCF_URL}/v1/bundles"
                
                async with self.session.get(bundles_url, headers=headers) as resp:
                    print(f"   📡 Bundles API Status: {resp.status}")
                    
                    if resp.status != 200:
                        error_text = await resp.text()
                        print(f"   ❌ Failed to get bundles: {error_text}")
                        continue
                        
                    bundles_data = await resp.json()
                    bundles_elements = bundles_data.get("elements", [])
                    print(f"   📊 Total bundles found: {len(bundles_elements)}")
                    
                    # Filter bundles for VMware Cloud Foundation as per flow.txt
                    vcf_bundles = []
                    print(f"   🔍 Filtering for VCF bundles...")
                    
                    for i, bundle in enumerate(bundles_elements):
                        description = bundle.get("description", "")
                        # Updated pattern to match actual VCF bundle descriptions
                        if re.search(r"upgrade bundle for VMware Cloud Foundation \d+\.\d+(?:\.\d+)?(?:\.\d+)?", description, re.IGNORECASE):
                            vcf_bundles.append(bundle)
                            print(f"      ✅ VCF Bundle {i+1}: {description[:80]}...")
                        elif re.search(r"VMware Cloud Foundation.*\d+\.\d+(?:\.\d+)?(?:\.\d+)?", description, re.IGNORECASE):
                            # Fallback pattern
                            vcf_bundles.append(bundle)
                            print(f"      ✅ VCF Bundle (fallback) {i+1}: {description[:80]}...")
                        elif "VMware Cloud Foundation" in description:
                            print(f"      📋 Possible VCF bundle {i+1}: {description[:80]}...")
                    
                    print(f"   📊 VCF bundles found: {len(vcf_bundles)}")
                    
                    if not vcf_bundles:
                        print(f"   ✅ No VCF update bundles found - domain is up to date (as per flow.txt)")
                        self.domain_data[domain_id] = {
                            "domain_name": domain_name,
                            "domain_prefix": domain['prefix'],
                            "current_version": current_version,
                            "update_status": "up_to_date",
                            "next_version": None,
                            "component_updates": {}
                        }
                        continue
                    
                    # Find the oldest bundle by releaseDate as per flow.txt
                    print(f"   📅 Sorting bundles by release date (oldest first)...")
                    sorted_bundles = sorted(vcf_bundles, key=lambda x: x.get("releaseDate", ""))
                    
                    if sorted_bundles:
                        target_bundle = sorted_bundles[0]
                        print(f"   🎯 Target bundle:")
                        print(f"      ID: {target_bundle.get('id')}")
                        print(f"      Description: {target_bundle.get('description')}")
                        print(f"      Release Date: {target_bundle.get('releaseDate')}")
                        print(f"      Version: {target_bundle.get('version')}")
                        
                        # Extract version following flow.txt format
                        description = target_bundle.get("description", "")
                        # Updated pattern to match actual VCF bundle descriptions
                        version_pattern = r"VMware Cloud Foundation (\d+\.\d+(?:\.\d+)?(?:\.\d+)?)"
                        match = re.search(version_pattern, description, re.IGNORECASE)
                        target_version = match.group(1) if match else target_bundle.get('version', 'Unknown')
                        
                        next_version_info = {
                            "versionDescription": description,
                            "versionNumber": target_version,
                            "releaseDate": target_bundle.get("releaseDate"),
                            "bundleId": target_bundle.get("id"),
                            "bundlesToDownload": [target_bundle.get("id")]
                        }
                        
                        print(f"   📋 Next Version Info:")
                        for key, value in next_version_info.items():
                            print(f"      {key}: {value}")
                        
                        # Check upgradable components
                        print(f"   🔧 Getting upgradable components...")
                        if target_version != "Unknown":
                            upgradables_url = f"{VCF_URL}/v1/upgradables/domains/{domain_id}"
                            params = {"targetVersion": target_version}
                            
                            async with self.session.get(upgradables_url, headers=headers, params=params) as resp:
                                print(f"      📡 Upgradables API Status: {resp.status}")
                                
                                component_updates = {}
                                if resp.status == 200:
                                    upgradables_data = await resp.json()
                                    components = upgradables_data.get("elements", [])
                                    print(f"      📊 Upgradable components found: {len(components)}")
                                    
                                    for i, component in enumerate(components):
                                        comp_bundle_id = component.get("bundleId")
                                        comp_type = component.get("componentType", "Unknown")
                                        
                                        print(f"         Component {i+1}: {comp_type} (Bundle: {comp_bundle_id})")
                                        
                                        if comp_bundle_id:
                                            # Get bundle details
                                            bundle_detail_url = f"{VCF_URL}/v1/bundles/{comp_bundle_id}"
                                            async with self.session.get(bundle_detail_url, headers=headers) as bundle_resp:
                                                if bundle_resp.status == 200:
                                                    bundle_detail = await bundle_resp.json()
                                                    component_updates[f"componentUpdate{i+1}"] = {
                                                        "id": comp_bundle_id,
                                                        "description": bundle_detail.get("description", ""),
                                                        "version": bundle_detail.get("version", ""),
                                                        "componentType": comp_type
                                                    }
                                                    print(f"            Description: {bundle_detail.get('description', '')[:60]}...")
                                                    print(f"            Version: {bundle_detail.get('version', '')}")
                                else:
                                    error_text = await resp.text()
                                    print(f"      ❌ Failed to get upgradables: {error_text}")
                        
                        # Store domain update info
                        self.domain_data[domain_id] = {
                            "domain_name": domain_name,
                            "domain_prefix": domain['prefix'],
                            "current_version": current_version,
                            "update_status": "updates_available",
                            "next_version": next_version_info,
                            "component_updates": component_updates
                        }
                        
                        print(f"   ✅ Domain {domain['prefix']}{domain_name}: Updates available!")
                
            except Exception as e:
                print(f"   ❌ Error checking updates for domain {domain_name}: {e}")
                self.domain_data[domain_id] = {
                    "domain_name": domain_name,
                    "domain_prefix": domain['prefix'],
                    "current_version": None,
                    "update_status": "error",
                    "error": str(e),
                    "next_version": None,
                    "component_updates": {}
                }
        
        return True

    async def print_summary(self):
        """Print final summary in flow.txt format"""
        print("\n" + "=" * 60)
        print("FINAL SUMMARY - Home Assistant Entity Data")
        print("=" * 60)
        
        print(f"\n📊 Overall Status:")
        total_domains = len(self.domains)
        domains_with_updates = sum(1 for d in self.domain_data.values() if d.get("update_status") == "updates_available")
        domains_up_to_date = sum(1 for d in self.domain_data.values() if d.get("update_status") == "up_to_date")
        domains_with_errors = sum(1 for d in self.domain_data.values() if d.get("update_status") == "error")
        
        print(f"   Total Active Domains: {total_domains}")
        print(f"   Domains with Updates: {domains_with_updates}")
        print(f"   Domains Up to Date: {domains_up_to_date}")
        print(f"   Domains with Errors: {domains_with_errors}")
        
        overall_status = "updates_available" if domains_with_updates > 0 else "up_to_date"
        print(f"   Overall Status: {overall_status}")
        
        print(f"\n🏢 Per-Domain Entities (as per flow.txt):")
        for domain_id, domain_data in self.domain_data.items():
            domain_name = domain_data.get("domain_name", "Unknown")
            prefix = domain_data.get("domain_prefix", "")
            status = domain_data.get("update_status", "unknown")
            
            print(f"\n   {prefix}{domain_name}:")
            print(f"      Entity: sensor.vcf_{domain_name.lower().replace(' ', '_')}_updates")
            print(f"      State: {status}")
            print(f"      Current Version: {domain_data.get('current_version', 'Unknown')}")
            
            next_version = domain_data.get("next_version")
            if next_version:
                print(f"      Attributes (following flow.txt naming):")
                print(f"         nextVersion_versionNumber: {next_version.get('versionNumber')}")
                print(f"         nextVersion_versionDescription: {next_version.get('versionDescription', '')[:60]}...")
                print(f"         nextVersion_releaseDate: {next_version.get('releaseDate')}")
                print(f"         nextVersion_bundlesToDownload: {next_version.get('bundlesToDownload')}")
                
                component_updates = domain_data.get("component_updates", {})
                if component_updates:
                    print(f"         Component Updates:")
                    for comp_name, comp_data in component_updates.items():
                        print(f"            nextVersion_componentUpdates_{comp_name}_description: {comp_data.get('description', '')[:40]}...")
                        print(f"            nextVersion_componentUpdates_{comp_name}_version: {comp_data.get('version')}")
                        print(f"            nextVersion_componentUpdates_{comp_name}_id: {comp_data.get('id')}")
            
            if "error" in domain_data:
                print(f"      Error: {domain_data['error']}")

async def main():
    print("🚀 VCF Flow.txt Workflow Tester")
    print("=" * 60)
    print(f"Target VCF: {VCF_URL}")
    print(f"Username: {VCF_USERNAME}")
    print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    async with VCFFlowTester() as tester:
        # Step 0: Authentication
        if not await tester.authenticate():
            print("❌ Authentication failed - stopping test")
            return False
        
        # Step 1: Get Domains
        if not await tester.get_domains():
            print("❌ Domain discovery failed - stopping test")
            return False
        
        # Step 2: Get SDDC Managers
        if not await tester.get_sddc_managers():
            print("❌ SDDC Manager mapping failed - stopping test")
            return False
        
        # Step 3: Check Updates
        if not await tester.check_domain_updates():
            print("❌ Update checking failed - stopping test")
            return False
        
        # Summary
        await tester.print_summary()
        
        print(f"\n✅ VCF Flow Test Completed Successfully!")
        return True

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        if result:
            print("\n🎉 All tests passed!")
            sys.exit(0)
        else:
            print("\n💥 Some tests failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)
