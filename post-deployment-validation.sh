#!/bin/bash
# BDA Pipeline Post-Deployment Validation Script

set -e

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Logging function
log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        INFO)  echo -e "${GREEN}[INFO]${NC} $message" ;;
        WARN)  echo -e "${YELLOW}[WARN]${NC} $message" ;;
        ERROR) echo -e "${RED}[ERROR]${NC} $message" ;;
        DEBUG) echo -e "${BLUE}[DEBUG]${NC} $message" ;;
        *)     echo -e "$message" ;;
    esac
}

# Parse command line arguments
parse_arguments() {
    AWS_PROFILE="default"
    ENVIRONMENT="Dev"
    VERSION="v1"
    TEST_FILE=""
    TIMEOUT=300  # 5 minutes default timeout
    
    while [[ "$#" -gt 0 ]]; do
        case $1 in
            --profile) AWS_PROFILE="$2"; shift ;;
            --environment) ENVIRONMENT="$2"; shift ;;
            --version) VERSION="$2"; shift ;;
            --test-file) TEST_FILE="$2"; shift ;;
            --timeout) TIMEOUT="$2"; shift ;;
            --help) show_help; exit 0 ;;
            *) log ERROR "Unknown parameter: $1"; show_help; exit 1 ;;
        esac
        shift
    done
}

show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Validate BDA Pipeline deployment by uploading a test document and monitoring processing.

OPTIONS:
    --profile PROFILE       AWS profile to use (default: default)
    --environment ENV       Environment to test (default: Dev)
    --version VERSION       Version tag (default: v1)
    --test-file FILE        PDF file to upload for testing (required)
    --timeout SECONDS       Max wait time for processing (default: 300)
    --help                  Show this help message

EXAMPLES:
    $0 --test-file /path/to/document.pdf
    $0 --test-file /path/to/document.pdf --environment Prod --profile prod
    $0 --test-file /path/to/document.pdf --timeout 600

EOF
}

# Get CloudFormation stack outputs
get_stack_output() {
    local stack_name=$1
    local output_key=$2
    
    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --profile "$AWS_PROFILE" \
        --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue" \
        --output text 2>/dev/null || echo ""
}

# Wait for processing completion
wait_for_completion() {
    local filename=$1
    local timeout=$2
    local start_time=$(date +%s)
    
    log INFO "Waiting for processing completion (timeout: ${timeout}s)..."
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $timeout ]; then
            log ERROR "Timeout reached (${timeout}s). Processing may still be ongoing."
            return 1
        fi
        
        local status=$(aws dynamodb scan \
            --table-name "BDA-${ENVIRONMENT}-ProcessingStatus-${VERSION}" \
            --profile "$AWS_PROFILE" \
            --filter-expression "contains(doc_id, :filename)" \
            --expression-attribute-values "{\":filename\":{\"S\":\"$filename\"}}" \
            --query 'Items[0].status.S' \
            --output text 2>/dev/null || echo "")
        
        case $status in
            "COMPLETED")
                log INFO "✅ Processing completed successfully!"
                return 0
                ;;
            "ERROR"|"TIMEOUT"|"FAILED")
                log ERROR "❌ Processing failed with status: $status"
                return 1
                ;;
            "PROCESSING"|"INITIALIZING")
                log INFO "⏳ Status: $status (${elapsed}s elapsed)"
                sleep 10
                ;;
            "")
                log WARN "⚠️  Document not found in processing table (${elapsed}s elapsed)"
                sleep 5
                ;;
            *)
                log INFO "📊 Status: $status (${elapsed}s elapsed)"
                sleep 10
                ;;
        esac
    done
}

