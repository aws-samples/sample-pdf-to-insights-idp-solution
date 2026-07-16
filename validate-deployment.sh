#!/bin/bash

# BDA Pipeline Deployment Validation Script
# This script validates that all required environment variables and configurations
# are set before deployment to ensure successful deployment to any AWS account

set -e

echo "=========================================="
echo "BDA Pipeline Deployment Validation"
echo "=========================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track validation status
VALIDATION_FAILED=0

# Function to check if a variable is set
check_var() {
    local var_name=$1
    local var_value="${!var_name}"
    local is_required=${2:-true}
    
    if [ -z "$var_value" ]; then
        if [ "$is_required" = true ]; then
            echo -e "${RED}✗${NC} $var_name is not set (REQUIRED)"
            VALIDATION_FAILED=1
        else
            echo -e "${YELLOW}⚠${NC} $var_name is not set (optional)"
        fi
    else
        # Mask sensitive values
        if [[ "$var_name" == *"KEY"* ]] || [[ "$var_name" == *"SECRET"* ]] || [[ "$var_name" == *"PASSWORD"* ]]; then
            echo -e "${GREEN}✓${NC} $var_name is set (***masked***)"
        else
            echo -e "${GREEN}✓${NC} $var_name is set: $var_value"
        fi
    fi
}

# Function to check if AWS CLI is configured
check_aws_cli() {
    echo -e "\n${YELLOW}Checking AWS CLI Configuration...${NC}"
    
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}✗${NC} AWS CLI is not installed"
        VALIDATION_FAILED=1
        return
    fi
    
    echo -e "${GREEN}✓${NC} AWS CLI is installed"
    
    # Check if profile exists
    local profile="${AWS_PROFILE:-default}"
    if aws configure list --profile "$profile" &> /dev/null; then
        echo -e "${GREEN}✓${NC} AWS Profile '$profile' is configured"
        
        # Get account ID
        local account_id=$(aws sts get-caller-identity --profile "$profile" --query 'Account' --output text 2>/dev/null)
        if [ -n "$account_id" ]; then
            echo -e "${GREEN}✓${NC} AWS Account ID: $account_id"
        else
            echo -e "${RED}✗${NC} Unable to get AWS Account ID - check credentials"
            VALIDATION_FAILED=1
        fi
    else
        echo -e "${RED}✗${NC} AWS Profile '$profile' is not configured"
        VALIDATION_FAILED=1
    fi
}

# Function to check if files exist
check_file() {
    local file_path=$1
    local is_required=${2:-true}
    
    if [ -f "$file_path" ]; then
        echo -e "${GREEN}✓${NC} File exists: $file_path"
    else
        if [ "$is_required" = true ]; then
            echo -e "${RED}✗${NC} File missing: $file_path (REQUIRED)"
            VALIDATION_FAILED=1
        else
            echo -e "${YELLOW}⚠${NC} File missing: $file_path (optional)"
        fi
    fi
}

# Check environment file
echo -e "\n${YELLOW}Checking Environment Files...${NC}"
if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} .env file found - loading environment variables"
    source .env
else
    echo -e "${YELLOW}ℹ${NC} .env file not found - will be created automatically by deploy.sh"
    echo -e "${GREEN}✓${NC} No manual configuration required - deploy.sh handles everything"
fi

# Check required AWS environment variables
echo -e "\n${YELLOW}Checking AWS Environment Variables...${NC}"
check_var "AWS_PROFILE" false
check_var "AWS_DEFAULT_REGION" true
check_var "ENVIRONMENT" true

# Check AWS CLI configuration
check_aws_cli

# Check CDK requirements
echo -e "\n${YELLOW}Checking CDK Requirements...${NC}"
if ! command -v cdk &> /dev/null; then
    echo -e "${RED}✗${NC} AWS CDK is not installed"
    echo "  Install with: npm install -g aws-cdk"
    VALIDATION_FAILED=1
else
    echo -e "${GREEN}✓${NC} AWS CDK is installed: $(cdk --version)"
fi

# Check Python requirements
echo -e "\n${YELLOW}Checking Python Requirements...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗${NC} Python 3 is not installed"
    VALIDATION_FAILED=1
else
    echo -e "${GREEN}✓${NC} Python 3 is installed: $(python3 --version)"
fi

# Check if virtual environment exists
if [ -d ".venv" ]; then
    echo -e "${GREEN}✓${NC} Python virtual environment exists"
