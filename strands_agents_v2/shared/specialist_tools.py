"""
Specialist Tools Module - Implements Agent-as-Tool Pattern
Following Strand Agents best practices for wrapping specialist agents as tools
"""

from strands import tool
from typing import Dict, Any, Optional
import json
import logging

logger = logging.getLogger(__name__)

@tool
def market_analyst_tool(query: str, suppress_outputs: bool = True) -> str:
    """
    Consult the Market Analyst Agent for financial calculations, metrics, and trend analysis.
    
    This specialist excels at:
    - Financial ratio calculations (P/E, ROI, cap rates)
    - Market trend identification and analysis
    - Performance metrics and comparisons
    - Numerical computations for real estate investments
    
    Args:
        query: The financial analysis question or calculation request
        suppress_outputs: Whether to suppress intermediate outputs (default: True)
        
    Returns:
        Market analysis results as a string
    """
    try:
        from ..market_analyst.agent import market_analyst_agent
        
        # Call the agent directly
        result = market_analyst_agent(query)
        
        # Handle output suppression if needed
        if suppress_outputs and isinstance(result, dict):
            # Remove intermediate outputs for cleaner agent-to-agent communication
            result.pop('intermediate_outputs', None)
            result.pop('debug_info', None)
            
        return str(result)
        
    except Exception as e:
        logger.error(f"Error consulting Market Analyst: {str(e)}")
        return f"Market Analyst consultation failed: {str(e)}"

@tool
def investment_advisor_tool(query: str, context: Optional[Dict] = None, suppress_outputs: bool = True) -> str:
    """
    Consult the Investment Advisory Agent for portfolio recommendations and risk assessment.
    
    This specialist excels at:
    - Portfolio optimization strategies
    - Risk assessment and mitigation
    - Investment recommendations based on market conditions
    - Asset allocation advice
    - ESG and sustainability considerations
    
    Args:
        query: The investment advisory question or recommendation request
        context: Optional market context or portfolio constraints
        suppress_outputs: Whether to suppress intermediate outputs (default: True)
        
    Returns:
        Investment advisory recommendations as a string
    """
    try:
        from ..investment_advisory.agent import investment_advisor_agent
        
        # Add context to query if provided
        if context:
            enriched_query = f"{query}\n\nContext: {json.dumps(context, indent=2)}"
        else:
            enriched_query = query
        
        # Call the agent directly
        result = investment_advisor_agent(enriched_query)
        
        # Handle output suppression if needed
        if suppress_outputs and isinstance(result, dict):
            result.pop('intermediate_outputs', None)
            result.pop('debug_info', None)
            
        return str(result)
        
    except Exception as e:
        logger.error(f"Error consulting Investment Advisor: {str(e)}")
        return f"Investment Advisor consultation failed: {str(e)}"

@tool
def external_api_tool(query: str, data_type: str = "market_data", suppress_outputs: bool = True) -> str:
    """
    External Data API - Fetches real-time market data and external information.
    
    USE FOR: Current stock prices, real-time quotes, economic indicators (GDP, inflation),
    market news, commodity prices, forex rates, cryptocurrency data,
    interest rates, bond yields, real estate market data.
    
    Args:
        query: Data retrieval request for current/real-time information
        data_type: Type of data to retrieve (market_data, economic_indicators, demographics)
        suppress_outputs: Whether to suppress intermediate outputs (default: True)
        
    Returns:
        Current market data and external information
    """
    try:
        from ..external_api.agent import external_api_agent
        
        # Enhance query with data type
        enhanced_query = f"{query} [Requesting {data_type}]"
        
        # Call the agent directly
        result = external_api_agent(enhanced_query)
        
        # Handle output suppression if needed
        if suppress_outputs and isinstance(result, dict):
            result.pop('intermediate_outputs', None)
            result.pop('debug_info', None)
            result.pop('raw_api_response', None)
            
        return str(result)
        
    except Exception as e:
        logger.error(f"Error consulting External API Agent: {str(e)}")
        return f"External API consultation failed: {str(e)}"

