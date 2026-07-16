#!/bin/bash

# BDA Cleanup Script - Comprehensive cleanup for AWS resources and local build artifacts
# Usage: ./cleanup.sh [--environment ENV] [--profile PROFILE] [--local-only]
#
# Modes:
#   Default: Full AWS teardown + local cleanup
#   --local-only: Local cleanup only (no AWS changes, ~900 MB freed)

set -e

# Default values
ENVIRONMENT="Dev"
AWS_PROFILE="default"
LOCAL_ONLY=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --profile)
            AWS_PROFILE="$2"
            shift 2
            ;;
        --local-only)
            LOCAL_ONLY=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "OPTIONS:"
            echo "  --environment ENV      Environment to clean up (default: Dev)"
            echo "  --profile PROFILE      AWS profile to use (default: default)"
            echo "  --local-only           Clean only local build artifacts, no AWS changes"
            echo "                         Removes: .venv, node_modules, dist, cdk.out (~900 MB)"
            echo "  --help                 Show this help message"
            echo ""
            echo "MODES:"
            echo "  Default (no --local-only):"
            echo "    - Destroys ALL CDK-managed AWS resources for the environment"
            echo "    - Cleans up local build artifacts"
            echo "    - Requires AWS profile and environment"
            echo ""
            echo "  Local-only mode (--local-only):"
            echo "    - Cleans only local files (no AWS operations)"
            echo "    - Removes .venv/ (~452 MB), node_modules/ (~446 MB), and build artifacts"
            echo "    - Safe: Does not touch AWS resources"
            echo "    - Does not require AWS credentials"
            echo ""
            echo "EXAMPLES:"
            echo "  $0 --local-only                              # Clean local files only (~900 MB freed)"
            echo "  $0 --environment Dev --profile GenAI         # Full AWS + local cleanup"
            echo ""
            echo "NOTE: Resources NOT managed by CDK will be preserved."
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Helper function to get directory size
get_size() {
    if [ -d "$1" ]; then
        du -sh "$1" 2>/dev/null | cut -f1
    else
        echo "0B"
    fi
}

# Display appropriate header based on mode
if [ "$LOCAL_ONLY" = true ]; then
    echo "🧹 BDA Local Cleanup Script"
    echo "==========================="
    echo "Mode: Local files only (no AWS changes)"
    echo ""

    # Show initial size
    INITIAL_SIZE=$(du -sh . 2>/dev/null | cut -f1)
    echo "Current project size: $INITIAL_SIZE"
    echo ""
    echo "⚠️  This will remove all local build artifacts and dependencies:"
    echo "   - Python virtual environment (.venv/) ~452 MB"
    echo "   - Node modules (node_modules/) ~446 MB"
    echo "   - Build artifacts (dist/, cdk.out/) ~3 MB"
    echo "   - Cache files (__pycache__, .pytest_cache)"
    echo ""
    echo "💡 AWS resources will NOT be touched."
    echo ""

    # Confirm with user
    read -p "Continue with local cleanup? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cleanup cancelled"
        exit 0
    fi
else
    echo "🚀 BDA Full Cleanup Script"
    echo "=========================="
    echo "Mode: AWS teardown + Local cleanup"
    echo "Environment: $ENVIRONMENT"
    echo "AWS Profile: $AWS_PROFILE"
    echo ""
    echo "⚠️  This will:"
    echo "   1. Destroy ALL CDK-managed AWS resources for this deployment"
    echo "   2. Clean up local build artifacts (~900 MB)"
    echo ""
    echo "💡 Resources NOT managed by CDK will be preserved."
    echo ""

    # Confirm with user
    read -p "Continue with full cleanup (AWS + local)? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cleanup cancelled"
        exit 0
    fi
fi