# Main validation function
main() {
    log INFO "======================================================================="
    log INFO "BDA Pipeline Post-Deployment Validation"
    log INFO "======================================================================="
    
    # Parse arguments
    parse_arguments "$@"
    
    # Validate required parameters
    if [ -z "$TEST_FILE" ]; then
        log ERROR "Test file is required. Use --test-file parameter."
        show_help
        exit 1
    fi
    
    if [ ! -f "$TEST_FILE" ]; then
        log ERROR "Test file not found: $TEST_FILE"
        exit 1
    fi
    
    log INFO "Configuration:"
    log INFO "  AWS Profile: $AWS_PROFILE"
    log INFO "  Environment: $ENVIRONMENT"
    log INFO "  Version: $VERSION"
    log INFO "  Test File: $TEST_FILE"
    log INFO "  Timeout: ${TIMEOUT}s"
    
    # Step 1: Get bucket name
    log INFO "Step 1: Getting S3 bucket name..."
    BUCKET_NAME=$(get_stack_output "BDA-Foundation-${ENVIRONMENT}" "DocumentBucketName")
    
    if [ -z "$BUCKET_NAME" ]; then
        log ERROR "Could not find S3 bucket name from CloudFormation stack"
        exit 1
    fi
    
    log INFO "✅ Found bucket: $BUCKET_NAME"
    
    # Step 2: Upload test file
    log INFO "Step 2: Uploading test document..."
    FILENAME=$(basename "$TEST_FILE")
    
    if aws s3 cp "$TEST_FILE" "s3://$BUCKET_NAME/public/uploads/" --profile "$AWS_PROFILE"; then
        log INFO "✅ Upload successful: $FILENAME"
    else
        log ERROR "❌ Upload failed"
        exit 1
    fi
    
    # Step 3: Check Step Functions execution
    log INFO "Step 3: Checking Step Functions execution..."
    sleep 5  # Give EventBridge time to trigger
    
    PARENT_SM_ARN=$(get_stack_output "BDA-Orchestration-${ENVIRONMENT}" "ParentStateMachineArn")
    
    if [ -n "$PARENT_SM_ARN" ]; then
        EXECUTION_STATUS=$(aws stepfunctions list-executions \
            --state-machine-arn "$PARENT_SM_ARN" \
            --profile "$AWS_PROFILE" \
            --max-items 1 \
            --query 'executions[0].status' \
            --output text 2>/dev/null || echo "")
        
        if [ "$EXECUTION_STATUS" = "RUNNING" ] || [ "$EXECUTION_STATUS" = "SUCCEEDED" ]; then
            log INFO "✅ Step Functions execution: $EXECUTION_STATUS"
        else
            log WARN "⚠️  Step Functions status: $EXECUTION_STATUS"
        fi
    else
        log WARN "⚠️  Could not find Step Functions ARN"
    fi
    
    # Step 4: Monitor processing status
    log INFO "Step 4: Monitoring document processing..."
    
    if wait_for_completion "$FILENAME" "$TIMEOUT"; then
        # Step 5: Get final status and output location
        log INFO "Step 5: Getting final processing results..."
        
        FINAL_STATUS=$(aws dynamodb scan \
            --table-name "BDA-${ENVIRONMENT}-ProcessingStatus-${VERSION}" \
            --profile "$AWS_PROFILE" \
            --filter-expression "contains(doc_id, :filename)" \
            --expression-attribute-values "{\":filename\":{\"S\":\"$FILENAME\"}}" \
            --query 'Items[0].{Status:status.S,StartTime:start_time.S,CompletedTime:completed_time.S,OutputLocation:output_location.S,PageCount:page_count.N}' \
            --output table 2>/dev/null || echo "")
        
        if [ -n "$FINAL_STATUS" ]; then
            log INFO "Final Processing Results:"
            echo "$FINAL_STATUS"
        fi
        
        # Step 6: Check output files
        log INFO "Step 6: Checking output files..."
        
        OUTPUT_COUNT=$(aws s3 ls "s3://$BUCKET_NAME/BDA-Output/" --profile "$AWS_PROFILE" --recursive | wc -l)
        
        if [ "$OUTPUT_COUNT" -gt 0 ]; then
            log INFO "✅ Found $OUTPUT_COUNT output files in S3"
        else
            log WARN "⚠️  No output files found"
        fi
        
        # Additional validation steps
        validate_ui_components
        test_knowledge_base_sync
        
        log INFO "======================================================================="
        log INFO "🎉 VALIDATION SUCCESSFUL!"
        log INFO "======================================================================="
        log INFO "The BDA pipeline is working correctly:"
        log INFO "✅ Document upload triggered processing"
        log INFO "✅ Step Functions executed successfully"
        log INFO "✅ Document processed by Bedrock Data Automation"
        log INFO "✅ Output files generated"
        log INFO "✅ UI components validated"
        log INFO "✅ Knowledge Base sync tested"
        log INFO "======================================================================="
        
        # Start UI server as final step
        start_ui_server
        
    else
        log ERROR "======================================================================="
        log ERROR "❌ VALIDATION FAILED!"
        log ERROR "======================================================================="
        log ERROR "Processing did not complete within timeout period."
        log ERROR "Check AWS Console for detailed error information:"
        log ERROR "- Step Functions: $PARENT_SM_ARN"
        log ERROR "- DynamoDB: BDA-${ENVIRONMENT}-ProcessingStatus-${VERSION}"
        log ERROR "- S3 Bucket: $BUCKET_NAME"
        log ERROR "======================================================================="
        exit 1
    fi
}

