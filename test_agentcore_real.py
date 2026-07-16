#!/usr/bin/env python3
"""
Test AgentCore Agents with Real Responses
This script tests all 4 agents and displays their actual responses
"""

import boto3
import json
import os
import time
import click
from typing import Dict, Any

# ANSI color codes for pretty output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")

def print_section(title: str, content: str = None):
    print(f"\n{Colors.CYAN}{Colors.BOLD}▶ {title}{Colors.ENDC}")
    if content:
        print(f"{Colors.GREEN}{content}{Colors.ENDC}")

def test_agent(client, runtime_arn: str, agent_name: str, test_prompts: list) -> Dict[str, Any]:
    """Test a single agent with multiple prompts"""
    results = []
    
    print_header(f"Testing {agent_name}")
    print(f"{Colors.YELLOW}Runtime ARN: {runtime_arn}{Colors.ENDC}")
    
    for i, prompt in enumerate(test_prompts, 1):
        print_section(f"Test {i}: {prompt[:100]}...")
        
        try:
            # Prepare the request
            payload = {
                "input": prompt,
                "sessionId": f"test-{agent_name}-{int(time.time())}",
                "context": {}
            }
            
            # Invoke the agent
            start_time = time.time()
            response = client.invoke_agent_runtime(
                agentRuntimeArn=runtime_arn,
                payload=json.dumps(payload)
            )
            elapsed = time.time() - start_time
            
            # Parse the response
            response_body = response['response'].read()
            
            # Try to parse as JSON
            try:
                response_data = json.loads(response_body)
                agent_response = response_data.get('response', str(response_data))
                
                # Display the response
                print(f"{Colors.GREEN}✅ Response received in {elapsed:.2f}s{Colors.ENDC}")
                print(f"\n{Colors.BOLD}Agent Response:{Colors.ENDC}")
                print("-" * 40)
                print(agent_response)
                print("-" * 40)
                
                # Store result
                results.append({
                    "prompt": prompt,
                    "response": agent_response,
                    "elapsed_time": elapsed,
                    "success": True
                })
                
            except json.JSONDecodeError:
                print(f"{Colors.YELLOW}Raw response: {response_body.decode('utf-8')}{Colors.ENDC}")
                results.append({
                    "prompt": prompt,
                    "response": response_body.decode('utf-8'),
                    "elapsed_time": elapsed,
                    "success": True
                })
                
        except Exception as e:
            print(f"{Colors.RED}❌ Error: {str(e)}{Colors.ENDC}")
            results.append({
                "prompt": prompt,
                "error": str(e),
                "success": False
            })
        
        print()  # Add spacing between tests
    
    return results

@click.command()
@click.option('--profile', default='ML', help='AWS profile')
@click.option('--region', help='AWS region (defaults to AWS_DEFAULT_REGION or AWS_REGION env var)')
def main(profile: str, region: str):
    # Configuration
    PROFILE = profile
    
    # Try to get region from multiple sources
    if not region:
        # Try to load from runtime_config.json
        config_file = 'agentcore/runtime_config.json'
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    region = config.get('region')
            except Exception:
                pass
    
    if not region:
        # Fall back to environment variables
        region = os.environ.get('AWS_DEFAULT_REGION') or os.environ.get('AWS_REGION')
    
    if not region:
        raise ValueError("AWS region must be set via --region parameter, runtime_config.json, or AWS_DEFAULT_REGION/AWS_REGION env var")
    
    REGION = region
    
    # Load runtime configuration
    with open('agentcore/runtime_config.json', 'r') as f:
        config = json.load(f)
    
    # Initialize AWS client
    print_header("AWS Bedrock AgentCore Real Response Tester")
    print(f"Profile: {PROFILE}")
    print(f"Region: {REGION}")
    print(f"Environment: {config['environment']}")
    
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    client = session.client('bedrock-agentcore')
    
    # Define test cases for each agent
    test_cases = {
        "coordinator": {
            "name": "Portfolio Coordinator",
            "arn": config['runtime_arns']['coordinator'],
            "prompts": [
                "What is your role as the portfolio coordinator?",
                "Analyze the Boston real estate market for multifamily properties",
                "What are the key metrics I should consider for a commercial property investment?"
            ]
        },
        "market_analyst": {
            "name": "Market Analyst",
            "arn": config['runtime_arns']['market_analyst'],
            "prompts": [
                "What factors should I consider when analyzing real estate investment returns?",
                "Explain the key financial metrics used in commercial property analysis",
                "How do market conditions affect cap rates in commercial real estate?"
            ]
        },
        "investment_advisory": {
            "name": "Investment Advisory",
            "arn": config['runtime_arns']['investment_advisory'],
            "prompts": [
                "What investment strategy would you recommend for a moderate risk investor?",
                "How should I diversify a $1M real estate portfolio?",
                "What are the risks of investing in commercial real estate?"
            ]
        },
        "external_api": {
            "name": "External API",
            "arn": config['runtime_arns']['external_api'],
            "prompts": [
                "What types of financial data can you help me retrieve?",
                "How would you approach gathering market intelligence for real estate investment?",
                "What data sources are important for investment analysis?"
            ]
        }
    }
    
    # Test each agent
    all_results = {}
    for agent_key, agent_config in test_cases.items():
        results = test_agent(
            client,
            agent_config['arn'],
            agent_config['name'],
            agent_config['prompts']
        )
        all_results[agent_key] = results
        time.sleep(2)  # Small delay between agents
    
    # Summary
    print_header("Test Summary")
    
    for agent_key, results in all_results.items():
        agent_name = test_cases[agent_key]['name']
        successful = sum(1 for r in results if r.get('success', False))
        total = len(results)
        
        if successful == total:
            status = f"{Colors.GREEN}✅ {successful}/{total} tests passed{Colors.ENDC}"
        elif successful > 0:
            status = f"{Colors.YELLOW}⚠️  {successful}/{total} tests passed{Colors.ENDC}"
        else:
            status = f"{Colors.RED}❌ {successful}/{total} tests passed{Colors.ENDC}"
        
        print(f"{agent_name}: {status}")
        
        # Show average response time for successful tests
        successful_tests = [r for r in results if r.get('success', False)]
        if successful_tests:
            avg_time = sum(r['elapsed_time'] for r in successful_tests) / len(successful_tests)
            print(f"  Average response time: {avg_time:.2f}s")
    
    print(f"\n{Colors.BOLD}✨ Testing complete!{Colors.ENDC}")
    
    # Option to save results
    save = input("\nSave detailed results to file? (y/n): ")
    if save.lower() == 'y':
        filename = f"test_results_{int(time.time())}.json"
        with open(filename, 'w') as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "config": config,
                "test_cases": test_cases,
                "results": all_results
            }, f, indent=2)
        print(f"Results saved to {filename}")

if __name__ == "__main__":
    main()