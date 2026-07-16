import json
import boto3
import requests
import time
import os
from requests_aws4auth import AWS4Auth

# amazonq-ignore-next-line
def handler(event, context):
    """
    Lambda function to create an OpenSearch Serverless index for Bedrock Knowledge Base.
    
    Args:
        event: Lambda event containing collection details
        context: Lambda context
        
    Returns:
        Response for CloudFormation custom resource
    """
    print(f"Received event: {json.dumps(event)}")
    
    # Handle CloudFormation custom resource events
    if 'RequestType' in event:
        request_type = event.get('RequestType')
        
        if request_type == 'Delete':
            # For delete events, just return success
            send_cfn_response(event, context, "SUCCESS", {
                "Message": "Resource deleted successfully"
            })
            return
            
        # Get properties from the CloudFormation custom resource event
        properties = event.get('ResourceProperties', {})
    else:
        # Direct invocation (not from CloudFormation)
        properties = event
    
    collection = properties.get('collection')
    endpoint = properties.get('endpoint')
    
    # Validate endpoint to prevent SSRF attacks
    if endpoint and not _is_valid_opensearch_endpoint(endpoint):
        raise ValueError("Invalid OpenSearch endpoint")
    
    vector_index_name = properties.get('vector_index_name')
    # amazonq-ignore-next-line
    vector_size = int(properties.get('vector_size', 1024))  # Default to 1024 for Titan v2
    metadata_field = properties.get('metadata_field')
    text_field = properties.get('text_field')
    vector_field = properties.get('vector_field')
    
    try:
        # Print debug information
        print(f"Collection name: {collection}")
        print(f"Endpoint: {endpoint}")
        print(f"Vector index name: {vector_index_name}")
        
        # Wait for the collection to be active
        wait_for_collection(collection)
        
        # Create the index
        wait_for_index = properties.get('wait_for_index', False)
        create_index(
            endpoint=endpoint,
            index_name=vector_index_name,
            vector_size=vector_size,
            metadata_field=metadata_field,
            text_field=text_field,
            vector_field=vector_field,
            wait_for_index=wait_for_index
        )
        
        # Signal the wait condition if URL is provided
        wait_handle_url = properties.get('wait_handle_url')
        if wait_handle_url:
            # Validate wait_handle_url to prevent SSRF
            if not _is_valid_wait_handle_url(wait_handle_url):
                raise ValueError("Invalid wait handle URL")
                
            print(f"Signaling wait condition: {wait_handle_url}")
            try:
                signal_data = json.dumps({
                    "Status": "SUCCESS",
                    "Reason": "Index creation completed successfully",
                    "UniqueId": "IndexCreator",
                    "Data": "Index creation completed"
                })
                
                response = requests.put(wait_handle_url, data=signal_data) # nosec  # B113: sending CFN wait signal to trusted endpoint
                print(f"Wait condition signal response: {response.status_code}")
                    
                print("Successfully signaled wait condition")
            except Exception as e:
                print(f"Error signaling wait condition: {str(e)}")
                # Continue even if signaling fails
        
        # If this is a CloudFormation custom resource request, send success response
        if 'ResponseURL' in event:
            send_cfn_response(event, context, "SUCCESS", {
                "Message": "Index created successfully",
                "IndexName": vector_index_name
            })
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Index created successfully',
                'indexName': vector_index_name
            })
        }
    except Exception as e:
        import traceback
        print(f"Error creating index: {str(e)}")
        print(f"Stack trace: {traceback.format_exc()}")
        
        # If this is a CloudFormation custom resource request, send failure response
        if 'ResponseURL' in event:
            send_cfn_response(event, context, "FAILED", {
                "Message": f"Error creating index: {str(e)}"
            })
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f'Error creating index: {str(e)}'
            })
        }

# Helper function to send response to CloudFormation
def send_cfn_response(event, context, response_status, response_data):
    """Send a response to CloudFormation to handle the custom resource lifecycle"""
    if 'ResponseURL' not in event:
        print("No ResponseURL found in the event")
        return
        
    response_body = {
        'Status': response_status,
        'Reason': f"See details in CloudWatch Log Stream: {context.log_stream_name}",
        'PhysicalResourceId': context.log_stream_name,
        'StackId': event.get('StackId'),
        'RequestId': event.get('RequestId'),
        'LogicalResourceId': event.get('LogicalResourceId'),
        'Data': response_data
    }
    
    print(f"Sending response to CloudFormation: {json.dumps(response_body)}")
    
    try:
        response = requests.put(
            event['ResponseURL'],
            data=json.dumps(response_body)
        ) # nosec  # B113: sending CFN response to trusted endpoint
        print(f"CloudFormation response status code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error sending response: {response.text}")
    except Exception as e:
        print(f"Error sending response to CloudFormation: {str(e)}")

