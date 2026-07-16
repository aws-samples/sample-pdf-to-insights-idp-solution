#!/usr/bin/env python3
"""
Real AgentCore Handler for Portfolio Advisory Agents
Implements the required /invocations endpoint with actual agent logic
"""

import os
import sys
import json
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn
import importlib
from pathlib import Path

# OpenTelemetry imports for session tracking and tracing
try:
    from opentelemetry import baggage, context, trace
    from opentelemetry.trace import get_current_span
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    get_current_span = None

# Import CloudWatch handler
try:
    from cloudwatch_handler import setup_cloudwatch_logging
    CW_AVAILABLE = True
except ImportError:
    CW_AVAILABLE = False

# Create a StreamHandler that outputs to stdout
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.INFO)

# Use JSON format for CloudWatch compatibility
formatter = logging.Formatter(
    '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
)
stdout_handler.setFormatter(formatter)

# Configure root logger
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    handlers=[stdout_handler],
    force=True  # Override any existing configuration
)

# Get logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level, logging.INFO))

# Ensure logs are immediately flushed to stdout
class FlushHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

# Replace handler with flush-enabled one
logger.handlers = []
flush_handler = FlushHandler(sys.stdout)
flush_handler.setFormatter(formatter)
logger.addHandler(flush_handler)

# Setup CloudWatch logging if available
if CW_AVAILABLE:
    try:
        cw_handler = setup_cloudwatch_logging(os.environ.get("AGENT_TYPE", "unknown"))
        logger.addHandler(cw_handler)
        logger.info("CloudWatch logging enabled")
    except Exception as e:
        logger.warning(f"Failed to setup CloudWatch logging: {e}")

# Initialize tracer for production observability
tracer = trace.get_tracer(__name__, "1.0.0") if OTEL_AVAILABLE else None

# Add project root to path for imports
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/strands_agents_v2')

# Create FastAPI app
app = FastAPI(
    title="AgentCore Runtime Handler",
    version="2.0.0"
)

# Get agent type from environment
AGENT_TYPE = os.environ.get("AGENT_TYPE", "coordinator")
KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID", "")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION")
if not AWS_REGION:
    raise ValueError("AWS region must be set via AWS_DEFAULT_REGION or AWS_REGION environment variable")

# Log startup information (reduced verbosity)
logger.info(f"Starting AgentCore handler for: {AGENT_TYPE}")
logger.debug(f"Knowledge Base ID: {KNOWLEDGE_BASE_ID}")  # Changed to debug
logger.debug(f"AWS Region: {AWS_REGION}")  # Changed to debug
logger.debug(f"Python path: {sys.path}")  # Changed to debug
logger.debug(f"Environment variables: {os.environ}")  # Changed to debug

# Global agent instance
agent_instance = None

def initialize_agent():
    """Initialize the appropriate agent based on AGENT_TYPE"""
    global agent_instance
    
    try:
        logger.debug(f"Initializing {AGENT_TYPE} agent...")  # Changed to debug
        
        # Map agent types to their modules and classes
        agent_mapping = {
            "coordinator": {
                "module": "strands_agents_v2.coordinator.agent",
                "instance": "coordinator_agent"
            },
            "market_analyst": {
                "module": "strands_agents_v2.market_analyst.agent",
                "instance": "market_analyst_agent"
            },
            "investment_advisory": {
                "module": "strands_agents_v2.investment_advisory.agent",
                "instance": "investment_advisory_agent"
            },
            "external_api": {
                "module": "strands_agents_v2.external_api.agent",
                "instance": "external_api_agent"
            }
        }
        
        if AGENT_TYPE not in agent_mapping:
            raise ValueError(f"Unknown agent type: {AGENT_TYPE}")
        
        agent_config = agent_mapping[AGENT_TYPE]
        
        # Import the agent module
        logger.debug(f"Importing module: {agent_config['module']}")  # Changed to debug
        agent_module = importlib.import_module(agent_config['module']) # nosemgrep
        # semgrep: ignore python.lang.security.audit.non-literal-import.non-literal-import
        # Reason: module value is selected from a hardcoded, internal whitelist (agent_mapping)
        # and AGENT_TYPE is validated above. This prevents untrusted input from controlling imports.
        
        # Get the agent instance
        agent_instance = getattr(agent_module, agent_config['instance'])
        
        logger.info(f"Successfully initialized {AGENT_TYPE} agent")  # Keep this at INFO
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize agent: {str(e)}", exc_info=True)
        # Fall back to a simple response function
        agent_instance = None
        return False

