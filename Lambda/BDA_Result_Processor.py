import boto3
import json
import os
import logging
from datetime import datetime
from pathlib import Path
import re

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

sfn = boto3.client('stepfunctions')
ddb = boto3.client('dynamodb')
s3_client = boto3.client('s3')
table_name = os.environ['STATUS_TABLE_NAME']

# Environment variables for output prefixes
TEXT_OUTPUT_PREFIX = os.environ.get('TEXT_OUTPUT_PREFIX', 'Extracted-text')
PAGE_OUTPUT_PREFIX = os.environ.get('PAGE_OUTPUT_PREFIX', 'Extracted-pages')
MARKDOWN_OUTPUT_PREFIX = os.environ.get('MARKDOWN_OUTPUT_PREFIX', 'Extracted-markdown')  # New environment variable

def lambda_handler(event, context):
    # Log the entire event
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Check if this is an EventBridge event from Bedrock Data Automation
    if 'source' in event and event['source'] == 'aws.bedrock' and 'detail' in event:
        # Handle EventBridge event from BDA
        return handle_eventbridge_event(event)
    else:
        # Handle direct invocation from Step Functions
        return handle_direct_invocation(event)

# amazonq-ignore-next-line
def handle_eventbridge_event(event):
    # Extract job_id from the event
    job_id = event['detail']['job_id']
    is_success = event['detail-type'] == 'Bedrock Data Automation Job Succeeded'
    
    # Log key event details
    logger.info(f"Processing BDA event with job_id: {job_id}")
    logger.info(f"Event type: {'Success' if is_success else 'Failure'}")
    
    # Extract the timestamp from the event
    event_time = event.get('time')
    
    try:
        # Try to find the record by querying items where BDA job_id might be stored
        response = ddb.scan(
            TableName=table_name,
            FilterExpression="contains(invocation_arn, :job_id)",
            ExpressionAttributeValues={
                ':job_id': {'S': job_id}
            }
        )
        
        # No matching records found
        if 'Items' not in response or not response['Items']:
            logger.error(f"No record found for job_id: {job_id}")
            return {'statusCode': 404, 'body': 'No matching record found'}
        
        # Get the task token from the first matching item
        item = response['Items'][0]
        doc_id = item['doc_id']['S']
        task_token = item['task_token']['S'] if 'task_token' in item else None
        
        if not task_token:
            logger.error(f"No task token found for doc_id: {doc_id}")
            return {'statusCode': 404, 'body': 'No task token found'}
        
        # Update DynamoDB with BDA job completion time
        if is_success:
            # Mark BDA job completion time
            ddb.update_item(
                TableName=table_name,
                Key={
                    'doc_id': {'S': doc_id}
                },
                UpdateExpression="SET bda_completion_time = :completion_time",
                ExpressionAttributeValues={
                    ':completion_time': {'S': event_time or datetime.now().isoformat()}
                }
            )
            
            # For successful jobs, send success with output location
            output_s3_bucket = event['detail']['output_s3_location']['s3_bucket']
            output_s3_key = event['detail']['output_s3_location']['name']
            
            output_location = f"s3://{output_s3_bucket}/{output_s3_key}"
            logger.info(f"Success event with output at: {output_location}")
            
            # Update DynamoDB with post-processing start time
            ddb.update_item(
                TableName=table_name,
                Key={
                    'doc_id': {'S': doc_id}
                },
                UpdateExpression="SET post_processing_start = :start_time",
                ExpressionAttributeValues={
                    ':start_time': {'S': datetime.now().isoformat()}
                }
            )
            
            # Extract text from the BDA output
            try:
                # Direct path to result.json
                result_json_path = f"BDA-Output//{job_id}/0/standard_output/0/result.json"
                logger.info(f"Looking for result.json at: s3://{output_s3_bucket}/{result_json_path}")
                
                # Get the result.json file
                response = s3_client.get_object(Bucket=output_s3_bucket, Key=result_json_path)
                result_json = json.loads(response['Body'].read().decode('utf-8'))
                
                # Extract and store document-level text
                doc_extraction_result = extract_document_text(doc_id, output_s3_bucket, result_json)
                
                # Extract and store page-level text as single file
                page_extraction_result = extract_pages_to_single_file(doc_id, output_s3_bucket, result_json)
                
                # Extract and store markdown content
                markdown_extraction_result = extract_markdown_content(doc_id, output_s3_bucket, result_json)
                
                # Update DynamoDB with extraction status
                ddb.update_item(
                    TableName=table_name,
                    Key={
                        'doc_id': {'S': doc_id}
                    },
                    UpdateExpression="SET text_extraction_status = :status, text_extraction_result = :result, page_extraction_result = :page_result, markdown_extraction_result = :md_result",
                    ExpressionAttributeValues={
                        ':status': {'S': 'COMPLETED'},
                        ':result': {'S': json.dumps(doc_extraction_result)},
                        ':page_result': {'S': json.dumps(page_extraction_result)},
                        ':md_result': {'S': json.dumps(markdown_extraction_result)}
                    }
                )
                logger.info(f"Text, page, and markdown extraction completed for doc_id: {doc_id}")
            except Exception as e:
                logger.error(f"Error extracting content: {str(e)}", exc_info=True)
                # Update DynamoDB with extraction error
                ddb.update_item(
                    TableName=table_name,
                    Key={
                        'doc_id': {'S': doc_id}
                    },
                    UpdateExpression="SET text_extraction_status = :status, text_extraction_error = :error",
                    ExpressionAttributeValues={
                        ':status': {'S': 'ERROR'},
                        ':error': {'S': str(e)}
                    }
                )
            
            # Send task success
            sfn.send_task_success(
                taskToken=task_token,
                output=json.dumps({
                    'output_location': output_location
                })
            )
            logger.info(f"Success sent for doc_id: {doc_id}")
        else:
            # For failed jobs, send failure with error details
            error_type = "BDAJobFailed"
            error_message = event['detail'].get('error_message', 'Unknown BDA processing error')
            logger.info(f"Failure event with error: {error_type} - {error_message}")
            
            # Update DynamoDB with error information
            ddb.update_item(
                TableName=table_name,
                Key={
                    'doc_id': {'S': doc_id}
                },
                UpdateExpression="SET error = :error, bda_completion_time = :completion_time",
                ExpressionAttributeValues={
                    ':error': {'S': error_message},
                    ':completion_time': {'S': event_time or datetime.now().isoformat()}
                }
            )
            
            sfn.send_task_failure(
                taskToken=task_token,
                error=error_type,
                cause=error_message
            )
            logger.info(f"Failure sent for doc_id: {doc_id}")
        
        return {
            'statusCode': 200,
            'body': f"Successfully processed BDA {'success' if is_success else 'failure'} event"
        }
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")
        return {
            'statusCode': 500,
            'body': f"Error: {str(e)}"
        }

