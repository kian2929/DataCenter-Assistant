import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

class VCFUpgradeOrchestrator:
    """Handles VCF upgrade orchestration for a specific domain."""
    
    def __init__(self, hass: HomeAssistant, domain_id: str, domain_name: str, 
                 vcf_url: str, coordinator, domain_prefix: Optional[str] = None):
        self.hass = hass
        self.domain_id = domain_id
        self.domain_name = domain_name
        self.vcf_url = vcf_url
        self.coordinator = coordinator
        self.domain_prefix = domain_prefix or f"domain{domain_id[:8]}"
        
        # State tracking
        self.current_status = "waiting_for_initiation"
        self.logs = "## No Messages\n\nNo upgrade process has been initiated."
        self.timeout_duration = timedelta(hours=3)  # Default component timeout
        self.precheck_timeout = timedelta(minutes=40)  # Precheck timeout
        
        # Upgrade data
        self.target_version = None
        self.component_bundles = {}
        self.upgrade_tasks = {}
        
    async def get_current_token(self) -> Optional[str]:
        """Get current VCF token from coordinator or refresh if needed."""
        try:
            # Get token from the coordinator's config entry
            if hasattr(self.coordinator, 'config_entry') and self.coordinator.config_entry:
                current_token = self.coordinator.config_entry.data.get("vcf_token")
                if current_token:
                    return current_token
            
            # Fallback: try to get from hass data
            integration_data = self.hass.data.get("datacenter_assistant", {})
            for entry_id, entry_data in integration_data.items():
                if isinstance(entry_data, dict) and "vcf_token" in entry_data:
                    return entry_data.get("vcf_token")
            
            # Try to refresh token through coordinator
            if hasattr(self.coordinator, 'config_entry'):
                try:
                    await self.coordinator.async_refresh()
                    # Try again after refresh
                    current_token = self.coordinator.config_entry.data.get("vcf_token")
                    if current_token:
                        _LOGGER.info("Successfully refreshed VCF token")
                        return current_token
                except Exception as e:
                    _LOGGER.warning(f"Failed to refresh coordinator data: {e}")
            
            _LOGGER.error("No VCF token found in coordinator or hass data")
            return None
        except Exception as e:
            _LOGGER.error(f"Failed to get VCF token: {e}")
            return None
    
    def update_status(self, new_status: str, timeout_info: Optional[str] = None):
        """Update the upgrade status."""
        self.current_status = new_status
        if timeout_info:
            self.current_status += f" (timeout: {timeout_info})"
        _LOGGER.info(f"Domain {self.domain_name}: Status updated to {self.current_status}")
        
        # Update coordinator data to reflect status change
        if hasattr(self.coordinator, 'data') and self.coordinator.data:
            upgrade_data = self.coordinator.data.setdefault("upgrade_status", {})
            upgrade_data[self.domain_id] = {
                "status": self.current_status,
                "logs": self.logs,
                "last_updated": datetime.now().isoformat()
            }
        
        # Trigger coordinator update to refresh all entities
        if hasattr(self.coordinator, 'async_update_listeners'):
            try:
                self.coordinator.async_update_listeners()
            except Exception as e:
                _LOGGER.debug(f"Error updating coordinator listeners: {e}")
    
    def add_log(self, message: str, level: str = "info"):
        """Add a log message to the upgrade logs."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if level == "error":
            icon = "❌"
        elif level == "warning":
            icon = "⚠️"
        elif level == "success":
            icon = "✅"
        else:
            icon = "ℹ️"
        
        # Initialize logs if needed
        if "No Messages" in self.logs:
            self.logs = f"# Upgrade Log for {self.domain_name}\n\n"
        
        self.logs += f"**{timestamp}** {icon} {message}\n\n"
        
        _LOGGER.info(f"Domain {self.domain_name}: {message}")
        
        # Trigger coordinator update to refresh log entities
        if hasattr(self.coordinator, 'async_update_listeners'):
            try:
                self.coordinator.async_update_listeners()
            except Exception as e:
                _LOGGER.debug(f"Error updating coordinator listeners: {e}")
    
    async def start_upgrade_process(self):
        """Start the complete upgrade process."""
        try:
            self.add_log("Starting VCF upgrade process", "info")
            self.update_status("update_process_started")
            
            # Get next version info from coordinator
            domain_updates = self.coordinator.data.get("domain_updates", {})
            domain_data = domain_updates.get(self.domain_id, {})
            next_version_info = domain_data.get("next_version")
            
            if not next_version_info:
                self.add_log("No update available - cannot proceed", "error")
                self.update_status("failed")
                return False
            
            self.target_version = next_version_info.get("versionNumber")
            self.add_log(f"Target version: {self.target_version}", "info")
            
            # Step 1: Download bundles
            if not await self._download_bundles():
                return False
            
            # Step 2: Set target version
            if not await self._set_target_version():
                return False
            
            # Step 3: Run prechecks
            precheck_result = await self._run_prechecks()
            if precheck_result == "failed":
                return False
            elif precheck_result == "waiting_for_acknowledgment":
                return True  # Process will continue when alerts are acknowledged
            
            # Step 4: Execute upgrades
            if not await self._execute_upgrades():
                return False
            
            # Step 5: Final validation
            if not await self._final_validation():
                return False
            
            self.add_log("Upgrade process completed successfully!", "success")
            self.update_status("successfully_completed")
            
            # Reset to default after brief success display
            await asyncio.sleep(10)
            self.update_status("waiting_for_initiation")
            self.logs = "## No Messages\n\nNo upgrade process has been initiated."
            
            return True
            
        except Exception as e:
            self.add_log(f"Upgrade process failed with error: {str(e)}", "error")
            self.update_status("failed")
            return False
    
    async def _download_bundles(self) -> bool:
        """Download all necessary bundles."""
        try:
            self.add_log("Starting bundle downloads", "info")
            self.update_status("downloading_bundles")
            
            # Get component updates from coordinator
            domain_updates = self.coordinator.data.get("domain_updates", {})
            domain_data = domain_updates.get(self.domain_id, {})
            component_updates = domain_data.get("component_updates", {})
            
            if not component_updates:
                self.add_log("No component bundles to download", "warning")
                return True
            
            token = await self.get_current_token()
            if not token:
                self.add_log("Cannot get VCF token for bundle download", "error")
                return False
            
            session = async_get_clientsession(self.hass)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            download_tasks = []
            for comp_name, comp_data in component_updates.items():
                bundle_id = comp_data.get("id")
                if bundle_id:
                    download_tasks.append(self._download_single_bundle(session, headers, bundle_id, comp_name))
            
            # Download all bundles concurrently
            results = await asyncio.gather(*download_tasks, return_exceptions=True)
            
            success_count = sum(1 for r in results if r is True)
            total_count = len(results)
            
            if success_count == total_count:
                self.add_log(f"Successfully started download for all {total_count} bundles", "success")
                return True
            else:
                self.add_log(f"Only {success_count}/{total_count} bundle downloads started successfully", "error")
                return False
                
        except Exception as e:
            self.add_log(f"Bundle download phase failed: {str(e)}", "error")
            return False
    
    async def _download_single_bundle(self, session, headers, bundle_id: str, component_name: str) -> bool:
        """Download a single bundle."""
        try:
            download_url = f"{self.vcf_url}/v1/bundles/{bundle_id}"
            patch_data = {"downloadNow": True}  # According to flow2.txt
            
            async with session.patch(download_url, headers=headers, json=patch_data, ssl=False) as resp:
                if resp.status in [200, 202, 204]:
                    self.add_log(f"Started download for {component_name} bundle", "info")
                    return True
                elif resp.status == 409:
                    # Bundle might already be downloaded
                    self.add_log(f"Bundle for {component_name} already downloaded or in progress", "info")
                    return True
                elif resp.status == 500:
                    error_text = await resp.text()
                    if "BundleDownloadSpec" in error_text:
                        self.add_log(f"Bundle {component_name} download spec issue - may already be downloaded", "warning")
                        return True  # Continue anyway
                    else:
                        self.add_log(f"Failed to download {component_name} bundle: {resp.status} - {error_text}", "error")
                        return False
                else:
                    error_text = await resp.text()
                    self.add_log(f"Failed to download {component_name} bundle: {resp.status} - {error_text}", "error")
                    return False
                    
        except Exception as e:
            self.add_log(f"Error downloading {component_name} bundle: {str(e)}", "error")
            return False
    
    async def _set_target_version(self) -> bool:
        """Set the target VCF version for the domain."""
        try:
            self.add_log(f"Setting target version to {self.target_version}", "info")
            self.update_status("setting_new_vcf_version_target")
            
            token = await self.get_current_token()
            if not token:
                self.add_log("Cannot get VCF token for setting target version", "error")
                return False
            
            session = async_get_clientsession(self.hass)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            target_url = f"{self.vcf_url}/v1/releases/domains/{self.domain_id}"
            patch_data = {"targetVersion": self.target_version}
            
            async with session.patch(target_url, headers=headers, json=patch_data, ssl=False) as resp:
                if resp.status in [200, 202]:
                    self.add_log(f"Successfully set target version to {self.target_version}", "success")
                    return True
                elif resp.status == 400:
                    error_text = await resp.text()
                    if "SAME_SOURCE_AND_TARGET_VCF_VERSION" in error_text:
                        self.add_log(f"Target version {self.target_version} is same as current version - this is expected for component-only updates", "warning")
                        return True  # Continue anyway for component updates
                    else:
                        self.add_log(f"Failed to set target version: {resp.status} - {error_text}", "error")
                        return False
                else:
                    error_text = await resp.text()
                    self.add_log(f"Failed to set target version: {resp.status} - {error_text}", "error")
                    return False
                    
        except Exception as e:
            self.add_log(f"Error setting target version: {str(e)}", "error")
            return False
    
    async def _run_prechecks(self) -> str:
        """Run upgrade prechecks. Returns: 'success', 'failed', or 'waiting_for_acknowledgment'."""
        try:
            self.add_log("Initializing upgrade prechecks", "info")
            self.update_status("initializing_prechecks")
            
            token = await self.get_current_token()
            if not token:
                self.add_log("Cannot get VCF token for prechecks", "error")
                return "failed"
            
            session = async_get_clientsession(self.hass)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            # Step 1: Get query ID and resources
            query_url = f"{self.vcf_url}/v1/system/check-sets/queries"
            query_data = {
                "checkSetType": "UPGRADE",
                "domains": [{
                    "domainId": self.domain_id
                }]
            }
            
            async with session.post(query_url, headers=headers, json=query_data, ssl=False) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    self.add_log(f"Failed to get precheck query: {resp.status} - {error_text}", "error")
                    return "failed"
                
                query_response = await resp.json()
                query_id = query_response.get("queryId")
                resources = query_response.get("resources", [])
                
                if not query_id:
                    self.add_log("No query ID received from precheck query", "error")
                    return "failed"
            
            self.add_log(f"Got precheck query ID: {query_id[:8]}...", "info")
            self.update_status("running_prechecks")
            
            # Step 2: Start prechecks
            checkset_url = f"{self.vcf_url}/v1/system/check-sets"
            checkset_data = {
                "queryId": query_id,
                "resources": [
                    {
                        "resourceId": resource.get("resourceId"),
                        "type": resource.get("resourceType"),
                        "targetVersion": self.target_version  # Use overall target version
                    } for resource in resources
                ],
                "targetVersion": self.target_version
            }
            
            async with session.post(checkset_url, headers=headers, json=checkset_data, ssl=False) as resp:
                if resp.status not in [200, 201, 202]:
                    error_text = await resp.text()
                    self.add_log(f"Failed to start prechecks: {resp.status} - {error_text}", "error")
                    return "failed"
                
                checkset_response = await resp.json()
                precheck_id = checkset_response.get("id")
                
                if not precheck_id:
                    self.add_log("No precheck process ID received", "error")
                    return "failed"
            
            self.add_log(f"Started precheck process: {precheck_id[:8]}...", "info")
            self.update_status("evaluating_prechecks", "40 minutes")
            
            # Step 3: Monitor prechecks with timeout
            return await self._monitor_prechecks(session, headers, precheck_id)
            
        except Exception as e:
            self.add_log(f"Precheck phase failed: {str(e)}", "error")
            return "failed"
    
    async def _monitor_prechecks(self, session, headers, precheck_id: str) -> str:
        """Monitor precheck progress with timeout."""
        try:
            start_time = datetime.now()
            check_url = f"{self.vcf_url}/v1/system/check-sets/{precheck_id}"
            
            while (datetime.now() - start_time) < self.precheck_timeout:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                async with session.get(check_url, headers=headers, ssl=False) as resp:
                    if resp.status != 200:
                        self.add_log(f"Failed to check precheck status: {resp.status}", "error")
                        return "failed"
                    
                    check_response = await resp.json()
                    
                    # Handle different status field names based on VCF API response
                    status = check_response.get("status") or check_response.get("executionStatus")
                    progress = check_response.get("discoveryProgress", {}).get("percentageComplete", 0)
                    
                    self.add_log(f"Precheck progress: {progress}%", "info")
                    
                    if status in ["COMPLETED_WITH_SUCCESS", "COMPLETED"]:
                        self.add_log("Prechecks completed successfully", "success")
                        return await self._process_precheck_results(check_response)
                    elif status in ["COMPLETED_WITH_FAILURE", "FAILED"]:
                        self.add_log("Prechecks completed with failures", "error")
                        return await self._process_precheck_results(check_response)
                    elif status in ["IN_PROGRESS"]:
                        # Continue monitoring
                        continue
                    else:
                        # For unknown status, log and continue monitoring if within timeout
                        self.add_log(f"Precheck status: {status} (progress: {progress}%)", "info")
                        continue
            
            # Timeout reached
            self.add_log("Precheck timeout reached (40 minutes)", "error")
            return "failed"
            
        except Exception as e:
            self.add_log(f"Error monitoring prechecks: {str(e)}", "error")
            return "failed"
    
    async def _process_precheck_results(self, check_response: Dict) -> str:
        """Process precheck results and determine next action."""
        try:
            self.update_status("prechecks_done")
            
            # Extract errors and warnings from response
            errors = []
            warnings = []
            
            # Handle VCF API response structure based on test results
            # Check for validation domain summary
            domain_summaries = check_response.get("presentedArtifactsMap", {}).get("validation-domain-summary", [])
            for summary in domain_summaries:
                domain_name = summary.get("domainName", "Unknown")
                critical_gaps = summary.get("criticalGapsCount", 0)
                warning_gaps = summary.get("warningGapsCount", 0)
                error_validations = summary.get("errorValidationsCount", 0)
                
                if critical_gaps > 0 or error_validations > 0:
                    errors.append(f"Domain {domain_name}: {critical_gaps} critical gaps, {error_validations} error validations")
                if warning_gaps > 0:
                    warnings.append(f"Domain {domain_name}: {warning_gaps} warning gaps")
            
            # Check validation results for detailed errors/warnings
            validation_result = check_response.get("validationResult", {})
            if validation_result:
                severity = validation_result.get("context", {}).get("severity")
                message = validation_result.get("message", "")
                
                if severity == "ERROR":
                    errors.append(message)
                elif severity == "WARNING":
                    warnings.append(message)
                    
                # Process nested errors
                nested_errors = validation_result.get("nestedErrors", [])
                for nested_error in nested_errors:
                    nested_severity = nested_error.get("context", {}).get("severity")
                    nested_message = nested_error.get("message", "")
                    validation_name = nested_error.get("context", {}).get("validationName", "")
                    
                    if nested_severity == "ERROR":
                        error_msg = f"{validation_name}: {nested_message}" if validation_name else nested_message
                        errors.append(error_msg)
                    elif nested_severity == "WARNING":
                        warning_msg = f"{validation_name}: {nested_message}" if validation_name else nested_message
                        warnings.append(warning_msg)
            
            # Add results to logs
            if errors:
                self.add_log("**Precheck Errors:**", "error")
                for error in errors:
                    self.add_log(f"- {error}", "error")
            
            if warnings:
                self.add_log("**Precheck Warnings:**", "warning")
                for warning in warnings:
                    self.add_log(f"- {warning}", "warning")
            
            if not errors and not warnings:
                self.add_log("All prechecks passed successfully", "success")
                return "success"
            
            # If there are errors, always fail
            if errors:
                self.add_log("Cannot proceed due to precheck errors", "error")
                return "failed"
            
            # If only warnings, check ignore alerts setting
            if warnings:
                ignore_alerts = await self._check_ignore_alerts_setting()
                if ignore_alerts:
                    self.add_log("Warnings detected but ignore alerts is enabled - continuing", "warning")
                    return "success"
                else:
                    self.add_log("Warnings detected - waiting for alert acknowledgment", "warning")
                    self.update_status("waiting_for_alert_acknowledgement")
                    return "waiting_for_acknowledgment"
            
            return "success"
            
        except Exception as e:
            self.add_log(f"Error processing precheck results: {str(e)}", "error")
            return "failed"
    
    async def _check_ignore_alerts_setting(self) -> bool:
        """Check if the ignore alerts switch is enabled."""
        try:
            # Get the switch entity state from Home Assistant
            entity_id = f"switch.vcf_{self.domain_prefix}_{self.domain_name.lower().replace(' ', '_').replace('-', '_')}_ignore_alerts"
            state = self.hass.states.get(entity_id)
            
            if state and state.state == "on":
                return True
            return False
            
        except Exception as e:
            _LOGGER.error(f"Error checking ignore alerts setting: {e}")
            return False
    
    async def acknowledge_alerts(self):
        """Handle alert acknowledgment."""
        try:
            self.add_log("Alerts were acknowledged. Continuing with upgrade.", "info")
            self.update_status("alerts_were_acknowledged")
            
            # Continue with upgrade process
            if not await self._execute_upgrades():
                return False
            
            if not await self._final_validation():
                return False
            
            self.add_log("Upgrade process completed successfully after alert acknowledgment!", "success")
            self.update_status("successfully_completed")
            
            # Reset to default after brief success display
            await asyncio.sleep(10)
            self.update_status("waiting_for_initiation")
            self.logs = "## No Messages\n\nNo upgrade process has been initiated."
            
            return True
            
        except Exception as e:
            self.add_log(f"Error during alert acknowledgment continuation: {str(e)}", "error")
            self.update_status("failed")
            return False
    
    async def _execute_upgrades(self) -> bool:
        """Execute component upgrades."""
        try:
            self.add_log("Starting component upgrades", "info")
            self.update_status("starting_upgrades")
            
            token = await self.get_current_token()
            if not token:
                self.add_log("Cannot get VCF token for upgrades", "error")
                return False
            
            session = async_get_clientsession(self.hass)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            # Get upgradable components
            upgradables_url = f"{self.vcf_url}/v1/upgradables/domains/{self.domain_id}/?targetVersion={self.target_version}"
            
            async with session.get(upgradables_url, headers=headers, ssl=False) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    self.add_log(f"Failed to get upgradable components: {resp.status} - {error_text}", "error")
                    return False
                
                upgradables_response = await resp.json()
                upgradable_resources = upgradables_response.get("elements", [])
            
            if not upgradable_resources:
                self.add_log("No upgradable components found", "warning")
                return True
            
            # Separate SDDC Manager from other components
            sddc_manager_resource = None
            other_resources = []
            
            for resource in upgradable_resources:
                if resource.get("status") == "AVAILABLE":
                    resource_type = resource.get("type", "").upper()
                    if "SDDC" in resource_type or "MANAGER" in resource_type:
                        sddc_manager_resource = resource
                    else:
                        other_resources.append(resource)
            
            # Upgrade SDDC Manager first if needed
            if sddc_manager_resource:
                self.add_log("Upgrading SDDC Manager first - API will be unavailable during this process", "warning")
                if not await self._upgrade_component(session, headers, sddc_manager_resource, is_sddc_manager=True):
                    return False
            
            # Upgrade other components
            for resource in other_resources:
                if not await self._upgrade_component(session, headers, resource):
                    return False
            
            self.add_log("All component upgrades completed successfully", "success")
            return True
            
        except Exception as e:
            self.add_log(f"Upgrade execution failed: {str(e)}", "error")
            return False

    async def _upgrade_component(self, session, headers, resource: Dict, is_sddc_manager: bool = False) -> bool:
        """Upgrade a single component."""
        try:
            resource_id = resource.get("id")
            resource_type = resource.get("type", "Unknown")
            self.add_log(f"Starting upgrade for {resource_type} (ID: {resource_id})", "info")
            
            # Start the upgrade
            upgrade_url = f"{self.vcf_url}/v1/upgrades"
            upgrade_data = {
                "resources": [resource]
            }
            
            async with session.post(upgrade_url, headers=headers, json=upgrade_data, ssl=False) as resp:
                if resp.status not in [200, 201, 202]:
                    error_text = await resp.text()
                    self.add_log(f"Failed to start upgrade for {resource_type}: {resp.status} - {error_text}", "error")
                    return False
                
                upgrade_response = await resp.json()
                upgrade_id = upgrade_response.get("id")
                
                if not upgrade_id:
                    self.add_log(f"No upgrade ID received for {resource_type}", "error")
                    return False
            
            self.add_log(f"Started upgrade for {resource_type}: {upgrade_id[:8]}...", "info")
            
            # Monitor the upgrade with appropriate timeout
            timeout_hours = 3  # Default timeout
            if is_sddc_manager:
                timeout_hours = 4  # Longer timeout for SDDC Manager
                return await self._monitor_sddc_manager_upgrade(session, upgrade_id, resource_type, timeout_hours)
            else:
                return await self._monitor_component_upgrade(session, headers, upgrade_id, resource_type, timeout_hours)
            
        except Exception as e:
            self.add_log(f"Error upgrading component {resource_type}: {str(e)}", "error")
            return False

    async def _monitor_sddc_manager_upgrade(self, session, upgrade_id: str, resource_type: str, timeout_hours: int) -> bool:
        """Monitor SDDC Manager upgrade with special handling for API unavailability."""
        try:
            start_time = datetime.now()
            timeout = timedelta(hours=timeout_hours)
            check_interval = 60  # Check every minute initially
            
            self.add_log(f"Monitoring {resource_type} upgrade (will be unavailable during upgrade)", "info")
            
            # Initial monitoring before API becomes unavailable
            initial_monitoring_time = timedelta(minutes=10)  # Monitor for 10 minutes initially
            
            while (datetime.now() - start_time) < initial_monitoring_time:
                await asyncio.sleep(check_interval)
                
                try:
                    # Try to get current token (will fail when API becomes unavailable)
                    token = await self.get_current_token()
                    if not token:
                        break
                    
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    }
                    
                    upgrade_url = f"{self.vcf_url}/v1/upgrades/{upgrade_id}"
                    async with session.get(upgrade_url, headers=headers, ssl=False) as resp:
                        if resp.status == 200:
                            upgrade_response = await resp.json()
                            status = upgrade_response.get("status", "UNKNOWN")
                            
                            if status in ["COMPLETED", "SUCCESSFUL"]:
                                self.add_log(f"{resource_type} upgrade completed successfully", "success")
                                return True
                            elif status in ["FAILED", "CANCELLED"]:
                                self.add_log(f"{resource_type} upgrade failed: {status}", "error")
                                return False
                            
                            self.add_log(f"{resource_type} upgrade status: {status}", "info")
                        else:
                            # API is becoming unavailable
                            break
                            
                except Exception:
                    # API is now unavailable, break and wait for recovery
                    break
            
            # API is now unavailable during SDDC Manager upgrade
            self.add_log(f"API is now unavailable during {resource_type} upgrade - waiting for recovery", "warning")
            
            # Wait for API to become available again
            return await self._wait_for_api_recovery(session, start_time, timeout)
            
        except Exception as e:
            self.add_log(f"Error monitoring {resource_type} upgrade: {str(e)}", "error")
            return False

    async def _wait_for_api_recovery(self, session, start_time: datetime, timeout: timedelta) -> bool:
        """Wait for API to recover after SDDC Manager upgrade."""
        try:
            recovery_check_interval = 120  # Check every 2 minutes during recovery
            
            self.add_log("Waiting for API to recover after SDDC Manager upgrade...", "info")
            
            while (datetime.now() - start_time) < timeout:
                await asyncio.sleep(recovery_check_interval)
                
                try:
                    # Try to access the domains endpoint to check if API is back
                    domains_url = f"{self.vcf_url}/v1/domains"
                    
                    # Try without auth first to see if API is responding
                    async with session.get(domains_url, ssl=False, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status in [200, 401]:  # 401 means API is responding but needs auth
                            self.add_log("API is responding again - waiting additional 5 minutes for stability", "info")
                            await asyncio.sleep(300)  # Wait additional 5 minutes
                            
                            # Now check with proper authentication
                            token = await self.get_current_token()
                            if token:
                                headers = {
                                    "Authorization": f"Bearer {token}",
                                    "Accept": "application/json"
                                }
                                
                                async with session.get(domains_url, headers=headers, ssl=False) as auth_resp:
                                    if auth_resp.status == 200:
                                        self.add_log("API fully recovered and authenticated successfully", "success")
                                        return True
                                    else:
                                        self.add_log("API responding but authentication failed - continuing to wait", "warning")
                            else:
                                self.add_log("API responding but token refresh failed - continuing to wait", "warning")
                        
                except Exception as e:
                    # API still not available, continue waiting
                    elapsed = datetime.now() - start_time
                    remaining = timeout - elapsed
                    self.add_log(f"API still unavailable - {remaining.total_seconds()/60:.1f} minutes remaining", "info")
                    continue
            
            # Timeout reached
            self.add_log("Timeout waiting for API recovery after SDDC Manager upgrade", "error")
            return False
            
        except Exception as e:
            self.add_log(f"Error waiting for API recovery: {str(e)}", "error")
            return False

    async def _monitor_component_upgrade(self, session, headers, upgrade_id: str, resource_type: str, timeout_hours: int) -> bool:
        """Monitor regular component upgrade."""
        try:
            start_time = datetime.now()
            timeout = timedelta(hours=timeout_hours)
            check_interval = 60  # Check every minute
            
            upgrade_url = f"{self.vcf_url}/v1/upgrades/{upgrade_id}"
            
            while (datetime.now() - start_time) < timeout:
                await asyncio.sleep(check_interval)
                
                async with session.get(upgrade_url, headers=headers, ssl=False) as resp:
                    if resp.status != 200:
                        self.add_log(f"Failed to check {resource_type} upgrade status: {resp.status}", "warning")
                        continue
                    
                    upgrade_response = await resp.json()
                    status = upgrade_response.get("status", "UNKNOWN")
                    
                    if status in ["COMPLETED", "SUCCESSFUL"]:
                        self.add_log(f"{resource_type} upgrade completed successfully", "success")
                        return True
                    elif status in ["FAILED", "CANCELLED"]:
                        self.add_log(f"{resource_type} upgrade failed: {status}", "error")
                        return False
                    elif status == "IN_PROGRESS":
                        progress = upgrade_response.get("progress", {}).get("percentageComplete", 0)
                        self.add_log(f"{resource_type} upgrade progress: {progress}%", "info")
                    else:
                        self.add_log(f"{resource_type} upgrade status: {status}", "info")
            
            # Timeout reached
            self.add_log(f"{resource_type} upgrade timeout reached ({timeout_hours} hours)", "error")
            return False
            
        except Exception as e:
            self.add_log(f"Error monitoring {resource_type} upgrade: {str(e)}", "error")
            return False
    
    async def _final_validation(self) -> bool:
        """Run final validation."""
        try:
            self.add_log("Running final validation", "info")
            
            token = await self.get_current_token()
            if not token:
                self.add_log("Cannot get VCF token for final validation", "error")
                return False
            
            session = async_get_clientsession(self.hass)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            validation_url = f"{self.vcf_url}/v1/releases/domains/{self.domain_id}/validations"
            validation_data = {"targetVersion": self.target_version}
            
            async with session.post(validation_url, headers=headers, json=validation_data, ssl=False) as resp:
                if resp.status in [200, 201, 202]:
                    validation_response = await resp.json()
                    execution_status = validation_response.get("executionStatus")
                    
                    if execution_status == "COMPLETED":
                        self.add_log("Final validation completed successfully", "success")
                        return True
                    else:
                        self.add_log(f"Final validation status: {execution_status}", "info")
                        return True  # Continue anyway as validation was started
                elif resp.status == 400:
                    error_text = await resp.text()
                    if "SAME_SOURCE_AND_TARGET_VCF_VERSION" in error_text:
                        self.add_log("Final validation skipped - same version scenario", "warning")
                        return True  # Skip validation for same-version scenarios
                    else:
                        self.add_log(f"Final validation failed: {resp.status} - {error_text}", "error")
                        return False
                else:
                    error_text = await resp.text()
                    self.add_log(f"Final validation failed: {resp.status} - {error_text}", "error")
                    return False
                    
        except Exception as e:
            self.add_log(f"Final validation failed: {str(e)}", "error")
            return False
