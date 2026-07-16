import os
import json
import logging
import boto3
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any, List
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get table names from environment variables
STATUS_TABLE_NAME = os.environ.get('STATUS_TABLE_NAME')
METRICS_TABLE_NAME = os.environ.get('METRICS_TABLE_NAME')

# Validate environment variables are set
if not STATUS_TABLE_NAME:
    raise ValueError("Missing required environment variable: STATUS_TABLE_NAME")
if not METRICS_TABLE_NAME:
    raise ValueError("Missing required environment variable: METRICS_TABLE_NAME")

class MetricsAggregator:
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.status_table = self.dynamodb.Table(STATUS_TABLE_NAME)
        self.metrics_table = self.dynamodb.Table(METRICS_TABLE_NAME)

    def get_processing_metrics(self, execution_id: str) -> List[Dict]:
        """
        Get all processing metrics for a specific execution ID.
        If execution_id-index exists, use Query; otherwise, use Scan.
        """
        try:
            items = []
            paginator = self.dynamodb.meta.client.get_paginator('query')
            
            for page in paginator.paginate(
                TableName=self.status_table.name,
                IndexName='execution_id-index',
                KeyConditionExpression='execution_id = :exec_id',
                ExpressionAttributeValues={':exec_id': execution_id}
            ):
                items.extend(page['Items'])
            
            return items
        except self.dynamodb.meta.client.exceptions.ValidationException as e:
            # If the index doesn't exist, fallback to scan
            logger.warning(f"GSI 'execution_id-index' not found, falling back to Scan: {str(e)}")
            
            items = []
            paginator = self.dynamodb.meta.client.get_paginator('scan')
            
            for page in paginator.paginate(
                TableName=self.status_table.name,
                FilterExpression='execution_id = :exec_id',
                ExpressionAttributeValues={':exec_id': execution_id}
            ):
                items.extend(page['Items'])
            
            return items

    def calculate_metrics(self, execution_id: str) -> Dict[str, Any]:
        documents = self.get_processing_metrics(execution_id)
        logger.info(f"Processing metrics for {len(documents)} documents")
        
        metrics = {
            'total_documents': len(documents),
            'completed': 0,
            'failed': 0,
            'processing': 0,
            'total_pages': 0,
            'total_processing_time': 0,
            'single_page_docs': 0,
            'multi_page_docs': 0,
            'start_time': None,
            'end_time': None,
            'document_types': {},
            'document_categories': {
                'single': 0,
                'multi-page': 0
            },
            'processing_stages': {
                'initialization': 0,
                'bda_processing': 0,
                'post_processing': 0
            },
            'errors': []
        }

        def parse_datetime(dt_str: str) -> datetime:
            if not dt_str:
                return None
            try:
                # Handle different datetime formats
                if 'Z' in dt_str:
                    dt = datetime.fromisoformat(dt_str.replace('Z', '')).replace(tzinfo=None)
                else:
                    dt = datetime.fromisoformat(dt_str).replace(tzinfo=None)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError as e:
                logger.warning(f"Error parsing datetime {dt_str}: {str(e)}")
                return None

        for doc in documents:
            try:
                status = doc.get('status', 'UNKNOWN')
                file_path = doc.get('doc_id', '')
                file_type = file_path.split('.')[-1].lower() if '.' in file_path else 'unknown'
                
                # Determine document type - use explicit doc_type or page_type as fallback
                doc_type = doc.get('doc_type', '')
                if not doc_type:
                    # For backward compatibility - use page_type if available
                    doc_type = doc.get('page_type', '')
                    
                if not doc_type:
                    # Last fallback - infer from processing_type if available
                    processing_type = doc.get('processing_type', '').lower().strip('"')
                    doc_type = 'single' if processing_type == 'single' else 'multi-page'
                
                # Track document types
                metrics['document_types'][file_type] = metrics['document_types'].get(file_type, 0) + 1

                # Properly handle page count from DynamoDB numeric type
                try:
                    page_count = int(doc.get('page_count', 0))
                    metrics['total_pages'] += page_count
                    logger.info(f"Added {page_count} pages from document {file_path}")
                except (TypeError, ValueError) as e:
                    logger.warning(f"Invalid page count for {file_path}: {str(e)}")

                # Handle start time - earliest time across all documents
                doc_start = None
                if doc.get('start_time'):
                    doc_start = parse_datetime(doc.get('start_time'))
                    if doc_start:
                        metrics['start_time'] = min(metrics['start_time'], doc_start) if metrics['start_time'] else doc_start

                # Process completion status and times
                if status == 'COMPLETED':
                    metrics['completed'] += 1
                    
                    # Track document categories based on doc_type
                    if doc_type == 'single':
                        metrics['single_page_docs'] += 1
                        metrics['document_categories']['single'] += 1
                    elif doc_type == 'multi-page':
                        metrics['multi_page_docs'] += 1
                        metrics['document_categories']['multi-page'] += 1
                    
                    # Calculate processing time
                    if doc.get('completion_time'):
                        completion_time = parse_datetime(doc.get('completion_time'))
                        if completion_time:
                            # Update end_time to latest completion time
                            metrics['end_time'] = max(metrics['end_time'], completion_time) if metrics['end_time'] else completion_time
                            
                            # Calculate processing time if we have both start and completion
                            if doc_start:
                                processing_time = (completion_time - doc_start).total_seconds()
                                metrics['total_processing_time'] += processing_time
                                logger.info(f"Document {file_path} processing time: {processing_time:.2f} seconds")
                    
                    # If the document has completed but completion_time is missing, use bda_completion_time as fallback
                    elif doc.get('bda_completion_time'):
                        bda_completion_time = parse_datetime(doc.get('bda_completion_time'))
                        if bda_completion_time:
                            metrics['end_time'] = max(metrics['end_time'], bda_completion_time) if metrics['end_time'] else bda_completion_time
                            logger.info(f"Using BDA completion time as fallback for document {file_path}")
                    
                    # Track processing stages if available
                    if doc.get('initialization_time') and doc_start:
                        init_time = parse_datetime(doc.get('initialization_time'))
                        if init_time:
                            init_duration = (init_time - doc_start).total_seconds()
                            metrics['processing_stages']['initialization'] += init_duration
                    
                    if doc.get('bda_start_time') and doc.get('bda_completion_time'):
                        bda_start = parse_datetime(doc.get('bda_start_time'))
                        bda_end = parse_datetime(doc.get('bda_completion_time'))
                        if bda_start and bda_end:
                            bda_duration = (bda_end - bda_start).total_seconds()
                            metrics['processing_stages']['bda_processing'] += bda_duration
                    
                    if doc.get('post_processing_start') and doc.get('completion_time'):
                        post_start = parse_datetime(doc.get('post_processing_start'))
                        if post_start and completion_time:
                            post_duration = (completion_time - post_start).total_seconds()
                            metrics['processing_stages']['post_processing'] += post_duration
                
                elif status in ['FAILED', 'ERROR']:
                    metrics['failed'] += 1
                    if doc.get('error'):
                        metrics['errors'].append({
                            'doc_id': file_path,
                            'error': doc.get('error')
                        })
                elif status in ['PROCESSING', 'PENDING']:
                    metrics['processing'] += 1

            except Exception as e:
                logger.warning(f"Error processing document metrics: {str(e)}, doc_id: {doc.get('doc_id')}")
                continue

        # Calculate derived metrics
        if metrics['completed'] > 0:
            metrics['average_processing_time'] = round(metrics['total_processing_time'] / metrics['completed'], 2)
            metrics['average_pages_per_doc'] = round(metrics['total_pages'] / metrics['total_documents'], 2)
            metrics['completion_rate'] = round((metrics['completed'] / metrics['total_documents']) * 100, 2)

        # Calculate total execution time
        if metrics['start_time'] and metrics['end_time']:
            total_execution_time = (metrics['end_time'] - metrics['start_time']).total_seconds()
            metrics['total_execution_time'] = round(total_execution_time, 2)
            logger.info(f"Total execution time: {total_execution_time:.2f} seconds")

        # Convert datetimes to ISO format strings
        if metrics['start_time']:
            metrics['start_time'] = metrics['start_time'].isoformat()
        if metrics['end_time']:
            metrics['end_time'] = metrics['end_time'].isoformat()
        
        logger.info(f"Final metrics: {json.dumps(metrics, default=str)}")
        return metrics

    def save_metrics(self, execution_id: str, metrics: Dict[str, Any]):
        timestamp = datetime.now(timezone.utc).isoformat()
        
        item = {
            'execution_id': execution_id,
            'timestamp': timestamp,
            'metrics': metrics,
            'status': 'COMPLETED'
        }
        
        self._convert_floats_to_decimal(item)
        self.metrics_table.put_item(Item=item)

    def _convert_floats_to_decimal(self, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, float):
                    obj[k] = Decimal(str(v))
                elif isinstance(v, (dict, list)):
                    self._convert_floats_to_decimal(v)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, float):
                    obj[i] = Decimal(str(v))
                elif isinstance(v, (dict, list)):
                    self._convert_floats_to_decimal(v)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        logger.info(f"Processing metrics for event: {json.dumps(event)}")
        
        execution_id = event.get('execution_id')
        if not execution_id:
            raise ValueError("Missing required parameter: execution_id")

        aggregator = MetricsAggregator()
        metrics = aggregator.calculate_metrics(execution_id)
        aggregator.save_metrics(execution_id, metrics)

        return {
            'statusCode': 200,
            'body': metrics
        }

    except Exception as e:
        logger.error(f"Error processing metrics: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'execution_id': event.get('execution_id')
            }
        }