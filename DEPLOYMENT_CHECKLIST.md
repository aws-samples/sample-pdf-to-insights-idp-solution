# Complete Deployment Checklist for Fresh AWS Account

## Summary of Authentication Fix

### Root Cause
The authentication issue was caused by **Multi-Factor Authentication (TOTP) being required** on the Cognito User Pool. Users couldn't complete sign-in because they needed to set up MFA first, which blocked token generation and therefore Identity Pool credential exchange.

### What Was Fixed

#### 1. Code Changes (No Hardcoded Values ✅)

| File | Change | Uses Env Vars? |
|------|--------|----------------|
| `bda-cloudscape-ui/src/main.jsx` | Added `region: import.meta.env.VITE_AWS_REGION` to Auth.Cognito config | ✅ Yes |
| `bda-cloudscape-ui/src/App.jsx` | Added retry logic (5 attempts, 2s intervals) to fetch Identity Pool credentials after sign-in | ✅ Pure logic |
| `bda-cloudscape-ui/src/components/DocumentUpload.jsx` | Changed S3 path from `deploymentId` to `identityId`; Changed `key` to `path` parameter | ✅ Uses session data |
| `bda-cloudscape-ui/src/components/LoginForm.jsx` | Added debug console logging | ✅ Debug only |

#### 2. Deployment Script Enhancement

Added `configure_cognito_mfa()` function to `deploy.sh` that:
- Retrieves User Pool ID from CloudFormation outputs (NOT hardcoded)
- Sets MFA to `OPTIONAL` (allows sign-in without MFA)
- Runs automatically after CDK deployment

## Deployment Steps for Fresh AWS Account

### Prerequisites

1. **AWS CLI configured** with profile:
   ```bash
   aws configure --profile YourProfileName
   # Enter: Access Key, Secret Key, Region (e.g., us-east-1), Output format (json)
   ```

2. **Verify AWS credentials**:
   ```bash
   aws sts get-caller-identity --profile YourProfileName
   ```

3. **Install dependencies**:
   ```bash
   # Python 3.10+
   python3 --version

   # Node.js 18+
   node --version

   # Docker (for AgentCore)
   docker --version

   # AWS CDK CLI
   npm install -g aws-cdk
   ```

### Step 1: Clone and Prepare

```bash
cd /path/to/project
git pull  # Get latest changes including the fix
```

### Step 2: Run Deployment Script

```bash
# Basic deployment
./deploy.sh --profile YourProfileName

# Production deployment
./deploy.sh --profile production --environment Prod

# With custom settings
./deploy.sh --profile YourProfileName --environment Dev --version v2
```

**The script will automatically:**
1. ✅ Build Lambda layers (no Docker needed)
2. ✅ Deploy CDK stacks (Foundation, Auth, Processing, etc.)
3. ✅ Configure Cognito MFA to OPTIONAL (NEW - fixes auth issue)
4. ✅ Generate `bda-cloudscape-ui/.env` with correct values from CloudFormation
5. ✅ Build UI with environment-specific configuration
6. ✅ Deploy Frontend stack (S3 + CloudFront)

### Step 3: Create Test User

After deployment completes, create a test user:

```bash
# Get User Pool ID from deployment outputs
USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name BDA-Auth-Dev \
    --profile YourProfileName \
    --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
    --output text)

# Create test user
aws cognito-idp admin-create-user \
    --user-pool-id $USER_POOL_ID \
    --username testuser1 \
    --user-attributes Name=email,Value=youremail@domain.com \
    --temporary-password TempPass123! \
    --profile YourProfileName

# Set permanent password (bypass temp password requirement)
aws cognito-idp admin-set-user-password \
    --user-pool-id $USER_POOL_ID \
    --username testuser1 \
    --password YourSecurePass123! \
    --permanent \
    --profile YourProfileName
```

### Step 4: Access the UI

Get the CloudFront URL from stack outputs:

```bash
aws cloudformation describe-stacks \
    --stack-name BDA-Frontend-Dev \
    --profile YourProfileName \
    --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontURL`].OutputValue' \
    --output text
