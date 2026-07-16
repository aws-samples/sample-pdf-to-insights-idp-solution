"""
Multi-Agent Workflow Orchestrator for BDA Strands Agents
Implements coordinated workflows between specialized agents using Tool-Agent pattern
Following Strand Agents best practices for multi-agent systems
"""

from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from ..shared.agent_tools import (
    orchestrate_multi_agent_workflow,
    orchestrate_sequential_workflow,
    orchestrate_parallel_workflow,
    synthesize_agent_responses
)
from ..shared.specialist_tools import (
    market_analyst_tool,
    investment_advisor_tool,
    external_api_tool,
    knowledge_base_tool
)
import asyncio
import json
import os
import time
from typing import Dict, List, Any, Optional, Union
from enum import Enum
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

class WorkflowType(Enum):
    COMPREHENSIVE_ANALYSIS = "comprehensive_market_analysis"
    RISK_ASSESSMENT = "investment_risk_assessment"
    MARKET_COMPARISON = "market_comparison_analysis"
    PORTFOLIO_OPTIMIZATION = "portfolio_optimization"
    CAMBRIDGE_ANALYSIS = "cambridge_market_absorption"

@dataclass
class WorkflowResult:
    workflow_type: WorkflowType
    session_id: str
    agents_involved: List[str]
    execution_time: float
    result: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None