@tool
def knowledge_base_tool(query: str, doc_type: str = "all", suppress_outputs: bool = True) -> str:
    """
    Knowledge Base - Searches historical documents and institutional knowledge.
    
    USE FOR: Past reports, historical analyses, previous investment decisions,
    company documentation, policies, procedures, lessons learned,
    market research archives, performance history.
    
    Args:
        query: Search query for historical/documented information
        doc_type: Type of documents to search (all, market_reports, investments, properties)
        suppress_outputs: Whether to suppress intermediate outputs (default: True)
        
    Returns:
        Historical documents and institutional knowledge
    """
    try:
        import boto3
        import os
        
        # Initialize Bedrock Agent Runtime client
        region = os.getenv('AWS_DEFAULT_REGION')
        if not region:
            region = os.getenv('AWS_REGION')  # Try alternative env var
            if not region:
                raise ValueError("AWS region must be set via AWS_DEFAULT_REGION or AWS_REGION environment variable")
        
        bedrock_agent_runtime = boto3.client(
            'bedrock-agent-runtime',
            region_name=region
        )
        
        # Get knowledge base ID from environment or config
        knowledge_base_id = os.getenv('KNOWLEDGE_BASE_ID', 'kb-placeholder')
        
        # Add document type filter to query if specified
        if doc_type != "all":
            enhanced_query = f"{query} [Filter: {doc_type}]"
        else:
            enhanced_query = query
        
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=knowledge_base_id,
            retrievalQuery={'text': enhanced_query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': 5,
                    'overrideSearchType': 'HYBRID'
                }
            }
        )
        
        # Process results
        results = []
        for result in response.get('retrievalResults', []):
            content = result.get('content', {}).get('text', '')
            if suppress_outputs:
                # Truncate very long content
                if len(content) > 500:
                    content = content[:500] + "..."
            results.append(content)
        
        if results:
            return f"Knowledge Base Results:\n" + "\n---\n".join(results)
        else:
            return "No relevant documents found in Knowledge Base."
            
    except Exception as e:
        logger.error(f"Error searching Knowledge Base: {str(e)}")
        return f"Knowledge Base search failed: {str(e)}"

# Composite tool for complex multi-agent queries
@tool
def consult_multiple_specialists(
    query: str,
    specialists: list = None,
    combine_results: bool = True
) -> str:
    """
    Consult multiple specialist agents for comprehensive analysis.
    
    This orchestration tool allows consulting multiple specialists in parallel
    and optionally combining their insights into a unified response.
    
    Args:
        query: The query to send to all specified specialists
        specialists: List of specialists to consult (market_analyst, investment_advisor, external_api, knowledge_base)
        combine_results: Whether to combine results into a synthesis (default: True)
        
    Returns:
        Combined or individual specialist responses
    """
    if specialists is None:
        specialists = ['market_analyst', 'investment_advisor']
    
    results = {}
    
    try:
        for specialist in specialists:
            if specialist == 'market_analyst':
                results['market_analyst'] = market_analyst_tool(query)
            elif specialist == 'investment_advisor':
                results['investment_advisor'] = investment_advisor_tool(query)
            elif specialist == 'external_api':
                results['external_api'] = external_api_tool(query)
            elif specialist == 'knowledge_base':
                results['knowledge_base'] = knowledge_base_tool(query)
        
        if combine_results:
            # Synthesize results
            synthesis = "Comprehensive Analysis:\n\n"
            for specialist, response in results.items():
                synthesis += f"**{specialist.replace('_', ' ').title()} Insights:**\n{response}\n\n"
            return synthesis
        else:
            return json.dumps(results, indent=2)
            
    except Exception as e:
        logger.error(f"Error in multi-specialist consultation: {str(e)}")
        return f"Multi-specialist consultation failed: {str(e)}"