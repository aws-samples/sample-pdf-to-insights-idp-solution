import json
import boto3
import os
import logging
from typing import Dict, Any, List
from urllib.parse import unquote_plus

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
stepfunctions_client = boto3.client('stepfunctions')
dynamodb = boto3.resource('dynamodb')

# Environment variables
STEP_FUNCTION_ARN = os.environ.get('STEP_FUNCTION_ARN')
STATUS_TABLE_NAME = os.environ.get('STATUS_TABLE_NAME')
PROJECT_ARN = os.environ.get('PROJECT_ARN')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle S3 upload events via EventBridge and automatically trigger document processing.
    
    Args:
        event: EventBridge event from S3
        context: Lambda context
        
    Returns:
        Processing results
    """
    try:
        logger.info(f"Received EventBridge event: {json.dumps(event)}")
        
        # Check if this is an EventBridge event from S3
        if event.get('source') == 'aws.s3' and event.get('detail-type') == 'Object Created':
            # Process EventBridge S3 event
            result = process_eventbridge_s3_event(event)
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Processed EventBridge S3 event',
                    'result': result
                })
            }
        else:
            # Fallback: Process legacy S3 direct notification format
            results = []
            for record in event.get('Records', []):
                if record.get('eventSource') == 'aws:s3':
                    result = process_s3_record(record)
                    results.append(result)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'Processed {len(results)} S3 events',
                    'results': results
                })
            }
        
    except Exception as e:
        logger.error(f"Error processing S3 event: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

def process_eventbridge_s3_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Process an EventBridge S3 event"""
    try:
        # Extract S3 information from EventBridge event
        detail = event.get('detail', {})
        bucket = detail.get('bucket', {}).get('name')
        key = detail.get('object', {}).get('key')
        reason = detail.get('reason', '')
        
        logger.info(f"Processing EventBridge S3 event: {reason} for {bucket}/{key}")
        
        # Validate required fields
        if not bucket or not key:
            logger.error(f"Missing bucket or key in EventBridge event: bucket={bucket}, key={key}")
            return {'status': 'error', 'reason': 'missing bucket or key'}
        
        # Only process upload events (PutObject, CompleteMultipartUpload, CopyObject) for PDF files in uploads/ or public/uploads/ folder
        upload_reasons = ['PutObject', 'CompleteMultipartUpload', 'CopyObject']
        if reason not in upload_reasons:
            logger.info(f"Ignoring non-upload event: {reason}")
            return {'status': 'ignored', 'reason': 'not an upload event'}
            
        if not (key.startswith('uploads/') or key.startswith('public/uploads/')):
            logger.info(f"Ignoring file outside uploads folder: {key}")
            return {'status': 'ignored', 'reason': 'not in uploads folder'}
            
        if not key.lower().endswith('.pdf'):
            logger.info(f"Ignoring non-PDF file: {key}")
            return {'status': 'ignored', 'reason': 'not a PDF file'}
        
        # Update document status to uploaded
        update_document_status(key, bucket)
        
        # Start processing workflow
        execution_result = start_processing_workflow(bucket, key)
        
        return {
            'status': 'processed',
            'bucket': bucket,
            'key': key,
            'execution': execution_result
        }
        
    except Exception as e:
        logger.error(f"Error processing EventBridge S3 event: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e)
        }

def process_s3_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single S3 record"""
    try:
        # Extract S3 information
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        event_name = record['eventName']
        
        logger.info(f"Processing S3 event: {event_name} for {bucket}/{key}")
        
        # Only process PUT events (uploads) for PDF files in uploads/ or public/uploads/ folder
        if not event_name.startswith('ObjectCreated:'):
            logger.info(f"Ignoring non-upload event: {event_name}")
            return {'status': 'ignored', 'reason': 'not an upload event'}
            
        if not (key.startswith('uploads/') or key.startswith('public/uploads/')):
            logger.info(f"Ignoring file outside uploads folder: {key}")
            return {'status': 'ignored', 'reason': 'not in uploads folder'}
            
        if not key.lower().endswith('.pdf'):
            logger.info(f"Ignoring non-PDF file: {key}")
            return {'status': 'ignored', 'reason': 'not a PDF file'}
        
        # Update document status to uploaded
        update_document_status(key, bucket)
        
        # Start processing workflow
        execution_result = start_processing_workflow(bucket, key)
        
        return {
            'status': 'processed',
            'bucket': bucket,
            'key': key,
            'execution': execution_result
        }
        
    except Exception as e:
        logger.error(f"Error processing S3 record: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'error': str(e)
        }

def update_document_status(s3_key: str, bucket: str):
    """Update document status to indicate successful upload"""
    try:
        from datetime import datetime
        
        status_table = dynamodb.Table(STATUS_TABLE_NAME)
        
        # Update the document status
        response = status_table.update_item(
            Key={'doc_id': s3_key},
            UpdateExpression="""
                SET #status = :status,
                    progress = :progress,
                    updated_at = :updated_at,
                    upload_completed_at = :upload_time
            """,
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': 'uploaded',
                ':progress': 10,
                ':updated_at': datetime.utcnow().isoformat(),
                ':upload_time': datetime.utcnow().isoformat()
            },
            ReturnValues='ALL_NEW'
        )
        
        logger.info(f"Updated document status for {s3_key}")
        return response
        
    except Exception as e:
        logger.error(f"Error updating document status: {str(e)}")
        raise

def start_processing_workflow(bucket: str, s3_key: str) -> Dict[str, Any]:
    """Start the Step Functions processing workflow"""
    try:
        # Use the exact file path as prefix to process only this specific file
        # This works because Step Functions will only find this one file with this exact prefix
        sf_input = {
            "executions": [
                {
                    "bucket": bucket,
                    "prefix": s3_key  # Use the full file path as prefix
                }
            ],
            "project_arn": PROJECT_ARN
        }
        
        # Generate execution name
        import uuid
        execution_id = str(uuid.uuid4())
        execution_name = f"bda-auto-processing-{execution_id}"
        
        # Start Step Functions execution
        response = stepfunctions_client.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            name=execution_name,
            input=json.dumps(sf_input)
        )
        
        execution_arn = response['executionArn']
        
        # Update document with execution details
        update_document_with_execution(s3_key, execution_id, execution_arn)
        
        logger.info(f"Started automatic processing workflow {execution_arn} for {s3_key}")
        
        return {
            'executionId': execution_id,
            'executionArn': execution_arn,
            'status': 'started'
        }
        
    except Exception as e:
        logger.error(f"Error starting processing workflow: {str(e)}")
        raise

def update_document_with_execution(s3_key: str, execution_id: str, execution_arn: str):
    """Update document with execution details"""
    try:
        status_table = dynamodb.Table(STATUS_TABLE_NAME)
        
        from datetime import datetime
        
        status_table.update_item(
            Key={'doc_id': s3_key},
            UpdateExpression="""
                SET #status = :status,
                    execution_id = :execution_id,
                    execution_arn = :execution_arn,
                    processing_start_time = :start_time,
                    updated_at = :updated_at,
                    progress = :progress
            """,
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': 'processing',
                ':execution_id': execution_id,
                ':execution_arn': execution_arn,
                ':start_time': datetime.utcnow().isoformat(),
                ':updated_at': datetime.utcnow().isoformat(),
                ':progress': 30
            }
        )
        
        logger.info(f"Updated document {s3_key} with execution details")
        
    except Exception as e:
        logger.error(f"Error updating document with execution: {str(e)}")
        raise 