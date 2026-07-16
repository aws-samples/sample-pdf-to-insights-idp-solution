import json
import boto3
import os
from datetime import datetime
import logging
from typing import Dict, Any, List
from boto3.dynamodb.conditions import Key, Attr
from decimal import Decimal

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
STATUS_TABLE_NAME = os.environ.get('STATUS_TABLE_NAME')
METRICS_TABLE_NAME = os.environ.get('METRICS_TABLE_NAME')

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for DynamoDB Decimal types"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert Decimal to int if it's a whole number, otherwise float
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Retrieve processing status for documents.
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        Response with status information
    """
    try:
        # Determine the request type
        path_parameters = event.get('pathParameters', {})
        query_parameters = event.get('queryStringParameters', {}) or {}
        
        if path_parameters and 'docId' in path_parameters:
            # Get status for specific document
            doc_id = path_parameters['docId']
            return get_document_status(doc_id)
        else:
            # Get status for all documents
            limit = int(query_parameters.get('limit', 50))
            return get_all_documents_status(limit)
            
    except Exception as e:
        logger.error(f"Error retrieving status: {str(e)}", exc_info=True)
        return create_error_response(500, f"Internal server error: {str(e)}")

def get_document_status(doc_id: str) -> Dict[str, Any]:
    """Get status for a specific document"""
    try:
        status_table = dynamodb.Table(STATUS_TABLE_NAME)
        
        response = status_table.get_item(Key={'doc_id': doc_id})
        
        if 'Item' not in response:
            return create_error_response(404, f"Document {doc_id} not found")
            
        item = response['Item']
        
        # Format the response
        document_status = format_document_status(item)
        
        return create_success_response({
            'document': document_status
        })
        
    except boto3.client('dynamodb').exceptions.ResourceNotFoundException:
        logger.error(f"Status table not found for document {doc_id}")
        return create_error_response(500, "Status table not available")
    except Exception as e:
        logger.error(f"Error getting document status for {doc_id}: {str(e)}", exc_info=True)
        return create_error_response(500, f"Failed to retrieve document status: {str(e)}")

def get_all_documents_status(limit: int = 50) -> Dict[str, Any]:
    """Get status for all documents with summary statistics"""
    try:
        status_table = dynamodb.Table(STATUS_TABLE_NAME)
        
        # Scan the table to get all documents (in production, consider pagination)
        response = status_table.scan(Limit=limit)
        items = response.get('Items', [])
        
        # Sort by created_at descending
        items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Format documents
        documents = [format_document_status(item) for item in items]
        
        # Calculate summary statistics
        summary = calculate_summary_stats(items)
        
        return create_success_response({
            'summary': summary,
            'documents': documents,
            'total': len(documents),
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except boto3.client('dynamodb').exceptions.ResourceNotFoundException:
        logger.error("Status table not found")
        return create_error_response(500, "Status table not available")
    except Exception as e:
        logger.error(f"Error getting all documents status: {str(e)}", exc_info=True)
        return create_error_response(500, f"Failed to retrieve documents status: {str(e)}")

def format_document_status(item: Dict[str, Any]) -> Dict[str, Any]:
    """Format a DynamoDB item for API response"""
    
    # Map internal status to user-friendly status
    status_mapping = {
        'upload_pending': 'queued',
        'uploaded': 'queued',
        'processing': 'processing',
        'bda_processing': 'processing',
        'completed': 'completed',
        'failed': 'failed',
        'error': 'failed'
    }
    
    internal_status = item.get('status', 'unknown')
    user_status = status_mapping.get(internal_status, internal_status)
    
    # Calculate progress based on status
    progress = calculate_progress(item)
    
    return {
        'id': item.get('document_id', item.get('doc_id')),
        'name': item.get('original_filename', 'Unknown'),
        'status': user_status,
        'progress': progress,
        'uploadTime': item.get('created_at'),
        'lastUpdated': item.get('updated_at'),
        'bucket': item.get('bucket'),
        'key': item.get('key'),
        'pageCount': item.get('page_count'),
        'executionId': item.get('execution_id'),
        'processingTime': calculate_processing_time(item),
        'errorMessage': item.get('error_message')
    }

def calculate_progress(item: Dict[str, Any]) -> int:
    """Calculate progress percentage based on status and processing stage"""
    status = item.get('status', '')
    
    progress_map = {
        'upload_pending': 0,
        'uploaded': 10,
        'processing': 30,
        'bda_processing': 60,
        'extracting': 80,
        'completed': 100,
        'failed': 0,
        'error': 0
    }
    
    # Check for more specific progress indicators
    if 'bda_start_time' in item and 'bda_end_time' in item:
        return 100
    elif 'bda_start_time' in item:
        return 70
    # amazonq-ignore-next-line
    elif status == 'processing':
        return 40
    
    return progress_map.get(status, 0)

def calculate_processing_time(item: Dict[str, Any]) -> str:
    """Calculate processing time if available"""
    try:
        if item.get('status') != 'completed':
            return "N/A"
            
        processing_time = _extract_processing_time(item)
        return _format_time_duration(processing_time) if processing_time else "N/A"
        
    except Exception:
        return "N/A"

def calculate_summary_stats(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate summary statistics from all documents"""
    status_mapping = {
        'upload_pending': 'queued', 'uploaded': 'queued',
        'processing': 'processing', 'bda_processing': 'processing', 'extracting': 'processing',
        'completed': 'completed',
        'failed': 'failed', 'error': 'failed'
    }
    
    status_counts = {'queued': 0, 'processing': 0, 'completed': 0, 'failed': 0}
    total_pages = 0
    processing_times = []
    
    for item in items:
        status = item.get('status', '')
        mapped_status = status_mapping.get(status, 'failed')
        status_counts[mapped_status] += 1
        
        page_count = item.get('page_count', 0)
        if isinstance(page_count, (int, float)):
            total_pages += int(page_count)
            
        if status == 'completed':
            processing_time = _extract_processing_time(item)
            if processing_time:
                processing_times.append(processing_time)
    
    avg_processing_time = _format_avg_time(processing_times)
    
    return {
        'total': len(items),
        'queued': status_counts['queued'],
        'processing': status_counts['processing'],
        'completed': status_counts['completed'],
        'failed': status_counts['failed'],
        'totalPages': total_pages,
        'avgProcessingTime': avg_processing_time
    }

def _extract_processing_time(item: Dict[str, Any]) -> float:
    """Extract processing time in seconds from item"""
    start_time = item.get('bda_start_time') or item.get('created_at')
    end_time = item.get('bda_end_time') or item.get('updated_at')
    
    if start_time and end_time:
        try:
            start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            return (end - start).total_seconds()
        except Exception:
            pass
    return None

def _format_avg_time(processing_times: List[float]) -> str:
    """Format average processing time"""
    if not processing_times:
        return "N/A"
    
    avg_seconds = sum(processing_times) / len(processing_times)
    return _format_time_duration(avg_seconds)

def _format_time_duration(seconds: float) -> str:
    """Format time duration in seconds to readable format"""
    minutes = int(seconds / 60)
    seconds = int(seconds % 60)
    return f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

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
        'body': json.dumps(data, cls=DecimalEncoder)
    }

def _get_cors_headers() -> Dict[str, str]:
    """Get standard CORS headers"""
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key',
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
    } 