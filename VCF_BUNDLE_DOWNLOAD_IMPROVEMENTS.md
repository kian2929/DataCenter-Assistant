# VCF Bundle Download Improvements

## Overview
Enhanced the bundle download process in the VCF upgrade workflow with proper data structure and pre-download checks to avoid unnecessary API calls and errors.

## Changes Made

### 1. Fixed Bundle Download Data Structure

**Before:**
```python
download_data = {"downloadNow": True}
```

**After:**
```python
download_data = {
    "bundleDownloadSpec": {
        "downloadNow": True
    }
}
```

**Why:** The VCF API expects the download specification to be nested under `bundleDownloadSpec` as per the official API documentation.

### 2. Added Pre-Download Bundle Status Check

**New Logic:**
1. Before attempting to download each bundle, check its current status via `GET /v1/bundles/{bundleId}`
2. If `downloadStatus` is already `"SUCCESSFUL"`, skip the download and increment the counter
3. Only attempt download for bundles that haven't been downloaded yet

**Benefits:**
- Avoids server errors when trying to download already-downloaded bundles
- Reduces unnecessary API calls
- Provides better progress reporting
- Handles edge cases where downloads were completed in previous runs

### 3. Enhanced Error Handling

**New Error Handling:**
```python
try:
    await self.vcf_client.api_request(f"/v1/bundles/{bundle_id}", method="PATCH", data=download_data)
except Exception as e:
    # If bundle is already downloaded or download request fails, check status
    bundle_status = await self.vcf_client.api_request(f"/v1/bundles/{bundle_id}")
    current_download_status = bundle_status.get("downloadStatus")
    if current_download_status == "SUCCESSFUL":
        # Bundle was already downloaded, continue
        downloaded += 1
        continue
    else:
        # Actual error, re-raise
        raise Exception(f"Failed to start download for bundle {bundle_id}: {e}")
```

**Benefits:**
- Graceful handling of "already downloaded" scenarios
- Distinguishes between real errors and benign status conflicts
- Provides specific error messages for debugging

### 4. Improved Logging and Progress Reporting

**Added Debug Logging:**
- Log total number of bundles found
- Log status check for each bundle
- Log when bundles are skipped due to already being downloaded
- Log when starting downloads for bundles

**Enhanced Progress Messages:**
- Different messages for already-downloaded vs newly-downloaded bundles
- More descriptive progress reporting in the upgrade logs

## Code Location
File: `custom_components/datacenter_assistant/upgrade_service.py`
Method: `_download_bundles()`

## API Endpoints Used
- `GET /v1/bundles/{bundleId}` - Check bundle download status
- `PATCH /v1/bundles/{bundleId}` - Start bundle download with proper data structure

## Expected Behavior
1. **First Run:** Checks all bundles, downloads those not yet downloaded
2. **Subsequent Runs:** Quickly skips already-downloaded bundles, only downloads new ones
3. **Error Scenarios:** Properly handles and reports actual download failures vs status conflicts
4. **Progress Reporting:** Accurate count and status for both skipped and downloaded bundles

## Testing Scenarios
- ✅ Fresh upgrade (no bundles downloaded)
- ✅ Resumed upgrade (some bundles already downloaded)
- ✅ Retry after failure (bundles may be in various states)
- ✅ All bundles already downloaded (should skip all and proceed)

## Compatibility
- Compatible with VCF API versions that support the bundle download specification
- Backward compatible with existing upgrade workflows
- No breaking changes to the external interface