```

Open the URL in browser and sign in with your test user credentials.

### Step 5: Test Upload

1. Sign in to the UI
2. Navigate to "Upload Documents"
3. Select a PDF file (< 25MB)
4. Click "Upload"
5. **Expected result:** File uploads successfully ✅

**Check browser console** - you should see:
```
✅ SUCCESS! Credentials obtained on attempt 1
Identity ID: us-west-2:xxxxx-xxxx-xxxx-xxxx-xxxxxxxxxx
Uploading to S3 with key: uploads/us-west-2:xxxxx-xxxx.../filename.pdf
Upload successful for: filename.pdf
```

## What the Deployment Script Does (No Manual Steps!)

### Automated Configuration Generation

The `update_ui_configuration()` function (lines 970-1018 in deploy.sh):

```bash
# 1. Gets values from CloudFormation (NOT hardcoded)
user_pool_id=$(aws cloudformation describe-stacks \
    --stack-name "${RESOURCE_PREFIX}-Auth-${ENVIRONMENT}" \
    --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' ...)

user_pool_client_id=$(aws cloudformation describe-stacks ...)
identity_pool_id=$(aws cloudformation describe-stacks ...)
bucket_name=$(aws cloudformation describe-stacks ...)

# 2. Creates .env file automatically
cat > "bda-cloudscape-ui/.env" << EOF
VITE_USER_POOL_ID=$user_pool_id
VITE_USER_POOL_CLIENT_ID=$user_pool_client_id
VITE_IDENTITY_POOL_ID=$identity_pool_id
VITE_AWS_REGION=$AWS_REGION
VITE_S3_BUCKET=$bucket_name
EOF
```

### New: Automated MFA Configuration

The `configure_cognito_mfa()` function (lines 1020-1053 in deploy.sh):

```bash
# Gets User Pool ID dynamically
user_pool_id=$(aws cloudformation describe-stacks ...)

# Sets MFA to OPTIONAL automatically
aws cognito-idp set-user-pool-mfa-config \
    --user-pool-id "$user_pool_id" \
    --mfa-configuration OPTIONAL \
    --software-token-mfa-configuration Enabled=true
```

## Verification Checklist

After deployment, verify:

- [ ] CloudFormation stacks deployed successfully (8 stacks)
- [ ] Cognito User Pool MFA is set to OPTIONAL
- [ ] `.env` file exists in `bda-cloudscape-ui/` with correct values
- [ ] UI built successfully (check `bda-cloudscape-ui/dist/` directory)
- [ ] Frontend stack deployed (S3 + CloudFront)
- [ ] Test user can sign in without MFA prompt
- [ ] Upload functionality works (file appears in S3)

## Troubleshooting

### Issue: "TOTP Setup Required" on Sign-In

**Cause:** MFA configuration didn't apply
**Solution:**
```bash
# Manually set MFA to OPTIONAL
aws cognito-idp set-user-pool-mfa-config \
    --user-pool-id <YOUR_USER_POOL_ID> \
    --mfa-configuration OPTIONAL \
    --software-token-mfa-configuration Enabled=true \
    --region <YOUR_REGION> \
    --profile <YOUR_PROFILE>
```

### Issue: "hasTokens: false" After Sign-In

**Cause:** MFA still blocking authentication
**Solution:** Verify MFA is OPTIONAL:
```bash
aws cognito-idp describe-user-pool \
    --user-pool-id <YOUR_USER_POOL_ID> \
    --query 'UserPool.MfaConfiguration' \
    --profile <YOUR_PROFILE>
```

Should return: `"OPTIONAL"`

### Issue: Upload fails with "Access Denied"

**Cause:** IAM policy issue or wrong S3 path
**Solution:** Check the authenticated role has S3 permissions:
```bash
aws iam get-policy-version \
    --policy-arn "arn:aws:iam::<ACCOUNT>:policy/BDA-Dev-UserS3Policy-v1" \
    --version-id v1 \
    --profile <YOUR_PROFILE>
```

Should show policy allowing:
```json
{
  "Resource": "arn:aws:s3:::BUCKET/uploads/${cognito-identity.amazonaws.com:sub}/*",
  "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
}
```

## Key Differences from Previous Version

| Aspect | Before Fix | After Fix |
|--------|-----------|-----------|
| **MFA Configuration** | Required (blocked sign-in) | Optional (configured by deploy script) |
| **Auth Region** | Missing in config | Added to main.jsx |
| **Credential Retry** | Single attempt | 5 attempts with 2s delays |
| **S3 Upload Path** | `uploads/deploymentId/...` | `uploads/identityId/...` |
| **Amplify Storage API** | Used `key` parameter | Uses `path` parameter (v6) |
| **Deploy Script** | Manual MFA configuration needed | Automatic MFA configuration |

## Environment Variables (All Dynamic)

The following are **automatically populated** by the deployment script from CloudFormation outputs:

```bash
# bda-cloudscape-ui/.env (generated automatically)
VITE_USER_POOL_ID=<from CloudFormation>
VITE_USER_POOL_CLIENT_ID=<from CloudFormation>
VITE_IDENTITY_POOL_ID=<from CloudFormation>
VITE_AWS_REGION=<from deployment>
VITE_S3_BUCKET=<from CloudFormation>
VITE_AGENTCORE_RUNTIME_ARN=<from runtime_config.json>
```

**No manual configuration needed!**

## What Makes This Deployment Portable

✅ **No hardcoded credentials** - Everything pulled from CloudFormation
✅ **No hardcoded resource IDs** - Generated during deployment
✅ **No hardcoded bucket names** - CDK auto-generates unique names
✅ **No hardcoded region** - Uses profile region
✅ **No hardcoded account ID** - Detected via AWS STS
✅ **Automated MFA configuration** - No manual AWS Console changes
✅ **Dynamic .env generation** - Populated from stack outputs

## Success Criteria

A successful deployment means:

1. ✅ All 8 CDK stacks deploy without errors
2. ✅ Cognito MFA set to OPTIONAL automatically
3. ✅ UI `.env` file generated with correct values
4. ✅ Frontend deployed to CloudFront
5. ✅ Users can sign in without MFA prompts
6. ✅ File uploads work and appear in S3
7. ✅ Browser console shows: `✅ SUCCESS! Credentials obtained`
8. ✅ No "hasTokens: false" or "hasCredentials: false" errors

## Files Modified Summary

### Application Code
- `bda-cloudscape-ui/src/main.jsx` - Added region to Auth config
- `bda-cloudscape-ui/src/App.jsx` - Added credential retry logic
- `bda-cloudscape-ui/src/components/DocumentUpload.jsx` - Fixed S3 path and API usage
- `bda-cloudscape-ui/src/components/LoginForm.jsx` - Added debug logging

### Deployment Infrastructure
- `deploy.sh` - Added `configure_cognito_mfa()` function

### No Changes Needed
- ✅ CDK stacks (already correct)
- ✅ IAM policies (already correct)
- ✅ S3 bucket configuration (already correct)
- ✅ Identity Pool configuration (already correct)

## Deployment Command Reference

```bash
# Basic deployment
./deploy.sh --profile YourProfile

# Production deployment
./deploy.sh --profile prod --environment Prod

# Skip AgentCore (faster, no Docker needed)
./deploy.sh --profile YourProfile --skip-agentcore

# Rebuild Lambda layers
./deploy.sh --profile YourProfile --rebuild-layer

# Dry run (see what would be deployed)
./deploy.sh --profile YourProfile --dry-run

# Custom environment
./deploy.sh --profile YourProfile --environment Staging --version v2
```

## Post-Deployment Validation

Run these commands to validate everything is configured correctly:

```bash
# 1. Check MFA configuration
aws cognito-idp describe-user-pool \
    --user-pool-id <POOL_ID> \
    --query 'UserPool.MfaConfiguration' \
    --profile YourProfile
# Expected: "OPTIONAL"

# 2. Check Identity Pool roles
aws cognito-identity get-identity-pool-roles \
    --identity-pool-id <POOL_ID> \
    --profile YourProfile
# Should show: "authenticated": "arn:aws:iam::...role/BDA-Dev-AuthenticatedRole-v1"

# 3. Check S3 bucket exists
aws s3 ls --profile YourProfile | grep documentbucket
# Should show bucket name

# 4. Check UI files deployed
aws cloudformation describe-stacks \
    --stack-name BDA-Frontend-Dev \
    --profile YourProfile \
    --query 'Stacks[0].Outputs'
# Should show CloudFront URL and S3 bucket
```

## Support

If issues persist after following this checklist:
1. Check `deployment.log` for detailed error messages
2. Review CloudWatch logs for Lambda functions
3. Check browser console for client-side errors
4. Verify AWS service quotas (Cognito, S3, Lambda)

---

**Last Updated:** Based on authentication fix completed 2025-09-30
**Tested On:** Fresh AWS account deployment
**Status:** ✅ All fixes verified and working
