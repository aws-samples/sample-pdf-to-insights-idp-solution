import boto3
import json
import os
import logging
import time
from datetime import datetime

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get environment variables
KB_ROLE_ARN = os.environ.get('KB_ROLE_ARN')
PROJECT_NAME = os.environ.get('PROJECT_NAME', f"BDA-Project-{datetime.now().strftime('%Y%m%d')}")
PROJECT_DESCRIPTION = os.environ.get('PROJECT_DESCRIPTION', "Data Automation Project for processing documents")
BUCKET_NAME = os.environ.get('BUCKET_NAME')

# Initialize Bedrock client with the correct service name
bedrock_client = boto3.client('bedrock-data-automation')

def wait_for_completion(client, get_status_function, status_kwargs, completion_states, error_states, status_path_in_response, max_iterations=15, delay=30):
    """
    Wait for a process to complete by checking its status
    """
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        try:
            response = get_status_function(**status_kwargs)
            
            # Extract status from the response using the provided path
            status = response
            for key in status_path_in_response.split('.'):
                status = status[key]
            
            logger.info(f"Current status: {status} (iteration {iteration}/{max_iterations})")
            
            if status in completion_states:
                logger.info("Process completed successfully")
                return response
            
            if status in error_states:
                logger.error(f"Process failed with status: {status}")
                return response
            
            logger.info(f"Waiting {delay} seconds...")
            time.sleep(delay)
        except Exception as e:
            logger.error(f"Error checking status: {str(e)}")
            time.sleep(delay)
    
    logger.warning(f"Timed out after {max_iterations} iterations")
    return None

def lambda_handler(event, context):
    """
    Handler for creating Bedrock Data Automation Project
    
    Parameters:
    event (dict): Event data
    context (LambdaContext): Lambda context
    
    Returns:
    dict: Response with project details
    """
    try:
        logger.info(f"Creating BDA project: {PROJECT_NAME}")
        logger.info(f"Using role ARN: {KB_ROLE_ARN}")
        logger.info(f"Using bucket: {BUCKET_NAME}")
        
        # Check if project already exists and delete it
        try:
            projects_list = bedrock_client.list_data_automation_projects()
            projects_existing = [project for project in projects_list.get("projects", []) 
                                if project.get("projectName") == PROJECT_NAME]
            
            if len(projects_existing) > 0:
                logger.info(f"Deleting existing project: {projects_existing[0]}")
                bedrock_client.delete_data_automation_project(projectArn=projects_existing[0]["projectArn"])
                time.sleep(5)  # Wait for deletion to complete
        except Exception as e:
            logger.warning(f"Error checking for existing projects: {str(e)}")
        
        # Define standard output configuration based on AWS workshop example
        standard_output_config = {
            "document": {
                "extraction": {
                    "granularity": {"types": ["DOCUMENT", "PAGE", "ELEMENT", "LINE", "WORD"]},
                    "boundingBox": {"state": "DISABLED"}
                },
                "generativeField": {"state": "ENABLED"},
                "outputFormat": {
                    "textFormat": {"types": ["PLAIN_TEXT", "MARKDOWN", "HTML", "CSV"]},
                    "additionalFileFormat": {"state": "ENABLED"}
                }
            }
        }
        
        # Create the BDA project with correct parameter names
        response = bedrock_client.create_data_automation_project(
            projectName=PROJECT_NAME,
            projectDescription=PROJECT_DESCRIPTION,
            projectStage='LIVE',
            standardOutputConfiguration=standard_output_config
        )
        
        project_arn = response['projectArn']
        project_id = project_arn.split('/')[-1]
        
        logger.info(f"Successfully created BDA project with ARN: {project_arn}")
        
        # Wait for the project to be created
        status_response = wait_for_completion(
            client=bedrock_client,
            get_status_function=bedrock_client.get_data_automation_project,
            status_kwargs={'projectArn': project_arn},
            completion_states=['COMPLETED'],
            error_states=['FAILED'],
            status_path_in_response='project.status',
            max_iterations=15,
            delay=10
        )
        
        if not status_response or status_response.get('project', {}).get('status') != 'COMPLETED':
            logger.error("Project creation did not complete successfully")
            return {
                'error': "Project creation did not complete successfully",
                'project_arn': project_arn,
                'project_id': project_id,
                'project_name': PROJECT_NAME
            }
            
        # Return successful response with ProjectArn, ID and project name
        return {
            'project_arn': project_arn,
            'project_id': project_id,
            'project_name': PROJECT_NAME
        }
        
    except Exception as e:

        logger.error(f"Error creating BDA project: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }