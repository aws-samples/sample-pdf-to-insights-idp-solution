import json
import os
import uuid
from datetime import datetime
import logging
from typing import Dict, Any
import boto3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
USE_AGENTCORE = os.environ.get('USE_AGENTCORE', 'true').lower() == 'true'
AGENTCORE_RUNTIME_ARN = os.environ.get('AGENTCORE_RUNTIME_ARN', '')
# Use AWS_REGION from Lambda environment, no fallback to hardcoded region
AWS_REGION = os.environ.get('DEPLOYMENT_REGION', os.environ.get('AWS_REGION'))

# Initialize boto3 client for AgentCore
if USE_AGENTCORE and AGENTCORE_RUNTIME_ARN:
    try:
        agentcore_client = boto3.client('bedrock-agentcore', region_name=AWS_REGION)
        logger.info(f"Initialized AgentCore client for region: {AWS_REGION}")
    except Exception as e:
        logger.error(f"Failed to initialize AgentCore client: {str(e)}")
        agentcore_client = None
else:
    agentcore_client = None

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle chat interactions - invokes AWS Bedrock AgentCore runtime.
    
    Args:
        event: API Gateway event containing chat message
        context: Lambda context
        
    Returns:
        Response with agent's reply
    """
    try:
        # Parse request body
        if 'body' in event:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        else:
            body = event
            
        message = body.get('message', '').strip()
        session_id = body.get('sessionId', str(uuid.uuid4()))
        
        if not message:
            return create_error_response(400, "Message is required")
            
        if USE_AGENTCORE and agentcore_client and AGENTCORE_RUNTIME_ARN:
            try:
                # Prepare the request for AgentCore
                request_payload = {
                    "input": message,
                    "sessionId": session_id,
                    "context": {},
                    "parameters": {}
                }
                
                logger.info(f"Invoking AgentCore runtime: {AGENTCORE_RUNTIME_ARN}")
                logger.info(f"Request: {json.dumps(request_payload)}")
                
                # Invoke the AgentCore runtime
                response = agentcore_client.invoke_agent_runtime(
                    agentRuntimeArn=AGENTCORE_RUNTIME_ARN,
                    payload=json.dumps(request_payload)
                )
                
                # Parse the response
                response_text = ""
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
                    response_text = "Received response from agent but couldn't parse it."
                
                logger.info(f"Agent response: {response_text[:200]}...")
                
                return create_success_response({
                    'response': response_text,
                    'sessionId': session_id,
                    'timestamp': datetime.utcnow().isoformat()
                })
                
            except Exception as agent_error:
                logger.error(f"Error invoking AgentCore: {str(agent_error)}", exc_info=True)
                
                # Fallback to a helpful error message
                return create_success_response({
                    'response': f"I'm having trouble connecting to the AI agent. Please ensure the AgentCore runtime is deployed and accessible. Error: {str(agent_error)}",
                    'sessionId': session_id,
                    'timestamp': datetime.utcnow().isoformat(),
                    'error': True
                })
        else:
            # AgentCore not configured
            error_msg = []
            if not USE_AGENTCORE:
                error_msg.append("AgentCore is disabled")
            if not agentcore_client:
                error_msg.append("AgentCore client not initialized")
            if not AGENTCORE_RUNTIME_ARN:
                error_msg.append("AgentCore runtime ARN not configured")
                
            return create_success_response({
                'response': f"The AI agent is not properly configured. Issues: {', '.join(error_msg)}. Please contact your administrator.",
                'sessionId': session_id,
                'timestamp': datetime.utcnow().isoformat(),
                'error': True
            })
        
    except Exception as e:
        logger.error(f"Error handling agent chat: {str(e)}", exc_info=True)
        return create_error_response(500, f"Internal server error: {str(e)}")


def create_success_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a successful API response"""
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(data)
    }

def create_error_response(status_code: int, message: str) -> Dict[str, Any]:
    """Create an error API response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'error': message,
            'timestamp': datetime.utcnow().isoformat()
        })
    } 