# Function to cleanup AgentCore runtimes created by this deployment
cleanup_agentcore_runtimes() {
    echo "🤖 Cleaning up AgentCore runtimes..."
    
    local runtime_config_file="agentcore/runtime_config.json"
    
    if [ ! -f "$runtime_config_file" ]; then
        echo "   No runtime_config.json found - skipping AgentCore cleanup"
        return 0
    fi
    
    # Check if jq is available
    if ! command -v jq &> /dev/null; then
        echo "   ⚠️  jq not found - skipping AgentCore cleanup"
        echo "   Install jq to enable AgentCore runtime cleanup"
        return 0
    fi
    
    # Check if bedrock-agentcore-control is available
    if ! aws bedrock-agentcore-control help --profile "$AWS_PROFILE" >/dev/null 2>&1; then
        echo "   ⚠️  bedrock-agentcore-control not available - skipping AgentCore cleanup"
        return 0
    fi
    
    # Read runtime IDs from config file
    local runtime_ids=$(jq -r '.runtime_ids | to_entries[] | "\(.key) \(.value)"' "$runtime_config_file" 2>/dev/null || echo "")
    
    if [ -z "$runtime_ids" ]; then
        echo "   No runtime IDs found in config file"
        return 0
    fi
    
    echo "   Found AgentCore runtimes created by this deployment:"
    
    # Delete each runtime
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            local agent_name=$(echo "$line" | cut -d' ' -f1)
            local runtime_id=$(echo "$line" | cut -d' ' -f2)
            
            echo "   🗑️  Deleting runtime: $agent_name ($runtime_id)"
            
            aws bedrock-agentcore-control delete-agent-runtime \
                --agent-runtime-id "$runtime_id" \
                --profile "$AWS_PROFILE" >/dev/null 2>&1 || echo "     ⚠️  Failed to delete $runtime_id (may already be deleted)"
        fi
    done <<< "$runtime_ids"
    
    # Clear the runtime config file
    echo "{}" > "$runtime_config_file"
    echo "   ✅ AgentCore runtimes cleanup completed"
}

# Function to prepare CDK environment
prepare_cdk_environment() {
    echo "🔧 Preparing CDK environment..."
    
    # Create missing lambda layer directories if they don't exist
    # CDK needs these to synthesize stacks before destroying
    if [ ! -d "lambda_layers/api-deps" ]; then
        echo "   Creating missing lambda_layers/api-deps directory..."
        mkdir -p lambda_layers/api-deps
    fi
    
    if [ ! -d "lambda_layers/python-deps" ]; then
        echo "   Creating missing lambda_layers/python-deps directory..."
        mkdir -p lambda_layers/python-deps
    fi
    
    echo "   ✅ CDK environment prepared"
}

# Function to destroy CDK stacks
destroy_cdk_stacks() {
    echo "☁️  Destroying CDK stacks..."

    # Set AWS profile for CDK
    export AWS_PROFILE="$AWS_PROFILE"

    # Check if any stacks exist for this environment in CloudFormation
    echo "   🔍 Discovering stacks for environment: $ENVIRONMENT..."
    local stacks=$(aws cloudformation list-stacks \
        --profile "$AWS_PROFILE" \
        --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE ROLLBACK_COMPLETE \
        --query "StackSummaries[?contains(StackName, 'BDA-') && contains(StackName, '-${ENVIRONMENT}')].StackName" \
        --output text 2>/dev/null | tr '\t' '\n' | grep -v '^$' || echo "")

    if [ -z "$stacks" ]; then
        echo "   📭 No stacks found for environment: $ENVIRONMENT"
        return 0
    fi

    local stack_count=$(echo "$stacks" | wc -l | tr -d ' ')
    echo "   📋 Found $stack_count stacks to destroy:"
    while IFS= read -r stack; do
        echo "     - $stack"
    done <<< "$stacks"
    echo ""

    # Activate Python environment for CDK
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    else
        echo "   ⚠️  Warning: Python virtual environment not found"
        echo "   💡 CDK destroy may fail without dependencies"
        echo "   💡 Run './deploy.sh' first to create the environment, then cleanup"
    fi

    # Show estimated time warning
    echo "   ⏱️  Stack destruction typically takes 3-8 minutes per stack"
    echo "   📊 Estimated total time: $((stack_count * 4)) minutes (may vary)"
    echo "   🔄 Progress will be shown in real-time below..."
    echo ""

    # Destroy using CDK (which handles dependencies correctly)
    echo "   🗑️  Starting CDK stack destruction..."
    echo "   📝 CDK Output:"
    echo "   ============================================================"

    # Use verbose CDK output and capture both stdout and stderr
    if cdk destroy --all --force --verbose --profile "$AWS_PROFILE" --context Environment="$ENVIRONMENT" 2>&1 | while IFS= read -r line; do
        # Add timestamp and indent to CDK output
        echo "   $(date '+%H:%M:%S') | $line"

        # Show key progress indicators
        if echo "$line" | grep -q "DELETE_IN_PROGRESS"; then
            echo "   🔄 Resource deletion in progress..."
        elif echo "$line" | grep -q "DELETE_COMPLETE"; then
            echo "   ✅ Resource deleted successfully"
        elif echo "$line" | grep -q "Stack.*DELETE_COMPLETE"; then
            echo "   🎉 Stack deletion completed!"
        elif echo "$line" | grep -q "DELETE_FAILED"; then
            echo "   ⚠️  Resource deletion failed (will retry)"
        fi
    done; then
        echo "   ============================================================"
        echo "   ✅ CDK stacks destruction completed successfully"
        deactivate 2>/dev/null || true
    else
        echo "   ============================================================"
        echo "   ❌ CDK stacks destruction failed"
        echo "   💡 Check the output above for specific error details"
        deactivate 2>/dev/null || true
        return 1
    fi
}