def extract_document_text(doc_id, output_s3_bucket, result_json):
    """Extract and store document-level text"""
    # Extract the plain text from document.representation.text
    if 'document' in result_json and 'representation' in result_json['document']:
        document_text = result_json['document']['representation'].get('text', '')
        
        # Generate the output key using the document name (sanitized)
        doc_name = os.path.basename(doc_id)
        doc_name = Path(doc_name).stem
        output_key = f"{TEXT_OUTPUT_PREFIX}/{doc_name}.txt"
        
        # Save the plain text to S3
        s3_client.put_object(
            Bucket=output_s3_bucket,
            Key=output_key,
            Body=document_text,
            ContentType='text/plain'
        )
        
        logger.info(f"Saved document text to s3://{output_s3_bucket}/{output_key}")
        return {
            'statusCode': 200,
            'text_file': f"s3://{output_s3_bucket}/{output_key}",
            'document_length': len(document_text)
        }
    else:
        logger.error("No document representation found in result.json")
        return {
            'statusCode': 400,
            'error': 'No document representation found in result.json'
        }

def extract_markdown_content(doc_id, output_s3_bucket, result_json):
    """Extract and store only combined markdown content"""
    doc_name = Path(doc_id).stem
    results = {
        'combined_markdown': None
    }
    
    # Initialize combined markdown content
    combined_markdown = []
    
    # Add document header to combined markdown
    combined_markdown.append(f"# {doc_name}")
    
    # Extract document-level information
    if 'document' in result_json:
        # Add page count if available
        page_count = len(result_json.get('pages', []))
        if page_count > 0:
            combined_markdown.append(f"*Total Pages: {page_count}*")
        
        # Add document metadata if available
        if 'metadata' in result_json['document']:
            metadata = result_json['document']['metadata']
            if metadata.get('title'):
                combined_markdown.append(f"**Title**: {metadata.get('title')}")
            if metadata.get('author'):
                combined_markdown.append(f"**Author**: {metadata.get('author')}")
            if metadata.get('creation_date'):
                combined_markdown.append(f"**Date**: {metadata.get('creation_date')}")
        
        # Add document summary if available
        if result_json['document'].get('summary'):
            combined_markdown.append("\n## Document Summary")
            combined_markdown.append(result_json['document']['summary'])
        
        # Add full document markdown content if available
        if 'representation' in result_json['document'] and 'markdown' in result_json['document']['representation']:
            document_markdown = result_json['document']['representation']['markdown']
            combined_markdown.append("\n## Full Document Content")
            combined_markdown.append(document_markdown)
    
    combined_markdown.append("\n---\n")
    
    # Process each page if available
    if 'pages' in result_json and result_json['pages']:
        pages = result_json['pages']
        
        logger.info(f"Processing {len(pages)} pages for document {doc_name}")
        
        # Process each page
        for i, page in enumerate(pages):
            if not page:  # Skip empty pages
                continue
                
            page_num = i + 1
            
            # Extract markdown content for this page
            page_markdown = ""
            if 'representation' in page and 'markdown' in page['representation']:
                page_markdown = page['representation']['markdown']
            elif 'representation' in page and 'text' in page['representation']:
                # If markdown not available, use plain text
                page_markdown = f"```\n{page['representation']['text']}\n```"
            
            # Add to combined markdown with page header
            if page_markdown:
                combined_markdown.append(f"\n## Page {page_num} of {len(pages)}")
                combined_markdown.append(page_markdown)
                combined_markdown.append("\n---\n")
    
    # Save only the combined markdown file
    combined_md_key = f"{MARKDOWN_OUTPUT_PREFIX}/{doc_name}_combined.md"
    s3_client.put_object(
        Bucket=output_s3_bucket,
        Key=combined_md_key,
        Body='\n'.join(combined_markdown),
        ContentType='text/markdown'
    )
    
    results['combined_markdown'] = f"s3://{output_s3_bucket}/{combined_md_key}"
    logger.info(f"Saved combined markdown to s3://{output_s3_bucket}/{combined_md_key}")
    
    return results

