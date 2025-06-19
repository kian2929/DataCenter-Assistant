# VCF Pre-Check Enhanced Logging

## Overview
Significantly enhanced the logging in the VCF pre-check process to provide comprehensive visibility into each step of the pre-check workflow, making it much easier to troubleshoot issues and understand what's happening during this critical phase.

## Enhanced Logging Areas

### 1. Pre-Check Workflow Overview
- **Phase Tracking**: Clear start/end logging for each of the 4 main steps
- **Target Version**: Logs the target version being checked
- **Exception Handling**: Detailed error context when pre-checks fail

### 2. Step 1: Initial Check-Sets Query
- **Request Details**: Logs the initial query data being sent
- **Response Analysis**: Shows the raw response and resource count
- **Resource Discovery**: Details each resource found with type, ID, and name
- **Processing Summary**: Shows how many valid resources were processed

### 3. Step 2: BOM (Bill of Materials) Processing
- **BOM Analysis**: Shows number of BOM entries found
- **Component Mapping**: Details each component and its target version
- **Resource Mapping**: Shows which resources map to which target versions
- **Missing Mappings**: Warns when resources don't have target versions

### 4. Step 3: Detailed Check-Sets Query
- **Query Structure**: Logs the detailed query being sent with resources and versions
- **Response Analysis**: Shows response structure and query ID
- **Resource Processing**: Details each resource and its check sets

### 5. Step 4: Check-Sets Execution and Monitoring
- **Execution Details**: Shows the final check-set data structure being executed
- **Run ID Tracking**: Logs the pre-check run ID for reference
- **Status Monitoring**: Numbered status checks with current status and progress
- **Results Processing**: Detailed analysis of validation results

## New Log Messages

### Phase and Step Tracking
- `Domain {id}: Starting pre-checks for target version {version}`
- `Domain {id}: Step 1 - Getting available check-sets`
- `Domain {id}: Step 2 - Processing BOM (Bill of Materials)`
- `Domain {id}: Step 3 - Getting detailed check-sets`
- `Domain {id}: Step 4 - Preparing check-sets for execution`

### Resource Discovery and Processing
- `Domain {id}: Found {n} resources in initial response`
- `Domain {id}: Resource {n} - Type: {type}, ID: {id}, Name: {name}`
- `Domain {id}: Processed {n} valid resources`

### BOM Processing
- `Domain {id}: Found {n} BOM entries`
- `Domain {id}: BOM {n} - Component: {name}, Version: {version}`
- `Domain {id}: Created BOM mapping for {n} components: {list}`
- `Domain {id}: Mapped {type} to version {version}`
- `Domain {id}: No target version found for resource type {type}` (WARNING)

### Check-Sets Preparation
- `Domain {id}: Processing resource {n} - Type: {type}, ID: {id}, Name: {name}`
- `Domain {id}: Resource {type} has {n} check sets`
- `Domain {id}: Check set {n} for {type} - ID: {id}, Name: {name}`
- `Domain {id}: Added {n} check sets for resource {type}`
- `Domain {id}: Prepared check-sets for {n} resources`

### Execution and Monitoring
- `Domain {id}: Pre-checks started with run ID: {id}`
- `Domain {id}: Pre-check status check #{n}`
- `Domain {id}: Pre-check status: {status}`
- `Domain {id}: Pre-check progress: {progress}`
- `Domain {id}: Pre-checks completed successfully`

### Results Analysis
- `Domain {id}: Processing pre-check results`
- `Domain {id}: Assessment output keys: {keys}`
- `Domain {id}: Validation data: {data}`
- `Domain {id}: Pre-check results - Errors: {n}, Warnings: {n}`

### Acknowledgement Handling
- `Domain {id}: Pre-checks completed with issues - Errors: {n}, Warnings: {n}`
- `Domain {id}: Waiting for user acknowledgement of pre-check issues`
- `Domain {id}: Still waiting for acknowledgement ({n} seconds)`
- `Domain {id}: User acknowledged pre-check issues, continuing with upgrade`

## Log Levels Used

### DEBUG
- Raw API request/response data
- Detailed data structure contents
- Step-by-step processing details
- Acknowledgement wait status

### INFO
- Phase and step transitions
- Resource counts and summaries
- Component mappings
- Status updates and completion
- Final results summary

### WARNING
- Missing target version mappings
- Unexpected response formats
- Pre-check issues requiring acknowledgement

### ERROR
- Pre-check failures
- API errors
- Exception details

## Benefits

### 1. Troubleshooting
- **Pinpoint Issues**: Identify exactly which step fails and why
- **Resource Problems**: See which resources are missing or misconfigured
- **API Issues**: Detect API response format problems
- **Mapping Failures**: Identify BOM mapping issues

### 2. Process Understanding
- **Resource Discovery**: See what resources VCF finds for pre-checks
- **Check Set Details**: Understand what checks will be performed
- **Progress Tracking**: Monitor pre-check execution in real-time
- **Results Analysis**: Understand validation results structure

### 3. Performance Monitoring
- **Step Timing**: See how long each step takes
- **Resource Counts**: Track resource and check set quantities
- **Status Frequency**: Monitor how often status checks occur

### 4. Integration Support
- **Run ID Tracking**: Reference pre-check runs in VCF UI
- **URL Generation**: Direct links to detailed results
- **Acknowledgement Flow**: Track user interaction requirements

## Example Enhanced Log Flow

```
2025-06-20 12:00:00 INFO Domain abc123: Starting pre-checks for target version 5.2.1.0
2025-06-20 12:00:01 INFO Domain abc123: Found 4 resources in initial response
2025-06-20 12:00:01 INFO Domain abc123: Resource 1 - Type: SDDC_MANAGER, ID: xyz789, Name: sddc-manager-01
2025-06-20 12:00:01 INFO Domain abc123: Resource 2 - Type: VCENTER, ID: def456, Name: vcenter-01
2025-06-20 12:00:02 INFO Domain abc123: Found 8 BOM entries
2025-06-20 12:00:02 INFO Domain abc123: Mapped SDDC_MANAGER to version 5.2.1.0-12345
2025-06-20 12:00:03 INFO Domain abc123: Got query ID: query-789
2025-06-20 12:00:04 INFO Domain abc123: Pre-checks started with run ID: run-456
2025-06-20 12:00:05 INFO Domain abc123: Pre-check status: IN_PROGRESS
2025-06-20 12:02:35 INFO Domain abc123: Pre-checks completed successfully
2025-06-20 12:02:36 INFO Domain abc123: Pre-check results - Errors: 0, Warnings: 2
2025-06-20 12:02:36 INFO Domain abc123: Waiting for user acknowledgement of pre-check issues
```

This enhanced logging makes the pre-check process completely transparent and much easier to debug when issues occur.
