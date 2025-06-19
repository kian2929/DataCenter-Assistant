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
        _LOGGER.info(f"Domain {domain_id}: Starting pre-checks for target version {target_version}")
        self.set_upgrade_status(domain_id, "running_prechecks")
        self.set_upgrade_logs(domain_id, "**Running Pre-checks**\n\nRunning upgrade pre-checks...")
        
        try:
            # Step 1: Get available check-sets
            _LOGGER.debug(f"Domain {domain_id}: Step 1 - Getting available check-sets")
            query_data = {
                "checkSetType": "UPGRADE",
                "domains": [{"domainId": domain_id}]
            }
            
            _LOGGER.debug(f"Domain {domain_id}: Sending initial check-sets query: {query_data}")
            first_response = await self.vcf_client.api_request("/v1/system/check-sets/queries", method="POST", data=query_data)
            _LOGGER.debug(f"Domain {domain_id}: Initial check-sets response: {first_response}")
            
            # Extract resource types
            resources_data = []
            first_response_resources = first_response.get("resources", [])
            _LOGGER.info(f"Domain {domain_id}: Found {len(first_response_resources) if isinstance(first_response_resources, list) else 0} resources in initial response")
            
            if isinstance(first_response_resources, list):
                for i, resource in enumerate(first_response_resources, 1):
                    if isinstance(resource, dict):
                        resource_type = resource.get("resourceType")
                        resource_id = resource.get("resourceId")
                        resource_name = resource.get("resourceName")
                        
                        _LOGGER.info(f"Domain {domain_id}: Resource {i} - Type: {resource_type}, ID: {resource_id}, Name: {resource_name}")
                        
                        if resource_type:
                            resources_data.append({
                                "resourceType": resource_type,
                                "resourceId": resource_id,
                                "resourceName": resource_name,
                                "domain": resource.get("domain")
                            })
            
            _LOGGER.info(f"Domain {domain_id}: Processed {len(resources_data)} valid resources")
            
            # Step 2: Get target versions for resources
            _LOGGER.debug(f"Domain {domain_id}: Step 2 - Processing BOM (Bill of Materials)")
            bom_data = next_release.get("bom", [])
            _LOGGER.info(f"Domain {domain_id}: Found {len(bom_data) if isinstance(bom_data, list) else 0} BOM entries")
            
            bom_map = {}
            if isinstance(bom_data, list):
                for i, item in enumerate(bom_data, 1):
                    if isinstance(item, dict):
                        name = item.get("name")
                        version = item.get("version")
                        _LOGGER.debug(f"Domain {domain_id}: BOM {i} - Component: {name}, Version: {version}")
                        if name and version:
                            bom_map[name] = version
            
            _LOGGER.info(f"Domain {domain_id}: Created BOM mapping for {len(bom_map)} components: {list(bom_map.keys())}")
            
            # Prepare resources with target versions
            resources_with_versions = []
            _LOGGER.debug(f"Domain {domain_id}: Mapping resources to target versions")
            
            for resource_data in resources_data:
                resource_type = resource_data["resourceType"]
                target_resource_version = bom_map.get(resource_type)
                
                _LOGGER.debug(f"Domain {domain_id}: Resource {resource_type} -> Target version: {target_resource_version}")
                
                if target_resource_version:
                    resources_with_versions.append({
                        "resourceType": resource_type,
                        "resourceTargetVersion": target_resource_version
                    })
                    _LOGGER.info(f"Domain {domain_id}: Mapped {resource_type} to version {target_resource_version}")
                else:
                    _LOGGER.warning(f"Domain {domain_id}: No target version found for resource type {resource_type}")
            
            _LOGGER.info(f"Domain {domain_id}: {len(resources_with_versions)} resources mapped to target versions")
            
            # Step 3: Get detailed check-sets
            _LOGGER.debug(f"Domain {domain_id}: Step 3 - Getting detailed check-sets")
            detailed_query_data = {
                "checkSetType": "UPGRADE",
                "domains": [{
                    "domainId": domain_id,
                    "resources": resources_with_versions
                }]
            }
            
            _LOGGER.debug(f"Domain {domain_id}: Sending detailed check-sets query: {detailed_query_data}")
            second_response = await self.vcf_client.api_request("/v1/system/check-sets/queries", method="POST", data=detailed_query_data)
            _LOGGER.debug(f"Domain {domain_id}: Detailed check-sets response keys: {list(second_response.keys()) if isinstance(second_response, dict) else 'Not a dict'}")
            
            query_id = second_response.get("queryId")
            _LOGGER.info(f"Domain {domain_id}: Got query ID: {query_id}")
            
            # Step 4: Prepare and execute check-sets
            _LOGGER.debug(f"Domain {domain_id}: Step 4 - Preparing check-sets for execution")
            check_set_data = {
                "resources": [],
                "queryId": query_id,
                "metadata": {
                    "targetVersion": target_version
                }
            }
            
            # Store resource info for later use
            resource_info = {}
            second_response_resources = second_response.get("resources", [])
            _LOGGER.info(f"Domain {domain_id}: Processing {len(second_response_resources) if isinstance(second_response_resources, list) else 0} resources from detailed response")
            
            if isinstance(second_response_resources, list):
                for i, resource in enumerate(second_response_resources, 1):
                    if isinstance(resource, dict):
                        resource_id = resource.get("resourceId")
                        resource_type = resource.get("resourceType")
                        resource_name = resource.get("resourceName")
                        
                        _LOGGER.info(f"Domain {domain_id}: Processing resource {i} - Type: {resource_type}, ID: {resource_id}, Name: {resource_name}")
                        
                        if resource_id and resource_type:
                            resource_info[resource_type] = resource_id
                        
                        # Prepare check sets data
                        check_sets_list = []
                        resource_check_sets = resource.get("checkSets", [])
                        
                        _LOGGER.debug(f"Domain {domain_id}: Resource {resource_type} has {len(resource_check_sets) if isinstance(resource_check_sets, list) else 0} check sets")
                        
                        if isinstance(resource_check_sets, list):
                            for j, cs in enumerate(resource_check_sets, 1):
                                if isinstance(cs, dict):
                                    check_set_id = cs.get("checkSetId")
                                    check_set_name = cs.get("checkSetName", "Unknown")
                                    _LOGGER.debug(f"Domain {domain_id}: Check set {j} for {resource_type} - ID: {check_set_id}, Name: {check_set_name}")
                                    if check_set_id:
                                        check_sets_list.append({"checkSetId": check_set_id})
                        
                        _LOGGER.info(f"Domain {domain_id}: Added {len(check_sets_list)} check sets for resource {resource_type}")
                        
                        check_set_data["resources"].append({
                            "resourceType": resource.get("resourceType"),
                            "resourceId": resource.get("resourceId"),
                            "resourceName": resource.get("resourceName"),
                            "domain": resource.get("domain"),
                            "checkSets": check_sets_list
                        })
            
            _LOGGER.info(f"Domain {domain_id}: Prepared check-sets for {len(check_set_data['resources'])} resources")
            _LOGGER.debug(f"Domain {domain_id}: Final check-set data structure: {check_set_data}")
            
            # Store resource info for upgrade execution
            if domain_id not in self._upgrade_states:
                self._upgrade_states[domain_id] = {}
            self._upgrade_states[domain_id]["resource_info"] = resource_info
            _LOGGER.debug(f"Domain {domain_id}: Stored resource info: {resource_info}")
            
            # Execute pre-checks
            _LOGGER.info(f"Domain {domain_id}: Executing pre-checks...")
            precheck_response = await self.vcf_client.api_request("/v1/system/check-sets", method="POST", data=check_set_data)
            _LOGGER.debug(f"Domain {domain_id}: Pre-check execution response: {precheck_response}")
            
            # Handle potential string response from PATCH operations
            if isinstance(precheck_response, dict):
                run_id = precheck_response.get("id")
            else:
                _LOGGER.warning(f"Domain {domain_id}: Pre-check response is not a dict: {precheck_response}")
                raise Exception("Pre-check execution did not return expected response format")
            
            if not run_id:
                raise Exception(f"No run ID returned from pre-check execution. Response: {precheck_response}")
            
            _LOGGER.info(f"Domain {domain_id}: Pre-checks started with run ID: {run_id}")
            
            # Wait for pre-checks to complete
            check_count = 0
            while True:
                check_count += 1
                _LOGGER.debug(f"Domain {domain_id}: Pre-check status check #{check_count}")
                
                status_response = await self.vcf_client.api_request(f"/v1/system/check-sets/{run_id}")
                
                if not isinstance(status_response, dict):
                    raise Exception(f"Unexpected response format from status check: {status_response}")
                    
                status = status_response.get("status")
                progress = status_response.get("progress", {})
                
                _LOGGER.info(f"Domain {domain_id}: Pre-check status: {status}")
                if isinstance(progress, dict) and progress:
                    _LOGGER.debug(f"Domain {domain_id}: Pre-check progress: {progress}")
                
                if status == "COMPLETED_WITH_SUCCESS":
                    _LOGGER.info(f"Domain {domain_id}: Pre-checks completed successfully")
                    break
                elif status == "COMPLETED_WITH_FAILURE":
                    _LOGGER.error(f"Domain {domain_id}: Pre-checks failed")
                    raise Exception("Pre-checks failed")
                elif status in ["FAILED", "CANCELLED"]:
                    _LOGGER.error(f"Domain {domain_id}: Pre-checks ended with status: {status}")
                    raise Exception(f"Pre-checks ended with status: {status}")
                
                _LOGGER.debug(f"Domain {domain_id}: Pre-checks still running, waiting 30 seconds...")
                await asyncio.sleep(30)  # Check every 30 seconds
            
            # Check for errors and warnings
            _LOGGER.debug(f"Domain {domain_id}: Processing pre-check results")
            assessment_output = status_response.get("presentedArtifactsMap", {})
            _LOGGER.debug(f"Domain {domain_id}: Assessment output keys: {list(assessment_output.keys()) if isinstance(assessment_output, dict) else 'Not a dict'}")
            
            error_count = 0
            warning_count = 0
            
            if isinstance(assessment_output, dict):
                validation_summary = assessment_output.get("validation-domain-summary", [{}])
                _LOGGER.debug(f"Domain {domain_id}: Validation summary type: {type(validation_summary)}, length: {len(validation_summary) if isinstance(validation_summary, list) else 'N/A'}")
                
                if isinstance(validation_summary, list) and len(validation_summary) > 0:
                    validation_data = validation_summary[0]
                    _LOGGER.debug(f"Domain {domain_id}: Validation data: {validation_data}")
                    
                    if isinstance(validation_data, dict):
                        error_count = validation_data.get("errorValidationsCount", 0)
                        warning_count = validation_data.get("warningGapsCount", 0)
                        
                        # Log additional validation details if available
                        for key, value in validation_data.items():
                            if "count" in key.lower() or "error" in key.lower() or "warning" in key.lower():
                                _LOGGER.debug(f"Domain {domain_id}: {key}: {value}")
                    else:
                        _LOGGER.warning(f"Domain {domain_id}: Validation data is not a dict: {validation_data}")
                else:
                    _LOGGER.warning(f"Domain {domain_id}: Validation summary is empty or not a list")
            else:
                _LOGGER.warning(f"Domain {domain_id}: Assessment output is not a dict")
            
            _LOGGER.info(f"Domain {domain_id}: Pre-check results - Errors: {error_count}, Warnings: {warning_count}")
            
            if error_count > 0 or warning_count > 0:
                _LOGGER.warning(f"Domain {domain_id}: Pre-checks completed with issues - Errors: {error_count}, Warnings: {warning_count}")
                
                # Get domain info for URL
                domain_info = self.hass.data.get("datacenter_assistant", {}).get("coordinator", {}).data
                domain_fqdn = None
                
                if domain_info and "domains" in domain_info:
                    for domain in domain_info["domains"]:
                        if domain.get("id") == domain_id:
                            domain_fqdn = domain.get("sddc_manager_fqdn")
                            _LOGGER.debug(f"Domain {domain_id}: Found domain FQDN: {domain_fqdn}")
                            break
                
                if not domain_fqdn:
                    _LOGGER.warning(f"Domain {domain_id}: Could not find domain FQDN for pre-check details URL")
                
                logs = f"""**Pre-check Results**

Errors: {error_count}
Warnings: {warning_count}

More details:
https://{domain_fqdn}/ui/sddc-manager/inventory/domains/mgmt-vi-domains/{domain_id}/updates/pre-check-details/DOMAIN/{domain_id}/false(monitoring-panel:monitoring/tasks)?assessmentId={run_id}

Waiting for acknowledgement..."""
                
                self.set_upgrade_status(domain_id, "waiting_acknowledgement")
                self.set_upgrade_logs(domain_id, logs)
                
                _LOGGER.info(f"Domain {domain_id}: Waiting for user acknowledgement of pre-check issues")
                
                # Wait for acknowledgement
                acknowledgement_wait_count = 0
                while not self._upgrade_states.get(domain_id, {}).get("acknowledged", False):
                    acknowledgement_wait_count += 1
                    if acknowledgement_wait_count % 12 == 0:  # Log every minute (12 * 5 seconds)
                        _LOGGER.debug(f"Domain {domain_id}: Still waiting for acknowledgement ({acknowledgement_wait_count * 5} seconds)")
                    await asyncio.sleep(5)
                
                _LOGGER.info(f"Domain {domain_id}: User acknowledged pre-check issues, continuing with upgrade")
                # Reset acknowledgement flag
                self._upgrade_states[domain_id]["acknowledged"] = False
            else:
                _LOGGER.info(f"Domain {domain_id}: Pre-checks passed successfully with no errors or warnings")
                self.set_upgrade_logs(domain_id, "**Pre-check Results**\n\nPre-check passed successfully. No warnings or errors. Continuing...")
            
        except Exception as e:
            _LOGGER.error(f"Domain {domain_id}: Pre-checks failed with exception: {e}")
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
                
                # Check if we only have HOST components left (which we skip)
                non_host_upgrades = []
                for upgrade in available_upgrades:
                    if not isinstance(upgrade, dict):
                        continue
                    bundle_id = upgrade.get("bundleId")
                    if not bundle_id:
                        continue
                    
                    try:
                        bundle_response = await self.vcf_client.api_request(f"/v1/bundles/{bundle_id}")
                        if isinstance(bundle_response, dict):
                            components = bundle_response.get("components", [])
                            if components and isinstance(components, list):
                                component_data = components[0]
                                if isinstance(component_data, dict):
                                    component_type = component_data.get("type", "")
                                    if component_type and "HOST" not in component_type:
                                        non_host_upgrades.append(upgrade)
                    except Exception as e:
                        _LOGGER.debug(f"Domain {domain_id}: Failed to check component type for bundle {bundle_id}: {e}")
                        non_host_upgrades.append(upgrade)  # Include if we can't check
                
                if not non_host_upgrades:
                    _LOGGER.info(f"Domain {domain_id}: Only HOST upgrades remain, and HOST upgrades are not implemented. Considering upgrade complete.")
                    break
                
                # Process each available upgrade
                processed_count = 0
                non_host_processed = 0
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
                    component_name = component_data.get("description", "unknown")  # Use description as name
                    component_version = component_data.get("toVersion", component_data.get("version", "unknown"))  # Use toVersion or fallback to version
                    
                    _LOGGER.info(f"Domain {domain_id}: Processing component - Type: {component_type}, Name: {component_name}, Version: {component_version}")
                    
                    # Execute upgrade based on component type
                    try:
                        if "SDDC_MANAGER" in component_type:
                            _LOGGER.info(f"Domain {domain_id}: Starting SDDC Manager upgrade with bundle {bundle_id}")
                            await self._upgrade_sddc_manager(domain_id, bundle_id)
                            processed_count += 1
                            non_host_processed += 1
                        elif "NSX_T_MANAGER" in component_type:
                            _LOGGER.info(f"Domain {domain_id}: Starting NSX-T Manager upgrade with bundle {bundle_id}")
                            await self._upgrade_nsx(domain_id, bundle_id)
                            processed_count += 1
                            non_host_processed += 1
                        elif "VCENTER" in component_type:
                            _LOGGER.info(f"Domain {domain_id}: Starting vCenter upgrade with bundle {bundle_id}")
                            await self._upgrade_vcenter(domain_id, bundle_id)
                            processed_count += 1
                            non_host_processed += 1
                        elif "ESX_HOST" in component_type or "HOST" in component_type:
                            # Skip ESX host upgrades as per requirements but log properly
                            _LOGGER.info(f"Domain {domain_id}: Skipping ESX host upgrade for component {component_name} (HOST upgrades not implemented)")
                            # Don't count HOST components as processed to avoid infinite loop
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
                
                _LOGGER.info(f"Domain {domain_id}: Completed upgrade cycle {upgrade_cycle}, processed {processed_count} upgrades ({non_host_processed} non-HOST)")
                
                # If we didn't process any non-HOST upgrades in this cycle, we might be done
                if non_host_processed == 0:
                    _LOGGER.info(f"Domain {domain_id}: No non-HOST upgrades processed this cycle")
                    
                    # Check if we should continue or exit
                    if processed_count == 0:
                        # Nothing processed at all - wait and try again
                        _LOGGER.info(f"Domain {domain_id}: No upgrades processed at all, waiting 60 seconds...")
                        await asyncio.sleep(60)
                    else:
                        # Only HOST upgrades were found - exit the loop since we don't process them
                        _LOGGER.info(f"Domain {domain_id}: Only HOST upgrades remain, exiting upgrade loop")
                        break
        
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