# No fallback responses - only real agent responses

@app.on_event("startup")
async def startup_event():
    """Initialize agent on startup"""
    logger.debug("FastAPI startup event triggered")  # Changed to debug
    
    if not initialize_agent():
        logger.error(f"Failed to initialize {AGENT_TYPE} agent - no fallback available")
    else:
        logger.info(f"{AGENT_TYPE} agent ready for invocations")  # Simplified message

@app.get("/ping")
async def health_check():
    """Health check endpoint required by AgentCore"""
    status = "healthy" if agent_instance else "unhealthy"
    logger.debug(f"Health check called - status: {status}")  # Changed to debug
    
    return {
        "status": status,
        "agent": AGENT_TYPE,
        "service": "agentcore-runtime",
        "initialized": agent_instance is not None
    }

@app.post("/invocations")
async def invoke(request: Request):
    """Main invocation endpoint required by AgentCore"""
    # Create span for observability
    span_context = {}
    if tracer:
        with tracer.start_as_current_span(
            "agentcore.invocation",
            attributes={
                "agent.type": AGENT_TYPE,
                "knowledge.base.id": KNOWLEDGE_BASE_ID,
                "region": AWS_REGION
            }
        ) as span:
            span_context['span'] = span
            return await _process_invocation(request, span_context)
    else:
        return await _process_invocation(request, span_context)

async def _process_invocation(request: Request, span_context: dict):
    """Process the actual invocation with optional span context"""
    try:
        span = span_context.get('span')
        
        # Log invocation start
        logger.debug(f"Invocation start for {AGENT_TYPE}")  # Changed to debug
        
        # Get request body
        body = await request.body()
        logger.debug(f"Received invocation body length: {len(body)} bytes")  # Changed to debug
        
        # Parse request
        if body:
            try:
                data = json.loads(body)
                logger.debug(f"Parsed JSON data: {json.dumps(data)[:500]}")  # Changed to debug
            except json.JSONDecodeError:
                # If not JSON, treat as plain text
                data = {"input": body.decode('utf-8') if isinstance(body, bytes) else str(body)}
                logger.debug(f"Non-JSON input received: {str(data)[:500]}")  # Changed to debug
        else:
            data = {}
            logger.warning("Empty request body received")
        
        # Extract input prompt
        prompt = data.get("input", data.get("prompt", data.get("query", "Hello")))
        session_id = data.get("sessionId", "default")
        request_context = data.get("context", {})
        
        # Add span attributes if available
        if span:
            span.set_attribute("session.id", session_id)
            span.set_attribute("prompt.length", len(prompt))
            span.set_attribute("has.context", bool(request_context))
        
        # Set session ID in baggage for correlation (if OpenTelemetry is available)
        if OTEL_AVAILABLE:
            ctx = baggage.set_baggage("session.id", session_id)
            context.attach(ctx)
        
        # Get trace information if available
        trace_id = span_id = None
        if OTEL_AVAILABLE and get_current_span:
            current_span = get_current_span()
            if current_span:
                span_context = current_span.get_span_context()
                if span_context:
                    trace_id = format(span_context.trace_id, '032x')
                    span_id = format(span_context.span_id, '016x')
        
        # Log the actual prompt from the user (this is what we want to see)
        logger.info(f"=== AGENT_PROMPT ===")
        logger.info(f"Session: {session_id}")
        if trace_id:
            logger.info(f"TraceId: {trace_id}")
            logger.info(f"SpanId: {span_id}")
        logger.info(f"Prompt: {prompt}")
        logger.info(f"===================")
        
        # Get response from real agent (no fallback)
        if not agent_instance:
            logger.error(f"Agent {AGENT_TYPE} not initialized - cannot process request")
            print(f"[STDOUT] ERROR: Agent not initialized", flush=True)
            raise HTTPException(status_code=503, detail=f"Agent {AGENT_TYPE} not initialized")
        
        try:
            logger.debug(f"Calling {AGENT_TYPE} agent...")  # Changed to debug
            
            # Check if the agent has an agentcore_handler method
            if hasattr(agent_instance, 'agentcore_handler'):
                # Use the AgentCore handler
                event = {
                    'input': prompt,
                    'sessionId': session_id,
                    'context': request_context
                }
                logger.debug(f"Using agentcore_handler method")  # Changed to debug
                
                # Create child span for agent processing
                if span:
                    with tracer.start_as_current_span(
                        "agent.processing",
                        attributes={"agent.method": "agentcore_handler"}
                    ) as agent_span:
                        response_data = agent_instance.agentcore_handler(event)
                        agent_span.set_attribute("response.type", type(response_data).__name__)
                else:
                    response_data = agent_instance.agentcore_handler(event)
                
                # Extract the response text
                if isinstance(response_data, dict):
                    response_text = response_data.get('response', str(response_data))
                else:
                    response_text = str(response_data)
            else:
                # Call the agent directly as a callable
                logger.debug(f"Calling agent as callable")  # Changed to debug
                
                # Create child span for agent processing
                if span:
                    with tracer.start_as_current_span(
                        "agent.processing",
                        attributes={"agent.method": "callable"}
                    ) as agent_span:
                        response_text = agent_instance(prompt)
                        agent_span.set_attribute("response.length", len(str(response_text)))
                else:
                    response_text = agent_instance(prompt)
                
                # Ensure we have a string
                if isinstance(response_text, dict):
                    response_text = json.dumps(response_text, indent=2)
                else:
                    response_text = str(response_text)
            
            # Log the actual LLM response (this is what we want to see)
            logger.info(f"=== AGENT_RESPONSE ===")
            logger.info(f"Session: {session_id}")
            if trace_id:
                logger.info(f"TraceId: {trace_id}")
                logger.info(f"SpanId: {span_id}")
            logger.info(f"Response: {response_text}")
            logger.info(f"======================")
                    
        except Exception as e:
            logger.error(f"Error calling agent: {str(e)}", exc_info=True)
            print(f"[STDOUT] ERROR: {str(e)}", flush=True)
            raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")
        
        # Add response metrics to span
        if span:
            span.set_attribute("response.length", len(str(response_text)))
            span.set_attribute("processing.success", True)
        
        # Format response
        response = {
            "response": str(response_text),  # Ensure it's always a string
            "sessionId": session_id,
            "agent": AGENT_TYPE,
            "metadata": {
                "agent_type": AGENT_TYPE,
                "knowledge_base_id": KNOWLEDGE_BASE_ID,
                "region": AWS_REGION,
                "initialized": True,
                "trace_id": trace_id if trace_id else None
            }
        }
        
        logger.debug(f"Invocation end for {AGENT_TYPE}, response size: {len(str(response_text))} bytes")  # Changed to debug
        
        return JSONResponse(content=response)
        
    except HTTPException:
        # Re-raise HTTP exceptions
        if span:
            span.set_attribute("processing.success", False)
            span.set_attribute("error.type", "HTTPException")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in invocation: {str(e)}", exc_info=True)
        print(f"[STDOUT] FATAL ERROR: {str(e)}", flush=True)
        sys.stdout.flush()
        
        if span:
            span.set_attribute("processing.success", False)
            span.set_attribute("error.message", str(e))
            span.set_attribute("error.type", type(e).__name__)
        
        error_response = {
            "error": str(e),
            "agent": AGENT_TYPE,
            "response": f"Error processing request: {str(e)}"
        }
        return JSONResponse(content=error_response, status_code=500)

@app.post("/stream")
async def stream_invoke(request: Request):
    """Streaming endpoint for real-time agent responses"""
    # Create span for observability
    span_context = {}
    if tracer:
        with tracer.start_as_current_span(
            "agentcore.stream",
            attributes={
                "agent.type": AGENT_TYPE,
                "streaming": True,
                "knowledge.base.id": KNOWLEDGE_BASE_ID,
                "region": AWS_REGION
            }
        ) as span:
            span_context['span'] = span
            return await _process_stream(request, span_context)
    else:
        return await _process_stream(request, span_context)