def extract_pages_to_single_file(doc_id, output_s3_bucket, result_json):
    """Extract all page-level text and save to a single file"""
    # Check if pages data exists
    if 'pages' not in result_json or not result_json['pages']:
        logger.warning("No pages data found in result.json")
        return {
            'statusCode': 404,
            'error': 'No pages data found in result.json'
        }
    
    doc_name = Path(doc_id).stem
    pages = result_json['pages']
    
    # Create the combined page content
    combined_content = []
    page_metadata = []
    
    # Extract metadata for document summary
    doc_metadata = {
        'document_id': doc_id,
        'total_pages': len(pages),
        'document_title': result_json.get('document', {}).get('title', 'Untitled Document'),
        'document_summary': result_json.get('document', {}).get('summary', '')
    }
    
    # Add document header
    combined_content.append(f"DOCUMENT: {doc_name}")
    combined_content.append(f"TOTAL PAGES: {len(pages)}")
    if doc_metadata['document_summary']:
        combined_content.append(f"\nSUMMARY: {doc_metadata['document_summary']}\n")
    combined_content.append('=' * 80)
    combined_content.append("")
    
    # Process each page in order
    for i, page in enumerate(pages):
        if not page:  # Skip empty pages
            continue
        
        # Get page number (1-based for user-friendly display)
        page_num = i + 1
        
        # Extract page text content from the most appropriate representation
        page_text = ""
        if 'representation' in page:
            # Try to get text in order of preference: text, markdown, html
            page_text = page['representation'].get('text', '')
            if not page_text and 'markdown' in page['representation']:
                page_text = page['representation'].get('markdown', '')
            if not page_text and 'html' in page['representation']:
                # Simple HTML-to-text conversion (could be enhanced)
                html_text = page['representation'].get('html', '')
                page_text = re.sub('<[^<]+?>', ' ', html_text)
        
        # Create page header with page number and horizontal line
        page_header = [
            f"\n{'='*80}",
            f"PAGE {page_num} OF {len(pages)}",
            f"{'='*80}\n"
        ]
        
        # Add page content or placeholder if empty
        if page_text:
            combined_content.extend(page_header)
            combined_content.append(page_text)
        else:
            combined_content.extend(page_header)
            combined_content.append("[No text content available for this page]")
        
        # Collect page metadata
        page_info = {
            'page_index': i,
            'page_number': page_num,
            'word_count': page.get('statistics', {}).get('word_count', 0),
            'image_uri': page.get('asset_metadata', {}).get('rectified_image', '')
        }
        page_metadata.append(page_info)
    
    # Save the combined page text
    output_key = f"{PAGE_OUTPUT_PREFIX}/{doc_name}_pages.txt"
    s3_client.put_object(
        Bucket=output_s3_bucket,
        Key=output_key,
        Body='\n'.join(combined_content),
        ContentType='text/plain'
    )
    logger.info(f"Saved combined page text to s3://{output_s3_bucket}/{output_key}")
    
    # Create metadata JSON with document info and links to the page file
    metadata = {
        'document_id': doc_id,
        'document_name': doc_name,
        'total_pages': len(pages),
        'page_file': f"s3://{output_s3_bucket}/{output_key}",
        'pages': page_metadata,
        'extraction_time': datetime.now().isoformat()
    }
    
    # Save metadata as JSON
    metadata_key = f"{PAGE_OUTPUT_PREFIX}/{doc_name}_metadata.json"
    s3_client.put_object(
        Bucket=output_s3_bucket,
        Key=metadata_key,
        Body=json.dumps(metadata, indent=2),
        ContentType='application/json'
    )
    logger.info(f"Saved page metadata to s3://{output_s3_bucket}/{metadata_key}")
    
    return {
        'statusCode': 200,
        'document_id': doc_id,
        'total_pages': len(pages),
        'page_file': f"s3://{output_s3_bucket}/{output_key}",
        'metadata_file': f"s3://{output_s3_bucket}/{metadata_key}"
    }