def wait_for_collection(collection_name):
    """
    Wait for the OpenSearch Serverless collection to be active.
    
    Args:
        collection_name: Name of the collection to wait for
    """
    client = boto3.client('opensearchserverless')
    
    print(f"Waiting for collection {collection_name} to be active...")
    
    # Check if collection_name is None
    if collection_name is None:
        raise Exception("Collection name is None. Please provide a valid collection name.")
    
    max_attempts = 30
    attempts = 0
    
    while attempts < max_attempts:
        try:
            response = client.batch_get_collection(
                names=[collection_name]
            )
            
            if response['collectionDetails'][0]['status'] == 'ACTIVE':
                print(f"Collection {collection_name} is now active")
                return
            
            print(f"Collection status: {response['collectionDetails'][0]['status']}")
        except Exception as e:
            print(f"Error checking collection status: {str(e)}")
        
        attempts += 1
        time.sleep(10)
    
    raise Exception(f"Collection {collection_name} did not become active within the timeout period")

def create_index(endpoint, index_name, vector_size, metadata_field, text_field, vector_field, wait_for_index=False):
    """
    Create an OpenSearch Serverless index for Bedrock Knowledge Base.
    
    Args:
        endpoint: OpenSearch Serverless endpoint
        index_name: Name of the index to create
        vector_size: Size of the vector embeddings
        metadata_field: Field name for metadata
        text_field: Field name for text chunks
        vector_field: Field name for vectors
        wait_for_index: Whether to wait for the index to be fully available
    """
    region = os.environ.get('AWS_REGION')
    if not region:
        raise ValueError("AWS_REGION environment variable must be set")
    service = 'aoss'
    
    # Get credentials
    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        service,
        session_token=credentials.token
    )
    
    # Fix URL formatting - remove https:// if it's already in the endpoint
    if endpoint.startswith('https://'):
        base_url = endpoint
    else:
        base_url = f"https://{endpoint}"
    
    url = f"{base_url}/{index_name}"
    
    print(f"Using URL: {url}")
    print(f"Using region: {region}")
    
    # Define the index mapping with FAISS engine type
    index_mapping = {
        "settings": {
            "index.knn": "true"
        },
        "mappings": {
            "properties": {
                
                text_field: {
                    "type": "text"
                },
                vector_field: {
                    "type": "knn_vector",
                    "dimension": vector_size,
                    "method": {
                        "name": "hnsw",
                        "space_type": "l2",
                        "engine": "faiss",  # Using FAISS engine as required by Bedrock
                        "parameters": {
                            "ef_construction": 512,
                            "m": 16
                        }
                    }
                }
            }
        }
    }
    
    # Check if index exists
    try:
        headers = {"Content-Type": "application/json"}
        print(f"Checking if index exists with headers: {headers}")
        response = requests.head(url, auth=awsauth, headers=headers) # nosec  # B113: sending request to trusted endpoint
        print(f"Head response: {response.status_code}")
        if response.status_code == 200:
            print(f"Index {index_name} already exists")
            return
    except Exception as e:
        print(f"Error checking if index exists: {str(e)}")
    
    # Create the index
    try:
        headers = {"Content-Type": "application/json"}
        print(f"Creating index with headers: {headers}")
        print(f"Auth: {awsauth}")
        print(f"Index mapping: {json.dumps(index_mapping)}")
        
        response = requests.put(
            url,
            auth=awsauth,
            json=index_mapping
        ) # nosec  # B113: sending request to trusted endpoint
        
        print(f"Create index response: {response.status_code}")
        if response.status_code not in [200, 201]:
            print(f"Error response: {response.text}")
            raise Exception(f"Failed to create index: {response.status_code} - {response.text}")
        
        print(f"Index {index_name} created successfully")
        
        if wait_for_index:
            wait_for_index_ready(endpoint, index_name, awsauth)
            
    except Exception as e:
        print(f"Error creating index: {str(e)}")
        raise