async def _process_stream(request: Request, span_context: dict):
    """Process streaming request with real-time response"""
    try:
        span = span_context.get('span')
        
        # Get request body
        body = await request.body()
        if body:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {"input": body.decode('utf-8') if isinstance(body, bytes) else str(body)}
        else:
            data = {}
        
        # Extract parameters
        prompt = data.get("input", data.get("prompt", data.get("query", "Hello")))
        session_id = data.get("sessionId", "default")
        request_context = data.get("context", {})
        
        # Add span attributes
        if span:
            span.set_attribute("session.id", session_id)
            span.set_attribute("prompt.length", len(prompt))
            span.set_attribute("streaming.enabled", True)
        
        # Set session ID in baggage
        if OTEL_AVAILABLE:
            ctx = baggage.set_baggage("session.id", session_id)
            context.attach(ctx)
        
        # Check if agent supports streaming
        if not agent_instance:
            logger.error(f"Agent {AGENT_TYPE} not initialized for streaming")
            raise HTTPException(status_code=503, detail=f"Agent {AGENT_TYPE} not initialized")
        
        if not hasattr(agent_instance, 'stream_handler'):
            logger.warning(f"Agent {AGENT_TYPE} does not support streaming, falling back to regular response")
            # Fall back to regular invocation wrapped in streaming
            event = {
                'input': prompt,
                'sessionId': session_id,
                'context': request_context
            }
            
            async def generate_fallback():
                """Generate single response as stream"""
                try:
                    if hasattr(agent_instance, 'agentcore_handler'):
                        response = agent_instance.agentcore_handler(event)
                        if isinstance(response, dict):
                            response_text = response.get('response', str(response))
                        else:
                            response_text = str(response)
                    else:
                        response_text = agent_instance(prompt)
                    
                    # Send as single chunk
                    yield f"data: {json.dumps({'type': 'text', 'data': response_text})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'sessionId': session_id})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            
            return StreamingResponse(
                generate_fallback(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Session-Id": session_id
                }
            )
        
        # Use agent's streaming capability
        async def generate_stream():
            """Generate streaming response from agent"""
            try:
                event_count = 0
                async for event in agent_instance.stream_handler(prompt, session_id, request_context):
                    event_count += 1
                    
                    # Log streaming events periodically
                    if event_count % 10 == 0:
                        logger.debug(f"Streamed {event_count} events for session {session_id}")
                    
                    # Format event for SSE
                    if isinstance(event, dict):
                        yield f"data: {json.dumps(event)}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'text', 'data': str(event)})}\n\n"
                
                # Send completion event
                yield f"data: {json.dumps({'type': 'done', 'sessionId': session_id, 'events': event_count})}\n\n"
                
                if span:
                    span.set_attribute("streaming.events", event_count)
                    span.set_attribute("streaming.success", True)
                    
            except Exception as e:
                logger.error(f"Streaming error: {str(e)}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
                
                if span:
                    span.set_attribute("streaming.success", False)
                    span.set_attribute("error.message", str(e))
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Session-Id": session_id,
                "X-Agent-Type": AGENT_TYPE
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Streaming endpoint error: {str(e)}", exc_info=True)
        if span:
            span.set_attribute("streaming.success", False)
            span.set_attribute("error.message", str(e))
        return JSONResponse(
            content={"error": str(e), "agent": AGENT_TYPE},
            status_code=500
        )

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "AgentCore Runtime",
        "agent": AGENT_TYPE,
        "status": "running",
        "initialized": agent_instance is not None,
        "endpoints": ["/ping", "/invocations", "/stream"],
        "streaming_supported": hasattr(agent_instance, 'stream_handler') if agent_instance else False
    }

# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "agent": AGENT_TYPE
        }
    )

if __name__ == "__main__":
    # Initialize agent before starting server
    initialize_agent()
    logger.info(f"Starting AgentCore handler on port 8080")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info") # nosec  # B104: running on all interfaces in a controlled environment