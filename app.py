from aws_cdk import (
    App,
    Environment,
    Tags,
    Aspects,
    Stack
)
from cdk_nag import AwsSolutionsChecks, NagSuppressions
from bda_stacks.storage_stack import BDAStorageStack
from bda_stacks.resources_stack import BDAResourcesStack
from bda_stacks.step_functions_stack import BDAStepFunctionsStack
from bda_stacks.knowledge_base_stack import BDAKnowledgeBaseStack
from bda_stacks.project_stack import BedrockProjectStack
from bda_stacks.api_gateway_stack import BDAApiGatewayStack
from bda_stacks.agentcore_deployment_stack import BDAAgentCoreDeploymentStack
from bda_stacks.bda_auth_stack import BDAAuthStack
from bda_stacks.frontend_stack import BDAFrontendStack
import os

app = App()

# Get context variables with defaults
# Bucket configuration options:
# - None (default): CDK auto-generates unique bucket name
# - ExistingBucketName: Import an existing bucket
# - CustomBucketName: Use a specific custom bucket name
existing_bucket_name = app.node.try_get_context('ExistingBucketName')
custom_bucket_name = app.node.try_get_context('CustomBucketName')
resource_prefix = app.node.try_get_context('ResourceNamePrefix') or 'BDA'
deployment_environment = app.node.try_get_context('Environment') or 'Dev'
version = app.node.try_get_context('Version') or 'v1'
project_name = app.node.try_get_context('ProjectName') or 'DocumentAutomation'
deployment_id = app.node.try_get_context('DeploymentId')  # Optional deployment identifier

# Build deployment info string
deployment_info = f"{project_name} stacks for {deployment_environment} environment (version {version})"
if deployment_id:
    deployment_info += f" [Deployment ID: {deployment_id}]"
print(f"Deploying {deployment_info}")

# Log bucket configuration
if existing_bucket_name:
    print(f"Using existing bucket: {existing_bucket_name}")
elif custom_bucket_name:
    print(f"Using custom bucket name: {custom_bucket_name}")
else:
    print("Using CDK auto-generated bucket name (recommended for multiple deployments)")

# Create the environment object with account and region
env = Environment(
    account=os.environ.get('CDK_DEFAULT_ACCOUNT'),
    region=os.environ.get('CDK_DEFAULT_REGION')
)

# Define common tags for all stacks
common_tags = {
    'Project': f'{resource_prefix}-{project_name}',
    'Environment': deployment_environment,
    'Version': version,
    'Owner': 'DataEngineering',
    'ManagedBy': 'CDK',
    'Purpose': 'DocumentProcessingAutomation'
}

# Create stack names using the functional grouping approach
# Include deployment ID if provided for complete stack isolation
if deployment_id:
    stack_suffix = f"{deployment_environment}-{deployment_id}"
else:
    stack_suffix = deployment_environment

auth_stack_name = f"{resource_prefix}-Auth-{stack_suffix}"
foundation_stack_name = f"{resource_prefix}-Foundation-{stack_suffix}"
processing_stack_name = f"{resource_prefix}-Processing-{stack_suffix}"
orchestration_stack_name = f"{resource_prefix}-Orchestration-{stack_suffix}"
knowledge_base_stack_name = f"{resource_prefix}-KnowledgeBase-{stack_suffix}"
automation_stack_name = f"{resource_prefix}-Automation-{stack_suffix}"
api_stack_name = f"{resource_prefix}-API-{stack_suffix}"
agentcore_deployment_stack_name = f"{resource_prefix}-AgentCoreDeployment-{stack_suffix}"
frontend_stack_name = f"{resource_prefix}-Frontend-{stack_suffix}"

print(f"Creating stacks:")
print(f"  - {auth_stack_name}")
print(f"  - {foundation_stack_name}")
print(f"  - {processing_stack_name}")
print(f"  - {orchestration_stack_name}")
print(f"  - {knowledge_base_stack_name}")
print(f"  - {automation_stack_name}")
print(f"  - {api_stack_name}")
print(f"  - {agentcore_deployment_stack_name}")
print(f"  - {frontend_stack_name}")

# Create the foundation stack first (storage, IAM, basic infrastructure)
foundation_stack = BDAStorageStack(
    app, foundation_stack_name,
    existing_bucket_name=existing_bucket_name,
    custom_bucket_name=custom_bucket_name,
    deployment_env=deployment_environment,  # Changed from 'environment' to 'deployment_env'
    version=version,
    deployment_id=deployment_id,
    env=env
)

# Create the auth stack (Cognito authentication) - needs foundation stack for S3 bucket
auth_stack = BDAAuthStack(
    app, auth_stack_name,
    storage_stack=foundation_stack,
    environment=deployment_environment,
    version=version,
    env=env
)

