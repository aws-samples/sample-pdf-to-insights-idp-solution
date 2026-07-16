import boto3
import os
import logging
import json
import cfnresponse

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock_client = boto3.client('bedrock')

def lambda_handler(event, context):
    """
    Custom resource handler to delete Bedrock Data Automation project
    when the CloudFormation stack is deleted.
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Extract the request type and physical resource ID
    request_type = event['RequestType']
    physical_id = event.get('PhysicalResourceId', None)
    
    try:
        # Only process Delete events
        if request_type == 'Delete':
            # Get the project ARN from the resource properties
            project_arn = event.get('ResourceProperties', {}).get('ProjectArn')
            
            if project_arn:
                logger.info(f"Deleting Bedrock Data Automation project: {project_arn}")
                
                # Delete the project
                try:
                    bedrock_client.delete_data_automation_project(
                        dataAutomationProjectArn=project_arn
                    )
                    logger.info(f"Successfully deleted project: {project_arn}")
                    
                    # Send success response
                    cfnresponse.send(event, context, cfnresponse.SUCCESS, 
                                    {"Message": f"Project {project_arn} deleted successfully"}, 
                                    physical_id)
                    return
                except bedrock_client.exceptions.ResourceNotFoundException:
                    logger.warning(f"Project {project_arn} not found, may have been deleted already")
                    # Still return success if the project doesn't exist
                    cfnresponse.send(event, context, cfnresponse.SUCCESS, 
                                    {"Message": f"Project {project_arn} not found"}, 
                                    physical_id)
                    return
                except Exception as e:
                    logger.error(f"Error deleting project: {str(e)}")
                    cfnresponse.send(event, context, cfnresponse.FAILED, 
                                    {"Error": f"Failed to delete project: {str(e)}"}, 
                                    physical_id)
                    return
            else:
                logger.warning("No ProjectArn provided in ResourceProperties")
        
        # For Create and Update events, just return success
        cfnresponse.send(event, context, cfnresponse.SUCCESS, 
                        {"Message": f"Request type {request_type} processed"}, 
                        physical_id or context.log_stream_name)
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        cfnresponse.send(event, context, cfnresponse.FAILED, 
                        {"Error": f"Error processing request: {str(e)}"}, 
                        physical_id or context.log_stream_name)