def handle_direct_invocation(event):
    # This handles the case when Lambda is invoked directly from Step Functions
    try:
        # Extract data from the event
        document = event.get('document', {})
        output_location = event.get('output_location')
        execution_id = event.get('execution_id')
        invocation_arn = event.get('invocation_arn')
        
        doc_key = document.get('key', '')
        logger.info(f"Processing direct invocation for document: {doc_key}")
        
        # Extract results if output location is provided
        extraction_results = {
            'document_text': None,
            'page_level': None,
            'markdown': None
        }
        
        if output_location:
            try:
                # Parse S3 URI for the output location
                parts = output_location.replace('s3://', '').split('/', 1)
                bucket = parts[0]
                output_path = parts[1] if len(parts) > 1 else ''
                
                # Extract job_id from the output_location
                import re
                match = re.search(r'BDA-Output\/?\/?([\w-]+)', output_path)
                if match:
                    job_id = match.group(1)
                    logger.info(f"Extracted job ID: {job_id}")
                    
                    # Direct path to result.json - WITH double slash preserved
                    result_json_path = f"BDA-Output//{job_id}/0/standard_output/0/result.json"
                    logger.info(f"Looking for result.json at: s3://{bucket}/{result_json_path}")
                    
                    # Get the result.json file
                    response = s3_client.get_object(Bucket=bucket, Key=result_json_path)
                    result_json = json.loads(response['Body'].read().decode('utf-8'))
                    
                    # Extract document text
                    doc_extraction_result = extract_document_text(doc_key, bucket, result_json)
                    extraction_results['document_text'] = doc_extraction_result
                    
                    # Extract page-level data
                    page_extraction_result = extract_pages_to_single_file(doc_key, bucket, result_json)
                    extraction_results['page_level'] = page_extraction_result
                    
                    # Extract markdown content
                    markdown_extraction_result = extract_markdown_content(doc_key, bucket, result_json)
                    extraction_results['markdown'] = markdown_extraction_result
                    
                    logger.info(f"Extraction completed for direct invocation")
                else:
                    logger.error(f"Could not extract job ID from output location: {output_location}")
                    extraction_results['error'] = f"Could not extract job ID from output location: {output_location}"
            except Exception as e:
                logger.error(f"Error extracting content: {str(e)}", exc_info=True)
                extraction_results['error'] = str(e)

        return {
            'statusCode': 200,
            'processed': True,
            'document': document,
            'output_location': output_location,
            'extraction_results': extraction_results
        }
    except Exception as e:
        logger.error(f"Error processing direct invocation: {str(e)}")
        return {
            'statusCode': 500,
            'body': f"Error: {str(e)}"
        }