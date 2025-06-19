"""VCF Upgrade Service for handling VCF domain upgrades."""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta
from .vcf_api import VCFAPIClient

_LOGGER = logging.getLogger(__name__)

class VCFUpgradeService:
    """Service to handle VCF domain upgrades following the upgrade workflow."""
    
    def __init__(self, hass: HomeAssistant, config_entry, vcf_client: VCFAPIClient):
        self.hass = hass
        self.config_entry = config_entry
        self.vcf_client = vcf_client
        self._upgrade_states: Dict[str, Dict[str, Any]] = {}
        self._upgrade_tasks: Dict[str, asyncio.Task] = {}
        
        # Initialize upgrade states for all domains
        self._initialize_upgrade_states()
    
    def _initialize_upgrade_states(self):
        """Initialize upgrade states for tracking."""
        # This will be populated when domains are discovered
        pass
    
    def get_upgrade_status(self, domain_id: str) -> str:
        """Get current upgrade status for a domain."""
        return self._upgrade_states.get(domain_id, {}).get("status", "waiting_for_initiation")
    
    def get_upgrade_logs(self, domain_id: str) -> str:
        """Get current upgrade logs for a domain."""
        return self._upgrade_states.get(domain_id, {}).get("logs", "No Messages")
    
    def set_upgrade_status(self, domain_id: str, status: str):
        """Set upgrade status for a domain."""
        if domain_id not in self._upgrade_states:
            self._upgrade_states[domain_id] = {}
        self._upgrade_states[domain_id]["status"] = status
        _LOGGER.info(f"Domain {domain_id} upgrade status changed to: {status}")
        
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
    
    def set_upgrade_logs(self, domain_id: str, logs: str):
        """Set upgrade logs for a domain."""
        if domain_id not in self._upgrade_states:
            self._upgrade_states[domain_id] = {}
        self._upgrade_states[domain_id]["logs"] = logs
        _LOGGER.debug(f"Domain {domain_id} upgrade logs updated")
        
        # Fire event for Home Assistant to update sensors (thread-safe)
        def fire_logs_event():
            self.hass.bus.fire(
                "vcf_upgrade_logs_changed",
                {"domain_id": domain_id, "logs": logs[:255]}  # Truncate for event
            )
        
        if hasattr(self.hass, 'loop') and self.hass.loop.is_running():
            # If called from a background thread, schedule on event loop
            self.hass.loop.call_soon_threadsafe(fire_logs_event)
        else:
            # Already on main thread or loop not running
            fire_logs_event()
    
    async def start_upgrade(self, domain_id: str, domain_data: Dict[str, Any]) -> bool:
        """Start upgrade process for a domain."""
        try:
            # Check if upgrade is already running
            if domain_id in self._upgrade_tasks and not self._upgrade_tasks[domain_id].done():
                _LOGGER.warning(f"Upgrade already running for domain {domain_id}")
                return False
            
            # Check if update is available
            if domain_data.get("update_status") != "updates_available":
                self.set_upgrade_logs(domain_id, "**No VCF update available**\n\nThere is currently no VCF update available for this domain.")
                return False
            
            # Start upgrade process
            self.set_upgrade_logs(domain_id, "**VCF Upgrade Started**\n\nStarting VCF upgrade process...")
            
            # Create and start upgrade task
            upgrade_task = asyncio.create_task(self._upgrade_workflow(domain_id, domain_data))
            self._upgrade_tasks[domain_id] = upgrade_task
            
            return True
            
        except Exception as e:
            _LOGGER.error(f"Error starting upgrade for domain {domain_id}: {e}")
            self.set_upgrade_status(domain_id, "failed")
            self.set_upgrade_logs(domain_id, f"**Upgrade Failed**\n\nError starting upgrade: {e}")
            return False
    
    async def acknowledge_alerts(self, domain_id: str) -> bool:
        """Acknowledge alerts and continue upgrade."""
        try:
            state = self._upgrade_states.get(domain_id, {})
            if state.get("status") == "waiting_acknowledgement":
                state["acknowledged"] = True
                self.set_upgrade_logs(domain_id, 
                    state.get("logs", "") + "\n\n**Alerts Acknowledged**\n\nContinuing with upgrade process...")
                return True
            return False
        except Exception as e:
            _LOGGER.error(f"Error acknowledging alerts for domain {domain_id}: {e}")
            return False
    
    async def _upgrade_workflow(self, domain_id: str, domain_data: Dict[str, Any]):
        """Main upgrade workflow implementation."""
        try:
            next_release = domain_data.get("next_release", {})
            target_version = next_release.get("version")
            
            if not target_version:
                raise ValueError("No target version found in next_release")
            
            # Step 1: Target the next VCF version
            await self._target_vcf_version(domain_id, target_version)
            
            # Step 2: Download bundles
            await self._download_bundles(domain_id, next_release)
            
            # Step 3: Run pre-checks
            await self._run_prechecks(domain_id, target_version, next_release)
            
            # Step 4: Start upgrades
            _LOGGER.info(f"Domain {domain_id}: Starting component upgrades phase")
            await self._start_upgrades(domain_id, target_version, domain_data)
            
            # Step 5: Final validation
            _LOGGER.info(f"Domain {domain_id}: Starting final validation phase")
            await self._final_validation(domain_id, target_version)
            
            # Success
            _LOGGER.info(f"Domain {domain_id}: Upgrade workflow completed successfully!")
            self.set_upgrade_status(domain_id, "successfully_completed")
            self.set_upgrade_logs(domain_id, "**Upgrade Completed Successfully**\n\nVCF upgrade completed successfully!")
            
            # Reset to waiting state after a delay
            _LOGGER.info(f"Domain {domain_id}: Resetting upgrade status to waiting after 10 seconds")
            await asyncio.sleep(10)
            self.set_upgrade_status(domain_id, "waiting_for_initiation")
            self.set_upgrade_logs(domain_id, "No Messages")
            
        except Exception as e:
            _LOGGER.error(f"Upgrade workflow failed for domain {domain_id}: {e}")
            self.set_upgrade_status(domain_id, "failed")
            self.set_upgrade_logs(domain_id, f"**Upgrade Failed**\n\nError: {e}")
    
    async def _target_vcf_version(self, domain_id: str, target_version: str):
        """Target the next VCF version for the domain."""
        self.set_upgrade_status(domain_id, "targeting_new_vcf_version")
        self.set_upgrade_logs(domain_id, f"**Targeting VCF Version**\n\nTargeting VCF version {target_version}...")
        
        try:
            data = {"targetVersion": target_version}
            
            _LOGGER.debug(f"Domain {domain_id}: Making PATCH request to /v1/releases/domains/{domain_id} with data: {data}")
            
            # Use the VCF API client with better error handling
            response = await self.vcf_client.api_request(f"/v1/releases/domains/{domain_id}", method="PATCH", data=data)
            
            _LOGGER.info(f"Successfully targeted version {target_version} for domain {domain_id}, response: {response}")
            
        except Exception as e:
            # Check if it's a JSON decode error (likely HTML error response)
            if "unexpected mimetype" in str(e) or "JSON" in str(e):
                error_msg = f"API returned non-JSON response. This might indicate the endpoint is not available or the request format is incorrect. Error: {e}"
            else:
                error_msg = f"Failed to target VCF version: {e}"
            
            _LOGGER.error(f"Domain {domain_id}: {error_msg}")
            raise Exception(error_msg)
    
    async def _download_bundles(self, domain_id: str, next_release: Dict[str, Any]):
        """Download all necessary bundles."""
        self.set_upgrade_status(domain_id, "downloading_bundles")
        self.set_upgrade_logs(domain_id, "**Downloading Bundles**\n\nDownloading required bundles...")
        
        try:
            patch_bundles = next_release.get("patchBundles", [])
            if not patch_bundles:
                _LOGGER.warning(f"No patch bundles found for domain {domain_id}")
                return
            
            total_bundles = len(patch_bundles)
            downloaded = 0
            
            _LOGGER.debug(f"Domain {domain_id}: Found {total_bundles} bundles to process")
            
            for bundle in patch_bundles:
                bundle_id = bundle.get("bundleId")
                if not bundle_id:
                    continue
                
                # Check if bundle is already downloaded
                _LOGGER.debug(f"Domain {domain_id}: Checking download status for bundle {bundle_id}")
                bundle_status = await self.vcf_client.api_request(f"/v1/bundles/{bundle_id}")
                current_download_status = bundle_status.get("downloadStatus")
                _LOGGER.debug(f"Domain {domain_id}: Bundle {bundle_id} download status: {current_download_status}")
                
                if current_download_status == "SUCCESSFUL":
                    # Bundle already downloaded, skip
                    _LOGGER.info(f"Domain {domain_id}: Bundle {bundle_id} already downloaded, skipping")
                    downloaded += 1
                    self.set_upgrade_logs(domain_id, 
                        f"**Downloading Bundles**\n\nProgress: {downloaded}/{total_bundles} bundles downloaded... (bundle {bundle_id} already downloaded)")
                    continue
                
                # Start download with correct data structure
                _LOGGER.debug(f"Domain {domain_id}: Starting download for bundle {bundle_id}")
                download_data = {
                    "bundleDownloadSpec": {
                        "downloadNow": True
                    }
                }
                
                try:
                    await self.vcf_client.api_request(f"/v1/bundles/{bundle_id}", method="PATCH", data=download_data)
                except Exception as e:
                    # If bundle is already downloaded or download request fails, check status
                    bundle_status = await self.vcf_client.api_request(f"/v1/bundles/{bundle_id}")
                    current_download_status = bundle_status.get("downloadStatus")
                    if current_download_status == "SUCCESSFUL":
                        downloaded += 1
                        self.set_upgrade_logs(domain_id, 
                            f"**Downloading Bundles**\n\nProgress: {downloaded}/{total_bundles} bundles downloaded... (bundle {bundle_id} was already downloaded)")
                        continue
                    else:
                        raise Exception(f"Failed to start download for bundle {bundle_id}: {e}")
                
                # Wait for download completion
                while True:
                    bundle_status = await self.vcf_client.api_request(f"/v1/bundles/{bundle_id}")
                    download_status = bundle_status.get("downloadStatus")
                    
                    if download_status == "SUCCESSFUL":
                        downloaded += 1
                        self.set_upgrade_logs(domain_id, 
                            f"**Downloading Bundles**\n\nProgress: {downloaded}/{total_bundles} bundles downloaded...")
                        break
                    elif download_status == "FAILED":
                        raise Exception(f"Bundle download failed for bundle {bundle_id}")
                    
                    await asyncio.sleep(30)  # Check every 30 seconds
            
            _LOGGER.info(f"All bundles downloaded successfully for domain {domain_id}")
            
        except Exception as e:
            raise Exception(f"Failed to download bundles: {e}")
    
    async def _run_prechecks(self, domain_id: str, target_version: str, next_release: Dict[str, Any]):
        """Run pre-checks for the upgrade."""
        self.set_upgrade_status(domain_id, "running_prechecks")
        self.set_upgrade_logs(domain_id, "**Running Pre-checks**\n\nRunning upgrade pre-checks...")
        
        try:
            # Step 1: Get available check-sets
            query_data = {
                "checkSetType": "UPGRADE",
                "domains": [{"domainId": domain_id}]
            }
            
            first_response = await self.vcf_client.api_request("/v1/system/check-sets/queries", method="POST", data=query_data)
            
            # Extract resource types
            resources_data = []
            first_response_resources = first_response.get("resources", [])
            
            if isinstance(first_response_resources, list):
                for resource in first_response_resources:
                    if isinstance(resource, dict):
                        resource_type = resource.get("resourceType")
                        if resource_type:
                            resources_data.append({
                                "resourceType": resource_type,
                                "resourceId": resource.get("resourceId"),
                                "resourceName": resource.get("resourceName"),
                                "domain": resource.get("domain")
                            })
            
            # Step 2: Get target versions for resources
            bom_data = next_release.get("bom", [])
            bom_map = {item.get("name"): item.get("version") for item in bom_data if item.get("name") and item.get("version")}
            
            # Prepare resources with target versions
            resources_with_versions = []
            for resource_data in resources_data:
                resource_type = resource_data["resourceType"]
                target_resource_version = bom_map.get(resource_type)
                
                if target_resource_version:
                    resources_with_versions.append({
                        "resourceType": resource_type,
                        "resourceTargetVersion": target_resource_version
                    })
            
            # Step 3: Get detailed check-sets
            detailed_query_data = {
                "checkSetType": "UPGRADE",
                "domains": [{
                    "domainId": domain_id,
                    "resources": resources_with_versions
                }]
            }
            
            second_response = await self.vcf_client.api_request("/v1/system/check-sets/queries", method="POST", data=detailed_query_data)
            
            # Step 4: Prepare and execute check-sets
            check_set_data = {
                "resources": [],
                "queryId": second_response.get("queryId"),
                "metadata": {
                    "targetVersion": target_version
                }
            }
            
            # Store resource info for later use
            resource_info = {}
            second_response_resources = second_response.get("resources", [])
            
            if isinstance(second_response_resources, list):
                for resource in second_response_resources:
                    if isinstance(resource, dict):
                        resource_id = resource.get("resourceId")
                        resource_type = resource.get("resourceType")
                        
                        if resource_id and resource_type:
                            resource_info[resource_type] = resource_id
                        
                        # Prepare check sets data
                        check_sets_list = []
                        resource_check_sets = resource.get("checkSets", [])
                        
                        if isinstance(resource_check_sets, list):
                            for cs in resource_check_sets:
                                if isinstance(cs, dict):
                                    check_set_id = cs.get("checkSetId")
                                    if check_set_id:
                                        check_sets_list.append({"checkSetId": check_set_id})
                        
                        check_set_data["resources"].append({
                            "resourceType": resource.get("resourceType"),
                            "resourceId": resource.get("resourceId"),
                            "resourceName": resource.get("resourceName"),
                            "domain": resource.get("domain"),
                            "checkSets": check_sets_list
                        })
            
            # Store resource info for upgrade execution
            if domain_id not in self._upgrade_states:
                self._upgrade_states[domain_id] = {}
            self._upgrade_states[domain_id]["resource_info"] = resource_info
            
            # Execute pre-checks
            precheck_response = await self.vcf_client.api_request("/v1/system/check-sets", method="POST", data=check_set_data)
            
            # Handle potential string response from PATCH operations
            if isinstance(precheck_response, dict):
                run_id = precheck_response.get("id")
            else:
                raise Exception("Pre-check execution did not return expected response format")
            
            if not run_id:
                raise Exception("No run ID returned from pre-check execution")
            
            # Wait for pre-checks to complete
            while True:
                status_response = await self.vcf_client.api_request(f"/v1/system/check-sets/{run_id}")
                
                if not isinstance(status_response, dict):
                    raise Exception("Unexpected response format from status check")
                    
                status = status_response.get("status")
                
                if status == "COMPLETED_WITH_SUCCESS":
                    break
                elif status == "COMPLETED_WITH_FAILURE":
                    raise Exception("Pre-checks failed")
                
                await asyncio.sleep(30)  # Check every 30 seconds
            
            # Check for errors and warnings
            assessment_output = status_response.get("presentedArtifactsMap", {})
            if isinstance(assessment_output, dict):
                validation_summary = assessment_output.get("validation-domain-summary", [{}])
                if isinstance(validation_summary, list) and len(validation_summary) > 0:
                    validation_data = validation_summary[0]
                    if isinstance(validation_data, dict):
                        error_count = validation_data.get("errorValidationsCount", 0)
                        warning_count = validation_data.get("warningGapsCount", 0)
                    else:
                        error_count = warning_count = 0
                else:
                    error_count = warning_count = 0
            else:
                error_count = warning_count = 0
            
            if error_count > 0 or warning_count > 0:
                # Get domain info for URL
                domain_info = self.hass.data.get("datacenter_assistant", {}).get("coordinator", {}).data
                domain_fqdn = None
                
                if domain_info and "domains" in domain_info:
                    for domain in domain_info["domains"]:
                        if domain.get("id") == domain_id:
                            domain_fqdn = domain.get("sddc_manager_fqdn")
                            break
                
                logs = f"""**Pre-check Results**

Errors: {error_count}
Warnings: {warning_count}

More details:
https://{domain_fqdn}/ui/sddc-manager/inventory/domains/mgmt-vi-domains/{domain_id}/updates/pre-check-details/DOMAIN/{domain_id}/false(monitoring-panel:monitoring/tasks)?assessmentId={run_id}

Waiting for acknowledgement..."""
                
                self.set_upgrade_status(domain_id, "waiting_acknowledgement")
                self.set_upgrade_logs(domain_id, logs)
                
                # Wait for acknowledgement
                while not self._upgrade_states.get(domain_id, {}).get("acknowledged", False):
                    await asyncio.sleep(5)
                
                # Reset acknowledgement flag
                self._upgrade_states[domain_id]["acknowledged"] = False
            else:
                self.set_upgrade_logs(domain_id, "**Pre-check Results**\n\nPre-check passed successfully. No warnings or errors. Continuing...")
            
        except Exception as e:
            raise Exception(f"Pre-checks failed: {e}")
    
    async def _start_upgrades(self, domain_id: str, target_version: str, domain_data: Dict[str, Any]):
        """Start component upgrades."""
        self.set_upgrade_status(domain_id, "starting_upgrades")
        self.set_upgrade_logs(domain_id, "**Starting Component Upgrades**\n\nStarting component upgrades...")
        
        try:
            upgrade_cycle = 0
            while True:
                upgrade_cycle += 1
                _LOGGER.info(f"Domain {domain_id}: Starting upgrade cycle {upgrade_cycle}")
                
                # Get what can be upgraded next
                _LOGGER.debug(f"Domain {domain_id}: Fetching available upgrades for target version {target_version}")
                upgradables_response = await self.vcf_client.api_request(
                    f"/v1/upgradables/domains/{domain_id}",
                    params={"targetVersion": target_version}
                )
                
                _LOGGER.debug(f"Domain {domain_id}: Upgradables response: {upgradables_response}")
                
                if not isinstance(upgradables_response, dict):
                    raise Exception("Unexpected response format from upgradables endpoint")

                all_elements = upgradables_response.get("elements", [])
                _LOGGER.info(f"Domain {domain_id}: Found {len(all_elements)} total upgradable elements")
                
                available_upgrades = [
                    upgrade for upgrade in all_elements
                    if isinstance(upgrade, dict) and upgrade.get("status") == "AVAILABLE"
                ]
                
                _LOGGER.info(f"Domain {domain_id}: Found {len(available_upgrades)} available upgrades")
                
                if not available_upgrades:
                    _LOGGER.info(f"Domain {domain_id}: No more upgrades available, checking if all are completed")
                    
                    # Check if all elements are completed
                    completed_elements = [
                        element for element in all_elements
                        if isinstance(element, dict) and element.get("status") == "COMPLETED"
                    ]
                    
                    _LOGGER.info(f"Domain {domain_id}: Found {len(completed_elements)} completed elements out of {len(all_elements)} total")
                    
                    if len(completed_elements) == len(all_elements):
                        _LOGGER.info(f"Domain {domain_id}: All upgrades completed successfully")
                        break
                    else:
                        # Log status of non-completed elements
                        for element in all_elements:
                            if isinstance(element, dict) and element.get("status") != "COMPLETED":
                                _LOGGER.info(f"Domain {domain_id}: Element {element.get('bundleId', 'unknown')} status: {element.get('status', 'unknown')}")
                        
                        # Wait before checking again
                        _LOGGER.info(f"Domain {domain_id}: Waiting 30 seconds before checking upgrades again...")
                        await asyncio.sleep(30)
                        continue
                
                # Process each available upgrade
                processed_count = 0
                for i, upgrade in enumerate(available_upgrades, 1):
                    _LOGGER.info(f"Domain {domain_id}: Processing upgrade {i}/{len(available_upgrades)}")
                    
                    if not isinstance(upgrade, dict):
                        _LOGGER.warning(f"Domain {domain_id}: Skipping non-dict upgrade: {upgrade}")
                        continue
                        
                    bundle_id = upgrade.get("bundleId")
                    upgrade_status = upgrade.get("status")
                    
                    _LOGGER.debug(f"Domain {domain_id}: Upgrade details - bundleId: {bundle_id}, status: {upgrade_status}")
                    
                    if not bundle_id:
                        _LOGGER.warning(f"Domain {domain_id}: Skipping upgrade with no bundleId: {upgrade}")
                        continue
                    
                    # Get bundle details to determine component type
                    _LOGGER.debug(f"Domain {domain_id}: Fetching bundle details for {bundle_id}")
                    try:
                        bundle_response = await self.vcf_client.api_request(f"/v1/bundles/{bundle_id}")
                    except Exception as e:
                        _LOGGER.error(f"Domain {domain_id}: Failed to fetch bundle {bundle_id}: {e}")
                        continue
                    
                    _LOGGER.debug(f"Domain {domain_id}: Bundle {bundle_id} response: {bundle_response}")
                    
                    if not isinstance(bundle_response, dict):
                        _LOGGER.warning(f"Domain {domain_id}: Unexpected bundle response format for {bundle_id}: {bundle_response}")
                        continue
                        
                    components = bundle_response.get("components", [])
                    _LOGGER.debug(f"Domain {domain_id}: Bundle {bundle_id} has {len(components)} components")
                    
                    if not components or not isinstance(components, list):
                        _LOGGER.warning(f"Domain {domain_id}: Bundle {bundle_id} has no valid components: {components}")
                        continue
                    
                    component_data = components[0]
                    if not isinstance(component_data, dict):
                        _LOGGER.warning(f"Domain {domain_id}: Bundle {bundle_id} first component is not a dict: {component_data}")
                        continue
                        
                    component_type = component_data.get("type", "")
                    component_name = component_data.get("name", "unknown")
                    component_version = component_data.get("version", "unknown")
                    
                    _LOGGER.info(f"Domain {domain_id}: Processing component - Type: {component_type}, Name: {component_name}, Version: {component_version}")
                    
                    # Execute upgrade based on component type
                    try:
                        if "SDDC_MANAGER" in component_type:
                            _LOGGER.info(f"Domain {domain_id}: Starting SDDC Manager upgrade with bundle {bundle_id}")
                            await self._upgrade_sddc_manager(domain_id, bundle_id)
                            processed_count += 1
                        elif "NSX_T_MANAGER" in component_type:
                            _LOGGER.info(f"Domain {domain_id}: Starting NSX-T Manager upgrade with bundle {bundle_id}")
                            await self._upgrade_nsx(domain_id, bundle_id)
                            processed_count += 1
                        elif "VCENTER" in component_type:
                            _LOGGER.info(f"Domain {domain_id}: Starting vCenter upgrade with bundle {bundle_id}")
                            await self._upgrade_vcenter(domain_id, bundle_id)
                            processed_count += 1
                        elif "ESX_HOST" in component_type or "HOST" in component_type:
                            # Skip ESX host upgrades as per requirements but log properly
                            _LOGGER.info(f"Domain {domain_id}: Skipping ESX host upgrade for component {component_name} (HOST upgrades not implemented)")
                            # Mark as processed so we don't loop indefinitely
                            processed_count += 1
                            continue
                        else:
                            _LOGGER.warning(f"Domain {domain_id}: Unknown component type: {component_type} for component {component_name}")
                            # For unknown types, still count as processed to avoid infinite loops
                            processed_count += 1
                            continue
                            
                    except Exception as e:
                        _LOGGER.error(f"Domain {domain_id}: Failed to upgrade component {component_name} ({component_type}): {e}")
                        # Continue with other upgrades even if one fails
                        continue
                    
                    # Wait a bit before processing next upgrade
                    _LOGGER.debug(f"Domain {domain_id}: Waiting 10 seconds before next upgrade...")
                    await asyncio.sleep(10)
                
                _LOGGER.info(f"Domain {domain_id}: Completed upgrade cycle {upgrade_cycle}, processed {processed_count} upgrades")
                
                # If we didn't process any upgrades in this cycle, wait longer before checking again
                if processed_count == 0:
                    _LOGGER.info(f"Domain {domain_id}: No upgrades processed this cycle, waiting 60 seconds...")
                    await asyncio.sleep(60)
        
        except Exception as e:
            raise Exception(f"Component upgrades failed: {e}")
    
    async def _upgrade_sddc_manager(self, domain_id: str, bundle_id: str):
        """Upgrade SDDC Manager."""
        _LOGGER.info(f"Domain {domain_id}: Starting SDDC Manager upgrade with bundle {bundle_id}")
        self.set_upgrade_status(domain_id, "upgrading_sddcmanager")
        self.set_upgrade_logs(domain_id, "**Upgrading SDDC Manager**\n\nUpgrading SDDC Manager. This may take up to 1 hour...")
        
        try:
            upgrade_data = {
                "bundleId": bundle_id,
                "resourceType": "DOMAIN",
                "resourceUpgradeSpecs": [{
                    "resourceId": domain_id,
                    "upgradeNow": True
                }]
            }
            
            _LOGGER.debug(f"Domain {domain_id}: Sending SDDC Manager upgrade request with data: {upgrade_data}")
            upgrade_response = await self.vcf_client.api_request("/v1/upgrades", method="POST", data=upgrade_data)
            _LOGGER.debug(f"Domain {domain_id}: SDDC Manager upgrade response: {upgrade_response}")
            
            upgrade_id = upgrade_response.get("id")
            
            if not upgrade_id:
                raise Exception(f"No upgrade ID returned from SDDC Manager upgrade response: {upgrade_response}")
            
            _LOGGER.info(f"Domain {domain_id}: SDDC Manager upgrade started with ID: {upgrade_id}")
            
            # Monitor upgrade progress
            check_count = 0
            while True:
                check_count += 1
                _LOGGER.debug(f"Domain {domain_id}: SDDC Manager upgrade status check #{check_count}")
                
                try:
                    status_response = await self.vcf_client.api_request(f"/v1/upgrades/{upgrade_id}")
                    status = status_response.get("status")
                    
                    _LOGGER.info(f"Domain {domain_id}: SDDC Manager upgrade status: {status}")
                    
                    if status == "COMPLETED_WITH_SUCCESS":
                        _LOGGER.info(f"Domain {domain_id}: SDDC Manager upgrade completed successfully")
                        break
                    elif status in ["FAILED", "COMPLETED_WITH_FAILURE"]:
                        error_msg = f"SDDC Manager upgrade failed with status: {status}"
                        _LOGGER.error(f"Domain {domain_id}: {error_msg}")
                        raise Exception(error_msg)
                    
                except Exception as api_error:
                    # During SDDC Manager upgrade, API might be unavailable
                    _LOGGER.warning(f"Domain {domain_id}: API temporarily unavailable during SDDC Manager upgrade: {api_error}")
                    
                    # Try to check if API is back online
                    try:
                        _LOGGER.debug(f"Domain {domain_id}: Testing if API is back online...")
                        await self.vcf_client.api_request("/v1/domains")
                        _LOGGER.info(f"Domain {domain_id}: API is back online after SDDC Manager upgrade")
                        # If successful, wait additional 5 minutes
                        _LOGGER.info(f"Domain {domain_id}: Waiting 5 minutes for SDDC Manager to fully stabilize...")
                        await asyncio.sleep(300)
                        break
                    except Exception as test_error:
                        _LOGGER.debug(f"Domain {domain_id}: API still not available: {test_error}")
                        pass
                
                _LOGGER.debug(f"Domain {domain_id}: Waiting 30 seconds before next SDDC Manager upgrade status check...")
                await asyncio.sleep(30)
            
            _LOGGER.info(f"SDDC Manager upgrade completed for domain {domain_id}")
            
        except Exception as e:
            raise Exception(f"SDDC Manager upgrade failed: {e}")
    
    async def _upgrade_nsx(self, domain_id: str, bundle_id: str):
        """Upgrade NSX-T Manager."""
        self.set_upgrade_status(domain_id, "upgrading_nsx")
        self.set_upgrade_logs(domain_id, "**Upgrading NSX-T**\n\nUpgrading NSX-T Manager. This may take up to 3 hours...")
        
        try:
            # Get NSX resources
            nsx_resources = await self.vcf_client.api_request(
                f"/v1/upgradables/domains/{domain_id}/nsxt",
                params={"bundleId": bundle_id}
            )
            
            if not isinstance(nsx_resources, dict):
                raise Exception("Unexpected response format from NSX resources endpoint")
            
            nsxt_manager_cluster = nsx_resources.get("nsxtManagerCluster", {})
            nsxt_host_clusters = nsx_resources.get("nsxtHostClusters", [])
            
            if not isinstance(nsxt_manager_cluster, dict) or not isinstance(nsxt_host_clusters, list):
                raise Exception("Invalid NSX resources structure")
            
            nsxt_manager_cluster_id = nsxt_manager_cluster.get("id")
            
            if not nsxt_host_clusters or not isinstance(nsxt_host_clusters[0], dict):
                raise Exception("Required NSX host clusters not found")
            
            nsxt_host_cluster_id = nsxt_host_clusters[0].get("id")
            
            if not nsxt_manager_cluster_id or not nsxt_host_cluster_id:
                raise Exception("Required NSX resource IDs not found")
            
            upgrade_data = {
                "bundleId": bundle_id,
                "resourceType": "DOMAIN",
                "draftMode": False,
                "nsxtUpgradeUserInputSpecs": [{
                    "nsxtUpgradeOptions": {
                        "isEdgeOnlyUpgrade": False,
                        "isHostClustersUpgradeParallel": True,
                        "isEdgeClustersUpgradeParallel": True
                    },
                    "nsxtId": nsxt_manager_cluster_id,
                    "nsxtHostClusterUpgradeSpecs": [{
                        "hostClusterId": nsxt_host_cluster_id,
                        "liveUpgrade": False,
                        "hostParallelUpgrade": False
                    }]
                }],
                "resourceUpgradeSpecs": [{
                    "resourceId": domain_id,
                    "upgradeNow": True
                }]
            }
            
            upgrade_response = await self.vcf_client.api_request("/v1/upgrades", method="POST", data=upgrade_data)
            upgrade_id = upgrade_response.get("id")
            
            if not upgrade_id:
                raise Exception("No upgrade ID returned")
            
            # Monitor upgrade progress
            await self._monitor_upgrade_progress(upgrade_id, "NSX-T upgrade")
            
            _LOGGER.info(f"NSX-T upgrade completed for domain {domain_id}")
            
        except Exception as e:
            raise Exception(f"NSX-T upgrade failed: {e}")
    
    async def _upgrade_vcenter(self, domain_id: str, bundle_id: str):
        """Upgrade vCenter."""
        self.set_upgrade_status(domain_id, "upgrading_vcenter")
        self.set_upgrade_logs(domain_id, "**Upgrading vCenter**\n\nUpgrading vCenter Server...")
        
        try:
            # Get vCenter resource ID from stored resource info
            resource_info = self._upgrade_states.get(domain_id, {}).get("resource_info", {})
            vcenter_resource_id = resource_info.get("VCENTER")
            
            if not vcenter_resource_id:
                raise Exception("vCenter resource ID not found")
            
            upgrade_data = {
                "bundleId": bundle_id,
                "resourceType": "DOMAIN",
                "resourceUpgradeSpecs": [{
                    "resourceId": domain_id,
                    "upgradeNow": True
                }],
                "vcenterUpgradeUserInputSpecs": [{
                    "resourceId": vcenter_resource_id,
                    "upgradeMechanism": "InPlace"
                }]
            }
            
            upgrade_response = await self.vcf_client.api_request("/v1/upgrades", method="POST", data=upgrade_data)
            upgrade_id = upgrade_response.get("id")
            
            if not upgrade_id:
                raise Exception("No upgrade ID returned")
            
            # Monitor upgrade progress
            await self._monitor_upgrade_progress(upgrade_id, "vCenter upgrade")
            
            _LOGGER.info(f"vCenter upgrade completed for domain {domain_id}")
            
        except Exception as e:
            raise Exception(f"vCenter upgrade failed: {e}")
    
    async def _monitor_upgrade_progress(self, upgrade_id: str, upgrade_name: str):
        """Monitor upgrade progress until completion."""
        while True:
            try:
                status_response = await self.vcf_client.api_request(f"/v1/upgrades/{upgrade_id}")
                status = status_response.get("status")
                
                if status == "COMPLETED_WITH_SUCCESS":
                    break
                elif status in ["FAILED", "COMPLETED_WITH_FAILURE"]:
                    raise Exception(f"{upgrade_name} failed with status: {status}")
                
            except Exception as api_error:
                # Handle potential authorization errors during vCenter upgrade
                if "vCenter" in upgrade_name:
                    _LOGGER.warning(f"API error during {upgrade_name}, retrying: {api_error}")
                else:
                    raise api_error
            
            await asyncio.sleep(30)
    
    async def _final_validation(self, domain_id: str, target_version: str):
        """Run final validation after all upgrades."""
        self.set_upgrade_status(domain_id, "final_validation")
        self.set_upgrade_logs(domain_id, "**Final Validation**\n\nRunning final validation...")
        
        try:
            validation_data = {"targetVersion": target_version}
            validation_response = await self.vcf_client.api_request(
                f"/v1/releases/domains/{domain_id}/validations",
                method="POST",
                data=validation_data
            )
            
            execution_status = validation_response.get("executionStatus")
            
            if execution_status != "COMPLETED":
                raise Exception(f"Final validation failed with status: {execution_status}")
            
            _LOGGER.info(f"Final validation completed successfully for domain {domain_id}")
            
        except Exception as e:
            raise Exception(f"Final validation failed: {e}")