class BDAWorkflowOrchestrator:
    """
    Orchestrates complex multi-agent workflows using Tool-Agent pattern
    Implements parallel, sequential, and synthesis patterns
    """
    
    def __init__(self, region: str = None):
        self.region = region or os.getenv('AWS_DEFAULT_REGION') or os.getenv('AWS_REGION')
        if not self.region:
            raise ValueError("AWS region must be set via parameter or environment variables")
        self.workflows = {}
        
        # Load configuration
        self.load_config()
        
        # Setup workflow definitions
        self.setup_workflows()
    
    def load_config(self):
        """Load configuration for workflow orchestration"""
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'bda_stacks', 'config.json')
        with open(config_path, 'r') as f:
            self.config = json.load(f)
    
    def setup_workflows(self):
        """Define workflow patterns using Tool-Agent pattern"""
        
        # Comprehensive Market Analysis Workflow
        self.workflows[WorkflowType.COMPREHENSIVE_ANALYSIS] = {
            'name': 'Comprehensive Market Analysis',
            'pattern': 'sequential',
            'agents': ['external_api', 'market_analyst', 'investment_advisory'],
            'suppress_outputs': True
        }
        
        # Risk Assessment Workflow
        self.workflows[WorkflowType.RISK_ASSESSMENT] = {
            'name': 'Investment Risk Assessment',
            'pattern': 'parallel',
            'agents': ['market_analyst', 'investment_advisory'],
            'suppress_outputs': True
        }
        
        # Market Comparison Workflow
        self.workflows[WorkflowType.MARKET_COMPARISON] = {
            'name': 'Market Comparison Analysis',
            'pattern': 'synthesis',
            'agents': ['external_api', 'market_analyst'],
            'suppress_outputs': True
        }
        
        # Portfolio Optimization Workflow
        self.workflows[WorkflowType.PORTFOLIO_OPTIMIZATION] = {
            'name': 'Portfolio Optimization',
            'pattern': 'sequential',
            'agents': ['market_analyst', 'investment_advisory'],
            'suppress_outputs': True
        }
        
        # Cambridge Market Analysis Workflow
        self.workflows[WorkflowType.CAMBRIDGE_ANALYSIS] = {
            'name': 'Cambridge Market Absorption Analysis',
            'pattern': 'synthesis',
            'agents': ['external_api', 'market_analyst', 'investment_advisory'],
            'suppress_outputs': True
        }
    
    async def execute_workflow(
        self,
        workflow_type: WorkflowType,
        query: str,
        session_id: str = None,
        context: Optional[Dict] = None
    ) -> WorkflowResult:
        """
        Execute a predefined workflow using Tool-Agent pattern
        
        Args:
            workflow_type: Type of workflow to execute
            query: User query to process
            session_id: Session identifier
            context: Additional context for the workflow
            
        Returns:
            WorkflowResult with execution details and results
        """
        start_time = time.time()
        session_id = session_id or f"workflow-{workflow_type.value}-{int(time.time())}"
        
        try:
            workflow_config = self.workflows.get(workflow_type)
            if not workflow_config:
                raise ValueError(f"Unknown workflow type: {workflow_type}")
            
            logger.info(f"Executing {workflow_config['name']} workflow")
            
            # Execute workflow using orchestrate_multi_agent_workflow tool
            result = await orchestrate_multi_agent_workflow(
                query=query,
                agents=workflow_config['agents'],
                pattern=workflow_config['pattern'],
                suppress_outputs=workflow_config['suppress_outputs']
            )
            
            # Add any additional context-specific processing
            if workflow_type == WorkflowType.CAMBRIDGE_ANALYSIS:
                result = await self._enhance_cambridge_analysis(result, query, context)
            elif workflow_type == WorkflowType.PORTFOLIO_OPTIMIZATION:
                result = await self._enhance_portfolio_optimization(result, context)
            
            execution_time = time.time() - start_time
            
            return WorkflowResult(
                workflow_type=workflow_type,
                session_id=session_id,
                agents_involved=workflow_config['agents'],
                execution_time=execution_time,
                result=result,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Workflow execution failed: {str(e)}")
            execution_time = time.time() - start_time
            
            return WorkflowResult(
                workflow_type=workflow_type,
                session_id=session_id,
                agents_involved=workflow_config.get('agents', []),
                execution_time=execution_time,
                result={},
                success=False,
                error_message=str(e)
            )
    
    async def _enhance_cambridge_analysis(
        self,
        base_result: Dict[str, Any],
        query: str,
        context: Optional[Dict]
    ) -> Dict[str, Any]:
        """
        Enhance Cambridge market analysis with specific insights
        """
        enhanced_result = base_result.copy()
        
        # Add Cambridge-specific analysis
        if 'agent_responses' in enhanced_result:
            market_data = enhanced_result['agent_responses'].get('external_api', {})
            
            # Request specific Cambridge metrics
            cambridge_metrics = market_analyst_tool(
                query="Calculate absorption rate trends and construction pipeline metrics for Cambridge office market",
                suppress_outputs=True
            )
            
            enhanced_result['cambridge_insights'] = {
                'absorption_trends': cambridge_metrics.get('absorption_trends', {}),
                'construction_pipeline': cambridge_metrics.get('construction_pipeline', {}),
                'market_fundamentals': market_data,
                'investment_opportunities': enhanced_result['agent_responses'].get('investment_advisory', {})
            }
        
        return enhanced_result
    
    async def _enhance_portfolio_optimization(
        self,
        base_result: Dict[str, Any],
        context: Optional[Dict]
    ) -> Dict[str, Any]:
        """
        Enhance portfolio optimization with allocation strategies
        """
        enhanced_result = base_result.copy()
        
        # Add portfolio-specific optimizations
        if context and 'portfolio_constraints' in context:
            constraints = context['portfolio_constraints']
            
            # Request optimization with constraints
            optimization = investment_advisor_tool(
                query=f"Optimize portfolio allocation with constraints: {json.dumps(constraints)}",
                context=enhanced_result.get('agent_responses', {}).get('market_analyst', {}),
                suppress_outputs=True
            )
            
            enhanced_result['optimization'] = {
                'recommended_allocation': optimization.get('allocation', {}),
                'risk_metrics': optimization.get('risk_metrics', {}),
                'expected_returns': optimization.get('expected_returns', {}),
                'constraints_applied': constraints
            }
        
        return enhanced_result
    
    async def execute_parallel_workflows(
        self,
        workflows: List[tuple],
        session_id: str = None
    ) -> List[WorkflowResult]:
        """
        Execute multiple workflows in parallel
        
        Args:
            workflows: List of (workflow_type, query, context) tuples
            session_id: Shared session identifier
            
        Returns:
            List of WorkflowResult objects
        """
        session_id = session_id or f"parallel-{int(time.time())}"
        
        tasks = []
        for workflow_type, query, context in workflows:
            task = self.execute_workflow(
                workflow_type=workflow_type,
                query=query,
                session_id=f"{session_id}-{workflow_type.value}",
                context=context
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to failed WorkflowResults
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                workflow_type, query, _ = workflows[i]
                processed_results.append(
                    WorkflowResult(
                        workflow_type=workflow_type,
                        session_id=f"{session_id}-{workflow_type.value}",
                        agents_involved=[],
                        execution_time=0.0,
                        result={},
                        success=False,
                        error_message=str(result)
                    )
                )
            else:
                processed_results.append(result)
        
        return processed_results
    
    def get_workflow_capabilities(self) -> Dict[str, Any]:
        """Return available workflows and their configurations"""
        capabilities = {}
        
        for workflow_type, config in self.workflows.items():
            capabilities[workflow_type.value] = {
                'name': config['name'],
                'pattern': config['pattern'],
                'agents': config['agents'],
                'description': self._get_workflow_description(workflow_type)
            }
        
        return capabilities
    
    def _get_workflow_description(self, workflow_type: WorkflowType) -> str:
        """Get description for a workflow type"""
        descriptions = {
            WorkflowType.COMPREHENSIVE_ANALYSIS: 
                "Complete market analysis combining external data, financial metrics, and investment recommendations",
            WorkflowType.RISK_ASSESSMENT: 
                "Parallel risk assessment using market analysis and investment advisory insights",
            WorkflowType.MARKET_COMPARISON: 
                "Synthesized comparison of multiple market segments and performance metrics",
            WorkflowType.PORTFOLIO_OPTIMIZATION: 
                "Sequential portfolio optimization with market analysis feeding investment recommendations",
            WorkflowType.CAMBRIDGE_ANALYSIS:
                "Specialized Cambridge market absorption and construction activity analysis with investment opportunities"
        }
        return descriptions.get(workflow_type, "Custom workflow")

# Create global orchestrator instance
orchestrator = BDAWorkflowOrchestrator()

# Tool functions for use in agents
@tool
async def execute_comprehensive_analysis(query: str, context: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Execute comprehensive market analysis workflow
    
    Args:
        query: Analysis query
        context: Additional context
        
    Returns:
        Comprehensive analysis results
    """
    result = await orchestrator.execute_workflow(
        WorkflowType.COMPREHENSIVE_ANALYSIS,
        query,
        context=context
    )
    return result.result if result.success else {'error': result.error_message}

@tool
async def execute_risk_assessment(query: str, context: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Execute investment risk assessment workflow
    
    Args:
        query: Risk assessment query
        context: Additional context
        
    Returns:
        Risk assessment results
    """
    result = await orchestrator.execute_workflow(
        WorkflowType.RISK_ASSESSMENT,
        query,
        context=context
    )
    return result.result if result.success else {'error': result.error_message}

@tool
async def execute_portfolio_optimization(
    query: str,
    constraints: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Execute portfolio optimization workflow
    
    Args:
        query: Optimization query
        constraints: Portfolio constraints
        
    Returns:
        Optimization results
    """
    context = {'portfolio_constraints': constraints} if constraints else None
    result = await orchestrator.execute_workflow(
        WorkflowType.PORTFOLIO_OPTIMIZATION,
        query,
        context=context
    )
    return result.result if result.success else {'error': result.error_message}

# Test function for local development
async def test_orchestrator():
    """Test the workflow orchestrator locally"""
    print("🧪 Testing BDA Workflow Orchestrator...")
    
    # Test comprehensive analysis
    result = await orchestrator.execute_workflow(
        WorkflowType.COMPREHENSIVE_ANALYSIS,
        "Analyze the commercial real estate market in Boston"
    )
    
    print(f"\n📊 Workflow Result:")
    print(f"  - Success: {result.success}")
    print(f"  - Execution Time: {result.execution_time:.2f}s")
    print(f"  - Agents Involved: {result.agents_involved}")
    
    if result.success:
        print(f"  - Result Keys: {list(result.result.keys())}")
    else:
        print(f"  - Error: {result.error_message}")
    
    return result

if __name__ == "__main__":
    asyncio.run(test_orchestrator())