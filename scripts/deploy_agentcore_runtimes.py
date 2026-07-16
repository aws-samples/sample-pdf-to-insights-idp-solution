#!/usr/bin/env python3
"""
Post-deployment script to create or update AgentCore runtimes.
Reads CDK stack outputs and manages AgentCore runtime lifecycle.
"""

import boto3
import json
import click
import time
import os
from typing import Dict, Any, Optional

class AgentCoreRuntimeManager:
    """Manages AgentCore runtime creation and updates."""
    
    def __init__(self, profile: str, region: str = None):
        """Initialize the manager with AWS credentials."""
        self.profile = profile
        self.region = region or os.environ.get('AWS_DEFAULT_REGION') or os.environ.get('AWS_REGION')
        if not self.region:
            raise ValueError("AWS region must be set via parameter or AWS_DEFAULT_REGION/AWS_REGION env var")
        
        # Initialize AWS session and clients
        session = boto3.Session(profile_name=profile, region_name=region)
        self.cfn_client = session.client('cloudformation')
        
        # Get AWS account ID dynamically from STS
        sts_client = session.client('sts')
        self.account_id = sts_client.get_caller_identity()['Account']
        
        # Check if bedrock-agentcore services are available
        try:
            self.agentcore_client = session.client('bedrock-agentcore')
            self.agentcore_control = session.client('bedrock-agentcore-control')
            self.has_agentcore = True
        except Exception as e:
            click.echo(f"⚠️  AgentCore services not available: {e}")
            click.echo("   Using configuration-only mode")
            self.has_agentcore = False
    
    def get_stack_outputs(self, stack_name: str) -> Dict[str, Any]:
        """Get outputs from CloudFormation stack."""
        try:
            response = self.cfn_client.describe_stacks(StackName=stack_name)
            outputs = {}
            
            for output in response['Stacks'][0].get('Outputs', []):
                outputs[output['OutputKey']] = output['OutputValue']
            
            return outputs
        except Exception as e:
            click.echo(f"❌ Error getting stack outputs: {e}")
            return {}
    
    def parse_ecr_config(self, ecr_config_json: str) -> Dict[str, Any]:
        """Parse the ECR configuration JSON from stack outputs."""
        try:
            return json.loads(ecr_config_json)
        except Exception as e:
            click.echo(f"❌ Error parsing ECR config: {e}")
            return {}
    
    def check_runtime_exists(self, runtime_id: str) -> bool:
        """Check if a runtime already exists."""
        if not self.has_agentcore:
            return False
            
        try:
            response = self.agentcore_control.get_agent_runtime(
                agentRuntimeId=runtime_id
            )
            return response.get('status') in ['READY', 'UPDATING']
        except:
            return False
    
    def create_runtime(self, agent_key: str, agent_config: Dict[str, Any], 
                      execution_role: str, kb_id: str) -> Optional[str]:
        """Create a new AgentCore runtime."""
        if not self.has_agentcore:
            click.echo(f"   ⚠️  Skipping runtime creation (AgentCore not available)")
            return agent_config.get('runtime_id')
        
        runtime_name = agent_config['runtime_name']
        
        click.echo(f"   Creating runtime: {runtime_name}")
        
        # Use the image_uri directly from the config (CDK-managed image)
        image_uri = agent_config.get('image_uri')
        if not image_uri:
            click.echo(f"   ❌ No image_uri found for {agent_key}")
            return None
        
        try:
            response = self.agentcore_control.create_agent_runtime(
                agentRuntimeName=runtime_name,
                description=agent_config['description'],
                agentRuntimeArtifact={
                    'containerConfiguration': {
                        'containerUri': image_uri
                    }
                },
                roleArn=execution_role,
                networkConfiguration={
                    'networkMode': 'PUBLIC'
                },
                environmentVariables={
                    'AGENT_TYPE': agent_key,
                    'KNOWLEDGE_BASE_ID': kb_id,
                    'LOG_LEVEL': 'INFO',
                    # Streaming configuration
                    'STREAMING_ENABLED': 'true',
                    'STREAMING_BUFFER_SIZE': '1024',
                    'STREAMING_TIMEOUT_SECONDS': '300',
                    # Enhanced observability
                    'METRICS_ENABLED': 'true',
                    'CLOUDWATCH_LOG_RETENTION_DAYS': '30',
                    'ENVIRONMENT': 'production',
                    # OpenTelemetry production configuration
                    'AGENT_OBSERVABILITY_ENABLED': 'true',
                    'OTEL_SERVICE_NAME': agent_key,
                    'OTEL_RESOURCE_ATTRIBUTES': f'service.name={agent_key},service.namespace=agentcore,service.version=2.0.0',
                    'OTEL_TRACES_EXPORTER': 'otlp',
                    'OTEL_METRICS_EXPORTER': 'otlp',
                    'OTEL_LOGS_EXPORTER': 'none',
                    'OTEL_EXPORTER_OTLP_PROTOCOL': 'http/protobuf',
                    'OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED': 'true',
                    'OTEL_PROPAGATORS': 'tracecontext,baggage,xray',
                    'OTEL_PYTHON_LOG_CORRELATION': 'true',
                    'OTEL_TRACES_SAMPLER': 'traceidratio',
                    'OTEL_TRACES_SAMPLER_ARG': '0.1'
                }
            )
            
            runtime_id = response['agentRuntimeId']
            click.echo(f"   ✅ Created runtime: {runtime_id}")
            return runtime_id
            
        except Exception as e:
            click.echo(f"   ❌ Failed to create runtime: {e}")
            return None
    
    def update_runtime(self, runtime_id: str, agent_key: str, 
                      agent_config: Dict[str, Any], kb_id: str) -> bool:
        """Update an existing AgentCore runtime."""
        if not self.has_agentcore:
            click.echo(f"   ⚠️  Skipping runtime update (AgentCore not available)")
            return True
        
        click.echo(f"   Updating runtime: {runtime_id}")
        
        # Use the image_uri directly from the config (CDK-managed image)
        image_uri = agent_config.get('image_uri')
        if not image_uri:
            click.echo(f"   ❌ No image_uri found for {agent_key}")
            return False
        
        try:
            response = self.agentcore_control.update_agent_runtime(
                agentRuntimeId=runtime_id,
                agentRuntimeArtifact={
                    'containerConfiguration': {
                        'containerUri': image_uri
                    }
                },
                environmentVariables={
                    'AGENT_TYPE': agent_key,
                    'KNOWLEDGE_BASE_ID': kb_id,
                    'LOG_LEVEL': 'INFO',
                    # Streaming configuration
                    'STREAMING_ENABLED': 'true',
                    'STREAMING_BUFFER_SIZE': '1024',
                    'STREAMING_TIMEOUT_SECONDS': '300',
                    # Enhanced observability
                    'METRICS_ENABLED': 'true',
                    'CLOUDWATCH_LOG_RETENTION_DAYS': '30',
                    'ENVIRONMENT': 'production',
                    # OpenTelemetry production configuration
                    'AGENT_OBSERVABILITY_ENABLED': 'true',
                    'OTEL_SERVICE_NAME': agent_key,
                    'OTEL_RESOURCE_ATTRIBUTES': f'service.name={agent_key},service.namespace=agentcore,service.version=2.0.0',
                    'OTEL_TRACES_EXPORTER': 'otlp',
                    'OTEL_METRICS_EXPORTER': 'otlp',
                    'OTEL_LOGS_EXPORTER': 'none',
                    'OTEL_EXPORTER_OTLP_PROTOCOL': 'http/protobuf',
                    'OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED': 'true',
                    'OTEL_PROPAGATORS': 'tracecontext,baggage,xray',
                    'OTEL_PYTHON_LOG_CORRELATION': 'true',
                    'OTEL_TRACES_SAMPLER': 'traceidratio',
                    'OTEL_TRACES_SAMPLER_ARG': '0.1'
                }
            )
            
            click.echo(f"   ✅ Updated runtime: {runtime_id}")
            return True
            
        except Exception as e:
            click.echo(f"   ❌ Failed to update runtime: {e}")
            return False
    
    def deploy_runtimes(self, environment: str):
        """Main deployment function."""
        stack_name = f"BDA-AgentCoreDeployment-{environment}"
        
        click.echo(f"\n🚀 Deploying AgentCore Runtimes")
        click.echo(f"   Stack: {stack_name}")
        click.echo(f"   Profile: {self.profile}")
        click.echo(f"   Region: {self.region}")
        click.echo("")
        
        # Get stack outputs
        click.echo("📋 Reading stack outputs...")
        outputs = self.get_stack_outputs(stack_name)
        
        if not outputs:
            click.echo("❌ No stack outputs found. Ensure CDK deployment completed successfully.")
            return False
        
        # Parse configurations
        ecr_config = self.parse_ecr_config(outputs.get('ECRRepositoriesConfig', '{}'))
        execution_role = outputs.get('AgentCoreExecutionRoleArn', '')
        kb_id = outputs.get('KnowledgeBaseId', '')
        
        if not ecr_config:
            click.echo("❌ Missing required configuration from stack outputs")
            return False
        
        agents = ecr_config.get('agents', {})
        
        click.echo(f"✅ Found {len(agents)} agents to deploy")
        click.echo("")
        
        # Process each agent
        runtime_arns = {}
        runtime_ids = {}
        for agent_key, agent_config in agents.items():
            click.echo(f"🔧 Processing {agent_key}...")
            
            # Always create new runtime
            new_runtime_id = self.create_runtime(
                agent_key, agent_config, execution_role, kb_id
            )
            if new_runtime_id:
                runtime_arns[agent_key] = f"arn:aws:bedrock-agentcore:{self.region}:{self.account_id}:runtime/{new_runtime_id}"
                runtime_ids[agent_key] = new_runtime_id
            
            click.echo("")
        
        # Summary
        click.echo("=" * 50)
        click.echo("📊 Deployment Summary")
        click.echo("=" * 50)
        
        if self.has_agentcore:
            click.echo(f"✅ Processed {len(runtime_arns)} runtimes")
        else:
            click.echo(f"⚠️  Configuration mode only (AgentCore not available)")
            click.echo(f"   Pre-existing runtime IDs preserved")
        
        click.echo("")
        click.echo("Runtime ARNs:")
        for agent_key, arn in runtime_arns.items():
            click.echo(f"  • {agent_key}: {arn}")
        
        # Save runtime IDs to a JSON file for use by test scripts
        if runtime_ids:
            runtime_config = {
                "environment": environment,
                "region": self.region,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "runtime_ids": runtime_ids,
                "runtime_arns": runtime_arns
            }
            
            config_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 
                'agentcore', 
                'runtime_config.json'
            )
            
            try:
                with open(config_file, 'w') as f:
                    json.dump(runtime_config, f, indent=2)
                click.echo(f"\n💾 Runtime configuration saved to: {config_file}")
            except Exception as e:
                click.echo(f"\n⚠️  Failed to save runtime config: {e}")
        
        click.echo("")
        click.echo("✨ Post-deployment complete!")
        click.echo("")
        click.echo("Next steps:")
        click.echo("1. Test agents: python3 agentcore/test_agentcore.py --profile " + self.profile)
        click.echo("2. View logs: aws logs tail /aws/bedrock-agentcore/runtimes/<runtime-id>")
        
        return True

@click.command()
@click.option('--profile', required=True, help='AWS profile to use')
@click.option('--environment', default='Dev', help='Environment (Dev/Staging/Prod)')
@click.option('--region', help='AWS region (defaults to AWS_DEFAULT_REGION or AWS_REGION env var)')
def main(profile: str, environment: str, region: str):
    """Deploy or update AgentCore runtimes after CDK deployment."""
    manager = AgentCoreRuntimeManager(profile, region)
    success = manager.deploy_runtimes(environment)
    
    if not success:
        click.echo("❌ Deployment failed")
        exit(1)

if __name__ == '__main__':
    main()