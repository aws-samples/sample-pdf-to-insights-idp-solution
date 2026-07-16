from aws_cdk import (
    Stack,
    Duration,
    CustomResource,
    aws_iam as iam,
    aws_lambda as lambda_,
    CfnOutput
)
from constructs import Construct
from cdk_nag import NagSuppressions

class BedrockProjectStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, 
                 deployment_env='Dev', version='v1', deployment_id=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Store deployment environment, version, and deployment ID
        self.deployment_env = deployment_env
        self.version = version
        self.deployment_id = deployment_id
        
        # Generate a deterministic suffix for resource names based on environment and deployment ID
        if deployment_id:
            self.unique_suffix = f"-{deployment_env.lower()}-{deployment_id}"
        else:
            self.unique_suffix = f"-{deployment_env.lower()}"
        
        # Reference resources from storage stack with validation
        if not storage_stack:
            raise ValueError("storage_stack parameter is required")
        if not hasattr(storage_stack, 'pdf_bucket') or not hasattr(storage_stack, 'bucket_name'):
            raise ValueError("storage_stack must have pdf_bucket and bucket_name attributes")
        
        self.pdf_bucket = storage_stack.pdf_bucket
        self.bucket_name = storage_stack.bucket_name
        
        # Create resource name prefix for consistent naming
        # Include deployment ID if provided for complete isolation
        if deployment_id:
            resource_name_prefix = f"BDA-{deployment_env}-{deployment_id}"
        else:
            resource_name_prefix = f"BDA-{deployment_env}"
        
        # Create IAM role for Bedrock Data Automation
        self.bda_role = iam.Role(
            self, "BedrockDataAutomationRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description=f"Role for Bedrock Data Automation to access S3 {self.unique_suffix}"
        )
        
        # Add permissions to BDA role
        self.bda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:ListBucket"
                ],
                resources=[
                    self.pdf_bucket.bucket_arn,
                    f"{self.pdf_bucket.bucket_arn}/*"
                ]
            )
        )

        # Add CDK Nag suppressions for BDA role
        NagSuppressions.add_resource_suppressions(
            self.bda_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard required for S3 object operations across all files in bucket",
                    "appliesTo": [
                        "Resource::<DocumentBucketAE41E5A9.Arn>/*"
                    ]
                }
            ]
        )
        
        # Create Lambda for BDA project creation
        self.bda_project_lambda = lambda_.Function(
            self, "BDAProjectCreator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("Lambda"),
            handler="BDA_Project.lambda_handler",
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "KB_ROLE_ARN": self.bda_role.role_arn,
                "PROJECT_NAME": f"BDA-Project{self.unique_suffix}",
                "PROJECT_DESCRIPTION": f"Data Automation Project for processing documents {self.unique_suffix}",
                "BUCKET_NAME": self.bucket_name
            }
        )
        
        # Grant necessary permissions to the BDA project Lambda
        self.bda_project_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-data-automation:CreateDataAutomationProject",
                    "bedrock-data-automation:ListDataAutomationProjects",
                    "bedrock-data-automation:DeleteDataAutomationProject",
                    "bedrock-data-automation:CreateDataAutomationProfile",
                    "bedrock-data-automation:ListDataAutomationProfiles",
                    "bedrock:CreateDataAutomationProject",
                    "bedrock:ListDataAutomationProjects",
                    "bedrock:DeleteDataAutomationProject",
                    "bedrock:GetDataAutomationProject",
                    "bedrock:CreateDataAutomationProfile",
                    "bedrock:ListDataAutomationProfiles",
                    "bedrock:TagResource"
                ],
                resources=["*"]
            )
        )

        # Add CDK Nag suppressions for BDA project Lambda
        NagSuppressions.add_resource_suppressions(
            self.bda_project_lambda.role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard required for Bedrock Data Automation service operations",
                    "appliesTo": [
                        "Resource::*"
                    ]
                }
            ]
        )
        
        # Invoke the Lambda function to create the BDA project
        # Create Lambda for BDA project cleanup
        self.bda_cleanup_lambda = lambda_.Function(
            self, "BDAProjectCleanup",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("Lambda"),
            handler="BDA_Cleanup.lambda_handler",
            timeout=Duration.minutes(5),
            memory_size=512
        )
        
        # Grant necessary permissions to the cleanup Lambda
        self.bda_cleanup_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:DeleteDataAutomationProject",
                    "bedrock:GetDataAutomationProject"
                ],
                resources=["*"]
            )
        )

        # Add CDK Nag suppressions for BDA cleanup Lambda
        NagSuppressions.add_resource_suppressions(
            self.bda_cleanup_lambda.role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard required for Bedrock Data Automation cleanup operations",
                    "appliesTo": [
                        "Resource::*"
                    ]
                }
            ]
        )
        
        bda_project_provider = lambda_.Function(
            self, "BDAProjectProvider",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_inline("""
import json
import boto3
import cfnresponse

def handler(event, context):
    if event['RequestType'] == 'Delete':
        try:
            # Extract project ARN and cleanup Lambda ARN from properties
            project_arn = event.get('PhysicalResourceId')
            cleanup_lambda_arn = event['ResourceProperties']['CleanupLambdaArn']
            
            if project_arn and project_arn != 'Unknown' and cleanup_lambda_arn:
                # Invoke the cleanup Lambda function
                lambda_client = boto3.client('lambda')
                response = lambda_client.invoke(
                    FunctionName=cleanup_lambda_arn,
                    InvocationType='RequestResponse',
                    Payload=json.dumps({
                        'RequestType': 'Delete',
                        'PhysicalResourceId': project_arn,
                        'ResourceProperties': {
                            'ProjectArn': project_arn
                        }
                    })
                )
                print(f"Cleanup Lambda response: {response}")
            
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")
            # Still return success to allow stack deletion to proceed
        
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
        return
    
    try:
        # Extract Lambda ARN from properties
        lambda_arn = event['ResourceProperties']['LambdaArn']
        
        # Invoke the Lambda function
        lambda_client = boto3.client('lambda')
        response = lambda_client.invoke(
            FunctionName=lambda_arn,
            InvocationType='RequestResponse',
            Payload=json.dumps({})
        )
        
        payload = json.loads(response['Payload'].read().decode('utf-8'))
        print(f"BDA project creation response: {payload}")
        
        # Return the result
        if response['StatusCode'] == 200:
            result = {
                'ProjectArn': payload.get('project_arn', 'Unknown'),
                'ProjectName': payload.get('project_name', 'Unknown'),
                'ProjectId': payload.get('project_id', 'Unknown')
            }
            cfnresponse.send(event, context, cfnresponse.SUCCESS, result, physicalResourceId=payload.get('project_arn'))
        else:
            cfnresponse.send(event, context, cfnresponse.FAILED, {'Error': str(payload)})
    except Exception as e:
        print(f"Error creating BDA project: {str(e)}")
        cfnresponse.send(event, context, cfnresponse.FAILED, {'Error': str(e)})
            """),
            handler="index.handler",
            timeout=Duration.minutes(5)
        )
        
        # Grant necessary permissions to the provider
        bda_project_provider.add_to_role_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[
                    self.bda_project_lambda.function_arn,
                    self.bda_cleanup_lambda.function_arn
                ]
            )
        )
        
        self.bda_project_cr = CustomResource(
            self, "BDAProjectResource",
            service_token=bda_project_provider.function_arn,
            properties={
                "LambdaArn": self.bda_project_lambda.function_arn,
                "CleanupLambdaArn": self.bda_cleanup_lambda.function_arn
            }
        )
        
        # Export project details
        CfnOutput(self, "ProjectArn", value=self.bda_project_cr.get_att_string("ProjectArn"))
        CfnOutput(self, "ProjectName", value=self.bda_project_cr.get_att_string("ProjectName"))
        CfnOutput(self, "ProjectId", value=self.bda_project_cr.get_att_string("ProjectId"))
        CfnOutput(self, "S3BucketName", value=self.bucket_name)