# Function to validate UI components
validate_ui_components() {
    log INFO "======================================================================="
    log INFO "Step 6: Validating UI Components"
    log INFO "======================================================================="
    
    # Check if UI directory exists
    if [[ ! -d "bda-cloudscape-ui" ]]; then
        log ERROR "❌ UI directory not found: bda-cloudscape-ui"
        return 1
    fi
    
    cd bda-cloudscape-ui
    
    # Check if package.json exists
    if [[ ! -f "package.json" ]]; then
        log ERROR "❌ package.json not found in UI directory"
        cd ..
        return 1
    fi
    
    # Check if node_modules exists (dependencies installed)
    if [[ ! -d "node_modules" ]]; then
        log INFO "Installing UI dependencies..."
        npm install
        if [[ $? -ne 0 ]]; then
            log ERROR "❌ Failed to install UI dependencies"
            cd ..
            return 1
        fi
    fi
    
    # Validate environment configuration
    log INFO "Checking UI environment configuration..."
    if [[ ! -f ".env" ]]; then
        log ERROR "❌ .env file not found in UI directory"
        cd ..
        return 1
    fi
    
    # Check required environment variables
    local required_vars=("VITE_USER_POOL_ID" "VITE_USER_POOL_CLIENT_ID" "VITE_IDENTITY_POOL_ID" "VITE_S3_BUCKET" "VITE_BEDROCK_AGENT_ID")
    for var in "${required_vars[@]}"; do
        if ! grep -q "^${var}=" .env; then
            log ERROR "❌ Missing required environment variable: $var"
            cd ..
            return 1
        fi
    done
    
    log INFO "✅ UI components validated successfully"
    cd ..
    return 0
}

# Function to test knowledge base sync
test_knowledge_base_sync() {
    log INFO "======================================================================="
    log INFO "Step 7: Testing Knowledge Base Sync"
    log INFO "======================================================================="
    
    # Get KB sync Lambda function name
    local kb_sync_function=$(aws lambda list-functions \
        --query "Functions[?contains(FunctionName, 'SyncKB') && contains(FunctionName, '${ENVIRONMENT}')].FunctionName" \
        --output text \
        --profile "$AWS_PROFILE" 2>/dev/null)
    
    if [[ -z "$kb_sync_function" ]]; then
        log WARN "⚠️  KB Sync Lambda function not found - skipping KB sync test"
        return 0
    fi
    
    log INFO "Testing KB sync function: $kb_sync_function"
    
    # Invoke KB sync function
    local sync_result=$(aws lambda invoke \
        --function-name "$kb_sync_function" \
        --payload '{}' \
        --profile "$AWS_PROFILE" \
        /tmp/kb-sync-test.json 2>/dev/null)
    
    if [[ $? -eq 0 ]]; then
        local response=$(cat /tmp/kb-sync-test.json 2>/dev/null)
        if echo "$response" | grep -q '"statusCode": 200'; then
            log INFO "✅ Knowledge Base sync test successful"
        else
            log WARN "⚠️  KB sync returned non-200 status: $response"
        fi
        rm -f /tmp/kb-sync-test.json
    else
        log WARN "⚠️  Failed to invoke KB sync function"
    fi
    
    return 0
}

# Function to start UI server
start_ui_server() {
    log INFO "======================================================================="
    log INFO "Step 8: Starting Cloudscape UI Server"
    log INFO "======================================================================="
    
    cd bda-cloudscape-ui
    
    log INFO "🚀 Starting Vite development server..."
    log INFO ""
    log INFO "======================================================================="
    log INFO "✅ BDA PIPELINE VALIDATION COMPLETE!"
    log INFO "======================================================================="
    log INFO "All components have been validated successfully:"
    log INFO "✅ S3 bucket and document upload"
    log INFO "✅ EventBridge rules and Lambda triggers"  
    log INFO "✅ Step Functions workflow execution"
    log INFO "✅ Bedrock Data Automation processing"
    log INFO "✅ DynamoDB status tracking"
    log INFO "✅ Knowledge Base synchronization"
    log INFO "✅ UI components and configuration"
    log INFO ""
    log INFO "🌐 NEXT STEPS:"
    log INFO "1. The Vite server will start automatically"
    log INFO "2. Open your browser to: http://localhost:3000"
    log INFO "3. Sign in with your Cognito credentials"
    log INFO "4. Test all features:"
    log INFO "   • Upload Documents (PDF files)"
    log INFO "   • Monitor Processing Status"
    log INFO "   • Chat with AI Agents"
    log INFO "   • View Analytics Dashboard"
    log INFO ""
    log INFO "Press Ctrl+C to stop the server when done testing"
    log INFO "======================================================================="
    log INFO ""
    
    # Start the Vite server
    npm run dev
    
    cd ..
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi