#!/bin/bash
# Enhanced Bedrock Data Automation (BDA) Pipeline Deployment Script
# Docker-free approach with integrated Lambda layer building

set -e  # Exit immediately if a command exits with a non-zero status
set -u  # Exit if an undefined variable is used

# Script configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly VENV_DIR="${SCRIPT_DIR}/.venv"
readonly LAYER_DIR="${SCRIPT_DIR}/lambda_layers/python-deps"
readonly API_LAYER_DIR="${SCRIPT_DIR}/lambda_layers/api-deps"
readonly CONFIG_FILE="${SCRIPT_DIR}/cdk-params.json"
readonly LOG_FILE="${SCRIPT_DIR}/deployment.log"

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
        INFO)  echo -e "${GREEN}[INFO]${NC} $message" | tee -a "$LOG_FILE" ;;
        WARN)  echo -e "${YELLOW}[WARN]${NC} $message" | tee -a "$LOG_FILE" ;;
        ERROR) echo -e "${RED}[ERROR]${NC} $message" | tee -a "$LOG_FILE" ;;
        DEBUG) echo -e "${BLUE}[DEBUG]${NC} $message" | tee -a "$LOG_FILE" ;;
        *)     echo -e "$message" | tee -a "$LOG_FILE" ;;
    esac
}

# Error handler
error_exit() {
    log ERROR "$1"
    log ERROR "Deployment failed. Check $LOG_FILE for details."
    exit 1
}

# Cleanup function
cleanup() {
    if [ -f "$CONFIG_FILE.tmp" ]; then
        rm -f "$CONFIG_FILE.tmp"
    fi
}

# Set trap for cleanup
trap cleanup EXIT

# Parse command line arguments
parse_arguments() {
    PROFILE_ARG=""
    SKIP_BOOTSTRAP=false
    VERBOSE=false
    DRY_RUN=false
    ENVIRONMENT="Dev"
    VERSION="v1"
    PROJECT_NAME="DocumentAutomation"
    REBUILD_LAYER=false
    DEPLOYMENT_ID=""
    EXISTING_BUCKET=""
    CUSTOM_BUCKET=""
    SKIP_AGENTCORE=false
    SKIP_UI=false
    SKIP_UI_BUILD=false
    QUICK_MODE=false
    CONFIG_ONLY=false

    while [[ "$#" -gt 0 ]]; do
        case $1 in
            --profile) PROFILE_ARG="$2"; shift ;;
            --profile=*) PROFILE_ARG="${1#*=}" ;;
            --environment) ENVIRONMENT="$2"; shift ;;
            --environment=*) ENVIRONMENT="${1#*=}" ;;
            --version) VERSION="$2"; shift ;;
            --version=*) VERSION="${1#*=}" ;;
            --project) PROJECT_NAME="$2"; shift ;;
            --project=*) PROJECT_NAME="${1#*=}" ;;
            --deployment-id) DEPLOYMENT_ID="$2"; shift ;;
            --deployment-id=*) DEPLOYMENT_ID="${1#*=}" ;;
            --existing-bucket) EXISTING_BUCKET="$2"; shift ;;
            --existing-bucket=*) EXISTING_BUCKET="${1#*=}" ;;
            --custom-bucket) CUSTOM_BUCKET="$2"; shift ;;
            --custom-bucket=*) CUSTOM_BUCKET="${1#*=}" ;;
            --rebuild-layer) REBUILD_LAYER=true ;;
            --skip-bootstrap) SKIP_BOOTSTRAP=true ;;
            --skip-agentcore) SKIP_AGENTCORE=true ;;
            --skip-ui) SKIP_UI=true ;;
            --skip-ui-build) SKIP_UI_BUILD=true ;;
            --quick) QUICK_MODE=true; SKIP_AGENTCORE=true; SKIP_UI_BUILD=true ;;
            --config-only) CONFIG_ONLY=true; SKIP_AGENTCORE=true; SKIP_UI_BUILD=true ;;
            --verbose) VERBOSE=true ;;
            --dry-run) DRY_RUN=true ;;
            --help) show_help; exit 0 ;;
            *) log ERROR "Unknown parameter: $1"; show_help; exit 1 ;;
        esac
        shift
    done
    
    # Set AWS profile from argument, environment variable, or use default
    if [ -n "$PROFILE_ARG" ]; then
        AWS_PROFILE=$PROFILE_ARG
    else
        AWS_PROFILE=${AWS_PROFILE:-"default"}
    fi
    
    # Set resource prefix based on project name
    RESOURCE_PREFIX=${RESOURCE_PREFIX:-"BDA"}
}

show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy the Bedrock Data Automation (BDA) Pipeline

OPTIONS:
    --profile PROFILE       AWS profile to use (default)
    --environment ENV       Deployment environment (default: Dev)
    --version VERSION       Version tag (default: v1)
    --project NAME          Project name (default: DocumentAutomation)
    --deployment-id ID      Unique deployment identifier for stack isolation
    --existing-bucket NAME  Import an existing S3 bucket
    --custom-bucket NAME    Use a custom S3 bucket name
    --rebuild-layer         Force rebuild of Lambda layer
    --skip-bootstrap       Skip CDK bootstrap check
    --skip-agentcore       Skip AgentCore Docker build and deployment
    --skip-ui              Skip frontend deployment entirely
    --skip-ui-build        Skip UI build (deploy config.json only) ~5-10min faster
    --quick                Quick mode: Skip AgentCore + UI build ~20-30min faster
    --config-only          Deploy only frontend runtime config ~30-40min faster
    --verbose              Enable verbose output
    --dry-run              Show what would be deployed without deploying
    --help                 Show this help message

BUCKET OPTIONS:
    Default (no option)     CDK auto-generates unique bucket name (RECOMMENDED)
    --existing-bucket       Import and use an existing S3 bucket
    --custom-bucket         Create bucket with specific custom name

EXAMPLES:
    # Full deployments
    $0                                              # Full deploy to Dev (~45 mins)
    $0 --environment Prod --profile production     # Deploy to Production

    # Fast deployments (RECOMMENDED for development)
    $0 --quick                                      # Infrastructure only (~10-15 mins)
    $0 --skip-ui-build                             # Infrastructure + config (~15-20 mins)
    $0 --config-only                               # Just update config.json (~5-8 mins)

    # Other options
    $0 --deployment-id feature-xyz                 # Deploy isolated feature stack
    $0 --existing-bucket my-existing-bucket        # Use existing bucket
    $0 --custom-bucket my-custom-name              # Use custom bucket name
    $0 --environment Staging --version v2          # Deploy version v2 to Staging
    $0 --rebuild-layer                             # Force rebuild Lambda layer

ENVIRONMENTS:
    Dev, Staging, Prod, Test (or any custom environment name)

DEPLOYMENT ISOLATION:
    Use --deployment-id to create completely isolated stack deployments.
    This allows multiple deployments in the same account/region without conflicts.
    Example: --deployment-id feature-abc creates stacks like BDA-Foundation-Dev-feature-abc

EOF
}

# Validate prerequisites
validate_prerequisites() {
    log INFO "Validating prerequisites..."
    
    # Check required commands (Docker IS required for AgentCore)
    local required_commands=("aws" "python3" "pip3" "node" "npm" "docker")
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            if [ "$cmd" = "docker" ] && [ "$SKIP_AGENTCORE" = true ]; then
                log WARN "Docker not found but --skip-agentcore specified, continuing..."
            else
                error_exit "Required command '$cmd' not found. Please install it and try again."
            fi
        fi
    done
    
    # Check Python version
    local python_version=$(python3 --version 2>&1 | awk '{print $2}')
    local python_major=$(echo "$python_version" | cut -d. -f1)
    local python_minor=$(echo "$python_version" | cut -d. -f2)
    
    if [ "$python_major" -lt 3 ] || ([ "$python_major" -eq 3 ] && [ "$python_minor" -lt 10 ]); then
        error_exit "Python 3.10 or higher is required. Current version: $python_version"
    fi
    
    # Check AWS CLI version
    local aws_version=$(aws --version 2>&1 | awk '{print $1}' | cut -d/ -f2)
    log INFO "Using AWS CLI version: $aws_version"
    
    # Check Node.js version for CDK
    local node_version=$(node --version | cut -d. -f1 | sed 's/v//')
    if [ "$node_version" -lt 18 ]; then
        log WARN "Node.js 18+ recommended for CDK. Current version: $(node --version)"
    fi
    
    # Setup Docker buildx for ARM64 if Docker is available and AgentCore is enabled
    if command -v docker &> /dev/null && [ "$SKIP_AGENTCORE" = false ]; then
        log INFO "Setting up Docker buildx for ARM64 architecture..."
        docker buildx create --name agentcore-builder --use 2>/dev/null || docker buildx use agentcore-builder
    fi
    
    log INFO "Prerequisites validation completed successfully"
}

# Setup directory structure
setup_directory_structure() {
    log INFO "Setting up directory structure..."
    
    # Create bda_stacks directory if it doesn't exist
    if [ ! -d "bda_stacks" ]; then
        log INFO "Creating bda_stacks directory..."
        mkdir -p bda_stacks
        touch bda_stacks/__init__.py
        
        # Move existing stack files if they exist at root level
        local stack_files=("resources_stack.py" "step_functions_stack.py" "project_stack.py" "storage_stack.py")
        for file in "${stack_files[@]}"; do
            if [ -f "$file" ]; then
                log INFO "Moving $file to bda_stacks/"
                mv "$file" bda_stacks/
            fi
        done
    fi
    
    # Ensure Lambda directory exists
    if [ ! -d "Lambda" ]; then
        log ERROR "Lambda directory not found. Please ensure it exists with Lambda function code."
        exit 1
    fi
    
    # Create lambda_layers directory structure
    mkdir -p "$LAYER_DIR"
    
    # Create api-deps directory structure
    mkdir -p "$API_LAYER_DIR/python"
    log INFO "Created API dependencies layer directory: $API_LAYER_DIR"
    
    # Create StateMachineDefinitions directory if it doesn't exist
    if [ ! -d "StateMachineDefinitions" ]; then
        log WARN "StateMachineDefinitions directory not found. Please ensure it exists with required JSON files."
    fi
    
    log INFO "Directory structure setup completed"
}

# Setup Python environment
setup_python_environment() {
    log INFO "Setting up Python environment..."
    
    if [ -d "$VENV_DIR" ]; then
        log INFO "Activating existing Python virtual environment..."
        source "$VENV_DIR/bin/activate"
    else
        log INFO "Creating and activating Python virtual environment..."
        python3 -m venv "$VENV_DIR" || error_exit "Failed to create virtual environment"
        source "$VENV_DIR/bin/activate"
    fi
    
    # Upgrade pip
    pip3 install --upgrade pip setuptools wheel || error_exit "Failed to upgrade pip"
    
    # Install required dependencies
    log INFO "Installing Python dependencies..."
    if [ -f "requirements.txt" ]; then
        pip3 install -r requirements.txt || error_exit "Failed to install requirements from requirements.txt"
    else
        log WARN "requirements.txt not found, installing core dependencies..."
        pip3 install aws-cdk-lib>=2.188.0 constructs>=10.0.0 boto3>=1.36.0 aws-lambda-powertools>=3.6.0 || error_exit "Failed to install core dependencies"
    fi
    
    log INFO "Python environment setup completed successfully"
}

# Prepare Lambda layer (called before CDK deployment)
prepare_lambda_layer() {
    log INFO "Preparing Lambda layer..."
    
    # Create requirements.txt for Lambda layer if it doesn't exist
    if [ ! -f "$LAYER_DIR/requirements.txt" ]; then
        log INFO "Creating Lambda layer requirements.txt..."
        cat > "$LAYER_DIR/requirements.txt" << EOF
pypdf==4.0.1
requests==2.31.0
requests-aws4auth==1.2.3
boto3>=1.36.0
aws-lambda-powertools>=3.6.0
chardet>=5.2.0
charset-normalizer>=3.3.0
idna>=3.4
urllib3>=1.26.0
certifi>=2023.0.0
EOF
    fi
    
    # Check if we need to build/rebuild the layer
    local python_dir="$LAYER_DIR/python"
    local should_build=false
    
    if [ "$REBUILD_LAYER" = true ]; then
        log INFO "Force rebuild requested, cleaning existing layer..."
        rm -rf "$python_dir"
        should_build=true
    elif [ ! -d "$python_dir" ] || [ -z "$(ls -A "$python_dir" 2>/dev/null)" ]; then
        log INFO "Lambda layer not found or empty, building..."
        should_build=true
    else
        log INFO "Using existing Lambda layer for $ENVIRONMENT"
        
        # Show detailed layer information for transparency
        local layer_size=$(du -sh "$python_dir" 2>/dev/null | cut -f1 || echo "unknown")
        local layer_date=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$python_dir" 2>/dev/null || echo "unknown")
        local python_packages=$(find "$python_dir" -name "*.dist-info" 2>/dev/null | wc -l | tr -d ' ' || echo "0")
        
        log INFO "  Layer size: $layer_size, Created: $layer_date, Packages: $python_packages"
        log INFO "  Validating layer integrity..."
        
        # Quick validation of critical packages
        local validation_passed=true
        local critical_packages=("requests" "pypdf" "boto3")
        
        for package in "${critical_packages[@]}"; do
            if [ ! -d "$python_dir/$package" ] && [ ! -f "$python_dir/${package}.py" ]; then
                log WARN "  ⚠ Missing critical package: $package"
                validation_passed=false
            fi
        done
        
        if [ "$validation_passed" = true ]; then
            log INFO "  ✓ Layer validation passed - proceeding with deployment"
        else
            log WARN "  ⚠ Layer validation failed - will rebuild"
            rm -rf "$python_dir"
            should_build=true
        fi
    fi
    
    if [ "$should_build" = true ]; then
        build_lambda_layer
    fi
    
    # Verify the layer has required packages
    verify_lambda_layer
    
    # Prepare API dependencies layer
    prepare_api_layer
}

# Build Lambda layer using local pip (no Docker required)
build_lambda_layer() {
    log INFO "Building Lambda layer dependencies..."
    
    local python_dir="$LAYER_DIR/python"
    
    # Create/clean the python directory
    rm -rf "$python_dir"
    mkdir -p "$python_dir"
    
    # Install dependencies using pip
    log INFO "Installing Lambda layer dependencies with pip..."
    
    if ! pip3 install -r "$LAYER_DIR/requirements.txt" -t "$python_dir" --no-cache-dir --upgrade; then
        error_exit "Failed to install Lambda layer dependencies"
    fi
    
    log INFO "✓ Lambda layer dependencies installed successfully"
    
    # Clean up to reduce layer size
    cleanup_lambda_layer "$python_dir"
    
    # Report layer size
    local layer_size=$(du -sh "$python_dir" | cut -f1)
    log INFO "Lambda layer size: $layer_size"
    
    # Warn if layer is getting large
    local layer_size_mb=$(du -sm "$python_dir" | cut -f1)
    if [ "$layer_size_mb" -gt 200 ]; then
        log WARN "Lambda layer size ($layer_size) is getting large. AWS limit is 250MB."
    fi
}

# Clean up Lambda layer to reduce size
cleanup_lambda_layer() {
    local python_dir=$1
    
    log INFO "Cleaning up Lambda layer to reduce size..."
    
    # Remove __pycache__ directories
    find "$python_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    
    # Remove .pyc and .pyo files
    find "$python_dir" -name "*.pyc" -delete 2>/dev/null || true
    find "$python_dir" -name "*.pyo" -delete 2>/dev/null || true
    
    # Remove .dist-info directories
    find "$python_dir" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
    
    # Remove test directories
    find "$python_dir" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
    find "$python_dir" -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
    
    log INFO "✓ Lambda layer cleanup completed"
}

# Prepare API dependencies layer
prepare_api_layer() {
    log INFO "Preparing API dependencies layer..."
    
    local API_PYTHON_DIR="${API_LAYER_DIR}/python"
    
    # Create requirements.txt for API layer if it doesn't exist
    if [ ! -f "$API_LAYER_DIR/requirements.txt" ]; then
        log INFO "Creating API layer requirements.txt..."
        cat > "$API_LAYER_DIR/requirements.txt" << EOF
boto3>=1.36.0
aws-lambda-powertools>=3.6.0
requests==2.31.0
urllib3>=1.26.0
certifi>=2023.0.0
EOF
    fi
    
    # Check if we need to build/rebuild the API layer
    local should_build=false
    
    if [ "$REBUILD_LAYER" = true ]; then
        log INFO "Force rebuild requested, cleaning existing API layer..."
        rm -rf "$API_PYTHON_DIR"
        should_build=true
    elif [ ! -d "$API_PYTHON_DIR" ] || [ -z "$(ls -A "$API_PYTHON_DIR" 2>/dev/null)" ]; then
        log INFO "API layer not found or empty, building..."
        should_build=true
    else
        log INFO "Using existing API layer for $ENVIRONMENT"
        
        # Show API layer information
        local api_layer_size=$(du -sh "$API_PYTHON_DIR" 2>/dev/null | cut -f1 || echo "unknown")
        local api_layer_date=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$API_PYTHON_DIR" 2>/dev/null || echo "unknown")
        local api_packages=$(find "$API_PYTHON_DIR" -name "*.dist-info" 2>/dev/null | wc -l | tr -d ' ' || echo "0")
        
        log INFO "  API layer size: $api_layer_size, Created: $api_layer_date, Packages: $api_packages"
        
        # Quick validation
        if [ -f "$API_PYTHON_DIR/boto3/__init__.py" ]; then
            log INFO "  ✓ API layer validation passed"
        else
            log WARN "  ⚠ API layer validation failed - will rebuild"
            rm -rf "$API_PYTHON_DIR"
            should_build=true
        fi
    fi
    
    if [ "$should_build" = true ]; then
        log INFO "Building API layer dependencies..."
        
        # Create/clean the python directory
        mkdir -p "$API_PYTHON_DIR"
        
        # Install dependencies using pip
        log INFO "Installing API layer dependencies with pip..."
        
        if ! pip3 install -r "$API_LAYER_DIR/requirements.txt" -t "$API_PYTHON_DIR" --no-cache-dir --upgrade; then
            error_exit "Failed to install API layer dependencies"
        fi
        
        log INFO "✓ API layer dependencies installed successfully"
        
        # Clean up to reduce layer size
        log INFO "Cleaning up API layer to reduce size..."
        find "$API_PYTHON_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        find "$API_PYTHON_DIR" -name "*.pyc" -delete 2>/dev/null || true
        find "$API_PYTHON_DIR" -name "*.pyo" -delete 2>/dev/null || true
        find "$API_PYTHON_DIR" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
        find "$API_PYTHON_DIR" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
        find "$API_PYTHON_DIR" -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
        
        # Report layer size
        local layer_size=$(du -sh "$API_PYTHON_DIR" | cut -f1)
        log INFO "✓ API layer size: $layer_size"
    fi
    
    log INFO "✓ API layer preparation completed"
}

# Verify Lambda layer has required packages
verify_lambda_layer() {
    log INFO "Verifying Lambda layer..."
    
    local python_dir="$LAYER_DIR/python"
    
    # Check if critical packages exist
    local critical_packages=("requests" "pypdf" "chardet" "idna")
    local missing_packages=()
    
    for package in "${critical_packages[@]}"; do
        if [ ! -d "$python_dir/$package" ] && [ ! -f "$python_dir/${package}.py" ]; then
            missing_packages+=("$package")
        fi
    done
    
    if [ ${#missing_packages[@]} -eq 0 ]; then
        log INFO "✓ Lambda layer verification successful - all critical packages found"
    else
        log WARN "⚠ Some packages may be missing: ${missing_packages[*]}"
        log WARN "This might cause import errors in Lambda functions"
    fi
    
    # List top-level packages for verification
    log INFO "Lambda layer contents:"
    ls -la "$python_dir" | grep -E "^d" | awk '{print $9}' | grep -v "^\\.$\\|^\\.\\.$" | head -10 | while read dir; do
        log INFO "  - $dir"
    done
}

# Validate AWS configuration
validate_aws_configuration() {
    log INFO "Validating AWS configuration..."
    
    # Validate the AWS profile
    if ! aws sts get-caller-identity --profile "$AWS_PROFILE" > /dev/null 2>&1; then
        error_exit "AWS profile '$AWS_PROFILE' is not configured correctly. Please run 'aws configure --profile $AWS_PROFILE' or set a different profile."
    fi
    
    # Get AWS account and region
    AWS_ACCOUNT=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query "Account" --output text) || error_exit "Failed to get AWS account ID"
    AWS_REGION=$(aws configure get region --profile "$AWS_PROFILE") || {
        log WARN "Region not set in profile, checking environment..."
        AWS_REGION=${AWS_DEFAULT_REGION:-${AWS_REGION}}
    }
    
    if [ -z "$AWS_ACCOUNT" ] || [ -z "$AWS_REGION" ]; then
        error_exit "Could not retrieve AWS account ($AWS_ACCOUNT) or region ($AWS_REGION). Please set AWS region in your profile or via AWS_DEFAULT_REGION/AWS_REGION environment variable."
    fi
    
    log INFO "Using AWS Account: $AWS_ACCOUNT"
    log INFO "Using AWS Region: $AWS_REGION"
    
    # Export CDK environment variables
    export CDK_DEFAULT_ACCOUNT=$AWS_ACCOUNT
    export CDK_DEFAULT_REGION=$AWS_REGION
    export AWS_PROFILE=$AWS_PROFILE
    
    log INFO "AWS configuration validation completed successfully"
}

# Create or update .env file from profile
create_or_update_env_file() {
    log INFO "Creating/updating .env file from AWS profile..."
    
    # Create .env from template if it doesn't exist
    if [ ! -f ".env" ]; then
        if [ -f ".env.template" ]; then
            log INFO "Creating .env from template..."
            cp .env.template .env
        else
            log INFO "Creating new .env file..."
            touch .env
        fi
    fi
    
    # Update .env with profile-derived values
    log INFO "Updating .env with AWS configuration..."
    
    # Function to update or add a key-value pair in .env
    update_env_var() {
        local key=$1
        local value=$2
        if grep -q "^${key}=" .env; then
            # Update existing value
            sed -i.bak "s|^${key}=.*|${key}=${value}|" .env
        else
            # Add new value
            echo "${key}=${value}" >> .env
        fi
    }
    
    # Update AWS configuration values
    update_env_var "AWS_PROFILE" "$AWS_PROFILE"
    update_env_var "AWS_DEFAULT_REGION" "$AWS_REGION"
    update_env_var "BEDROCK_REGION" "$AWS_REGION"
    update_env_var "ENVIRONMENT" "$ENVIRONMENT"
    
    # Set default values for API keys if not present
    if ! grep -q "^ALPHA_VANTAGE_API_KEY=" .env; then
        update_env_var "ALPHA_VANTAGE_API_KEY" "demo"
    fi
    if ! grep -q "^CMC_API_KEY=" .env; then
        update_env_var "CMC_API_KEY" "demo"
    fi
    if ! grep -q "^FRED_API_KEY=" .env; then
        update_env_var "FRED_API_KEY" "demo"
    fi
    if ! grep -q "^NEWS_API_KEY=" .env; then
        update_env_var "NEWS_API_KEY" "demo"
    fi
    if ! grep -q "^REAL_ESTATE_API_KEY=" .env; then
        update_env_var "REAL_ESTATE_API_KEY" "demo"
    fi
    
    # Clean up backup file
    rm -f .env.bak
    
    log INFO "✅ .env file updated with AWS profile configuration"
    log INFO "   AWS_PROFILE: $AWS_PROFILE"
    log INFO "   AWS Region: $AWS_REGION"
    log INFO "   Environment: $ENVIRONMENT"
}

# Validate API keys and show warnings
validate_api_keys() {
    log INFO "Validating API key configuration..."
    
    local demo_keys=()
    local missing_keys=()
    
    # Check for demo API keys
    if grep -q "^ALPHA_VANTAGE_API_KEY=demo" .env; then
        demo_keys+=("ALPHA_VANTAGE_API_KEY (stock market data)")
    fi
    if grep -q "^CMC_API_KEY=demo" .env; then
        demo_keys+=("CMC_API_KEY (cryptocurrency data)")
    fi
    if grep -q "^FRED_API_KEY=demo" .env; then
        demo_keys+=("FRED_API_KEY (economic indicators)")
    fi
    if grep -q "^NEWS_API_KEY=demo" .env; then
        demo_keys+=("NEWS_API_KEY (market news)")
    fi
    
    # Show warnings for demo keys
    if [ ${#demo_keys[@]} -gt 0 ]; then
        log WARN "⚠️  Demo API keys detected - agents will return 'data not available' messages:"
        for key in "${demo_keys[@]}"; do
            log WARN "   • $key"
        done
        log WARN ""
        log WARN "For full functionality, configure real API keys in .env file:"
        log WARN "   • Alpha Vantage: https://www.alphavantage.co/support/#api-key"
        log WARN "   • CoinMarketCap: https://coinmarketcap.com/api/"
        log WARN "   • FRED: https://fred.stlouisfed.org/docs/api/api_key.html"
        log WARN "   • News API: https://newsapi.org/"
        log WARN ""
    else
        log INFO "✅ Real API keys configured for external data access"
    fi
}

# Create CDK parameters file
create_cdk_parameters() {
    log INFO "Creating CDK parameters file for environment: $ENVIRONMENT..."
    
    cat > "$CONFIG_FILE" << EOF
{
  "ResourceNamePrefix": "${RESOURCE_PREFIX}",
  "Environment": "${ENVIRONMENT}",
  "Version": "${VERSION}",
  "ProjectName": "${PROJECT_NAME}"
}
EOF
    
    log INFO "CDK parameters file created: $CONFIG_FILE"
    log INFO "  Environment: $ENVIRONMENT"
    log INFO "  Version: $VERSION"
    log INFO "  Project: $PROJECT_NAME"
}

# Generate configuration files from templates
generate_config_from_templates() {
    log INFO "Generating configuration files from templates..."
    
    # Generate runtime_config.json if template exists
    if [ -f "agentcore/runtime_config.json.template" ]; then
        log INFO "Generating agentcore/runtime_config.json from template..."
        
        # This is a placeholder - in production, runtime IDs would be obtained from deployment
        TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
        
        # Create runtime_config.json with dynamic values
        # Note: Runtime IDs should be populated after AgentCore deployment
        cat > "agentcore/runtime_config.json" << EOF
{
  "environment": "$ENVIRONMENT",
  "region": "$AWS_REGION",
  "created_at": "$TIMESTAMP",
  "runtime_ids": {
    "coordinator": "TBD-AFTER-DEPLOYMENT",
    "market_analyst": "TBD-AFTER-DEPLOYMENT",
    "investment_advisory": "TBD-AFTER-DEPLOYMENT",
    "external_api": "TBD-AFTER-DEPLOYMENT"
  },
  "runtime_arns": {
    "coordinator": "arn:aws:bedrock-agentcore:$AWS_REGION:$AWS_ACCOUNT:runtime/TBD",
    "market_analyst": "arn:aws:bedrock-agentcore:$AWS_REGION:$AWS_ACCOUNT:runtime/TBD",
    "investment_advisory": "arn:aws:bedrock-agentcore:$AWS_REGION:$AWS_ACCOUNT:runtime/TBD",
    "external_api": "arn:aws:bedrock-agentcore:$AWS_REGION:$AWS_ACCOUNT:runtime/TBD"
  }
}
EOF
        log INFO "Generated agentcore/runtime_config.json (runtime IDs to be updated after deployment)"
    fi
    
    # Generate .bedrock_agentcore.yaml if template exists
    if [ -f ".bedrock_agentcore.yaml.template" ]; then
        log INFO "Generating .bedrock_agentcore.yaml from template..."
        
        # Get Knowledge Base ID from environment or placeholder
        KB_ID="${KNOWLEDGE_BASE_ID:-KB-PLACEHOLDER}"
        AGENT_ID="bda_coordinator_agent-${VERSION}"
        SESSION_ID=$(uuidgen 2>/dev/null || echo "session-$(date +%s)")
        
        # Generate the YAML file with dynamic values
        sed -e "s/\${AWS_ACCOUNT}/$AWS_ACCOUNT/g" \
            -e "s/\${AWS_REGION}/$AWS_REGION/g" \
            -e "s/\${KNOWLEDGE_BASE_ID}/$KB_ID/g" \
            -e "s/\${AGENT_ID}/$AGENT_ID/g" \
            -e "s/\${SESSION_ID}/$SESSION_ID/g" \
            ".bedrock_agentcore.yaml.template" > ".bedrock_agentcore.yaml"
        
        log INFO "Generated .bedrock_agentcore.yaml"
    fi
    
    log INFO "Configuration file generation completed"
}

# Perform CDK bootstrap
perform_cdk_bootstrap() {
    if [ "$SKIP_BOOTSTRAP" = true ]; then
        log INFO "Skipping CDK bootstrap as requested"
        return 0
    fi
    
    log INFO "Checking CDK bootstrap status..."
    
    # Check if bootstrap stack exists
    local bootstrap_stack_name="CDKToolkit"
    if aws cloudformation describe-stacks --stack-name "$bootstrap_stack_name" --profile "$AWS_PROFILE" > /dev/null 2>&1; then
        log INFO "CDK bootstrap stack already exists"
        return 0
    fi
    
    log INFO "Performing CDK bootstrap..."
    if ! cdk bootstrap --profile "$AWS_PROFILE"; then
        log WARN "CDK bootstrap failed, but continuing with deployment..."
        return 0
    fi
    
    log INFO "CDK bootstrap completed successfully"
}

# Build and push AgentCore Docker images
build_and_push_agentcore_images() {
    log INFO "Building and pushing AgentCore Docker images..."
    
    if [ "$SKIP_AGENTCORE" = true ]; then
        log INFO "Skipping AgentCore build (--skip-agentcore specified)"
        return 0
    fi
    
    if ! command -v docker &> /dev/null; then
        log WARN "Docker not available, skipping AgentCore image builds"
        return 0
    fi
    
    # Get ECR repository details
    local ECR_REPO="bedrock-agentcore-portfolio-advisor"
    local ECR_URI="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
    
    # Check if ECR repository exists, create if needed
    if ! aws ecr describe-repositories --repository-names "$ECR_REPO" --profile "$AWS_PROFILE" --region "$AWS_REGION" &>/dev/null; then
        log INFO "Creating ECR repository: $ECR_REPO"
        aws ecr create-repository --repository-name "$ECR_REPO" --profile "$AWS_PROFILE" --region "$AWS_REGION" || {
            log WARN "Could not create ECR repository, it may be created by CDK"
        }
    fi
    
    # Login to ECR
    log INFO "Logging into ECR..."
    aws ecr get-login-password --region "$AWS_REGION" --profile "$AWS_PROFILE" | \
        docker login --username AWS --password-stdin "$ECR_URI" || {
            log ERROR "Failed to login to ECR"
            return 1
        }
    
    # Build and push each agent with production-ready streaming/observability
    local agents=("coordinator" "market_analyst" "investment_advisory" "external_api")
    local build_date=$(date +%Y%m%d-%H%M%S)
    local images_exist=true

    # Check if images already exist in ECR
    log INFO "Checking for existing Docker images in ECR..."
    for agent in "${agents[@]}"; do
        if ! aws ecr describe-images \
            --repository-name "$ECR_REPO" \
            --image-ids imageTag="${agent}-${ENVIRONMENT}-v2" \
            --profile "$AWS_PROFILE" \
            --region "$AWS_REGION" &>/dev/null; then
            images_exist=false
            break
        fi
    done

    if [ "$images_exist" = true ]; then
        log INFO "✓ All AgentCore images already exist in ECR, skipping build"
        log INFO "  Use --rebuild-layer to force rebuild if needed"
        return 0
    fi

    log INFO "Building AgentCore Docker images..."

    for agent in "${agents[@]}"; do
        log INFO "Building and pushing $agent..."

        # Build with appropriate tags for environment
        if docker buildx build \
            --platform linux/arm64 \
            --build-arg AGENT_TYPE="$agent" \
            -t "${ECR_URI}:${agent}-${ENVIRONMENT}-v2" \
            -t "${ECR_URI}:${agent}-${ENVIRONMENT}-${build_date}" \
            -t "${ECR_URI}:${agent}-latest" \
            -f agentcore/Dockerfile.minimal \
            --push \
            . >/dev/null 2>&1; then
            log INFO "  ✓ Successfully pushed $agent"
        else
            log ERROR "  ✗ Failed to build/push $agent"
            return 1
        fi
    done
    
    log INFO "✓ All AgentCore images built and pushed successfully"
    return 0
}

# Deploy CDK stack
deploy_cdk_stack() {
    log INFO "Deploying CDK stack for environment: $ENVIRONMENT (excluding frontend)..."
    
    if [ "$DRY_RUN" = true ]; then
        log INFO "DRY RUN: Would execute CDK deployment with specific stacks for environment $ENVIRONMENT"
        return 0
    fi
    
    log INFO "Executing CDK deployment..."
    log INFO "CDK will use the pre-built Lambda layer (no Docker required)"
    
    # Check if CDK is available
    if ! command -v cdk &> /dev/null; then
        error_exit "CDK CLI not found. Please install the AWS CDK CLI with: npm install -g aws-cdk"
    fi
    
    # Create stack suffix
    if [ -n "$DEPLOYMENT_ID" ]; then
        stack_suffix="${ENVIRONMENT}-${DEPLOYMENT_ID}"
    else
        stack_suffix="$ENVIRONMENT"
    fi
    
    # Deploy specific stacks in order, excluding frontend
    local stacks_to_deploy=(
        "${RESOURCE_PREFIX}-Foundation-${stack_suffix}"
        "${RESOURCE_PREFIX}-Auth-${stack_suffix}"
        "${RESOURCE_PREFIX}-Processing-${stack_suffix}"
        "${RESOURCE_PREFIX}-Orchestration-${stack_suffix}"
        "${RESOURCE_PREFIX}-KnowledgeBase-${stack_suffix}"
        "${RESOURCE_PREFIX}-Automation-${stack_suffix}"
        "${RESOURCE_PREFIX}-API-${stack_suffix}"
        "${RESOURCE_PREFIX}-AgentCoreDeployment-${stack_suffix}"
    )
    
    # Use array to properly handle arguments and spaces
    local cdk_args=(
        "deploy"
        "${stacks_to_deploy[@]}"
        "--context" "Environment=$ENVIRONMENT"
        "--context" "ResourceNamePrefix=$RESOURCE_PREFIX"
        "--context" "Version=$VERSION"
        "--context" "ProjectName=$PROJECT_NAME"
        "--profile" "$AWS_PROFILE"
        "--require-approval" "never"
        "--progress" "events"
        "--concurrency" "3"
    )
    
    # Add optional context parameters
    if [ -n "$DEPLOYMENT_ID" ]; then
        cdk_args+=("--context" "DeploymentId=$DEPLOYMENT_ID")
        log INFO "Using deployment ID: $DEPLOYMENT_ID"
    fi
    
    if [ -n "$EXISTING_BUCKET" ]; then
        cdk_args+=("--context" "ExistingBucketName=$EXISTING_BUCKET")
        log INFO "Using existing bucket: $EXISTING_BUCKET"
    fi
    
    if [ -n "$CUSTOM_BUCKET" ]; then
        cdk_args+=("--context" "CustomBucketName=$CUSTOM_BUCKET")
        log INFO "Using custom bucket name: $CUSTOM_BUCKET"
    fi
    
    if [ "$VERBOSE" = true ]; then
        cdk_args+=("--verbose")
    fi
    
    # Execute CDK deployment
    log INFO "Deploying stacks: ${stacks_to_deploy[*]}"
    if cdk "${cdk_args[@]}"; then
        log INFO "✓ CDK deployment completed successfully"
        return 0
    else
        error_exit "CDK deployment failed"
    fi
}

# Create uploads folder in S3 bucket
create_uploads_folder() {
    if [ "$DRY_RUN" = true ]; then
        log INFO "DRY RUN: Would create uploads/ folder in S3 bucket"
        return 0
    fi
    
    log INFO "Creating public/uploads/ folder in S3 bucket..."
    
    # Get the bucket name from CloudFormation outputs
    local BUCKET_NAME=$(aws cloudformation describe-stacks \
        --stack-name "${RESOURCE_PREFIX}-Foundation-${ENVIRONMENT}" \
        --profile "$AWS_PROFILE" \
        --query 'Stacks[0].Outputs[?OutputKey==`DocumentBucketName`].OutputValue' \
        --output text)
    
    if [ -z "$BUCKET_NAME" ] || [ "$BUCKET_NAME" = "None" ]; then
        log WARN "Could not find S3 bucket name, skipping uploads/ folder creation"
        return 0
    fi
    
    log INFO "Found S3 bucket: $BUCKET_NAME"
    
    # Create uploads/ folder
    if aws s3api put-object \
        --bucket "$BUCKET_NAME" \
        --key "public/uploads/" \
        --profile "$AWS_PROFILE" > /dev/null 2>&1; then
        log INFO "Successfully created uploads/ folder in bucket $BUCKET_NAME"
    else
        log WARN "Failed to create uploads/ folder in bucket $BUCKET_NAME"
        log WARN "You may need to manually create it: aws s3api put-object --bucket $BUCKET_NAME --key uploads/"
    fi
}

# Update Lambda agent environment variables
update_lambda_agent_variables() {
    if [ "$DRY_RUN" = true ]; then
        log INFO "DRY RUN: Would update Lambda agent environment variables"
        return 0
    fi
    
    log INFO "Updating Lambda agent environment variables..."
    
    # Get AgentCore runtime ARN from runtime_config.json
    local AGENTCORE_RUNTIME_ARN=""
    if [ -f "agentcore/runtime_config.json" ]; then
        AGENTCORE_RUNTIME_ARN=$(python3 -c "import json; data=json.load(open('agentcore/runtime_config.json')); print(data.get('runtime_arns', {}).get('coordinator', ''))" 2>/dev/null || echo "")
    fi
    
    if [ -z "$AGENTCORE_RUNTIME_ARN" ]; then
        log WARN "AgentCore runtime ARN not found, skipping Lambda environment variable update"
        return 0
    fi
    
    log INFO "Found AgentCore Runtime ARN: $AGENTCORE_RUNTIME_ARN"
    
    # Update Lambda environment variables
    local lambda_function_name="${RESOURCE_PREFIX}-${ENVIRONMENT}-AgentHandler-${VERSION}"
    
    # Create temporary JSON file for environment variables (avoids escaping issues)
    local temp_env_file="/tmp/lambda-env-${RANDOM}.json"
    cat > "$temp_env_file" << EOF
{
  "Variables": {
    "AGENTCORE_RUNTIME_ARN": "$AGENTCORE_RUNTIME_ARN",
    "USE_AGENTCORE": "true"
  }
}
EOF
    
    if aws lambda update-function-configuration \
        --function-name "$lambda_function_name" \
        --environment "file://$temp_env_file" \
        --profile "$AWS_PROFILE" > /dev/null 2>&1; then
        log INFO "Successfully updated Lambda environment variables for $lambda_function_name"
        rm -f "$temp_env_file"
    else
        log WARN "Failed to update Lambda environment variables for $lambda_function_name"
        log WARN "You may need to manually update the environment variables in the AWS console"
        rm -f "$temp_env_file"
    fi
}

# Function to update UI configuration with deployment values
update_ui_configuration() {
    if [ "$DRY_RUN" = true ]; then
        log INFO "DRY RUN: Would update UI configuration with deployment values"
        return 0
    fi
    
    log INFO "Updating UI configuration with deployment values..."
    
    # Get deployment values from CloudFormation
    local user_pool_id user_pool_client_id identity_pool_id bucket_name
    
    user_pool_id=$(aws cloudformation describe-stacks \
        --stack-name "${RESOURCE_PREFIX}-Auth-${ENVIRONMENT}" \
        --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
        --output text --profile "$AWS_PROFILE" 2>/dev/null)
    
    user_pool_client_id=$(aws cloudformation describe-stacks \
        --stack-name "${RESOURCE_PREFIX}-Auth-${ENVIRONMENT}" \
        --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' \
        --output text --profile "$AWS_PROFILE" 2>/dev/null)
    
    identity_pool_id=$(aws cloudformation describe-stacks \
        --stack-name "${RESOURCE_PREFIX}-Auth-${ENVIRONMENT}" \
        --query 'Stacks[0].Outputs[?OutputKey==`IdentityPoolId`].OutputValue' \
        --output text --profile "$AWS_PROFILE" 2>/dev/null)
    
    bucket_name=$(aws cloudformation describe-stacks \
        --stack-name "${RESOURCE_PREFIX}-Foundation-${ENVIRONMENT}" \
        --query 'Stacks[0].Outputs[?OutputKey==`DocumentBucketName`].OutputValue' \
        --output text --profile "$AWS_PROFILE" 2>/dev/null)
    
    # Get AgentCore runtime ARN if available
    local agentcore_runtime_arn=""
    if [ -f "agentcore/runtime_config.json" ]; then
        agentcore_runtime_arn=$(python3 -c "import json; data=json.load(open('agentcore/runtime_config.json')); print(data.get('runtime_arns', {}).get('coordinator', ''))" 2>/dev/null || echo "")
    fi
    
    # Create new .env file
    cat > "bda-cloudscape-ui/.env" << EOF
VITE_USER_POOL_ID=$user_pool_id
VITE_USER_POOL_CLIENT_ID=$user_pool_client_id
VITE_IDENTITY_POOL_ID=$identity_pool_id
VITE_AWS_REGION=$AWS_REGION
VITE_S3_BUCKET=$bucket_name
VITE_AGENTCORE_RUNTIME_ARN=$agentcore_runtime_arn
EOF
    
    log INFO "✅ UI configuration updated with deployment values"
}

# Configure Cognito MFA settings
configure_cognito_mfa() {
    if [ "$DRY_RUN" = true ]; then
        log INFO "DRY RUN: Would configure Cognito MFA to OPTIONAL"
        return 0
    fi

    log INFO "Configuring Cognito MFA settings..."

    # Get User Pool ID from CloudFormation
    local user_pool_id=$(aws cloudformation describe-stacks \
        --stack-name "${RESOURCE_PREFIX}-Auth-${ENVIRONMENT}" \
        --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
        --output text --profile "$AWS_PROFILE" 2>/dev/null)

    if [ -z "$user_pool_id" ] || [ "$user_pool_id" = "None" ]; then
        log WARN "Could not find User Pool ID, skipping MFA configuration"
        return 0
    fi

    log INFO "Found User Pool ID: $user_pool_id"

    # Set MFA to OPTIONAL (allows sign-in without MFA setup)
    if aws cognito-idp set-user-pool-mfa-config \
        --user-pool-id "$user_pool_id" \
        --mfa-configuration OPTIONAL \
        --software-token-mfa-configuration Enabled=true \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE" > /dev/null 2>&1; then
        log INFO "✅ MFA configured as OPTIONAL (users can sign in without MFA)"
    else
        log WARN "Failed to configure MFA (non-critical - may need manual configuration)"
    fi
}

# Build UI after configuration update
build_ui() {
    if [ "$SKIP_UI_BUILD" = true ]; then
        log INFO "Skipping UI build (--skip-ui-build or --quick specified)"
        log INFO "The frontend stack will deploy runtime config.json only"
        return 0
    fi

    if [ "$DRY_RUN" = true ]; then
        log INFO "DRY RUN: Would build UI"
        return 0
    fi

    log INFO "Building UI..."

    if [ ! -d "bda-cloudscape-ui" ]; then
        log WARN "UI directory not found, skipping UI build"
        return 0
    fi

    cd bda-cloudscape-ui

    log INFO "Installing UI dependencies..."
    if ! npm install; then
        log ERROR "Failed to install UI dependencies"
        cd ..
        return 1
    fi

    log INFO "Building UI..."
    if ! npm run build; then
        log ERROR "Failed to build UI"
        cd ..
        return 1
    fi

    cd ..
    log INFO "✅ UI built successfully"
}

# Helper function to format elapsed time
format_duration() {
    local seconds=$1
    local hours=$((seconds / 3600))
    local minutes=$(((seconds % 3600) / 60))
    local secs=$((seconds % 60))

    if [ $hours -gt 0 ]; then
        printf "%dh %dm %ds" $hours $minutes $secs
    elif [ $minutes -gt 0 ]; then
        printf "%dm %ds" $minutes $secs
    else
        printf "%ds" $secs
    fi
}

# Main deployment function
main() {
    # Capture start time
    local START_TIME=$(date +%s)
    local START_TIME_HUMAN=$(date '+%Y-%m-%d %H:%M:%S')

    # Initialize log file
    echo "Deployment started at $START_TIME_HUMAN" > "$LOG_FILE"

    log INFO "======================================================================="
    log INFO "Bedrock Data Automation (BDA) Pipeline Deployment"
    log INFO "Docker-Free Deployment with Integrated Lambda Layer Building"
    log INFO "======================================================================="
    log INFO "Start time: $START_TIME_HUMAN"
    log INFO ""

    # Parse arguments
    parse_arguments "$@"
    
    log INFO "Deployment Configuration:"
    log INFO "  AWS Profile: $AWS_PROFILE"
    log INFO "  Environment: $ENVIRONMENT"
    log INFO "  Version: $VERSION"
    log INFO "  Project: $PROJECT_NAME"
    log INFO "  Resource Prefix: $RESOURCE_PREFIX"
    log INFO "  Rebuild Layer: $REBUILD_LAYER"
    log INFO ""

    # Display deployment mode
    log INFO "Deployment Mode:"
    if [ "$QUICK_MODE" = true ]; then
        log INFO "  🚀 QUICK MODE - Infrastructure only (~10-15 min estimated)"
        log INFO "     ↳ Skipping: AgentCore images, UI build"
    elif [ "$CONFIG_ONLY" = true ]; then
        log INFO "  ⚡ CONFIG-ONLY MODE - Runtime config only (~5-8 min estimated)"
        log INFO "     ↳ Skipping: AgentCore images, UI build"
    elif [ "$SKIP_UI_BUILD" = true ]; then
        log INFO "  📦 SKIP-UI-BUILD MODE - Infrastructure + config (~15-20 min estimated)"
        log INFO "     ↳ Skipping: UI build"
    elif [ "$SKIP_AGENTCORE" = true ] && [ "$SKIP_UI" = false ]; then
        log INFO "  🐳 NO-AGENTCORE MODE - Infrastructure + UI (~25-30 min estimated)"
        log INFO "     ↳ Skipping: AgentCore Docker images"
    elif [ "$SKIP_UI" = true ] && [ "$SKIP_AGENTCORE" = false ]; then
        log INFO "  🎨 NO-UI MODE - Infrastructure + AgentCore (~30-35 min estimated)"
        log INFO "     ↳ Skipping: Frontend deployment"
    else
        log INFO "  🎯 FULL DEPLOYMENT - Complete infrastructure (~40-50 min estimated)"
        log INFO "     ↳ Includes: All stacks, AgentCore, UI"
    fi
    log INFO ""

    if [ "$DRY_RUN" = true ]; then
        log INFO "DRY RUN MODE - No actual deployment will occur"
        log INFO ""
    fi
    
    # Validate prerequisites (Docker not required)
    validate_prerequisites
    
    # Setup directory structure
    setup_directory_structure
    
    # Setup Python environment
    setup_python_environment
    
    # Prepare Lambda layer (this is where the magic happens!)
    prepare_lambda_layer
    
    # Validate AWS configuration
    validate_aws_configuration
    
    # Create or update .env file with AWS profile settings
    create_or_update_env_file
    
    # Validate API key configuration and show warnings
    validate_api_keys
    
    # Build and push AgentCore Docker images (default behavior)
    build_and_push_agentcore_images
    
    # Create CDK parameters
    create_cdk_parameters
    
    # Generate configuration files from templates
    generate_config_from_templates
    
    # Perform CDK bootstrap
    perform_cdk_bootstrap
    
    # Deploy CDK stack (excludes frontend stack)
    deploy_cdk_stack
    
    # Run post-deployment script to create/update AgentCore runtimes
    if [ "$DRY_RUN" = false ]; then
        log INFO "Running post-deployment script for AgentCore runtimes..."
        
        # Check if the script exists
        if [ -f "scripts/deploy_agentcore_runtimes.py" ]; then
            # Make script executable
            chmod +x scripts/deploy_agentcore_runtimes.py
            
            # Run the post-deployment script
            python3 scripts/deploy_agentcore_runtimes.py \
                --profile "$AWS_PROFILE" \
                --environment "$ENVIRONMENT" \
                --region "$AWS_REGION"
            
            if [ $? -eq 0 ]; then
                log INFO "AgentCore runtimes deployed successfully!"
            else
                log WARN "AgentCore runtime deployment had issues (check logs above)"
            fi
        else
            log WARN "Post-deployment script not found: scripts/deploy_agentcore_runtimes.py"
            log WARN "AgentCore runtimes not created/updated"
        fi
    fi
    
    # Create uploads folder
    create_uploads_folder
    
    # Update Lambda agent environment variables
    update_lambda_agent_variables
    
    # Configure Cognito MFA settings
    configure_cognito_mfa

    # Update UI configuration with deployment values
    update_ui_configuration

    # Build UI after configuration update
    build_ui

    # Deploy frontend stack after successful UI build
    if [ "$SKIP_UI" = false ] && [ "$DRY_RUN" = false ] && [ $? -eq 0 ]; then
        log INFO "Deploying frontend stack..."

        # Create stack suffix
        if [ -n "$DEPLOYMENT_ID" ]; then
            stack_suffix="${ENVIRONMENT}-${DEPLOYMENT_ID}"
        else
            stack_suffix="$ENVIRONMENT"
        fi

        if [ "$SKIP_UI_BUILD" = true ]; then
            log INFO "Deploying config.json only (UI dist not built)"
        else
            log INFO "Deploying UI dist and config.json"
        fi

        # Create CDK arguments for frontend deployment (matching main deployment)
        local frontend_cdk_args=(
            "deploy"
            "${RESOURCE_PREFIX}-Frontend-${stack_suffix}"
            "--context" "Environment=$ENVIRONMENT"
            "--context" "ResourceNamePrefix=$RESOURCE_PREFIX"
            "--context" "Version=$VERSION"
            "--context" "ProjectName=$PROJECT_NAME"
            "--profile" "$AWS_PROFILE"
            "--require-approval" "never"
        )

        # Add optional context parameters
        if [ -n "$DEPLOYMENT_ID" ]; then
            frontend_cdk_args+=("--context" "DeploymentId=$DEPLOYMENT_ID")
        fi

        if ! cdk "${frontend_cdk_args[@]}" 2>&1; then
            log ERROR "Frontend stack deployment failed"
            log ERROR "Check the output above for details"
            exit 1
        else
            if [ "$SKIP_UI_BUILD" = true ]; then
                log INFO "✅ Frontend config deployed successfully (runtime config.json only)"
            else
                log INFO "✅ Frontend stack deployed successfully (UI + config)"
            fi
        fi
    elif [ "$SKIP_UI" = true ]; then
        log INFO "Skipping frontend deployment (--skip-ui specified)"
    fi
    
    # Update .env file with CDK outputs
    if [ "$DRY_RUN" = false ]; then
        log INFO "Updating .env file with CDK deployment outputs..."
        
        if [ -f "scripts/update_env_from_cdk.py" ]; then
            python3 scripts/update_env_from_cdk.py \
                --profile "$AWS_PROFILE" \
                --environment "$ENVIRONMENT" \
                --env-file ".env"
            
            if [ $? -eq 0 ]; then
                log INFO "✅ .env file updated with deployment outputs"
            else
                log WARN "Could not update .env with all CDK outputs (non-critical)"
            fi
        else
            log WARN "update_env_from_cdk.py script not found (non-critical)"
        fi
    fi
    
    log INFO "======================================================================="
    log INFO "Deployment completed successfully!"
    log INFO "======================================================================="
    log INFO "Deployed stacks:"
    log INFO "  ✓ Foundation (Storage, DynamoDB)"
    log INFO "  ✓ Processing (Lambda functions)"
    log INFO "  ✓ Orchestration (Step Functions)"
    log INFO "  ✓ Knowledge Base (OpenSearch, Vector DB)"
    log INFO "  ✓ Automation (BDA Projects)"
    log INFO "  ✓ API Gateway (REST endpoints)"
    log INFO "  ✓ AgentCore Deployment (ECR, IAM roles)"
    log INFO "  ✓ Frontend (S3 + CloudFront)"
    
    if [ "$SKIP_AGENTCORE" = false ]; then
        log INFO "  ✓ AgentCore Images (with streaming & observability)"
        log INFO "  ✓ AgentCore Runtimes (4 agents deployed)"
    fi
    
    log INFO ""
    log INFO "Environment: $ENVIRONMENT"
    log INFO "S3 Bucket: Auto-generated unique name (check CloudFormation outputs)"
    log INFO "Lambda layer: Built successfully"
    log INFO "UI: Built and deployed to CloudFront"
    
    if [ "$SKIP_AGENTCORE" = false ]; then
        log INFO "AgentCore: Docker images built and deployed with:"
        log INFO "  • Real-time streaming support (SSE)"
        log INFO "  • Full OpenTelemetry observability"
        log INFO "  • CloudWatch metrics and structured logging"
        log INFO "  • Production-ready configuration"
    fi
    
    if [ "$DRY_RUN" = false ]; then
        log INFO ""
        log INFO "Next steps:"
        log INFO "1. Check AWS CloudFormation console for stack outputs and resource details"
        log INFO "2. Test the Step Functions state machines"
        
        if [ "$SKIP_AGENTCORE" = false ]; then
            log INFO "3. Test deployed agents: python3 agentcore/test_agentcore.py --profile $AWS_PROFILE"
            log INFO "4. Test streaming: python3 agentcore/test_streaming.py --profile $AWS_PROFILE --test all"
            log INFO "5. View metrics: CloudWatch → Application Signals → AgentCore/Production"
            log INFO "6. Upload test documents to the S3 bucket to trigger processing"
            log INFO "7. Access UI via CloudFront URL (see Frontend stack outputs)"
        else
            log INFO "3. Upload test documents to the S3 bucket to trigger processing"
            log INFO "4. Access UI via CloudFront URL (see Frontend stack outputs)"
        fi
    fi

    # Calculate and display deployment time
    local END_TIME=$(date +%s)
    local END_TIME_HUMAN=$(date '+%Y-%m-%d %H:%M:%S')
    local ELAPSED_SECONDS=$((END_TIME - START_TIME))
    local ELAPSED_FORMATTED=$(format_duration $ELAPSED_SECONDS)

    log INFO "======================================================================="
    log INFO ""
    log INFO "⏱️  Deployment Timing:"
    log INFO "   Start:    $START_TIME_HUMAN"
    log INFO "   End:      $END_TIME_HUMAN"
    log INFO "   Duration: $ELAPSED_FORMATTED"
    log INFO ""
    log INFO "======================================================================="
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi