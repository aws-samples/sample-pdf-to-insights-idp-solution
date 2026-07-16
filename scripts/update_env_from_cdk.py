#!/usr/bin/env python3
"""
Update .env file with values from CDK stack outputs
This script reads CloudFormation outputs and updates environment variables
"""

import argparse
import boto3
import json
import os
import re
from pathlib import Path
from typing import Dict, Optional

def get_stack_outputs(stack_name: str, profile: Optional[str] = None) -> Dict[str, str]:
    """
    Get outputs from a CloudFormation stack
    
    Args:
        stack_name: Name of the CloudFormation stack
        profile: AWS profile name (optional)
        
    Returns:
        Dict of output key-value pairs
    """
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    cf_client = session.client('cloudformation')
    
    try:
        response = cf_client.describe_stacks(StackName=stack_name)
        
        if not response['Stacks']:
            raise ValueError(f"Stack {stack_name} not found")
        
        stack = response['Stacks'][0]
        outputs = {}
        
        if 'Outputs' in stack:
            for output in stack['Outputs']:
                outputs[output['OutputKey']] = output['OutputValue']
        
        return outputs
        
    except Exception as e:
        print(f"Error retrieving stack outputs: {e}")
        return {}

def update_env_file(outputs: Dict[str, str], env_file_path: Path) -> None:
    """
    Update .env file with CDK outputs
    
    Args:
        outputs: CDK stack outputs
        env_file_path: Path to .env file
    """
    # Mapping of CDK output keys to environment variable names
    output_mapping = {
        'KnowledgeBaseId': 'KNOWLEDGE_BASE_ID',
        'AgentId': 'BEDROCK_AGENT_ID',
        'AgentAliasId': 'BEDROCK_AGENT_ALIAS_ID',
        'DataSourceId': 'KNOWLEDGE_BASE_DATA_SOURCE_ID',
        'PDFBucketName': 'PDF_BUCKET_NAME',
        'AgentRoleArn': 'AGENT_ROLE_ARN',
        'KnowledgeBaseName': 'KNOWLEDGE_BASE_NAME',
        # Processing and Storage outputs
        'ProcessingStatusTableName': 'VITE_DYNAMODB_TABLE_NAME',
        'MetricsTableName': 'VITE_DYNAMODB_METRICS_TABLE_NAME',
        'DocumentBucketName': 'VITE_S3_BUCKET',
        # AgentCore deployment outputs
        'AgentCoreExecutionRoleArn': 'AGENTCORE_EXECUTION_ROLE_ARN',
        'ECRPushRoleArn': 'ECR_PUSH_ROLE_ARN',
        'coordinatorECRRepositoryURI': 'COORDINATOR_ECR_URI',
        'marketanalystECRRepositoryURI': 'MARKET_ANALYST_ECR_URI',
        'investmentadvisoryECRRepositoryURI': 'INVESTMENT_ADVISORY_ECR_URI',
        'externalapiECRRepositoryURI': 'EXTERNAL_API_ECR_URI',
        'visualizationECRRepositoryURI': 'VISUALIZATION_ECR_URI',
        'riskanalyticsECRRepositoryURI': 'RISK_ANALYTICS_ECR_URI',
        'realestatedataECRRepositoryURI': 'REAL_ESTATE_DATA_ECR_URI'
    }
    
    # Read existing .env file or create from template
    if env_file_path.exists():
        with open(env_file_path, 'r') as f:
            env_content = f.read()
    else:
        # Copy from template
        template_path = env_file_path.parent / '.env.template'
        if template_path.exists():
            with open(template_path, 'r') as f:
                env_content = f.read()
        else:
            env_content = ""
    
    # Update values
    updated = False
    for cdk_key, env_var in output_mapping.items():
        if cdk_key in outputs:
            value = outputs[cdk_key]
            
            # Check if variable exists in file
            pattern = rf'^{env_var}=.*$'
            if re.search(pattern, env_content, re.MULTILINE):
                # Update existing value
                env_content = re.sub(
                    pattern,
                    f'{env_var}={value}',
                    env_content,
                    flags=re.MULTILINE
                )
                print(f"✅ Updated {env_var}={value}")
            else:
                # Add new variable
                env_content += f"\n{env_var}={value}"
                print(f"✅ Added {env_var}={value}")
            
            updated = True
    
    # Write updated content
    if updated:
        with open(env_file_path, 'w') as f:
            f.write(env_content)
        print(f"\n✅ Updated {env_file_path}")
    else:
        print("⚠️  No matching outputs found to update")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Update .env file with CDK stack outputs'
    )
    parser.add_argument(
        '--environment',
        required=True,
        help='Environment name (Dev, Staging, Prod)'
    )
    parser.add_argument(
        '--profile',
        help='AWS profile to use'
    )
    parser.add_argument(
        '--env-file',
        default='.env',
        help='Path to .env file (default: .env)'
    )
    parser.add_argument(
        '--show-outputs',
        action='store_true',
        help='Show all stack outputs without updating .env'
    )
    
    args = parser.parse_args()
    
    # Get project root and UI directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    # Point to the UI directory for .env file
    env_file_path = project_root / 'bda-cloudscape-ui' / args.env_file
    
    # List of stacks to check for outputs
    stack_names = [
        f"BDA-Foundation-{args.environment}",
        f"BDA-Processing-{args.environment}",
        f"BDA-KnowledgeBase-{args.environment}",
        f"BDA-AgentCoreDeployment-{args.environment}",
        f"BDA-Auth-{args.environment}"
    ]
    
    all_outputs = {}
    
    for stack_name in stack_names:
        print(f"🔍 Checking stack: {stack_name}")
        if args.profile:
            print(f"   Using AWS profile: {args.profile}")
        
        # Get stack outputs
        outputs = get_stack_outputs(stack_name, args.profile)
        if outputs:
            print(f"   ✓ Found {len(outputs)} outputs")
            all_outputs.update(outputs)
    
    outputs = all_outputs
    
    if not outputs:
        print("❌ No outputs found")
        return 1
    
    if args.show_outputs:
        print("\n📋 Stack Outputs:")
        for key, value in outputs.items():
            print(f"   {key}: {value}")
    else:
        print(f"\n📝 Updating {env_file_path}")
        update_env_file(outputs, env_file_path)
    
    # Show important values
    if 'KnowledgeBaseId' in outputs:
        print(f"\n💡 Knowledge Base ID: {outputs['KnowledgeBaseId']}")
        print("   You can now run: export KNOWLEDGE_BASE_ID=" + outputs['KnowledgeBaseId'])
    
    return 0

if __name__ == "__main__":
    exit(main())