# Function to cleanup CloudWatch logs created by CDK for this environment
cleanup_cloudwatch_logs() {
    echo "📋 Cleaning up CloudWatch logs..."
    echo "   ⚠️  Only deleting log groups for resources in this deployment's stacks"
    
    # Get deployed stacks for this environment
    local stacks=$(aws cloudformation list-stacks \
        --profile "$AWS_PROFILE" \
        --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE DELETE_COMPLETE UPDATE_ROLLBACK_COMPLETE ROLLBACK_COMPLETE \
        --query "StackSummaries[?contains(StackName, 'BDA-') && contains(StackName, '-${ENVIRONMENT}')].StackName" \
        --output text 2>/dev/null | tr '\t' '\n' | grep -v '^$' || echo "")
    
    if [ -z "$stacks" ]; then
        echo "   📭 No stacks found - skipping log cleanup"
        return 0
    fi
    
    # Extract Lambda function names from stack resources
    echo "   🔍 Finding Lambda functions in deployment stacks..."
    local lambda_functions=""
    while IFS= read -r stack; do
        if [ -n "$stack" ]; then
            local functions=$(aws cloudformation list-stack-resources \
                --stack-name "$stack" \
                --profile "$AWS_PROFILE" \
                --query "StackResourceSummaries[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" \
                --output text 2>/dev/null | tr '\t' '\n' || echo "")
            lambda_functions="${lambda_functions}${functions}"$'\n'
        fi
    done <<< "$stacks"
    
    # Delete log groups only for deployed Lambda functions
    if [ -n "$lambda_functions" ]; then
        echo "   Found Lambda functions from this deployment:"
        while IFS= read -r function_name; do
            if [ -n "$function_name" ]; then
                local log_group="/aws/lambda/${function_name}"
                echo "   🗑️  Deleting: $log_group"
                aws logs delete-log-group \
                    --log-group-name "$log_group" \
                    --profile "$AWS_PROFILE" >/dev/null 2>&1 || echo "     ⚠️  Failed (may not exist)"
            fi
        done <<< "$(echo "$lambda_functions" | grep -v '^$')"
    else
        echo "   No Lambda functions found"
    fi
    
    # Step Functions logs - use exact pattern matching
    local sfn_log_groups=$(aws logs describe-log-groups \
        --log-group-name-prefix "/aws/vendedlogs/states/BDA-" \
        --profile "$AWS_PROFILE" \
        --query "logGroups[?contains(logGroupName, '-${ENVIRONMENT}-')].logGroupName" \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$sfn_log_groups" ]; then
        echo "   Found Step Functions log groups:"
        for log_group in $sfn_log_groups; do
            echo "   🗑️  Deleting: $log_group"
            aws logs delete-log-group \
                --log-group-name "$log_group" \
                --profile "$AWS_PROFILE" >/dev/null 2>&1 || echo "     ⚠️  Failed (may not exist)"
        done
    fi
    
    echo "   ✅ CloudWatch logs cleanup completed"
}
}

