import json
import boto3
import os
import uuid
from datetime import datetime
import logging
from typing import Dict, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
stepfunctions_client = boto3.client('stepfunctions')
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# Environment variables
STEP_FUNCTION_ARN = os.environ.get('STEP_FUNCTION_ARN')
STATUS_TABLE_NAME = os.environ.get('STATUS_TABLE_NAME')
BUCKET_NAME = os.environ.get('BUCKET_NAME')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Start the Step Functions workflow for document processing.
    
    Args:
        event: API Gateway event containing processing options
        context: Lambda context
        
    Returns:
        Response with execution details
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
        document_id = body.get('documentId')
        options = body.get('options', {})
        
        if not document_id and not file_name:
            return create_error_response(400, "documentId or fileName is required")
            
        # Find the document in DynamoDB by document ID (preferred) or filename
        if document_id:
            document_info = find_document_by_id(document_id)
        else:
            document_info = find_document_by_filename(file_name)
            
        if not document_info:
            identifier = document_id if document_id else file_name
            return create_error_response(404, f"Document {identifier} not found or not uploaded")
            
        # Verify the file exists in S3
        s3_key = document_info['key']
        bucket = document_info['bucket']
        
        if not verify_s3_file_exists(bucket, s3_key):
            return create_error_response(404, f"File {s3_key} not found in S3")
            
        # Generate execution ID
        execution_id = str(uuid.uuid4())
        
        # Prepare Step Functions input for Parent State Machine
        # Extract the folder path from the document key
        key_parts = s3_key.split('/')
        if len(key_parts) > 1:
            # For uploads/document-id/filename.pdf, use uploads/document-id/ as prefix
            prefix = '/'.join(key_parts[:-1]) + '/'
        else:
            # Fallback if no folder structure
            prefix = 'uploads/'
        
        # Get project ARN from environment variable (should be set by CDK)
        project_arn = os.environ.get('PROJECT_ARN')
        if not project_arn:
            # Fallback to constructing ARN if not provided
            region = os.environ.get('AWS_REGION')
            account_id = os.environ.get('AWS_ACCOUNT_ID')
            
            if not region or not account_id:
                raise ValueError("AWS_REGION and AWS_ACCOUNT_ID environment variables must be set")
            
            # Use a more generic project ID pattern - this should be replaced with actual project ARN
            project_arn = f"arn:aws:bedrock:{region}:{account_id}:data-automation-project/BDA-Project"
        
        sf_input = {
            "executions": [
                {
                    "bucket": bucket,
                    "prefix": prefix
                }
            ],
            "project_arn": project_arn
        }
        
        # Start Step Functions execution
        execution_name = f"bda-processing-{execution_id}"
        
        response = stepfunctions_client.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            name=execution_name,
            input=json.dumps(sf_input)
        )
        
        execution_arn = response['executionArn']
        
        # Update document status in DynamoDB
        update_document_status(
            document_info['doc_id'],
            execution_id,
            execution_arn,
            options
        )
        
        logger.info(f"Started Step Functions execution {execution_arn} for document {file_name}")
        
        return create_success_response({
            'executionId': execution_id,
            'executionArn': execution_arn,
            'documentId': document_info.get('document_id'),
            'status': 'processing_started',
            'message': 'Document processing workflow started successfully'
        })
        
    except Exception as e:
        logger.error(f"Error starting processing workflow: {str(e)}", exc_info=True)
        return create_error_response(500, f"Internal server error: {str(e)}")

def find_document_by_id(document_id: str) -> Dict[str, Any]:
    """Find document in DynamoDB by document ID"""
    try:
        status_table = dynamodb.Table(STATUS_TABLE_NAME)
        
        # Scan for documents with matching document_id
        response = status_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('document_id').eq(document_id)
        )
        
        items = response.get('Items', [])
        if not items:
            return None
            
        # Return the first matching document
        return items[0]
        
    except Exception as e:
        logger.error(f"Error finding document by ID {document_id}: {str(e)}")
        return None

def find_document_by_filename(filename: str) -> Dict[str, Any]:
    """Find document in DynamoDB by original filename"""
    try:
        status_table = dynamodb.Table(STATUS_TABLE_NAME)
        
        # Scan for documents with matching filename
        # In production, consider using a GSI for better performance
        response = status_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('original_filename').eq(filename)
        )
        
        items = response.get('Items', [])
        if not items:
            return None
            
        # Return the most recent document with this filename
        items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return items[0]
        
    except Exception as e:
        logger.error(f"Error finding document {filename}: {str(e)}")
        return None

def verify_s3_file_exists(bucket: str, key: str) -> bool:
    """Verify that the file exists in S3, trying different encodings"""
    import urllib.parse
    
    # Try direct key lookup
    if _check_s3_key(bucket, key):
        return True
    
    # Try URL-encoded version
    encoded_key = _create_encoded_key(key)
    if _check_s3_key(bucket, encoded_key):
        return True
    
    # Try case-insensitive directory listing
    return _check_directory_listing(bucket, key)

def _check_s3_key(bucket: str, key: str) -> bool:
    """Check if S3 key exists"""
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except s3_client.exceptions.NoSuchKey:
        return False
    except Exception as e:
        logger.error(f"Error checking S3 file {bucket}/{key}: {str(e)}")
        return False

def _create_encoded_key(key: str) -> str:
    """Create URL-encoded version of key"""
    import urllib.parse
    key_parts = key.split('/')[:-1]
    encoded_filename = urllib.parse.quote_plus(key.split('/')[-1])
    return '/'.join(key_parts) + '/' + encoded_filename

def _check_directory_listing(bucket: str, key: str) -> bool:
    """Check directory listing for case-insensitive match"""
    try:
        prefix = '/'.join(key.split('/')[:-1]) + '/'
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        if 'Contents' not in response:
            return False
        
        target_filename = key.split('/')[-1].lower()
        existing_files = [obj['Key'] for obj in response['Contents']]
        logger.info(f"Files in {bucket}/{prefix}: {existing_files}")
        
        return any(f.split('/')[-1].lower() == target_filename for f in existing_files)
    except Exception as e:
        logger.error(f"Error listing S3 directory {bucket}/{prefix}: {str(e)}")
        return False

def update_document_status(doc_id: str, execution_id: str, execution_arn: str, options: Dict[str, Any]):
    """Update document status in DynamoDB"""
    try:
        status_table = dynamodb.Table(STATUS_TABLE_NAME)
        current_time = datetime.utcnow().isoformat()
        
        update_params = _build_update_params(execution_id, execution_arn, options, current_time)
        
        status_table.update_item(
            Key={'doc_id': doc_id},
            **update_params
        )
        
        logger.info(f"Updated status for document {doc_id} to processing")
        
    except Exception as e:
        logger.error(f"Error updating document status: {str(e)}")
        raise

def _build_update_params(execution_id: str, execution_arn: str, options: Dict[str, Any], current_time: str) -> Dict[str, Any]:
    """Build DynamoDB update parameters"""
    return {
        'UpdateExpression': '''SET #status = :status, execution_id = :execution_id, 
                              execution_arn = :execution_arn, processing_options = :options, 
                              processing_start_time = :start_time, updated_at = :updated_at''',
        'ExpressionAttributeNames': {'#status': 'status'},
        'ExpressionAttributeValues': {
            ':status': 'processing',
            ':execution_id': execution_id,
            ':execution_arn': execution_arn,
            ':options': options,
            ':start_time': current_time,
            ':updated_at': current_time
        }
    }

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