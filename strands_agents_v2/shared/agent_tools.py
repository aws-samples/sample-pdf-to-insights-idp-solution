"""
Agent Tools Module - Direct Agent Invocation Patterns
Implements orchestration patterns without HTTP communication
"""

from strands import tool
import asyncio
import json
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# Import specialist tools for orchestration
from .specialist_tools import (
    market_analyst_tool,
    investment_advisor_tool,
    external_api_tool,
    knowledge_base_tool
)

@tool
async def orchestrate_sequential_workflow(
    query: str,
    agents: List[str],
    pass_context: bool = True
) -> Dict[str, Any]:
    """
    Execute agents sequentially, passing context forward
    
    Args:
        query: Initial query to process
        agents: List of agent names to execute in order
        pass_context: Whether to pass previous results as context to next agent
        
    Returns:
        Dict containing results from each agent and final synthesis
    """
    results = {
        'workflow_type': 'sequential',
        'query': query,
        'agents': agents,
        'agent_responses': {},
        'final_result': None
    }
    
    accumulated_context = {}
    current_query = query
    
    try:
        for agent_name in agents:
            # Build context-aware query if passing context
            if pass_context and accumulated_context:
                current_query = f"{query}\n\nPrevious Analysis:\n{json.dumps(accumulated_context, indent=2)}"
            
            # Execute appropriate agent
            if agent_name == 'market_analyst':
                response = market_analyst_tool(current_query)
            elif agent_name == 'investment_advisor':
                response = investment_advisor_tool(current_query, accumulated_context if pass_context else None)
            elif agent_name == 'external_api':
                response = external_api_tool(current_query)
            elif agent_name == 'knowledge_base':
                response = knowledge_base_tool(current_query)
            else:
                response = f"Unknown agent: {agent_name}"
            
            results['agent_responses'][agent_name] = response
            
            # Add to context for next agent
            if pass_context:
                accumulated_context[agent_name] = response
        
        # Final result is the last agent's response or synthesis
        results['final_result'] = results['agent_responses'].get(agents[-1]) if agents else None
        
    except Exception as e:
        logger.error(f"Sequential workflow error: {str(e)}")
        results['error'] = str(e)
    
    return results

@tool
async def orchestrate_parallel_workflow(
    query: str,
    agents: List[str]
) -> Dict[str, Any]:
    """
    Execute agents in parallel for faster processing
    
    Args:
        query: Query to send to all agents
        agents: List of agent names to execute in parallel
        
    Returns:
        Dict containing results from all agents
    """
    results = {
        'workflow_type': 'parallel',
        'query': query,
        'agents': agents,
        'agent_responses': {}
    }
    
    try:
        # Create tasks for parallel execution
        tasks = []
        for agent_name in agents:
            if agent_name == 'market_analyst':
                task = asyncio.create_task(asyncio.to_thread(market_analyst_tool, query))
            elif agent_name == 'investment_advisor':
                task = asyncio.create_task(asyncio.to_thread(investment_advisor_tool, query))
            elif agent_name == 'external_api':
                task = asyncio.create_task(asyncio.to_thread(external_api_tool, query))
            elif agent_name == 'knowledge_base':
                task = asyncio.create_task(asyncio.to_thread(knowledge_base_tool, query))
            else:
                continue
            tasks.append((agent_name, task))
        
        # Wait for all tasks to complete
        for agent_name, task in tasks:
            try:
                response = await task
                results['agent_responses'][agent_name] = response
            except Exception as e:
                results['agent_responses'][agent_name] = f"Error: {str(e)}"
        
    except Exception as e:
        logger.error(f"Parallel workflow error: {str(e)}")
        results['error'] = str(e)
    
    return results

@tool
def synthesize_agent_responses(responses: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synthesize responses from multiple agents into unified insights
    
    Args:
        responses: Dictionary of agent responses
        
    Returns:
        Synthesized analysis with key findings and recommendations
    """
    synthesis = {
        'key_findings': [],
        'recommendations': [],
        'data_points': [],
        'consensus_areas': [],
        'divergent_views': []
    }
    
    try:
        for agent, response in responses.items():
            if isinstance(response, str):
                # Parse string responses for key information
                if 'recommendation' in response.lower():
                    synthesis['recommendations'].append({
                        'source': agent,
                        'content': response
                    })
                elif any(word in response.lower() for word in ['finding', 'analysis', 'result']):
                    synthesis['key_findings'].append({
                        'source': agent,
                        'content': response
                    })
                else:
                    synthesis['data_points'].append({
                        'source': agent,
                        'content': response
                    })
            elif isinstance(response, dict):
                # Extract structured information
                if 'findings' in response:
                    synthesis['key_findings'].extend(response['findings'])
                if 'recommendations' in response:
                    synthesis['recommendations'].extend(response['recommendations'])
                if 'data' in response:
                    synthesis['data_points'].append({
                        'source': agent,
                        'data': response['data']
                    })
        
        # Identify consensus and divergence (simplified)
        if len(synthesis['key_findings']) > 1:
            synthesis['consensus_areas'].append("Multiple agents identified similar market conditions")
        
    except Exception as e:
        logger.error(f"Synthesis error: {str(e)}")
        synthesis['error'] = str(e)
    
    return synthesis

@tool
async def orchestrate_multi_agent_workflow(
    query: str,
    agents: List[str],
    pattern: str = "sequential",
    suppress_outputs: bool = True
) -> Dict[str, Any]:
    """
    Orchestrate a multi-agent workflow with specified pattern
    
    Args:
        query: Query to process
        agents: List of agent names to involve
        pattern: Workflow pattern (sequential, parallel, synthesis)
        suppress_outputs: Whether to suppress intermediate outputs
        
    Returns:
        Orchestrated results from multiple agents
    """
    results = {
        'query': query,
        'pattern': pattern,
        'agents': agents,
        'agent_responses': {},
        'synthesis': None
    }
    
    try:
        if pattern == "parallel":
            workflow_result = await orchestrate_parallel_workflow(query, agents)
            results['agent_responses'] = workflow_result.get('agent_responses', {})
            
        elif pattern == "sequential":
            workflow_result = await orchestrate_sequential_workflow(query, agents, pass_context=True)
            results['agent_responses'] = workflow_result.get('agent_responses', {})
            
        elif pattern == "synthesis":
            # Get responses from all agents in parallel then synthesize
            workflow_result = await orchestrate_parallel_workflow(query, agents)
            results['agent_responses'] = workflow_result.get('agent_responses', {})
            results['synthesis'] = synthesize_agent_responses(results['agent_responses'])
        
        else:
            results['error'] = f"Unknown pattern: {pattern}"
        
        # Apply output suppression if needed
        if suppress_outputs and 'agent_responses' in results:
            for agent in results['agent_responses']:
                response = results['agent_responses'][agent]
                if isinstance(response, dict):
                    response.pop('intermediate_outputs', None)
                    response.pop('debug_info', None)
        
    except Exception as e:
        logger.error(f"Multi-agent workflow error: {str(e)}")
        results['error'] = str(e)
    
    return results

# Backward compatibility exports (these now use direct invocation)
use_market_analyst_agent = market_analyst_tool
use_investment_advisory_agent = investment_advisor_tool
use_external_api_agent = external_api_tool