# Function to cleanup local Lambda layer contents
cleanup_local_lambda_layers() {
    echo "📁 Cleaning up local Lambda layer contents..."
    echo "   📋 These are cached Python dependencies from previous builds"
    
    # Clean python-deps layer contents
    if [ -d "lambda_layers/python-deps/python" ]; then
        local py_deps_size=$(du -sh lambda_layers/python-deps/python 2>/dev/null | cut -f1 || echo "unknown")
        echo "   🗑️  Removing python-deps layer contents ($py_deps_size)..."
        rm -rf lambda_layers/python-deps/python
        echo "   ✅ Removed lambda_layers/python-deps/python"
    else
        echo "   📂 No python-deps layer contents found"
    fi
    
    # Clean api-deps layer contents
    if [ -d "lambda_layers/api-deps/python" ]; then
        local api_deps_size=$(du -sh lambda_layers/api-deps/python 2>/dev/null | cut -f1 || echo "unknown")
        echo "   🗑️  Removing api-deps layer contents ($api_deps_size)..."
        rm -rf lambda_layers/api-deps/python
        echo "   ✅ Removed lambda_layers/api-deps/python"
    else
        echo "   📂 No api-deps layer contents found"
    fi
    
    # Clean any __pycache__ directories
    local pycache_count=$(find lambda_layers/ -maxdepth 3 -type d -name "__pycache__" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$pycache_count" -gt 0 ]; then
        echo "   🗑️  Removing $pycache_count __pycache__ directories..."
        find lambda_layers/ -maxdepth 3 -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        echo "   ✅ Cleaned Python cache directories"
    else
        echo "   📂 No __pycache__ directories found"
    fi
    
    echo "   ✅ Local Lambda layer cleanup completed"
}

# Function to clean up CDK artifacts
cleanup_cdk_artifacts() {
    echo "🧹 Cleaning up CDK artifacts..."

    # Remove CDK output directory
    if [ -d "cdk.out" ]; then
        local file_count=$(find cdk.out -type f 2>/dev/null | wc -l | tr -d ' ')

        if [ "$file_count" -gt 1000 ]; then
            echo "   🗑️  Removing cdk.out directory ($file_count files)..."
            echo "   🕰️  Large directory detected, this may take a moment..."
        else
            echo "   🗑️  Removing cdk.out directory ($file_count files)..."
        fi

        # Use background process with monitoring for large directories
        if [ "$file_count" -gt 5000 ]; then
            # For very large directories, delete in background and show progress
            rm -rf cdk.out 2>/dev/null &
            local rm_pid=$!
            local dots=0

            while kill -0 $rm_pid 2>/dev/null; do
                echo -n "."
                sleep 1
                dots=$((dots + 1))
                if [ $dots -gt 60 ]; then
                    echo ""
                    echo "   ⚠️  Still removing files (this may take a while for large directories)..."
                    echo "   💡 Tip: Run 'rm -rf cdk.out' manually in another terminal if needed"
                    break
                fi
            done
            wait $rm_pid 2>/dev/null
            echo ""
            echo "   ✅ Removed cdk.out directory"
        else
            # For smaller directories, just remove normally
            rm -rf cdk.out 2>/dev/null
            echo "   ✅ Removed cdk.out directory"
        fi
    else
        echo "   📂 No cdk.out directory found"
    fi

    echo "   ✅ CDK artifacts cleanup completed"
}

# Function to cleanup UI build artifacts
cleanup_ui_artifacts() {
    echo "🎨 Cleaning up UI build artifacts..."

    # Clean UI dist directory
    if [ -d "bda-cloudscape-ui/dist" ]; then
        echo "   🗑️  Removing UI dist directory..."
        rm -rf bda-cloudscape-ui/dist
        echo "   ✅ Removed bda-cloudscape-ui/dist"
    fi
    
    # Clean UI .env file
    if [ -f "bda-cloudscape-ui/.env" ]; then
        echo "   🗑️  Removing UI .env file..."
        rm -f bda-cloudscape-ui/.env
        echo "   ✅ Removed bda-cloudscape-ui/.env"
    fi
    
    echo "   ✅ UI artifacts cleanup completed"
}

# Function to cleanup Python virtual environment
cleanup_python_venv() {
    echo "🐍 Cleaning up Python virtual environment..."

    if [ -d ".venv" ]; then
        SIZE=$(get_size ".venv")
        echo "   🗑️  Removing .venv/ - $SIZE"
        rm -rf .venv
        echo "   ✅ Removed .venv/"
    else
        echo "   📂 No .venv directory found"
    fi

    echo "   ✅ Python venv cleanup completed"
}

# Function to cleanup Node modules
cleanup_node_modules() {
    echo "📦 Cleaning up Node modules..."

    if [ -d "bda-cloudscape-ui/node_modules" ]; then
        SIZE=$(get_size "bda-cloudscape-ui/node_modules")
        echo "   🗑️  Removing bda-cloudscape-ui/node_modules/ - $SIZE"
        rm -rf bda-cloudscape-ui/node_modules
        echo "   ✅ Removed bda-cloudscape-ui/node_modules/"
    else
        echo "   📂 No node_modules directory found"
    fi

    echo "   ✅ Node modules cleanup completed"
}

# Function to cleanup CDK staging directory
cleanup_cdk_staging() {
    echo "🗄️  Cleaning up CDK staging..."

    if [ -d ".cdk.staging" ]; then
        SIZE=$(get_size ".cdk.staging")
        echo "   🗑️  Removing .cdk.staging/ - $SIZE"
        rm -rf .cdk.staging
        echo "   ✅ Removed .cdk.staging/"
    else
        echo "   📂 No .cdk.staging directory found"
    fi

    echo "   ✅ CDK staging cleanup completed"
}

# Function to cleanup all Python cache files (not just lambda_layers)
cleanup_all_python_cache() {
    echo "🧹 Cleaning up Python cache files..."

    echo "   🗑️  Removing __pycache__ directories..."
    local pycache_count=$(find . -type d -name "__pycache__" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$pycache_count" -gt 0 ]; then
        find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        echo "   ✅ Removed $pycache_count __pycache__ directories"
    else
        echo "   📂 No __pycache__ directories found"
    fi

    echo "   🗑️  Removing *.pyc files..."
    find . -type f -name "*.pyc" -delete 2>/dev/null || true

    echo "   🗑️  Removing *.pyo files..."
    find . -type f -name "*.pyo" -delete 2>/dev/null || true

    echo "   ✅ Python cache cleanup completed"
}

# Function to cleanup pytest cache
cleanup_pytest_cache() {
    echo "🧪 Cleaning up pytest cache..."

    local pytest_count=$(find . -type d -name ".pytest_cache" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$pytest_count" -gt 0 ]; then
        echo "   🗑️  Removing $pytest_count .pytest_cache directories..."
        find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
        echo "   ✅ Removed .pytest_cache directories"
    else
        echo "   📂 No .pytest_cache directories found"
    fi

    echo "   ✅ Pytest cache cleanup completed"
}

# Function to cleanup temporary files
cleanup_temp_files() {
    echo "🗑️  Cleaning up temporary files..."

    # Remove deployment log
    if [ -f "deployment.log" ]; then
        echo "   🗑️  Removing deployment.log..."
        rm -f deployment.log
    fi

    # Remove temporary files
    echo "   🗑️  Removing *.tmp files..."
    find . -type f -name "*.tmp" -delete 2>/dev/null || true

    echo "   🗑️  Removing *.bak files..."
    find . -type f -name "*.bak" -delete 2>/dev/null || true

    echo "   🗑️  Removing .DS_Store files..."
    find . -type f -name ".DS_Store" -delete 2>/dev/null || true

    echo "   ✅ Temporary files cleanup completed"
}

# Main cleanup process
main() {
    echo "🔄 Starting cleanup process..."
    echo ""

    if [ "$LOCAL_ONLY" = true ]; then
        # Local-only mode: Clean build artifacts, no AWS operations

        # Step 1: Python virtual environment
        cleanup_python_venv
        echo ""

        # Step 2: Node modules
        cleanup_node_modules
        echo ""

        # Step 3: UI build artifacts
        cleanup_ui_artifacts
        echo ""

        # Step 4: CDK artifacts
        cleanup_cdk_artifacts
        echo ""

        # Step 5: CDK staging
        cleanup_cdk_staging
        echo ""

        # Step 6: Lambda layer contents
        cleanup_local_lambda_layers
        echo ""

        # Step 7: Python cache files
        cleanup_all_python_cache
        echo ""

        # Step 8: Pytest cache
        cleanup_pytest_cache
        echo ""

        # Step 9: Temporary files
        cleanup_temp_files
        echo ""

        # Show final size
        FINAL_SIZE=$(du -sh . 2>/dev/null | cut -f1)
        echo "🎉 Local cleanup completed successfully!"
        echo ""
        echo "Summary:"
        echo "✅ Python virtual environment (.venv/) removed"
        echo "✅ Node modules (node_modules/) removed"
        echo "✅ Build artifacts (dist/, cdk.out/) cleaned"
        echo "✅ Cache files (__pycache__, .pytest_cache) removed"
        echo "✅ Temporary files cleaned"
        echo ""
        echo "📊 Project size:"
        echo "   Before: $INITIAL_SIZE"
        echo "   After:  $FINAL_SIZE"
        echo ""
        echo "💡 To restore build environment, run:"
        echo "   1. python3 -m venv .venv && source .venv/bin/activate"
        echo "   2. pip install -r requirements.txt"
        echo "   3. cd bda-cloudscape-ui && npm install"
        echo ""
        echo "   Or simply run: ./deploy.sh"

    else
        # Full mode: AWS teardown + local cleanup

        # Step 1: Prepare CDK environment (create missing directories)
        prepare_cdk_environment
        echo ""

        # Step 2: Clean up AgentCore runtimes created by this deployment
        cleanup_agentcore_runtimes
        echo ""

        # Step 3: Clean up CloudWatch logs (environment-specific)
        cleanup_cloudwatch_logs
        echo ""

        # Step 4: Destroy CDK stacks (this handles all CloudFormation resources including Frontend)
        # Note: This requires Python venv to be intact
        destroy_cdk_stacks
        echo ""

        # Step 5: Clean up local Lambda layer contents
        cleanup_local_lambda_layers
        echo ""

        # Step 6: Clean up UI build artifacts
        cleanup_ui_artifacts
        echo ""

        # Step 7: Node modules
        cleanup_node_modules
        echo ""

        # Step 8: Python cache files
        cleanup_all_python_cache
        echo ""

        # Step 9: Pytest cache
        cleanup_pytest_cache
        echo ""

        # Step 10: Temporary files
        cleanup_temp_files
        echo ""

        # Step 11: CDK staging (after CDK destroy completes)
        cleanup_cdk_staging
        echo ""

        # Step 12: CDK artifacts (after CDK destroy completes)
        cleanup_cdk_artifacts
        echo ""

        # Step 13: Python virtual environment (LAST - needed for CDK destroy)
        cleanup_python_venv
        echo ""

        echo "🎉 Full cleanup completed successfully!"
        echo ""
        echo "Summary:"
        echo "AWS Resources:"
        echo "✅ CDK-managed resources destroyed (including Frontend stack)"
        echo "✅ AgentCore runtimes (from this deployment) removed"
        echo "✅ CloudWatch logs (environment-specific) deleted"
        echo ""
        echo "Local Files:"
        echo "✅ Python virtual environment (.venv/) removed"
        echo "✅ Node modules (node_modules/) removed"
        echo "✅ Build artifacts (dist/, cdk.out/) cleaned"
        echo "✅ Cache files (__pycache__, .pytest_cache) removed"
        echo "✅ Temporary files cleaned"
        echo ""
        echo "💡 Note: Only resources created by CDK for this deployment were removed."
        echo "   Manually created resources and other deployments are preserved."
    fi
}

# Run main function
main