def wait_for_index_ready(endpoint, index_name, awsauth):
    """Wait for the index to be ready and fully propagated"""
    if endpoint.startswith('https://'):
        base_url = endpoint
    else:
        base_url = f"https://{endpoint}"

    url = f"{base_url}/{index_name}"

    # First, wait for the index to respond to GET requests
    max_attempts = 20
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, auth=awsauth) # nosec  # B113: sending request to trusted endpoint
            if response.status_code == 200:
                print(f"Index {index_name} responds to GET requests")
                break
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error checking index status: {str(e)}")

        if attempt < max_attempts - 1:
            print(f"Waiting for index to respond... (attempt {attempt + 1}/{max_attempts})")
            time.sleep(5)

    # Additional wait for OpenSearch Serverless eventual consistency
    # Bedrock needs the index to be fully propagated before Knowledge Base creation
    print(f"Index exists, waiting 30 seconds for OpenSearch Serverless propagation...")
    time.sleep(30)

    # Verify the index is still accessible after propagation wait
    try:
        response = requests.get(url, auth=awsauth) # nosec  # B113: sending request to trusted endpoint
        if response.status_code == 200:
            print(f"Index {index_name} is ready and fully propagated")
        else:
            print(f"Warning: Index returned status {response.status_code} after propagation wait")
    except Exception as e:
        print(f"Warning: Error verifying index after propagation: {str(e)}")

def _is_valid_opensearch_endpoint(endpoint):
    """Validate OpenSearch endpoint to prevent SSRF"""
    import re
    
    # Remove protocol if present for validation
    clean_endpoint = endpoint.replace('https://', '').replace('http://', '')
    
    print(f"Validating endpoint: {clean_endpoint}")
    
    # Check if it's a valid AWS OpenSearch/AOSS endpoint
    aws_domain_patterns = [
        r'\.aoss\.amazonaws\.com$',           # OpenSearch Serverless
        r'\.es\.amazonaws\.com$',             # Elasticsearch Service  
        r'\.aoss\.[a-z0-9-]+\.amazonaws\.com$',  # Regional AOSS format
        r'\.aoss\.[a-z0-9-]+\.on\.aws$',     # Alternative AWS format
    ]
    
    # Also ensure it doesn't contain suspicious patterns
    suspicious_patterns = [
        r'^localhost',
        r'^127\.',
        r'^192\.168\.',
        r'^10\.',
        r'^172\.(1[6-9]|2[0-9]|3[0-1])\.',
        r'[<>"\'\s]',  # Prevent injection
    ]
    
    # Check for suspicious patterns first
    for pattern in suspicious_patterns:
        if re.search(pattern, clean_endpoint, re.IGNORECASE):
            print(f"Endpoint contains suspicious pattern: {pattern}")
            return False
    
    # Check if endpoint contains AWS OpenSearch patterns
    for pattern in aws_domain_patterns:
        if re.search(pattern, clean_endpoint, re.IGNORECASE):
            print(f"Endpoint validated successfully")
            return True
    
    print(f"Endpoint validation failed for: {clean_endpoint}")
    print("Expected AWS OpenSearch Serverless or Elasticsearch endpoint")
    return False

def _is_valid_wait_handle_url(url):
    """Validate wait handle URL to prevent SSRF"""
    import urllib.parse
    import re

    try:
        parsed = urllib.parse.urlparse(url)

        # Only allow HTTPS
        if parsed.scheme != 'https':
            print(f"Wait handle URL validation failed: scheme is {parsed.scheme}, expected https")
            return False

        # Only allow AWS CloudFormation wait condition domains
        # These follow patterns like: cloudformation-waitcondition-{region}.s3-{region}.amazonaws.com
        allowed_patterns = [
            r'^cloudformation-waitcondition-[a-z0-9-]+\.s3[.-][a-z0-9-]+\.amazonaws\.com$',
            r'^s3[.-][a-z0-9-]+\.amazonaws\.com$',
            r'^cloudformation\.[a-z0-9-]+\.amazonaws\.com$'
        ]

        for pattern in allowed_patterns:
            if re.match(pattern, parsed.netloc):
                print(f"Wait handle URL validated successfully: {parsed.netloc}")
                return True

        print(f"Wait handle URL validation failed: {parsed.netloc} does not match allowed patterns")
        return False
    except Exception as e:
        print(f"Wait handle URL validation error: {str(e)}")
        return False

def _wait_for_index_availability(url, awsauth, headers, index_name):
    """Wait for index to be available with exponential backoff"""
    import time
    
    print(f"Waiting for index {index_name} to be fully available...")
    
    backoff_times = [2, 4, 6, 8, 10]  # Progressive backoff instead of fixed delays
    
    for attempt, wait_time in enumerate(backoff_times, 1):
        try:
            verify_response = requests.get(url, auth=awsauth, headers=headers) # nosec  # B113: sending request to trusted endpoint
            if verify_response.status_code == 200:
                print(f"Index {index_name} is fully available")
                return
            print(f"Index not yet available (attempt {attempt}/{len(backoff_times)}): {verify_response.status_code}")
        except Exception as e:
            print(f"Error verifying index: {str(e)}")
        
        if attempt < len(backoff_times):
            time.sleep(wait_time)
    
    raise Exception(f"Index {index_name} did not become available within the timeout period")