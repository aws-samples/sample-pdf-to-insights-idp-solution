"""
Strands-compatible Knowledge Base Wrapper for BDA
Provides seamless integration between Strands agents and Bedrock Knowledge Base
"""

import boto3
import os
from typing import Dict, List, Any
from strands import tool

class BDAKnowledgeBaseWrapper:
    def __init__(self, knowledge_base_id: str, region: str = None):
        self.knowledge_base_id = knowledge_base_id
        self.region = region or os.getenv('AWS_DEFAULT_REGION') or os.getenv('AWS_REGION')
        if not self.region:
            raise ValueError("AWS region must be set via parameter or environment variables")
        self.bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=region)
    
    def search(self, query: str, max_results: int = 10, search_type: str = 'HYBRID') -> Dict[str, Any]:
        """
        Search the knowledge base with enhanced error handling and formatting
        """
        try:
            response = self.bedrock_agent_runtime.retrieve(
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={'text': query},
                retrievalConfiguration={
                    'vectorSearchConfiguration': {
                        'numberOfResults': max_results,
                        'overrideSearchType': search_type
                    }
                }
            )
            
            # Format results for Strands agents
            formatted_results = []
            for result in response.get('retrievalResults', []):
                formatted_results.append({
                    'content': result.get('content', {}).get('text', ''),
                    'metadata': result.get('metadata', {}),
                    'score': result.get('score', 0),
                    'location': result.get('location', {})
                })
            
            return {
                'query': query,
                'results': formatted_results,
                'total_results': len(formatted_results),
                'search_type': search_type,
                'knowledge_base_id': self.knowledge_base_id
            }
            
        except Exception as e:
            return {
                'query': query,
                'error': f"Knowledge base search failed: {str(e)}",
                'results': [],
                'total_results': 0
            }

# Global knowledge base wrapper instance
# KB ID must be provided via environment variable (set by CDK deployment)
kb_id = os.getenv('KNOWLEDGE_BASE_ID')
if not kb_id:
    import logging
    logging.warning("KNOWLEDGE_BASE_ID environment variable not set. Knowledge base features will be disabled.")
    # Create a dummy wrapper that returns empty results
    class DummyKBWrapper:
        def search(self, query: str, max_results: int = 10, search_type: str = 'HYBRID') -> Dict[str, Any]:
            return {
                'query': query,
                'error': 'Knowledge Base ID not configured. Please set KNOWLEDGE_BASE_ID environment variable.',
                'results': [],
                'total_results': 0
            }
    kb_wrapper = DummyKBWrapper()
else:
    kb_wrapper = BDAKnowledgeBaseWrapper(
        knowledge_base_id=kb_id,
        region=os.getenv('AWS_DEFAULT_REGION') or os.getenv('AWS_REGION')
    )

@tool
def search_bda_knowledge_base(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Strands tool for searching the BDA knowledge base
    
    Args:
        query: Search query for real estate market information
        max_results: Maximum number of results to return
        
    Returns:
        Dict containing search results and metadata
    """
    return kb_wrapper.search(query, max_results)

@tool
def get_market_documents(location: str, property_type: str = "commercial") -> Dict[str, Any]:
    """
    Retrieve market documents for a specific location and property type
    
    Args:
        location: Geographic location (city, state, region)
        property_type: Type of property (commercial, residential, industrial)
        
    Returns:
        Dict containing relevant market documents
    """
    query = f"{location} {property_type} real estate market analysis"
    return kb_wrapper.search(query, max_results=15)

@tool
def get_investment_insights(investment_type: str, market_conditions: str = "") -> Dict[str, Any]:
    """
    Retrieve investment insights from the knowledge base
    
    Args:
        investment_type: Type of investment (commercial real estate, REITs, etc.)
        market_conditions: Additional market condition context
        
    Returns:
        Dict containing investment analysis and insights
    """
    query = f"{investment_type} investment analysis {market_conditions}"
    return kb_wrapper.search(query, max_results=12)
