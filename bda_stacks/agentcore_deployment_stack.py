from aws_cdk import (
    Stack,
    CfnOutput,
    aws_ecr as ecr,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    RemovalPolicy
)
from constructs import Construct
from cdk_nag import NagSuppressions
import json
import os
import hashlib
import time

class BDAAgentCoreDeploymentStack(Stack):
    """
    Stack for AgentCore deployment resources.
    Creates ECR repositories and IAM roles for deploying Strand Agents to AWS Bedrock AgentCore.
    """
    
    def __init__(self, scope: Construct, construct_id: str, knowledge_base_stack,
                 deployment_env='Dev', version='v1', deployment_id=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Store deployment environment, version, and deployment ID
        self.deployment_env = deployment_env
        self.version = version
        self.deployment_id = deployment_id
        
        # Get knowledge base ID from the knowledge base stack
        self.knowledge_base_id = knowledge_base_stack.knowledge_base_id

        # Create resource name prefix for consistent naming
        # Include deployment ID if provided for complete isolation
        if deployment_id:
            resource_name_prefix = f"BDA-{deployment_env}-{deployment_id}"
        else:
            resource_name_prefix = f"BDA-{deployment_env}"
        
        # Generate a short unique suffix based on timestamp
        # This ensures all resources in this stack share the same suffix
        timestamp = int(time.time())
        self.unique_suffix = hashlib.md5(f"{timestamp}".encode()).hexdigest()[:8] # nosec # B324: using MD5 for non-security purpose

        # Define agents to deploy - using minimal Dockerfile with build args
        # Runtime names include unique suffix to allow multiple deployments
        self.agents = {
            'coordinator': {
                'name': 'coordinator',
                'runtime_name': f'portfolio_coordinator_runtime_{self.unique_suffix}',
                'description': 'Main orchestrator for real estate portfolio advisory',
                'tag': 'coordinator-cdk',
                'memory': 2048
            },
            'market_analyst': {
                'name': 'market-analyst', 
                'runtime_name': f'market_analyst_runtime_{self.unique_suffix}',
                'description': 'Financial metrics and market trend analysis',
                'tag': 'market-analyst-cdk',
                'memory': 1024
            },
            'investment_advisory': {
                'name': 'investment-advisory',
                'runtime_name': f'investment_advisory_runtime_{self.unique_suffix}',
                'description': 'Investment recommendations and portfolio optimization',
                'tag': 'investment-advisory-cdk',
                'memory': 1024
            },
            'external_api': {
                'name': 'external-api',
                'runtime_name': f'external_api_runtime_{self.unique_suffix}',
                'description': 'Real-time market data and external information',
                'tag': 'external-api-cdk',
                'memory': 512
            }
        }

        # Create a SINGLE ECR repository for all agents with unique suffix
        self.ecr_repository = ecr.Repository(
            self, "AgentCoreRepository",
            repository_name=f"{resource_name_prefix.lower()}-agentcore-{self.unique_suffix}-{deployment_env.lower()}",
            image_scan_on_push=True,
            encryption=ecr.RepositoryEncryption.AES_256,
            removal_policy=RemovalPolicy.DESTROY,  # Be careful in production
            lifecycle_rules=[
                ecr.LifecycleRule(
                    description="Keep only last 10 images per tag prefix",
                    max_image_count=10,
                    tag_prefix_list=[agent['name'] for agent in self.agents.values()]
                )
            ]
        )
        
        # Build and push Docker images for each agent using the minimal Dockerfile
        self.docker_images = {}
        for agent_key, agent_config in self.agents.items():
            # Build Docker image using CDK assets with build args
            docker_image = ecr_assets.DockerImageAsset(
                self, f"{agent_key}DockerImage",
                directory=os.path.join(os.path.dirname(__file__), '..'),  # Project root
                file='agentcore/Dockerfile.minimal',  # Use the single minimal Dockerfile
                build_args={
                    'AGENT_TYPE': agent_key,  # Pass agent type as build arg
                    'RUNTIME_ID': agent_config['runtime_name']  # Pass runtime ID for CloudWatch logging
                },
                platform=ecr_assets.Platform.LINUX_ARM64
            )
            
            self.docker_images[agent_key] = docker_image
            
            # Tag and push to ECR repository
            # CDK will automatically handle the push during deployment

        # Create IAM role for AgentCore with unique suffix
        # This role will be assumed by AgentCore to run the agents
        self.agentcore_execution_role = iam.Role(
            self, 'AgentCoreExecutionRole',
            role_name=f"{resource_name_prefix}-AgentCoreExecutionRole-{self.unique_suffix}",
            assumed_by=iam.ServicePrincipal('bedrock-agentcore.amazonaws.com'),
            description='Execution role for BDA agents in AgentCore'
        )

        # Add necessary policies to the execution role
        # Policy for accessing Bedrock models
        self.agentcore_execution_role.add_to_policy(
            iam.PolicyStatement(
                sid='BedrockModelAccess',
                effect=iam.Effect.ALLOW,
                actions=[
                    'bedrock:InvokeModel',
                    'bedrock:InvokeModelWithResponseStream'
                ],
                resources=['*']  # You can restrict to specific models if needed
            )
        )

        # Add CDK Nag suppressions for AgentCore execution role
        NagSuppressions.add_resource_suppressions(
            self.agentcore_execution_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcards required for Bedrock models, ECR operations, CloudWatch logs, and X-Ray tracing",
                    "appliesTo": [
                        "Resource::*"
                    ]
                }
            ]
        )
        
        # Policy for accessing ECR to pull container images
        self.agentcore_execution_role.add_to_policy(
            iam.PolicyStatement(
                sid='ECRAccess',
                effect=iam.Effect.ALLOW,
                actions=[
                    'ecr:GetAuthorizationToken',
                    'ecr:BatchCheckLayerAvailability',
                    'ecr:GetDownloadUrlForLayer',
                    'ecr:BatchGetImage'
                ],
                resources=['*']
            )
        )

        # Policy for accessing the knowledge base
        self.agentcore_execution_role.add_to_policy(
            iam.PolicyStatement(
                sid='KnowledgeBaseAccess',
                effect=iam.Effect.ALLOW,
                actions=[
                    'bedrock:Retrieve',
                    'bedrock:RetrieveAndGenerate'
                ],
                resources=[knowledge_base_stack.knowledge_base_arn]
            )
        )

        # Policy for CloudWatch Logs
        self.agentcore_execution_role.add_to_policy(
            iam.PolicyStatement(
                sid='CloudWatchLogsAccess',
                effect=iam.Effect.ALLOW,
                actions=[
                    'logs:CreateLogGroup',
                    'logs:CreateLogStream',
                    'logs:PutLogEvents',
                    'logs:DescribeLogGroups',
                    'logs:DescribeLogStreams'
                ],
                resources=['*']
            )
        )

        # Policy for X-Ray tracing (for observability)
        self.agentcore_execution_role.add_to_policy(
            iam.PolicyStatement(
                sid='XRayAccess',
                effect=iam.Effect.ALLOW,
                actions=[
                    'xray:PutTraceSegments',
                    'xray:PutTelemetryRecords'
                ],
                resources=['*']
            )
        )

        # Create a role for pushing images to ECR (used by deployment scripts)
        self.ecr_push_role = iam.Role(
            self, 'ECRPushRole',
            role_name=f"{resource_name_prefix}-ECRPushRole-{self.unique_suffix}",
            assumed_by=iam.AccountPrincipal(self.account),
            description='Role for pushing Docker images to ECR'
        )

        # Grant ECR push permissions to the single repository
        self.ecr_repository.grant_pull_push(self.ecr_push_role)

        # Add CDK Nag suppressions for ECR push role
        NagSuppressions.add_resource_suppressions(
            self.ecr_push_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcards required for ECR operations",
                    "appliesTo": [
                        "Resource::*"
                    ]
                }
            ]
        )

        # Output all necessary values
        CfnOutput(self, 'KnowledgeBaseId',
                  value=self.knowledge_base_id,
                  description='Knowledge Base ID for agents to use')

        CfnOutput(self, 'AgentCoreExecutionRoleArn',
                  value=self.agentcore_execution_role.role_arn,
                  description='IAM role ARN for AgentCore execution')

        CfnOutput(self, 'ECRPushRoleArn',
                  value=self.ecr_push_role.role_arn,
                  description='IAM role ARN for pushing images to ECR')

        # Output single ECR repository URI
        CfnOutput(self, 'ECRRepositoryURI',
                  value=self.ecr_repository.repository_uri,
                  description='ECR repository URI for all agents')

        # Output agent image tags configuration
        agent_images_config = {}
        for agent_key, docker_image in self.docker_images.items():
            agent_config = self.agents[agent_key]
            agent_images_config[agent_key] = {
                'image_uri': docker_image.image_uri,
                'repository_uri': self.ecr_repository.repository_uri,
                'tag': agent_config['tag'],
                'description': agent_config['description'],
                'runtime_name': agent_config['runtime_name'],
                'memory': agent_config.get('memory', 1024)
            }
        
        # Output a JSON configuration for easy parsing
        ecr_config = {
            'repository_uri': self.ecr_repository.repository_uri,
            'repository_name': self.ecr_repository.repository_name,
            'repository_arn': self.ecr_repository.repository_arn,
            'agents': agent_images_config
        }
        
        CfnOutput(self, 'ECRRepositoriesConfig',
                  value=json.dumps(ecr_config),
                  description='JSON configuration of all ECR repositories')

        # Output deployment configuration
        deployment_config = {
            'knowledge_base_id': self.knowledge_base_id,
            'execution_role_arn': self.agentcore_execution_role.role_arn,
            'environment': deployment_env,
            'version': version,
            'repository_uri': self.ecr_repository.repository_uri,
            'agents': agent_images_config
        }
        
        CfnOutput(self, 'AgentCoreDeploymentConfig',
                  value=json.dumps(deployment_config),
                  description='Complete deployment configuration for AgentCore')
        
        # Note: Runtime ARNs will be available after post-deployment script runs
        # Since runtime IDs are generated dynamically by AWS
        
        # Output deployment note
        CfnOutput(self, 'DeploymentNote',
                  value='Docker images built and pushed to ECR. Run post-deployment script to create/update AgentCore runtimes.',
                  description='Important deployment information')