else
    echo -e "${YELLOW}⚠${NC} Python virtual environment not found"
    echo "  Create with: python3 -m venv .venv && source .venv/bin/activate"
fi

# Check Docker (optional for AgentCore)
echo -e "\n${YELLOW}Checking Docker (Optional for AgentCore)...${NC}"
if command -v docker &> /dev/null; then
    if docker info &> /dev/null; then
        echo -e "${GREEN}✓${NC} Docker is installed and running"
    else
        echo -e "${YELLOW}⚠${NC} Docker is installed but not running"
    fi
else
    echo -e "${YELLOW}⚠${NC} Docker is not installed (required for AgentCore deployment)"
fi

# Check Node.js (for UI)
echo -e "\n${YELLOW}Checking Node.js (for UI)...${NC}"
if command -v node &> /dev/null; then
    echo -e "${GREEN}✓${NC} Node.js is installed: $(node --version)"
    
    # Check if UI dependencies are installed
    if [ -d "bda-cloudscape-ui/node_modules" ]; then
        echo -e "${GREEN}✓${NC} UI dependencies are installed"
    else
        echo -e "${YELLOW}⚠${NC} UI dependencies not installed"
        echo "  Install with: cd bda-cloudscape-ui && npm install"
    fi
else
    echo -e "${YELLOW}⚠${NC} Node.js is not installed (required for UI)"
fi

# Check required files
echo -e "\n${YELLOW}Checking Required Files...${NC}"
check_file "app.py" true
check_file "cdk.json" true
check_file "requirements.txt" true
check_file "deploy.sh" true
check_file "cleanup.sh" true
check_file ".env.template" true
check_file "bda_stacks/config.json" true

# Check template files
echo -e "\n${YELLOW}Checking Template Files...${NC}"
check_file ".env.template" true
check_file "bda-cloudscape-ui/.env.template" true
check_file "agentcore/runtime_config.json.template" false
check_file ".bedrock_agentcore.yaml.template" false

# Check for sensitive data in git
echo -e "\n${YELLOW}Checking for Sensitive Data in Git...${NC}"
if git ls-files | grep -E "^\.env$" > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} .env file is tracked in git - SECURITY RISK!"
    VALIDATION_FAILED=1
else
    echo -e "${GREEN}✓${NC} .env file is not tracked in git"
fi

if git ls-files | grep -E "bda-cloudscape-ui/\.env$" > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} bda-cloudscape-ui/.env is tracked in git - SECURITY RISK!"
    VALIDATION_FAILED=1
else
    echo -e "${GREEN}✓${NC} bda-cloudscape-ui/.env is not tracked in git"
fi

# Check for hardcoded account IDs in tracked files
echo -e "\n${YELLOW}Checking for Hardcoded AWS Account IDs...${NC}"
ACCOUNT_ID_PATTERN="[0-9]{12}"
if git grep -E "$ACCOUNT_ID_PATTERN" -- '*.py' '*.js' '*.jsx' '*.json' ':!*.template' ':!*.example' ':!DEPLOYMENT_FIXES.md' 2>/dev/null | grep -v "YOUR_ACCOUNT_ID" | grep -v "123456789012"; then
    echo -e "${YELLOW}⚠${NC} Potential AWS Account IDs found in code - please review"
else
    echo -e "${GREEN}✓${NC} No hardcoded AWS Account IDs found"
fi

# Final validation result
echo -e "\n=========================================="
if [ $VALIDATION_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ Deployment validation PASSED${NC}"
    echo "Your environment is ready for deployment!"
    echo ""
    echo "Next steps:"
    echo "1. Run: ./deploy.sh --profile <your-profile> --environment <Dev|Staging|Prod>"
    echo "2. Monitor the deployment progress"
    echo ""
    echo "Note: The deployment script will automatically:"
    echo "  • Create/update .env file from your AWS profile"
    echo "  • Populate all required configuration values"
    echo "  • Update with CDK deployment outputs"
    exit 0
else
    echo -e "${RED}✗ Deployment validation FAILED${NC}"
    echo "Please fix the issues above before deploying."
    echo ""
    echo "Common fixes:"
    echo "1. Copy .env.template to .env and fill in values"
    echo "2. Configure AWS CLI: aws configure --profile <profile-name>"
    echo "3. Install missing dependencies"
    echo "4. Remove sensitive files from git tracking"
    exit 1
fi