# Create the processing stack (Lambda functions, compute resources)
processing_stack = BDAResourcesStack(
    app, processing_stack_name,
    storage_stack=foundation_stack,
    deployment_env=deployment_environment,  # Changed from 'environment' to 'deployment_env'
    version=version,
    deployment_id=deployment_id,
    env=env
)

# Create the orchestration stack (Step Functions, EventBridge)
orchestration_stack = BDAStepFunctionsStack(
    app, orchestration_stack_name,
    resources_stack=processing_stack,
    deployment_env=deployment_environment,  # Changed from 'environment' to 'deployment_env'
    version=version,
    deployment_id=deployment_id,
    env=env
)

# Create the knowledge base stack (for use by Strand Agents)
knowledge_base_stack = BDAKnowledgeBaseStack(
    app, knowledge_base_stack_name,
    storage_stack=foundation_stack,
    deployment_env=deployment_environment,  # Changed from 'environment' to 'deployment_env'
    version=version,
    deployment_id=deployment_id,
    env=env
)

# Create the automation stack (BDA projects, data processing)
automation_stack = BedrockProjectStack(
    app, automation_stack_name,
    storage_stack=foundation_stack,
    deployment_env=deployment_environment,  # Changed from 'environment' to 'deployment_env'
    version=version,
    deployment_id=deployment_id,
    env=env
)

# Create the API Gateway stack (REST API for UI)
api_stack = BDAApiGatewayStack(
    app, api_stack_name,
    storage_stack=foundation_stack,
    resources_stack=processing_stack,
    step_functions_stack=orchestration_stack,
    knowledge_base_stack=knowledge_base_stack,
    automation_stack=automation_stack,
    auth_stack=auth_stack,
    deployment_env=deployment_environment,
    version=version,
    deployment_id=deployment_id,
    env=env
)

# Create the AgentCore deployment stack (ECR repositories and IAM roles)
agentcore_deployment_stack = BDAAgentCoreDeploymentStack(
    app, agentcore_deployment_stack_name,
    knowledge_base_stack=knowledge_base_stack,
    deployment_env=deployment_environment,
    version=version,
    deployment_id=deployment_id,
    env=env
)

# Create the frontend stack (S3 + CloudFront for UI)
frontend_stack = BDAFrontendStack(
    app, frontend_stack_name,
    storage_stack=foundation_stack,
    auth_stack=auth_stack,
    deployment_env=deployment_environment,
    env=env,
    version=version
)

# Add explicit dependencies to ensure stacks are created in correct order
auth_stack.add_dependency(foundation_stack)
processing_stack.add_dependency(foundation_stack)
orchestration_stack.add_dependency(processing_stack)
knowledge_base_stack.add_dependency(foundation_stack)
automation_stack.add_dependency(foundation_stack)
api_stack.add_dependency(orchestration_stack)
api_stack.add_dependency(knowledge_base_stack)
api_stack.add_dependency(automation_stack)
agentcore_deployment_stack.add_dependency(knowledge_base_stack)
# frontend_stack.add_dependency(agentcore_deployment_stack)

# Setup S3 event handler in API stack to avoid circular dependencies
api_stack.add_s3_event_handler(
    step_function_arn=orchestration_stack.parent_state_machine.state_machine_arn,
    project_arn=automation_stack.bda_project_cr.get_att_string("ProjectArn"),
    deployment_env=deployment_environment,
    version=version,
    deployment_id=deployment_id
)

# Apply common tags to all stacks
for stack in [auth_stack, foundation_stack, processing_stack, orchestration_stack, knowledge_base_stack, 
              automation_stack, api_stack, agentcore_deployment_stack, frontend_stack]:
    for key, value in common_tags.items():
        Tags.of(stack).add(key, value)

print(f"Stack dependencies configured for proper deployment order")

# Enable CDK Nag security and best practices checks with proper Aspects pattern
print("Enabling CDK Nag security and best practices checks...")
Aspects.of(app).add(AwsSolutionsChecks(verbose=True))

# Add suppressions for common acceptable findings across all stacks
common_suppressions = [
    {
        "id": "AwsSolutions-IAM4",
        "reason": "AWS managed policies are acceptable for Lambda execution roles"
    },
    {
        "id": "AwsSolutions-L1",
        "reason": "Lambda runtime versions are managed and updated regularly"
    },
    {
        "id": "AwsSolutions-S1",
        "reason": "S3 server access logging not required for document storage bucket in development"
    },
    {
        "id": "AwsSolutions-S10",
        "reason": "S3 bucket policy explicitly denies all requests that do not use SSL/HTTPS via aws:SecureTransport condition"
    }
]

