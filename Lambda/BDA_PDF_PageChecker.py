import os
import json
import boto3
import logging
from io import BytesIO
from typing import Dict, Any, Tuple
from pypdf import PdfReader

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get environment variables
STATUS_TABLE_NAME = os.environ.get('STATUS_TABLE_NAME', 'BDAProcessingStatus')

class DocumentAnalyzer:
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.dynamodb = boto3.resource('dynamodb')
        # Get bucket name from environment variable if available
        self.bucket_name = os.environ.get('BUCKET_NAME')
        self.status_table = self.dynamodb.Table(STATUS_TABLE_NAME)

    def get_page_count(self, bucket: str, key: str) -> Dict[str, Any]:
        try:
            if not key.lower().endswith('.pdf'):
                return {
                    'page_count': 1,
                    'processing_type': 'sync',
                    'api_method': 'DetectDocumentText'
                }

            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            pdf_bytes = response['Body'].read()
            reader = PdfReader(BytesIO(pdf_bytes))
            page_count = len(reader.pages)

            processing_type = 'async' if page_count > 1 else 'sync'

            # Update DynamoDB with the accurate page count
            try:
                self.status_table.update_item(
                    Key={'doc_id': key},
                    UpdateExpression='SET page_count = :pageCount',
                    ExpressionAttributeValues={':pageCount': page_count}
                )
                logger.info(f"Updated DynamoDB with page count {page_count} for document {key}")
            except Exception as db_error:
                logger.error(f"Error updating DynamoDB: {str(db_error)}")
                # Continue processing even if DynamoDB update fails

            return {
                'page_count': page_count,
                'processing_type': processing_type,
                'api_method': 'async' if page_count > 1 else 'sync'
            }

        except Exception as e:
            logger.error(f"Error analyzing document {bucket}/{key}: {str(e)}")
            raise

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        bucket = event.get('bucket')
        key = event.get('key')
        execution_id = event.get('execution_id')

        if not all([bucket, key]):
            raise ValueError("Missing required parameters: bucket and key")

        analyzer = DocumentAnalyzer()
        result = analyzer.get_page_count(bucket, key)

        return {
            'statusCode': 200,
            'page_count': result['page_count'],
            'processing_type': result['processing_type'],
            'api_method': result['api_method']
        }

    except Exception as e:
        logger.error(f"Handler error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'error': str(e)
        }