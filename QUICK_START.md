# Quick Start - Fresh Deployment

## For a Brand New AWS Account/Environment

### Step 1: Configure AWS CLI Profile

```bash
# If you haven't already
aws configure --profile GenAI
# Enter: Access Key, Secret Key, Region (e.g., us-west-2), Output format (json)

# Verify it works
aws sts get-caller-identity --profile GenAI
```

### Step 2: Run Deployment

```bash
./deploy.sh --profile GenAI --environment Dev
```

**That's it!** The script will:
1. ✅ Deploy all CDK stacks (Foundation, Auth, Processing, etc.)
2. ✅ Configure Cognito MFA to OPTIONAL automatically
3. ✅ Generate `bda-cloudscape-ui/.env` with correct values from CloudFormation
4. ✅ Build the UI
5. ✅ Deploy Frontend to CloudFront

**Expected time:** 15-30 minutes (includes Docker builds for AgentCore)

---

## Step 3: Create Test User

After deployment completes:

```bash
# Get User Pool ID (automatically from CloudFormation)
USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name BDA-Auth-Dev \
    --profile GenAI \
    --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
    --output text)

echo "User Pool ID: $USER_POOL_ID"

# Create test user
aws cognito-idp admin-create-user \
    --user-pool-id $USER_POOL_ID \
    --username testuser1 \
    --user-attributes Name=email,Value=youremail@example.com \
    --temporary-password TempPass123! \
    --profile GenAI

# Set permanent password (skip forced password change)
aws cognito-idp admin-set-user-password \
    --user-pool-id $USER_POOL_ID \
    --username testuser1 \
    --password YourSecurePass123! \
    --permanent \
    --profile GenAI

echo "✅ Test user created: testuser1 / YourSecurePass123!"
```

---

## Step 4: Get CloudFront URL

```bash
aws cloudformation describe-stacks \
    --stack-name BDA-Frontend-Dev \
    --profile GenAI \
    --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontURL`].OutputValue' \
    --output text
```

Copy the URL and open in your browser.

---

## Step 5: Test It Works

1. **Sign in** with: `testuser1` / `YourSecurePass123!`
2. Navigate to **"Upload Documents"**
3. Upload a PDF file
4. **Expected:** Upload succeeds ✅

**Check browser console** - you should see:
```
✅ SUCCESS! Credentials obtained on attempt 1
Identity ID: us-west-2:xxxxx-xxxx-xxxx...
Uploading to S3 with key: uploads/us-west-2:xxxxx.../filename.pdf
Upload successful for: filename.pdf
```

---

## Deployment Options

### Skip AgentCore (Faster, No Docker Needed)
```bash
./deploy.sh --profile GenAI --environment Dev --skip-agentcore
```
**Time saved:** ~10 minutes (no Docker image builds)

### Rebuild Lambda Layers
```bash
./deploy.sh --profile GenAI --environment Dev --rebuild-layer
```
Use this if you update Lambda dependencies.

### Production Deployment
```bash
./deploy.sh --profile GenAI --environment Prod
```
Creates separate `Prod` stacks.

### Dry Run (Preview Changes)
```bash
./deploy.sh --profile GenAI --environment Dev --dry-run
```
Shows what would be deployed without actually deploying.

---

## What Gets Deployed

| Stack | Resources |
|-------|-----------|
| **BDA-Foundation-Dev** | S3 bucket (auto-generated unique name), DynamoDB tables |
| **BDA-Auth-Dev** | Cognito User Pool, Identity Pool, IAM roles |
| **BDA-Processing-Dev** | Lambda functions, Lambda layers |
| **BDA-Orchestration-Dev** | Step Functions state machines |
| **BDA-KnowledgeBase-Dev** | OpenSearch, Vector DB |
| **BDA-Automation-Dev** | Bedrock Projects |
| **BDA-API-Dev** | API Gateway REST endpoints |
| **BDA-AgentCoreDeployment-Dev** | ECR repositories, IAM roles, AgentCore runtimes |
| **BDA-Frontend-Dev** | S3 static site, CloudFront distribution |

**Total:** 9 CloudFormation stacks

---

## Troubleshooting

### Deployment Failed?

Check the log:
```bash
tail -f deployment.log
```

### MFA Still Required on Sign-In?

Manually configure it:
```bash
USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name BDA-Auth-Dev \
    --profile GenAI \
    --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
    --output text)

aws cognito-idp set-user-pool-mfa-config \
    --user-pool-id $USER_POOL_ID \
    --mfa-configuration OPTIONAL \
    --software-token-mfa-configuration Enabled=true \
    --region us-west-2 \
    --profile GenAI
```

### Upload Still Fails?

Check credentials in browser console:
- Should see: `hasCredentials: true, hasTokens: true, hasIdentityId: true`
- If false, sign out completely, clear browser storage, and sign in again

### Get All Stack Outputs

```bash
# List all stacks
aws cloudformation list-stacks --profile GenAI \
    --query "StackSummaries[?contains(StackName, 'BDA')].{Name:StackName,Status:StackStatus}" \
    --output table

# Get specific stack outputs
aws cloudformation describe-stacks \
    --stack-name BDA-Auth-Dev \
    --profile GenAI \
    --query 'Stacks[0].Outputs' \
    --output table
```

---

## For Different Environments

### Dev Environment (default)
```bash
./deploy.sh --profile GenAI --environment Dev
```
- Stacks: `BDA-*-Dev`
- User Pool: `BDA-Dev-UserPool-v1`

### Staging Environment
```bash
./deploy.sh --profile GenAI --environment Staging
```
- Stacks: `BDA-*-Staging`
- User Pool: `BDA-Staging-UserPool-v1`

### Production Environment
```bash
./deploy.sh --profile GenAI --environment Prod
```
- Stacks: `BDA-*-Prod`
- User Pool: `BDA-Prod-UserPool-v1`

Each environment is **completely isolated** with separate resources.

---

## Cleanup (Delete Everything)

To delete all resources:
```bash
./cleanup.sh --profile GenAI --environment Dev
```

This will:
1. Empty S3 buckets
2. Delete all CloudFormation stacks
3. Remove ECR repositories
4. Clean up local build artifacts

**Warning:** This is **irreversible**. All data will be lost.

---

## Key Points

✅ **No manual configuration needed** - Script does everything
✅ **No hardcoded values** - Everything from CloudFormation
✅ **Works on any AWS account** - Fully portable
✅ **Works from any computer** - No local config dependencies
✅ **Automatic MFA configuration** - No Console changes needed
✅ **Automatic .env generation** - UI config populated automatically

---

## Next Steps After Deployment

1. **Create users:**
   ```bash
   aws cognito-idp admin-create-user --user-pool-id $USER_POOL_ID --username user1 ...
   ```

2. **Test document upload** via UI

3. **Monitor processing:**
   - Check S3 bucket for uploaded files
   - Check DynamoDB tables for processing status
   - Check CloudWatch logs for Lambda execution

4. **Test AgentCore** (if deployed):
   ```bash
   python3 agentcore/test_agentcore.py --profile GenAI
   ```

5. **View metrics in CloudWatch:**
   - Go to CloudWatch → Application Signals
   - Look for AgentCore/Production metrics

---

## Support

- **Full documentation:** See `DEPLOYMENT_CHECKLIST.md`
- **Detailed logs:** Check `deployment.log`
- **Stack outputs:** Use AWS CloudFormation Console
- **Issues:** Check CloudWatch Logs for each Lambda function

---

**Ready to deploy?** Just run:
```bash
./deploy.sh --profile GenAI --environment Dev
```

That's all you need! ✨
