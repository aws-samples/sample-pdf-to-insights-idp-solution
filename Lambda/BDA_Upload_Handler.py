import json
import boto3
import os
import uuid
from datetime import datetime, timedelta
import logging
from typing import Dict, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Environment variables
BUCKET_NAME = os.environ.get('BUCKET_NAME')
STATUS_TABLE_NAME = os.environ.get('STATUS_TABLE_NAME')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Generate presigned URL for PDF upload and initialize document tracking.
    
    Args:
        event: API Gateway event containing file information
        context: Lambda context
        
    Returns:
        Response with presigned URL and document ID
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
            
        file_name = body.get('fileName')
        file_type = body.get('fileType', 'application/pdf')
        
        if not file_name:
            return create_error_response(400, "fileName is required")
            
        if not file_name.lower().endswith('.pdf'):
            return create_error_response(400, "Only PDF files are allowed")
            
        # Generate unique document ID and S3 key
        doc_id = str(uuid.uuid4())
        s3_key = f"uploads/{doc_id}/{file_name}"
        
        # Generate presigned URL for upload (valid for 1 hour)
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': s3_key,
                'ContentType': file_type,
                'Metadata': {
                    'original-filename': file_name,
                    'upload-timestamp': datetime.utcnow().isoformat(),
                    'document-id': doc_id
                }
            },
            ExpiresIn=3600  # 1 hour
        )
        
        # Initialize document tracking in DynamoDB
        status_table = dynamodb.Table(STATUS_TABLE_NAME)
        
        # Create initial status record
        status_item = {
            'doc_id': s3_key,
            'document_id': doc_id,
            'original_filename': file_name,
            'status': 'upload_pending',
            'upload_url': presigned_url,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'progress': 0,
            'bucket': BUCKET_NAME,
            'key': s3_key
        }
        
        status_table.put_item(Item=status_item)
        
        logger.info(f"Generated presigned URL for document {doc_id}: {file_name}")
        
        return create_success_response({
            'documentId': doc_id,
            'uploadUrl': presigned_url,
            's3Key': s3_key,
            'expiresIn': 3600,
            'message': 'Presigned URL generated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error generating presigned URL: {str(e)}", exc_info=True)
        return create_error_response(500, f"Internal server error: {str(e)}")

def create_success_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a successful API response"""
    return _create_api_response(200, data)

def create_error_response(status_code: int, message: str) -> Dict[str, Any]:
    """Create an error API response"""
    error_data = {
        'error': message,
        'timestamp': datetime.utcnow().isoformat()
    }
    return _create_api_response(status_code, error_data)

def _create_api_response(status_code: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create standardized API response with CORS headers"""
    return {
        'statusCode': status_code,
        'headers': _get_cors_headers(),
        'body': json.dumps(data)
    }

def _get_cors_headers() -> Dict[str, str]:
    """Get standard CORS headers"""
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
    } 