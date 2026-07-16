#!/usr/bin/env python3
"""
Test the 4 main AWS Bedrock AgentCore Runtimes
Tests portfolio coordinator, market analyst, investment advisory, and external API agents
"""

import boto3
import click
import json
import time
import os
from typing import Dict, Any, Optional

# Test prompts for each agent
TEST_PROMPTS = {
    "portfolio_coordinator_runtime": {
        "name": "Portfolio Coordinator",
        "prompt": "What is your role as the portfolio coordinator?",
        "expected_keywords": ["coordinator", "orchestrate", "portfolio"]
    },
    "market_analyst_runtime": {
        "name": "Market Analyst",
        "prompt": "What factors should I consider when calculating return on investment for a commercial property?",
        "expected_keywords": ["ROI", "return", "investment", "factors", "property"]
    },
    "investment_advisory_runtime": {
        "name": "Investment Advisory",
        "prompt": "What investment strategy would you recommend for a moderate risk investor?",
        "expected_keywords": ["investment", "moderate", "risk", "strategy"]
    },
    "external_api_runtime": {
        "name": "External API",
        "prompt": "What types of financial data can you help me retrieve for investment analysis?",
        "expected_keywords": ["financial", "data", "investment", "analysis", "market"]
    }
}

class AgentCoreTester:
    def __init__(self, profile: str = "ML", region: str = None):
        self.profile = profile
        
        # Try to get region from multiple sources
        # 1. Explicit parameter
        # 2. Runtime config file (created by deployment)
        # 3. Environment variables
        self.region = region
        
        if not self.region:
            # Try to load from runtime_config.json
            config_file = os.path.join(os.path.dirname(__file__), 'runtime_config.json')
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                        self.region = config.get('region')
                except Exception:
                    pass
        
        if not self.region:
            # Fall back to environment variables
            self.region = os.environ.get('AWS_DEFAULT_REGION') or os.environ.get('AWS_REGION')
        
        if not self.region:
            raise ValueError("AWS region must be set via --region parameter, runtime_config.json, or AWS_DEFAULT_REGION/AWS_REGION env var")
        
        # Initialize AWS clients
        session = boto3.Session(profile_name=profile, region_name=self.region)
        self.agentcore_client = session.client('bedrock-agentcore')
        self.agentcore_control = session.client('bedrock-agentcore-control')
        
        # Load runtime IDs from config file if it exists
        self.runtime_ids = self.load_runtime_ids()
        
        click.echo("🧪 AWS Bedrock AgentCore Tester")
        click.echo(f"   Profile: {profile}")
        click.echo(f"   Region: {self.region}")
        click.echo("")
    
    def load_runtime_ids(self) -> Dict[str, str]:
        """Load runtime IDs from the config file created by deployment script."""
        config_file = os.path.join(
            os.path.dirname(__file__), 
            'runtime_config.json'
        )
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    runtime_ids = config.get('runtime_ids', {})
                    
                    # Map to expected format
                    return {
                        "portfolio_coordinator_runtime": runtime_ids.get('coordinator', ''),
                        "market_analyst_runtime": runtime_ids.get('market_analyst', ''),
                        "investment_advisory_runtime": runtime_ids.get('investment_advisory', ''),
                        "external_api_runtime": runtime_ids.get('external_api', '')
                    }
            except Exception as e:
                click.echo(f"⚠️  Failed to load runtime config: {e}")
        
        # Return empty dict if no config file
        return {}
    
    def test_runtime(self, runtime_id: str, test_config: Dict[str, Any]) -> Dict[str, Any]:
        """Test a single runtime"""
        agent_name = test_config["name"]
        prompt = test_config["prompt"]
        expected_keywords = test_config["expected_keywords"]
        
        click.echo(f"\n🔬 Testing {agent_name}")
        click.echo(f"   Runtime ID: {runtime_id}")
        click.echo(f"   Prompt: {prompt[:50]}...")
        
        try:
            # Check runtime status and get ARN
            response = self.agentcore_control.get_agent_runtime(
                agentRuntimeId=runtime_id
            )
            
            status = response.get('status', 'UNKNOWN')
            runtime_arn = response.get('agentRuntimeArn')
            
            if status != 'READY':
                click.echo(f"   ⚠️  Runtime status: {status}")
                return {"success": False, "error": f"Runtime not ready: {status}"}
            
            click.echo(f"   ✅ Runtime is READY")
            click.echo(f"   ARN: {runtime_arn}")
            
            # Prepare invocation request
            request = {
                "input": prompt,
                "sessionId": f"test-{int(time.time())}",
                "context": {},
                "parameters": {}
            }
            
            # Invoke the runtime using ARN
            start_time = time.time()
            
            response = self.agentcore_client.invoke_agent_runtime(
                agentRuntimeArn=runtime_arn,
                payload=json.dumps(request)
            )
            
            elapsed_time = time.time() - start_time
            
            # Parse response - handle streaming body
            if 'response' in response and hasattr(response['response'], 'read'):
                # It's a streaming body
                response_data = response['response'].read().decode('utf-8')
                try:
                    response_body = json.loads(response_data)
                    response_text = response_body.get('response', response_data)
                except json.JSONDecodeError:
                    response_text = response_data
            elif 'payload' in response:
                response_body = json.loads(response.get('payload', '{}'))
                response_text = response_body.get('response', '')
            else:
                response_text = str(response)
            
            click.echo(f"   Response received ({elapsed_time:.2f}s)")
            click.echo(f"   Response preview: {response_text[:100]}...")
            
            # Check for expected keywords
            keywords_found = []
            for keyword in expected_keywords:
                if keyword.lower() in response_text.lower():
                    keywords_found.append(keyword)
            
            if keywords_found:
                click.echo(f"   ✅ Found keywords: {', '.join(keywords_found)}")
                return {"success": True, "response": response_text, "elapsed_time": elapsed_time}
            else:
                click.echo(f"   ⚠️  Expected keywords not found")
                return {"success": True, "response": response_text, "elapsed_time": elapsed_time, "warning": "Keywords not found"}
            
        except Exception as e:
            click.echo(f"   ❌ Error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def test_all_agents(self):
        """Test all 4 agents"""
        # Use runtime IDs loaded from config file
        runtime_ids = self.runtime_ids
        
        if not runtime_ids or not any(runtime_ids.values()):
            click.echo("❌ No runtime IDs found!")
            click.echo("   Please run the deployment script first:")
            click.echo("   ./deploy.sh --profile <profile> --environment <env>")
            return {}
        
        results = {}
        successful = 0
        failed = 0
        
        click.echo("🚀 Testing 4 AgentCore Runtimes")
        click.echo("="*50)
        
        for runtime_name, runtime_id in runtime_ids.items():
            test_config = TEST_PROMPTS.get(runtime_name)
            if test_config:
                result = self.test_runtime(runtime_id, test_config)
                results[runtime_name] = result
                
                if result.get("success"):
                    successful += 1
                else:
                    failed += 1
        
        # Summary
        click.echo("\n" + "="*50)
        click.echo("📊 Test Summary")
        click.echo("="*50)
        click.echo(f"✅ Successful: {successful}")
        click.echo(f"❌ Failed: {failed}")
        
        for runtime_name, result in results.items():
            agent_name = TEST_PROMPTS[runtime_name]["name"]
            if result.get("success"):
                warning = " ⚠️" if result.get("warning") else ""
                click.echo(f"   • {agent_name}: PASSED{warning} ({result.get('elapsed_time', 0):.2f}s)")
            else:
                click.echo(f"   • {agent_name}: FAILED - {result.get('error', 'Unknown error')}")
        
        return results

@click.command()
@click.option('--profile', default='ML', help='AWS profile')
@click.option('--region', help='AWS region (defaults to AWS_DEFAULT_REGION or AWS_REGION env var)')
@click.option('--agent', help='Test specific agent only')
def main(profile: str, region: str, agent: str):
    """Test AWS Bedrock AgentCore Runtimes"""
    
    tester = AgentCoreTester(profile=profile, region=region)
    
    if agent:
        # Test specific agent
        runtime_ids_map = {
            "coordinator": tester.runtime_ids.get("portfolio_coordinator_runtime", ""),
            "market_analyst": tester.runtime_ids.get("market_analyst_runtime", ""),
            "investment_advisory": tester.runtime_ids.get("investment_advisory_runtime", ""),
            "external_api": tester.runtime_ids.get("external_api_runtime", "")
        }
        
        if not any(runtime_ids_map.values()):
            click.echo("❌ No runtime IDs found!")
            click.echo("   Please run the deployment script first:")
            click.echo("   ./deploy.sh --profile <profile> --environment <env>")
            return
        
        if agent in runtime_ids_map:
            runtime_id = runtime_ids_map[agent]
            if not runtime_id:
                click.echo(f"❌ Runtime ID not found for {agent}")
                return
            # Map agent names to test config keys
            test_config_map = {
                "coordinator": "portfolio_coordinator_runtime",
                "market_analyst": "market_analyst_runtime",
                "investment_advisory": "investment_advisory_runtime",
                "external_api": "external_api_runtime"
            }
            test_config_key = test_config_map.get(agent)
            test_config = TEST_PROMPTS.get(test_config_key)
            if test_config:
                result = tester.test_runtime(runtime_id, test_config)
                if result.get("success"):
                    click.echo(f"\n✅ {agent} test passed!")
                else:
                    click.echo(f"\n❌ {agent} test failed!")
            else:
                click.echo(f"❌ No test configuration for {agent}")
        else:
            click.echo(f"❌ Unknown agent: {agent}")
            click.echo(f"Available agents: {', '.join(runtime_ids_map.keys())}")
    else:
        # Test all agents
        tester.test_all_agents()
    
    click.echo("\n✨ Testing complete!")

if __name__ == "__main__":
    main()