import os
import json
import boto3
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get environment variables
KNOWLEDGE_BASE_ID = os.environ.get('KNOWLEDGE_BASE_ID')
DATA_SOURCE_ID = os.environ.get('DATA_SOURCE_ID')
BUCKET_NAME = os.environ.get('BUCKET_NAME')
EXTRACTED_TEXT_PREFIX = os.environ.get('EXTRACTED_TEXT_PREFIX', 'Extracted-markdown')

def lambda_handler(event, context):
    """
    Handler function for S3 events to sync the Knowledge Base.
    
    Args:
        event: The event object from S3 or direct invocation
        context: The Lambda context
        
    Returns:
        Response with status and details
    """
    try:
        # Log the event for debugging
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Validate that we have the required environment variables
        if not KNOWLEDGE_BASE_ID or not DATA_SOURCE_ID:
            error_msg = "Missing required environment variables: KNOWLEDGE_BASE_ID, DATA_SOURCE_ID"
            logger.error(error_msg)
            return {
                'statusCode': 500,
                'body': json.dumps({'error': error_msg})
            }
        
        # Check if the event is from S3
        if 'Records' in event:
            # Process S3 event
            if not event['Records']:
                logger.info("No records in event, skipping")
                return {
                    'statusCode': 200,
                    'body': json.dumps({'message': 'No records to process'})
                }
            
            # Extract the bucket and key information
            record = event['Records'][0]
            event_name = record['eventName']
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            logger.info(f"Processing {event_name} for {bucket}/{key}")
        else:
            # Direct invocation - use environment variables
            bucket = BUCKET_NAME
            event_name = "MANUAL_SYNC"
            key = f"{EXTRACTED_TEXT_PREFIX}/manual-sync-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            
            logger.info(f"Manual sync initiated for bucket {bucket}")
        
        # Initialize Bedrock Agent client (not regular Bedrock client)
        bedrock_client = boto3.client('bedrock-agent')
        
        # Start the ingestion job
        description = f"Triggered by {event_name} on {bucket}/{key} at {datetime.now().isoformat()}"
        response = bedrock_client.start_ingestion_job(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            dataSourceId=DATA_SOURCE_ID,
            description=description
        )
        
        job_id = response['ingestionJob']['ingestionJobId']
        logger.info(f"Started ingestion job: {job_id}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Successfully started Knowledge Base ingestion',
                'ingestionJobId': job_id,
                'knowledgeBaseId': KNOWLEDGE_BASE_ID,
                'dataSourceId': DATA_SOURCE_ID,
                'triggerEvent': event_name,
                'triggerFile': f"s3://{bucket}/{key}"
            })
        }
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }