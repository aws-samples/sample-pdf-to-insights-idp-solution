from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_apigateway as apigateway,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_stepfunctions as sfn,
    aws_logs as logs,
    RemovalPolicy,
    aws_events as events,
    aws_events_targets as targets
)
from constructs import Construct
from cdk_nag import NagSuppressions
import json

class BDAApiGatewayStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
                 storage_stack, resources_stack, step_functions_stack, knowledge_base_stack, automation_stack,
                 auth_stack=None, deployment_env='Dev', version='v1', deployment_id=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Store deployment environment, version, and deployment ID
        self.deployment_env = deployment_env
        self.version = version
        self.deployment_id = deployment_id
        self.auth_stack = auth_stack
        
        # Create resource name prefix for consistent naming
        # Include deployment ID if provided for complete isolation
        if deployment_id:
            resource_name_prefix = f"BDA-{deployment_env}-{deployment_id}"
        else:
            resource_name_prefix = f"BDA-{deployment_env}"

        # Reference resources from other stacks
        self.pdf_bucket = storage_stack.pdf_bucket
        self.bucket_name = storage_stack.bucket_name
        self.processing_status_table = storage_stack.processing_status_table
        self.metrics_table = storage_stack.metrics_table
        
        # Get Step Functions state machine ARN from resources stack
        self.step_function_arn = step_functions_stack.parent_state_machine.state_machine_arn
        
        # Get project ARN from automation stack
        self.project_arn = automation_stack.bda_project_cr.get_att_string("ProjectArn")
        
        # Create Lambda layer for API functions
        self.api_layer = self.create_api_layer(resource_name_prefix)
        
        # Create Lambda functions for API endpoints
        self.create_api_functions(resource_name_prefix)
        
        # Create API Gateway
        self.create_api_gateway(resource_name_prefix)
        
        # Setup CORS and permissions
        self.setup_cors_and_permissions()

    def create_api_layer(self, resource_name_prefix):
        """Create Lambda layer for API functions"""
        return lambda_.LayerVersion(
            self, "ApiLayer",
            layer_version_name=f"{resource_name_prefix}-ApiLayer-{self.version}",
            code=lambda_.Code.from_asset("lambda_layers/api-deps"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description=f"API dependencies layer for BDA ({self.deployment_env})"
        )

    def create_api_functions(self, resource_name_prefix):
        """Create Lambda functions for API endpoints"""
        
        # Common environment variables
        common_env = {
            "BUCKET_NAME": self.bucket_name,
            "STATUS_TABLE_NAME": self.processing_status_table.table_name,
            "METRICS_TABLE_NAME": self.metrics_table.table_name,
            "STEP_FUNCTION_ARN": self.step_function_arn,
            "PROJECT_ARN": self.project_arn,
            "ENVIRONMENT": self.deployment_env,
            "POWERTOOLS_SERVICE_NAME": "BDAApi"
        }

        # Upload Handler - Generates presigned URLs for S3 uploads
        self.upload_handler = lambda_.Function(
            self, "UploadHandler",
            function_name=f"{resource_name_prefix}-UploadHandler-{self.version}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("Lambda"),
            handler="BDA_Upload_Handler.lambda_handler",
            timeout=Duration.seconds(30),
            memory_size=512,
            environment=common_env,
            layers=[self.api_layer]
        )

        # Status Handler - Returns processing status for documents
        self.status_handler = lambda_.Function(
            self, "StatusHandler",
            function_name=f"{resource_name_prefix}-StatusHandler-{self.version}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("Lambda"),
            handler="BDA_Status_Handler.lambda_handler",
            timeout=Duration.seconds(30),
            memory_size=512,
            environment=common_env,
            layers=[self.api_layer]
        )

        # Process Handler - Starts the Step Functions workflow
        self.process_handler = lambda_.Function(
            self, "ProcessHandler",
            function_name=f"{resource_name_prefix}-ProcessHandler-{self.version}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("Lambda"),
            handler="BDA_Process_Handler.lambda_handler",
            timeout=Duration.seconds(30),
            memory_size=512,
            environment=common_env,
            layers=[self.api_layer]
        )

        # Load AgentCore runtime configuration if available
        agentcore_runtime_arn = ""
        try:
            import os
            config_file = os.path.join(os.path.dirname(__file__), '../agentcore/runtime_config.json')
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    runtime_config = json.load(f)
                    # Use the coordinator runtime ARN
                    agentcore_runtime_arn = runtime_config.get('runtime_arns', {}).get('coordinator', '')
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            import logging
            logging.warning(f"AgentCore config not available: {e}. Using empty runtime ARN.")
            agentcore_runtime_arn = ""

        # Agent Chat Handler - Invokes AgentCore Runtime
        self.agent_handler = lambda_.Function(
            self, "AgentHandler",
            function_name=f"{resource_name_prefix}-AgentHandler-{self.version}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("Lambda"),
            handler="BDA_Agent_Handler.lambda_handler",
            timeout=Duration.minutes(2),
            memory_size=1024,
            environment={
                **common_env,
                "USE_AGENTCORE": "true",
                "AGENTCORE_RUNTIME_ARN": agentcore_runtime_arn,
                "DEPLOYMENT_REGION": self.region
            },
            layers=[self.api_layer]
        )

        # Grant permissions to Lambda functions
        self.setup_lambda_permissions()

        # Add CDK Nag suppressions for Lambda functions
        self.add_lambda_nag_suppressions()

    def setup_lambda_permissions(self):
        """Setup IAM permissions for Lambda functions"""
        
        # Upload Handler permissions - specific actions only
        self.upload_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[f"{self.pdf_bucket.bucket_arn}/uploads/*"]
            )
        )
        self.processing_status_table.grant_write_data(self.upload_handler)
        
        # Status Handler permissions
        self.processing_status_table.grant_read_data(self.status_handler)
        self.metrics_table.grant_read_data(self.status_handler)
        
        # Process Handler permissions
        self.processing_status_table.grant_read_write_data(self.process_handler)
        self.process_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[self.step_function_arn]
            )
        )
        
        # Agent Handler permissions for AgentCore
        self.agent_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:GetAgentRuntime"
                ],
                resources=["*"]  # Can be restricted to specific runtime ARNs if needed
            )
        )

    def add_lambda_nag_suppressions(self):
        """Add CDK Nag suppressions for Lambda functions"""

        # Upload Handler suppressions
        NagSuppressions.add_resource_suppressions(
            self.upload_handler.role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcards required for S3 operations and DynamoDB GSI access",
                    "appliesTo": [
                        "Action::s3:Abort*",
                        "Resource::<DocumentBucketAE41E5A9.Arn>/*",
                        "Resource::<ProcessingStatusTableBB30F634.Arn>/index/*"
                    ]
                }
            ]
        )

        # Status Handler suppressions
        NagSuppressions.add_resource_suppressions(
            self.status_handler.role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcards required for DynamoDB GSI access patterns",
                    "appliesTo": [
                        "Resource::<ProcessingStatusTableBB30F634.Arn>/index/*"
                    ]
                }
            ]
        )

        # Process Handler suppressions
        NagSuppressions.add_resource_suppressions(
            self.process_handler.role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcards required for DynamoDB GSI access patterns",
                    "appliesTo": [
                        "Resource::<ProcessingStatusTableBB30F634.Arn>/index/*"
                    ]
                }
            ]
        )

        # Agent Handler suppressions
        NagSuppressions.add_resource_suppressions(
            self.agent_handler.role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard required for AgentCore runtime access across different regions",
                    "appliesTo": [
                        "Resource::*"
                    ]
                }
            ]
        )

    def create_api_gateway(self, resource_name_prefix):
        """Create API Gateway with endpoints"""
        
        # Configure CORS origins based on deployment environment
        allowed_origins = [
            "http://localhost:3000",  # Local development
            "http://localhost:5173"   # Vite dev server
        ]
        if self.deployment_env.lower() == 'prod':
            # Add production domains here
            allowed_origins.extend(["https://yourdomain.com"])
        elif self.deployment_env.lower() in ['dev', 'staging']:
            # Keep localhost for development environments
            pass
        
        # Create API Gateway without access logging
        # Note: Access logging requires a CloudWatch role ARN to be configured at the account level
        # This is a one-time setup: aws apigateway update-account --region <region> --patch-operations op=replace,path=/cloudwatchRoleArn,value=<role-arn>
        self.api = apigateway.RestApi(
            self, "BDAApi",
            rest_api_name=f"{resource_name_prefix}-API-{self.version}",
            description=f"BDA Document Processing API ({self.deployment_env})",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=allowed_origins,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key"]
            ),
            deploy_options=apigateway.StageOptions(
                stage_name=self.deployment_env.lower(),
                throttling_rate_limit=100,
                throttling_burst_limit=200,
                metrics_enabled=True
            ),
            # Enable request validation
            policy=iam.PolicyDocument(
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        principals=[iam.AnyPrincipal()],
                        actions=["execute-api:Invoke"],
                        resources=["*"]
                    )
                ]
            )
        )

        # Create request validation models
        self.create_request_models()

        # Create API resources and methods
        self.create_api_endpoints()

        # Add CDK Nag suppressions for API Gateway
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/BDAApi/DeploymentStage.{self.deployment_env.lower()}",
            [
                {
                    "id": "AwsSolutions-APIG3",
                    "reason": "WAFv2 is not required for this development/internal API. Consider enabling for production environments."
                },
                {
                    "id": "AwsSolutions-APIG1",
                    "reason": "Access logging disabled to avoid account-level CloudWatch role requirement. Enable by configuring CloudWatch role ARN in API Gateway account settings."
                },
                {
                    "id": "AwsSolutions-APIG6",
                    "reason": "CloudWatch logging disabled to avoid account-level CloudWatch role requirement. Enable by configuring CloudWatch role ARN in API Gateway account settings."
                }
            ]
        )

    def create_request_models(self):
        """Create request validation models for API Gateway"""

        # Upload request model
        self.upload_model = self.api.add_model(
            "UploadModel",
            content_type="application/json",
            model_name="UploadRequest",
            schema=apigateway.JsonSchema(
                schema=apigateway.JsonSchemaVersion.DRAFT4,
                title="Upload Request",
                type=apigateway.JsonSchemaType.OBJECT,
                properties={
                    "fileName": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING,
                        min_length=1,
                        max_length=255
                    ),
                    "fileSize": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.NUMBER,
                        minimum=1,
                        maximum=100000000  # 100MB
                    )
                },
                required=["fileName", "fileSize"]
            )
        )

        # Process request model
        self.process_model = self.api.add_model(
            "ProcessModel",
            content_type="application/json",
            model_name="ProcessRequest",
            schema=apigateway.JsonSchema(
                schema=apigateway.JsonSchemaVersion.DRAFT4,
                title="Process Request",
                type=apigateway.JsonSchemaType.OBJECT,
                properties={
                    "docId": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING,
                        min_length=1,
                        max_length=255
                    ),
                    "s3Key": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING,
                        min_length=1,
                        max_length=1024
                    )
                },
                required=["docId", "s3Key"]
            )
        )

        # Agent chat request model
        self.agent_model = self.api.add_model(
            "AgentModel",
            content_type="application/json",
            model_name="AgentRequest",
            schema=apigateway.JsonSchema(
                schema=apigateway.JsonSchemaVersion.DRAFT4,
                title="Agent Chat Request",
                type=apigateway.JsonSchemaType.OBJECT,
                properties={
                    "message": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING,
                        min_length=1,
                        max_length=4000
                    ),
                    "sessionId": apigateway.JsonSchema(
                        type=apigateway.JsonSchemaType.STRING,
                        min_length=1,
                        max_length=255
                    )
                },
                required=["message"]
            )
        )

        # Create request validator
        self.request_validator = self.api.add_request_validator(
            "RequestValidator",
            request_validator_name=f"BDA-{self.deployment_env}-RequestValidator",
            validate_request_body=True,
            validate_request_parameters=True
        )

    def create_api_endpoints(self):
        """Create API endpoints and integrate with Lambda functions"""
        
        # Create authorizer if auth_stack is available
        authorizer = None
        if self.auth_stack and hasattr(self.auth_stack, 'user_pool'):
            authorizer = apigateway.CognitoUserPoolsAuthorizer(
                self, "ApiAuthorizer",
                cognito_user_pools=[self.auth_stack.user_pool]
            )
        
        # Determine authorization type based on auth_stack availability
        auth_type = apigateway.AuthorizationType.COGNITO if authorizer else apigateway.AuthorizationType.API_KEY
        
        # /upload resource
        upload_resource = self.api.root.add_resource("upload")
        
        # POST /upload/presigned-url
        presigned_url_resource = upload_resource.add_resource("presigned-url")
        presigned_url_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.upload_handler),
            authorization_type=auth_type,
            authorizer=authorizer,
            request_validator=self.request_validator,
            request_models={
                "application/json": self.upload_model
            }
        )

        # /process resource
        process_resource = self.api.root.add_resource("process")
        
        # POST /process/start
        start_resource = process_resource.add_resource("start")
        start_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.process_handler),
            authorization_type=auth_type,
            authorizer=authorizer,
            request_validator=self.request_validator,
            request_models={
                "application/json": self.process_model
            }
        )

        # /status resource
        status_resource = self.api.root.add_resource("status")
        
        # GET /status/all
        all_status_resource = status_resource.add_resource("all")
        all_status_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.status_handler),
            authorization_type=auth_type,
            authorizer=authorizer
        )
        
        # GET /status/{docId}
        doc_status_resource = status_resource.add_resource("{docId}")
        doc_status_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.status_handler),
            authorization_type=auth_type,
            authorizer=authorizer
        )

        # /agent resource
        agent_resource = self.api.root.add_resource("agent")
        
        # POST /agent/chat
        chat_resource = agent_resource.add_resource("chat")
        chat_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.agent_handler),
            authorization_type=auth_type,
            authorizer=authorizer,
            request_validator=self.request_validator,
            request_models={
                "application/json": self.agent_model
            }
        )

        # CORS is already handled by default_cors_preflight_options in API Gateway creation

    def setup_cors_and_permissions(self):
        """Setup additional CORS and permissions"""
        
        # Export API Gateway URL
        CfnOutput(
            self, "ApiGatewayUrl",
            value=self.api.url,
            description=f"BDA API Gateway URL ({self.deployment_env})"
        )

        # Export API Gateway ID
        CfnOutput(
            self, "ApiGatewayId",
            value=self.api.rest_api_id,
            description=f"BDA API Gateway ID ({self.deployment_env})"
        )

        # Export Lambda function ARNs
        CfnOutput(
            self, "UploadHandlerArn",
            value=self.upload_handler.function_arn,
            description=f"Upload Handler Lambda ARN ({self.deployment_env})"
        )

        CfnOutput(
            self, "StatusHandlerArn",
            value=self.status_handler.function_arn,
            description=f"Status Handler Lambda ARN ({self.deployment_env})"
        )

        CfnOutput(
            self, "ProcessHandlerArn",
            value=self.process_handler.function_arn,
            description=f"Process Handler Lambda ARN ({self.deployment_env})"
        )

        CfnOutput(
            self, "AgentHandlerArn",
            value=self.agent_handler.function_arn,
            description=f"Agent Handler Lambda ARN ({self.deployment_env})"
        )

    def add_s3_event_handler(self, step_function_arn: str, project_arn: str, deployment_env: str, version: str, deployment_id=None):
        """Add S3 event handler for automatic processing via EventBridge"""
        if deployment_id:
            resource_name_prefix = f"BDA-{deployment_env}-{deployment_id}"
        else:
            resource_name_prefix = f"BDA-{deployment_env}"
        
        # S3 Event Handler - Automatically triggers processing on upload
        self.s3_event_handler = lambda_.Function(
            self, "S3EventHandler",
            function_name=f"{resource_name_prefix}-S3EventHandler-{version}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("Lambda"),
            handler="BDA_S3_Event_Handler.lambda_handler",
            timeout=Duration.minutes(1),
            memory_size=512,
            environment={
                "BUCKET_NAME": self.bucket_name,
                "STATUS_TABLE_NAME": self.processing_status_table.table_name,
                "STEP_FUNCTION_ARN": step_function_arn,
                "PROJECT_ARN": project_arn,
                "ENVIRONMENT": deployment_env,
                "POWERTOOLS_SERVICE_NAME": "BDAS3EventHandler"
            },
            layers=[self.api_layer]
        )
        
        # Grant permissions to S3 event handler
        self.processing_status_table.grant_read_write_data(self.s3_event_handler)
        self.s3_event_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[step_function_arn]
            )
        )
        
        # Only enable event bridge notifications for buckets we own (not imported buckets)
        # Check if the bucket is imported by checking if it's a construct
        if hasattr(self.pdf_bucket, "node") and hasattr(self.pdf_bucket.node, "default_child"):
            # Configure S3 bucket to send events to EventBridge
            self.pdf_bucket.enable_event_bridge_notification()
        
        # Create EventBridge rule to filter S3 upload events for PDF files in uploads/ or public/uploads/ folder
        self.s3_upload_rule = events.Rule(
            self, "S3UploadRule",
            rule_name=f"{resource_name_prefix}-S3Upload-Rule-{version}",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": [self.bucket_name]},
                    "object": {
                        "key": [
                            {"prefix": "uploads/"},
                            {"prefix": "public/uploads/"}
                        ]
                    }
                }
            ),
            description=f"Rule for S3 PDF upload events in uploads/ or public/uploads/ folder ({deployment_env})"
        )
        
        # Add Lambda function as target for the EventBridge rule
        self.s3_upload_rule.add_target(targets.LambdaFunction(self.s3_event_handler))

        # Add CDK Nag suppressions for S3 event handler
        NagSuppressions.add_resource_suppressions(
            self.s3_event_handler.role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcards required for DynamoDB GSI access patterns",
                    "appliesTo": [
                        "Resource::<ProcessingStatusTableBB30F634.Arn>/index/*"
                    ]
                }
            ]
        ) 