# Add specific IAM wildcard suppressions for each stack
iam_wildcard_suppressions = [
    {
        "id": "AwsSolutions-IAM5",
        "reason": "Wildcard permissions required for S3 object operations on user upload paths and document processing",
        "appliesTo": [
            "Resource::<DocumentBucketAE41E5A9.Arn>/public/uploads/*",
            "Resource::<DocumentBucketAE41E5A9.Arn>/uploads/*",
            "Resource::<DocumentBucketAE41E5A9.Arn>/extracted-Markdown/*",
            "Resource::<DocumentBucketAE41E5A9.Arn>/*"
        ]
    },
    {
        "id": "AwsSolutions-IAM5",
        "reason": "Wildcard permissions required for DynamoDB GSI access patterns",
        "appliesTo": [
            "Resource::<ProcessingStatusTableBB30F634.Arn>/index/*"
        ]
    },
    {
        "id": "AwsSolutions-IAM5",
        "reason": "Bedrock wildcard permissions required for dynamic resource access. Data automation projects and blueprints are created dynamically at runtime and cannot be predefined with specific ARNs. This is required for the Step Functions workflow to invoke Bedrock data automation services across different projects and blueprints. References: https://docs.aws.amazon.com/bedrock/latest/userguide/data-automation-projects.html",
        "appliesTo": [
            "Resource::arn:aws:bedrock:*:*:blueprint/*",
            "Resource::arn:aws:bedrock:*:*:data-automation-project/*",
            f"Resource::arn:aws:bedrock:{env.region if env.region else '*'}:{env.account if env.account else '*'}:blueprint/*",
            f"Resource::arn:aws:bedrock:{env.region if env.region else '*'}:{env.account if env.account else '*'}:data-automation-project/*",
            f"Resource::arn:aws:bedrock:{env.region if env.region else '*'}:{env.account if env.account else '*'}:agent-alias/*/*",
            f"Resource::arn:aws:bedrock-agentcore:{env.region if env.region else '*'}:{env.account if env.account else '*'}:runtime/*",
            f"Resource::arn:aws:bedrock:{env.region if env.region else '*'}:{env.account if env.account else '*'}:*"
        ]
    },
    {
        "id": "AwsSolutions-IAM5",
        "reason": "Wildcard permissions required for S3 bucket operations",
        "appliesTo": [
            "Action::s3:GetBucket*",
            "Action::s3:GetObject*",
            "Action::s3:List*",
            "Action::s3:Abort*",
            "Action::s3:DeleteObject*"
        ]
    },
    {
        "id": "AwsSolutions-IAM5",
        "reason": "Wildcard permissions required for Step Functions and EventBridge operations",
        "appliesTo": [
            f"Resource::arn:aws:states:{env.region}:{env.account}:stateMachine:BDA-{deployment_environment}-*",
            f"Resource::arn:aws:events:{env.region}:{env.account}:rule/BDA-{deployment_environment}-*",
            f"Resource::arn:aws:states:{env.region}:{env.account}:*"
        ]
    },
    {
        "id": "AwsSolutions-IAM5",
        "reason": "Wildcard permissions required for cross-service operations, Bedrock Data Automation, AgentCore, and resource management",
        "appliesTo": [
            "Resource::*"
        ]
    }
]

# Add warning suppressions for Lambda environment and EventBridge
warning_suppressions = [
    {
        "id": "UnclearLambdaEnvironment",
        "reason": "Lambda functions are imported from other stacks with resolved environments"
    },
    {
        "id": "@aws-cdk/aws-events:ruleUnresolvedEnvironment",
        "reason": "EventBridge rules and targets are in the same environment, cross-environment setup not needed"
    }
]

# Add CDK-specific suppressions
cdk_suppressions = [
    {
        "id": "AwsSolutions-IAM5",
        "reason": "CDK bucket deployment requires wildcard permissions for asset operations",
        "appliesTo": [
            "Resource::arn:aws:s3:::cdk-*/*",
            f"Resource::arn:aws:s3:::cdk-hnb659fds-assets-{env.account}-{env.region}/*"
        ]
    },
    {
        "id": "AwsSolutions-CFR1",
        "reason": "Geo restrictions not required for internal applications"
    },
    {
        "id": "AwsSolutions-CFR2",
        "reason": "WAF integration not required for development/internal applications"
    },
    {
        "id": "AwsSolutions-CFR4",
        "reason": "TLS 1.2 minimum protocol version is configured"
    }
]

# Apply suppressions to all stacks
for stack in [auth_stack, foundation_stack, processing_stack, orchestration_stack, knowledge_base_stack,
              automation_stack, api_stack, agentcore_deployment_stack, frontend_stack]:
    NagSuppressions.add_stack_suppressions(stack, common_suppressions)
    NagSuppressions.add_stack_suppressions(stack, iam_wildcard_suppressions)
    NagSuppressions.add_stack_suppressions(stack, warning_suppressions)
    NagSuppressions.add_stack_suppressions(stack, cdk_suppressions)

# Note: Resource-specific suppressions are handled in individual stack files:
# - Step Functions suppressions: bda_stacks/step_functions_stack.py
# - Knowledge Base suppressions: bda_stacks/knowledge_base_stack.py

print("CDK Nag configuration completed")

app.synth()