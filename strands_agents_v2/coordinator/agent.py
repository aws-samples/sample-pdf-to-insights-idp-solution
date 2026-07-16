"""
BDA Coordinator Agent V2 - Enhanced for AgentCore with Agents-as-Tools Pattern
Implements Strands 1.1.0 multi-agent orchestration primitives
"""

from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from strands_agents_v2.shared.agent_base import AgentCoreBaseAgent
from strands_agents_v2.shared.prompt_loader import PromptLoader
import boto3
import json
import os
import asyncio
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Load configuration
def load_config():
    """Load configuration from config.json"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'bda_stacks', 'config.json')
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load config: {e}, using defaults")
        return {
            'agentModelId': 'us.anthropic.claude-sonnet-4-5-20250514-v1:0',
            'region': os.getenv('AWS_DEFAULT_REGION') or os.getenv('AWS_REGION')
        }

config = load_config()

class EnhancedCoordinatorAgentV2(AgentCoreBaseAgent):
    """
    Enhanced Coordinator Agent V2 with Agents-as-Tools Pattern
    Orchestrates multiple specialist agents for comprehensive real estate analysis
    """
    
    def __init__(self):
        # Initialize base without tools first
        super().__init__(
            agent_name="BDA-Coordinator-Agent-V2",
            agent_type="orchestrator",
            model_config={
                "model_id": config.get('agentModelId', 'us.anthropic.claude-sonnet-4-5-20250514-v1:0'),
                "region": config.get('region', os.getenv('AWS_DEFAULT_REGION') or os.getenv('AWS_REGION'))
            },
            tools=[]  # Initialize empty, will add tools after
        )
        
        # Initialize specialist agents as tools
        self._initialize_specialist_agents()
        
        # Add specialist tools for orchestration
        self.tools = [
            self.market_analyst_tool,
            self.investment_advisor_tool,
            self.external_api_tool,
            self.search_knowledge_base
        ]
        
        # Recreate agent with all tools
        self.agent = self._create_strands_agent()
    
    def _initialize_specialist_agents(self):
        """Initialize specialist agents as tools"""
        try:
            # Import specialist tools from shared module
            from strands_agents_v2.shared.specialist_tools import (
                market_analyst_tool,
                investment_advisor_tool,
                external_api_tool
            )
            
            # Assign tools to instance
            self.market_analyst_tool = market_analyst_tool
            self.investment_advisor_tool = investment_advisor_tool
            self.external_api_tool = external_api_tool
            
        except Exception as e:
            logger.error(f"Failed to initialize specialist agents: {e}")
            raise RuntimeError(f"Could not initialize specialist agents: {e}")
    
    def get_system_prompt(self) -> str:
        """Load prompt from assets/AgentPrompts.txt file"""
        return PromptLoader.get_prompt('coordinator')
    
    @tool
    async def search_knowledge_base(self, query: str) -> Dict[str, Any]:
        """
        Search BDA knowledge base for relevant information
        
        Args:
            query: Search query
            
        Returns:
            Dict containing search results
        """
        try:
            bedrock_runtime = boto3.client('bedrock-agent-runtime', region_name=config.get('region'))
            knowledge_base_id = os.getenv('KNOWLEDGE_BASE_ID', 'kb-placeholder')
            
            response = bedrock_runtime.retrieve(
                knowledgeBaseId=knowledge_base_id,
                retrievalQuery={'text': query},
                retrievalConfiguration={
                    'vectorSearchConfiguration': {
                        'numberOfResults': 5,
                        'overrideSearchType': 'HYBRID'
                    }
                }
            )
            
            results = []
            for result in response.get('retrievalResults', []):
                results.append({
                    'content': result.get('content', {}).get('text', ''),
                    'score': result.get('score', 0)
                })
            
            return {'query': query, 'results': results, 'count': len(results)}
            
        except Exception as e:
            logger.error(f"Knowledge base search failed: {e}")
            return {'query': query, 'error': str(e), 'results': []}
    
    async def _invoke_agent(self, user_input: str, context: Dict[str, Any]) -> Any:
        """Let the Strands Agent handle orchestration automatically"""
        # Simply pass the query to the agent - it will decide which tools to use
        if context:
            contextualized_input = f"Context: {json.dumps(context)}\n\nUser Query: {user_input}"
        else:
            contextualized_input = user_input
        
        # The Strands Agent will automatically:
        # 1. Analyze the query
        # 2. Decide which tools to use
        # 3. Call the tools
        # 4. Synthesize the results
        # Agent is callable, call it directly (not invoke)
        return self.agent(contextualized_input)

# Create singleton instance for AgentCore
coordinator_agent_v2 = EnhancedCoordinatorAgentV2()
coordinator_agent = coordinator_agent_v2  # Backward compatibility alias

# AgentCore handler
def agentcore_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """AgentCore entry point"""
    return coordinator_agent_v2.agentcore_handler(event)

# For local testing
if __name__ == "__main__":
    test_event = {
        'input': 'Analyze Cambridge market absorption rates and suggest investment opportunities',
        'sessionId': 'test-session-002'
    }
    
    result = agentcore_handler(test_event)
    print(json.dumps(result, indent=2))