"""
Base Agent Class for AgentCore Integration
Provides common functionality for all BDA agents deployed on AWS Bedrock AgentCore
"""

from strands import Agent, tool
from strands.models.bedrock import BedrockModel
import asyncio
import json
import os
from typing import Dict, Any, Optional
import logging

# Configure logging
logger = logging.getLogger(__name__)

class SimpleSessionManager:
    """Simple session manager for agent state management"""
    def __init__(self, session_id=None, persist_sessions=True):
        self.session_id = session_id
        self.persist_sessions = persist_sessions
        self.messages = []
    
    def append_message(self, message):
        self.messages.append(message)
    
    def initialize(self):
        pass
    
    def redact_latest_message(self):
        if self.messages:
            self.messages.pop()
    
    def sync_agent(self):
        pass
    
    def register_hooks(self, hooks=None):
        pass

class AgentCoreBaseAgent:
    """
    Base class for all BDA agents with AgentCore integration
    Provides standard AgentCore handler and common functionality
    """
    
    def __init__(self, agent_name: str, agent_type: str, model_config: Dict[str, Any], tools: list = None, suppress_outputs: bool = True):
        self.agent_name = agent_name
        self.agent_type = agent_type
        self.model_config = model_config
        self.tools = tools or []
        self.suppress_outputs = suppress_outputs  # Enable output suppression by default
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize Strands agent
        self.agent = self._create_strands_agent()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load agent configuration from config.json"""
        try:
            config_path = os.path.join(
                os.path.dirname(__file__), 
                '..', '..', 'bda_stacks', 'config.json'
            )
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}, using defaults")
            return {
                'agentModelId': 'us.anthropic.claude-3-7-sonnet-20250219-v1:0',
                'region': os.getenv('AWS_DEFAULT_REGION') or os.getenv('AWS_REGION')
            }
    
    def _create_strands_agent(self) -> Agent:
        """Create the Strands agent instance"""
        return Agent(
            name=self.agent_name,
            model=BedrockModel(
                model_id=self.model_config.get('model_id', self.config.get('agentModelId')),
                region=self.model_config.get('region', os.getenv('AWS_DEFAULT_REGION') or os.getenv('AWS_REGION'))
            ),
            tools=self.tools,
            system_prompt=self.get_system_prompt(),
            session_manager=SimpleSessionManager(
                session_id=None,
                persist_sessions=True
            )
        )
    
    def get_system_prompt(self) -> str:
        """Override in subclasses to provide agent-specific prompts"""
        return f"You are {self.agent_name}, a specialized {self.agent_type} agent in the BDA Real Estate Portfolio Advisory system."
    
    async def process_request(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming AgentCore request with output suppression support"""
        try:
            # Extract request data
            user_input = event.get('input', event.get('prompt', ''))
            session_id = event.get('sessionId', event.get('session_id', 'default'))
            context = event.get('context', {})
            suppress_outputs = event.get('suppress_outputs', self.suppress_outputs)
            
            # Set session ID if agent has session manager
            if hasattr(self.agent, 'session_manager') and self.agent.session_manager:
                self.agent.session_manager.session_id = session_id
            
            # Process through Strands agent
            response = await self._invoke_agent(user_input, context)
            
            # Apply output suppression if enabled
            if suppress_outputs:
                response = self._suppress_intermediate_outputs(response)
            
            # Format response for AgentCore
            return self._format_response(response, session_id)
            
        except Exception as e:
            logger.error(f"Error processing request: {str(e)}", exc_info=True)
            return self._format_error(str(e), event.get('sessionId', 'default'))
    
    async def _invoke_agent(self, user_input: str, context: Dict[str, Any]) -> Any:
        """Invoke the Strands agent with context"""
        # Add context to the prompt if provided
        if context:
            contextualized_input = f"Context: {json.dumps(context)}\n\nUser Query: {user_input}"
        else:
            contextualized_input = user_input
            
        # Agent is callable, use it directly and convert to string
        result = self.agent(contextualized_input)
        return str(result)
    
    async def stream_handler(self, user_input: str, session_id: str, context: Dict[str, Any] = None):
        """
        Stream agent responses in real-time using Strands stream_async
        
        Args:
            user_input: The user's prompt
            session_id: Session identifier
            context: Optional context dictionary
            
        Yields:
            Dict events containing streaming data
        """
        try:
            # Set session ID if agent has session manager
            if hasattr(self.agent, 'session_manager') and self.agent.session_manager:
                self.agent.session_manager.session_id = session_id
            
            # Add context to the prompt if provided
            if context:
                contextualized_input = f"Context: {json.dumps(context)}\n\nUser Query: {user_input}"
            else:
                contextualized_input = user_input
            
            # Check if agent supports stream_async
            if hasattr(self.agent, 'stream_async'):
                logger.info(f"Starting streaming for session {session_id}")
                
                # Stream events from the agent
                async for event in self.agent.stream_async(contextualized_input):
                    # Process different event types
                    if isinstance(event, dict):
                        # Handle different event types from Strands
                        if "data" in event:
                            # Text generation event
                            yield {
                                "type": "text",
                                "data": event["data"],
                                "sessionId": session_id,
                                "agent": self.agent_name
                            }
                        elif "delta" in event:
                            # Raw model output delta
                            yield {
                                "type": "delta",
                                "delta": event["delta"],
                                "sessionId": session_id,
                                "agent": self.agent_name
                            }
                        elif "tool" in event:
                            # Tool usage event
                            yield {
                                "type": "tool",
                                "tool": event["tool"],
                                "sessionId": session_id,
                                "agent": self.agent_name
                            }
                        elif "reasoning" in event:
                            # Reasoning event
                            yield {
                                "type": "reasoning",
                                "reasoning": event["reasoning"],
                                "sessionId": session_id,
                                "agent": self.agent_name
                            }
                        elif "lifecycle" in event:
                            # Lifecycle event
                            yield {
                                "type": "lifecycle",
                                "lifecycle": event["lifecycle"],
                                "sessionId": session_id,
                                "agent": self.agent_name
                            }
                        else:
                            # Unknown event type, pass through
                            yield {
                                "type": "event",
                                "event": event,
                                "sessionId": session_id,
                                "agent": self.agent_name
                            }
                    else:
                        # Plain text response
                        yield {
                            "type": "text",
                            "data": str(event),
                            "sessionId": session_id,
                            "agent": self.agent_name
                        }
                
                logger.info(f"Streaming completed for session {session_id}")
                
            else:
                # Fallback for agents without streaming support
                logger.warning(f"Agent {self.agent_name} doesn't support stream_async, using single response")
                
                # Get single response and yield as one event
                result = self.agent(contextualized_input)
                yield {
                    "type": "text",
                    "data": str(result),
                    "sessionId": session_id,
                    "agent": self.agent_name,
                    "streaming": False
                }
                
        except Exception as e:
            logger.error(f"Streaming error for session {session_id}: {str(e)}", exc_info=True)
            yield {
                "type": "error",
                "error": str(e),
                "sessionId": session_id,
                "agent": self.agent_name
            }
    
    def _suppress_intermediate_outputs(self, response: Any) -> Any:
        """Suppress intermediate outputs for cleaner agent communication"""
        if isinstance(response, dict):
            # Remove common intermediate output keys
            suppressed = response.copy()
            keys_to_suppress = ['intermediate_outputs', 'debug_info', 'raw_response', 'processing_steps']
            for key in keys_to_suppress:
                suppressed.pop(key, None)
            return suppressed
        return response
    
    def _format_response(self, response: Any, session_id: str) -> Dict[str, Any]:
        """Format response for AgentCore with output suppression metadata"""
        return {
            'response': response,
            'sessionId': session_id,
            'agent': self.agent_name,
            'type': self.agent_type,
            'metadata': {
                'model': self.model_config.get('model_id', self.config.get('agentModelId')),
                'framework': 'strands',
                'capabilities': [tool.__name__ for tool in self.tools],
                'output_suppression': self.suppress_outputs
            }
        }
    
    def _format_error(self, error_message: str, session_id: str) -> Dict[str, Any]:
        """Format error response for AgentCore"""
        return {
            'error': error_message,
            'sessionId': session_id,
            'agent': self.agent_name,
            'type': self.agent_type,
            'status': 'error'
        }
    
    def agentcore_handler(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point for AgentCore invocations
        Properly handles async processing with event loop management
        """
        try:
            # Check if there's already a running loop
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, can't use asyncio.run
                # Create a new thread to run the async function
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.process_request(event))
                    return future.result()
            except RuntimeError:
                # No running loop, safe to use asyncio.run
                return asyncio.run(self.process_request(event))
        except Exception as e:
            logger.error(f"Handler error: {str(e)}", exc_info=True)
            return self._format_error(str(e), event.get('sessionId', 'default'))

    def add_tool(self, tool_func):
        """Add a new tool to the agent"""
        self.tools.append(tool_func)
        # Recreate agent with updated tools
        self.agent = self._create_strands_agent()
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Return agent capabilities for discovery"""
        return {
            'name': self.agent_name,
            'type': self.agent_type,
            'tools': [tool.__name__ for tool in self.tools],
            'model': self.model_config,
            'description': self.get_system_prompt()
        }
    
    def __call__(self, prompt: str, suppress_outputs: bool = None) -> str:
        """
        Make the agent directly callable as a tool
        
        Args:
            prompt: The prompt to send to the agent
            suppress_outputs: Whether to suppress intermediate outputs (uses agent default if None)
            
        Returns:
            String response from the agent
        """
        try:
            # Use the agent's suppress_outputs setting if not specified
            if suppress_outputs is None:
                suppress_outputs = self.suppress_outputs
            
            # Call the Strands agent directly
            result = self.agent(prompt)
            
            # Apply output suppression if needed
            if suppress_outputs:
                result = self._suppress_intermediate_outputs(result)
            
            # Ensure we return a string
            if isinstance(result, dict):
                return json.dumps(result, indent=2)
            return str(result)
            
        except Exception as e:
            logger.error(f"Error in agent __call__: {str(e)}")
            return f"Agent invocation error: {str(e)}"