from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    CfnOutput,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets
)
from constructs import Construct
from cdk_nag import NagSuppressions
import os
import subprocess
import sys

class BDAResourcesStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, 
                 deployment_env='Dev', version='v1', deployment_id=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Store deployment environment, version, and deployment ID
        # Using 'deployment_env' instead of 'environment' to avoid CDK reserved property
        self.deployment_env = deployment_env
        self.version = version
        self.deployment_id = deployment_id
        
        # Create resource name prefix for consistent naming
        # Include deployment ID if provided for complete isolation
        if deployment_id:
            resource_name_prefix = f"BDA-{deployment_env}-{deployment_id}"
        else:
            resource_name_prefix = f"BDA-{deployment_env}"

        # Reference resources from storage stack
        self.pdf_bucket = storage_stack.pdf_bucket
        self.bucket_name = storage_stack.bucket_name
        self.processing_status_table = storage_stack.processing_status_table
        self.metrics_table = storage_stack.metrics_table
        
        # Use the output prefixes from the storage stack
        self.text_output_prefix = storage_stack.text_output_prefix
        self.page_output_prefix = storage_stack.page_output_prefix
        self.markdown_output_prefix = storage_stack.markdown_output_prefix

        # Create Lambda Layer (Docker-free approach)
        try:
            self.python_deps_layer = self.create_python_layer(resource_name_prefix)
        except Exception as e:
            raise RuntimeError(f"Failed to create Python layer: {str(e)}")

        # Create Lambda Functions with environment-aware naming
        try:
            self.create_lambda_functions(resource_name_prefix)
        except Exception as e:
            raise RuntimeError(f"Failed to create Lambda functions: {str(e)}")
        
        # Create IAM role for Step Functions
        try:
            self.sfn_role = self.create_step_functions_role(resource_name_prefix)
        except Exception as e:
            raise RuntimeError(f"Failed to create Step Functions role: {str(e)}")
        
        # Setup Step Functions permissions
        try:
            self.setup_step_functions_permissions()
        except Exception as e:
            raise RuntimeError(f"Failed to setup Step Functions permissions: {str(e)}")

        # Add NAG suppressions for Step Functions role
        NagSuppressions.add_resource_suppressions(
            self.sfn_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard permissions required for S3 operations on document bucket",
                    "appliesTo": [
                        f"Resource::arn:aws:s3:::<DocumentBucketAE41E5A9>/*"
                    ]
                }
            ],
            apply_to_children=True
        )

        # Export resources for other stacks to use
        CfnOutput(self, "StepFunctionsRoleArn", 
                 value=self.sfn_role.role_arn,
                 description=f"Step Functions execution role ARN ({deployment_env})")
        
        CfnOutput(self, "PythonDepsLayerArn", 
                 value=self.python_deps_layer.layer_version_arn,
                 description=f"Python dependencies layer ARN ({deployment_env})")

    def create_python_layer(self, resource_name_prefix):
        """Create Lambda layer using pre-built approach (no Docker required)"""
        
        layer_dir = "lambda_layers/python-deps"
        
        # Ensure the layer directory exists
        os.makedirs(layer_dir, exist_ok=True)
        
        # Create requirements.txt if it doesn't exist
        requirements_path = os.path.join(layer_dir, "requirements.txt")
        if not os.path.exists(requirements_path):
            self._create_requirements_file(requirements_path)
        
        # Check if the python directory already exists and has content
        python_dir = os.path.join(layer_dir, "python")
        if not os.path.exists(python_dir) or not os.listdir(python_dir):
            self._log_layer_action("Building", self.deployment_env)
            self.build_layer_dependencies(layer_dir)
        else:
            self._log_layer_action("Using existing", self.deployment_env)

        # Create the Lambda layer pointing to the pre-built directory
        return lambda_.LayerVersion(
            self, "PythonDependenciesLayer",
            layer_version_name=f"{resource_name_prefix}-PythonDeps-{self.version}",
            code=lambda_.Code.from_asset(layer_dir),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description=f"Layer containing Python dependencies for {self.deployment_env} environment"
        )

    def build_layer_dependencies(self, layer_dir):
        """Build Lambda layer dependencies using local pip (no Docker)"""
        
        # Validate and normalize layer_dir to prevent path traversal
        layer_dir = os.path.normpath(layer_dir)
        if not layer_dir.startswith("lambda_layers/"):
            raise ValueError("Invalid layer directory path")
        
        python_dir = os.path.join(layer_dir, "python")
        requirements_path = os.path.join(layer_dir, "requirements.txt")
        
        # Validate requirements_path to prevent path traversal
        abs_requirements_path = os.path.abspath(requirements_path)
        abs_layer_dir = os.path.abspath(layer_dir)
        if not abs_requirements_path.startswith(abs_layer_dir):
            raise ValueError("Invalid requirements file path")
        
        # Create python directory
        os.makedirs(python_dir, exist_ok=True)
        
        # Install dependencies using pip
        try:
            print("Installing Lambda layer dependencies...")
            
            # Use pip to install dependencies to the python directory
            cmd = [
                sys.executable, "-m", "pip", "install",
                "-r", requirements_path,
                "-t", python_dir,
                "--no-cache-dir",
                "--upgrade"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print("✓ Lambda layer dependencies installed successfully")
            
            # Clean up unnecessary files to reduce layer size
            self.cleanup_layer_directory(python_dir)
            
        except subprocess.CalledProcessError as e:
            print(f"Error installing Lambda layer dependencies: {e}")
            print(f"stdout: {e.stdout}")
            print(f"stderr: {e.stderr}")
            raise

    def cleanup_layer_directory(self, python_dir):
        """Clean up unnecessary files from the Lambda layer to reduce size"""
        
        import shutil
        import glob
        
        # Validate and normalize python_dir to prevent path traversal
        python_dir = os.path.normpath(python_dir)
        if not python_dir.startswith("lambda_layers/"):
            raise ValueError("Invalid python directory path")
        
        try:
            # Validate python_dir is safe before glob operations
            abs_python_dir = os.path.abspath(python_dir)
            if not abs_python_dir.startswith(os.path.abspath("lambda_layers/")):
                raise ValueError("Invalid python directory path")
            
            # Remove __pycache__ directories
            for pycache_dir in glob.glob(os.path.join(python_dir, "**", "__pycache__"), recursive=True):
                if os.path.abspath(pycache_dir).startswith(abs_python_dir):
                    shutil.rmtree(pycache_dir, ignore_errors=True)
            
            # Remove .pyc and .pyo files
            for pyc_file in glob.glob(os.path.join(python_dir, "**", "*.pyc"), recursive=True):
                if os.path.abspath(pyc_file).startswith(abs_python_dir):
                    os.remove(pyc_file)
            
            for pyo_file in glob.glob(os.path.join(python_dir, "**", "*.pyo"), recursive=True):
                if os.path.abspath(pyo_file).startswith(abs_python_dir):
                    os.remove(pyo_file)
            
            # Remove .dist-info directories
            for dist_info in glob.glob(os.path.join(python_dir, "*.dist-info"), recursive=False):
                if os.path.abspath(dist_info).startswith(abs_python_dir):
                    shutil.rmtree(dist_info, ignore_errors=True)
            
            # Remove test directories
            for test_dir in glob.glob(os.path.join(python_dir, "**/tests"), recursive=True):
                if os.path.abspath(test_dir).startswith(abs_python_dir):
                    shutil.rmtree(test_dir, ignore_errors=True)
                
            for test_dir in glob.glob(os.path.join(python_dir, "**/test"), recursive=True):
                if os.path.abspath(test_dir).startswith(abs_python_dir):
                    shutil.rmtree(test_dir, ignore_errors=True)
            
            print("✓ Lambda layer cleanup completed")
            
        except Exception as e:
            print(f"Warning: Layer cleanup had issues: {e}")
            # Continue anyway - cleanup is optional

    def _create_requirements_file(self, requirements_path: str):
        """Create requirements.txt with dependencies"""
        # Validate requirements_path to prevent path traversal
        normalized_path = os.path.normpath(requirements_path)
        if not normalized_path.startswith("lambda_layers/") or ".." in normalized_path:
            raise ValueError("Invalid requirements file path")
        
        requirements = [
            "pypdf==4.0.1", "requests==2.31.0", "requests-aws4auth==1.2.3",
            "boto3>=1.36.0", "aws-lambda-powertools>=3.6.0", "chardet>=5.2.0",
            "charset-normalizer>=3.3.0", "idna>=3.4", "urllib3>=1.26.0", "certifi>=2023.0.0"
        ]
        with open(normalized_path, 'w') as f:
            f.write('\n'.join(requirements) + '\n')

    def _log_layer_action(self, action: str, env: str):
        """Log layer dependency actions"""
        print(f"{action} Lambda layer dependencies for {env}...")

    def create_step_functions_role(self, resource_name_prefix):
        """Create IAM role for Step Functions"""
        
        sfn_role = iam.Role(
            self, "StepFunctionsRole",
            role_name=f"{resource_name_prefix}-StepFunctions-Role-{self.version}",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            description=f"Role for BDA Step Functions state machines ({self.deployment_env})"
        )
        
        # Add managed policy for Lambda invocation
        sfn_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaRole")
        )
        
        # Add Step Functions specific permissions with scoped resources
        sfn_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "states:StartExecution",
                    "states:SendTaskSuccess",
                    "states:SendTaskFailure"
                ],
                resources=[f"arn:aws:states:{self.region}:{self.account}:stateMachine:{resource_name_prefix}-*"]
            )
        )
        
        sfn_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "events:PutRule",
                    "events:PutTargets",
                    "events:DescribeRule",
                    "events:DeleteRule",
                    "events:RemoveTargets"
                ],
                resources=[f"arn:aws:events:{self.region}:{self.account}:rule/{resource_name_prefix}-*"]
            )
        )
        
        # Note: No CDK Nag suppressions needed - all permissions use specific resources or conditions
        
        return sfn_role

    def setup_step_functions_permissions(self):
        """Setup permissions for Step Functions role"""
        
        # Import config for external buckets
        import json
        try:
            # Use secure path construction to prevent path traversal
            config_dir = os.path.dirname(os.path.abspath(__file__))
            config_filename = 'config.json'
            # Validate filename to prevent path traversal
            if os.path.sep in config_filename or config_filename.startswith('..'):
                raise ValueError("Invalid config filename")
            config_path = os.path.join(config_dir, config_filename)
            # Ensure the resolved path is within the expected directory
            if not os.path.abspath(config_path).startswith(os.path.abspath(config_dir)):
                raise ValueError("Config path outside allowed directory")
            with open(config_path, 'r') as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            config = {}
        
        # Create bucket resources list (no wildcards)
        bucket_resources = [self.pdf_bucket.bucket_arn]

        # Add external buckets from config (bucket-level only)
        external_buckets = []
        if 'externalBuckets' in config:
            for bucket in config['externalBuckets']:
                bucket_resources.append(f"arn:aws:s3:::{bucket}")
                external_buckets.append(bucket)

        # Grant bucket-level permissions (no wildcards)
        self.sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="StepFunctionsS3BucketAccess",
                actions=["s3:ListBucket", "s3:GetBucketLocation"],
                resources=bucket_resources
            )
        )

        # Grant object-level permissions using correct resource pattern
        # Main bucket objects - use bucket_arn/* for object operations
        self.sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="StepFunctionsS3ObjectAccess",
                actions=[
                    "s3:GetObject",
                    "s3:PutObject"
                ],
                resources=[f"{self.pdf_bucket.bucket_arn}/*"],
                conditions={
                    "StringLike": {
                        "s3:prefix": [
                            "uploads/",
                            "extracted-Text/",
                            "extracted-Tables/",
                            "extracted-Markdown/",
                            "results/"
                        ]
                    }
                }
            )
        )

        # External bucket objects (if any) - use correct resource pattern
        if external_buckets:
            for bucket in external_buckets:
                self.sfn_role.add_to_policy(
                    iam.PolicyStatement(
                        sid=f"StepFunctionsExternalBucket{bucket.replace('-', '').replace('_', '')[:20]}",
                        actions=[
                            "s3:GetObject",
                            "s3:PutObject"
                        ],
                        resources=[f"arn:aws:s3:::{bucket}/*"],
                        conditions={
                            "StringLike": {
                                "s3:prefix": ["*"]
                            }
                        }
                    )
                )
        
        # Grant specific DynamoDB permissions without wildcard GSI access
        self.sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="StepFunctionsDynamoDBAccess",
                actions=[
                    "dynamodb:PutItem",
                    "dynamodb:GetItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Scan",
                    "dynamodb:Query"
                ],
                resources=[
                    self.processing_status_table.table_arn,
                    self.processing_status_table.table_arn + "/index/execution_id-index",
                    self.metrics_table.table_arn
                ]
            )
        )
        
        # Get the actual account and region from the stack
        account = self.account
        region = self.region
        
        # Grant specific Bedrock Data Automation permissions with multi-region support
        self.sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="StepFunctionsBedrockDataAutomation",
                actions=[
                    "bedrock:InvokeDataAutomationAsync",
                    "bedrock-dataautomationruntime:InvokeDataAutomationAsync"
                ],
                resources=[
                    f"arn:aws:bedrock:{region}:{account}:data-automation-project/*",
                    f"arn:aws:bedrock:{region}:{account}:blueprint/*",
                    # AWS-managed profiles across US regions for cross-region access
                    f"arn:aws:bedrock:us-east-1:{account}:data-automation-profile/us.data-automation-v1",
                    f"arn:aws:bedrock:us-east-2:{account}:data-automation-profile/us.data-automation-v1",
                    f"arn:aws:bedrock:us-west-1:{account}:data-automation-profile/us.data-automation-v1",
                    f"arn:aws:bedrock:us-west-2:{account}:data-automation-profile/us.data-automation-v1"
                ]
            )
        )

        # Grant Bedrock model access for data automation
        self.sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="StepFunctionsBedrockModels",
                actions=[
                    "bedrock:InvokeModel"
                ],
                resources=[
                    f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0",
                    f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
                ]
            )
        )

        # BDA Project CRUD permissions
        self.sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="BDAProjectsPermissions",
                actions=[
                    "bedrock:CreateDataAutomationProject",
                    "bedrock:UpdateDataAutomationProject",
                    "bedrock:GetDataAutomationProject",
                    "bedrock:GetDataAutomationStatus",
                    "bedrock:ListDataAutomationProjects",
                    "bedrock:InvokeDataAutomationAsync"
                ],
                resources=[f"arn:aws:bedrock:{region}:{account}:data-automation-project/*"]
            )
        )

        # BDA Blueprint permissions
        self.sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="BDABlueprintPermissions",
                actions=[
                    "bedrock:GetBlueprint",
                    "bedrock:ListBlueprints",
                    "bedrock:UpdateBlueprint",
                    "bedrock:DeleteBlueprint"
                ],
                resources=[f"arn:aws:bedrock:{region}:{account}:blueprint/*"]
            )
        )

        # BDA Create permissions (requires wildcard per AWS requirements)
        self.sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="BDACreatePermissions",
                actions=[
                    "bedrock:CreateDataAutomationProject",
                    "bedrock:CreateBlueprint"
                ],
                resources=["*"]
            )
        )

        # Additional S3 permissions for Bedrock Data Automation (no conditions)
        self.sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockDataAutomationS3Access",
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:GetObjectVersion"
                ],
                resources=[f"arn:aws:s3:::{self.bucket_name}/*"]
            )
        )

        # Add EventBridge permissions for Step Functions managed rules
        self.sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="StepFunctionsEventBridgeAccess",
                actions=[
                    "events:CreateRule",
                    "events:DeleteRule",
                    "events:DescribeRule",
                    "events:EnableRule",
                    "events:DisableRule",
                    "events:ListTargetsByRule",
                    "events:PutRule",
                    "events:PutTargets",
                    "events:RemoveTargets"
                ],
                resources=[
                    f"arn:aws:events:{region}:{account}:rule/StepFunctions-*",
                    f"arn:aws:events:{region}:{account}:rule/*"
                ]
            )
        )

        # Add IAM permissions for Step Functions service-linked role
        self.sfn_role.add_to_policy(
            iam.PolicyStatement(
                sid="StepFunctionsServiceLinkedRoleAccess",
                actions=[
                    "iam:CreateServiceLinkedRole",
                    "iam:PassRole"
                ],
                resources=[
                    f"arn:aws:iam::{account}:role/aws-service-role/states.amazonaws.com/AWSServiceRoleForStepFunctions",
                    f"arn:aws:iam::{account}:role/BDA-*-StepFunctions-Role-*"
                ],
                conditions={
                    "StringEquals": {
                        "iam:AWSServiceName": "states.amazonaws.com"
                    }
                }
            )
        )

        # Add CDK Nag suppressions for Step Functions role wildcards
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/StepFunctionsRole/DefaultPolicy/Resource",
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Step Functions requires wildcard permissions for: 1) Bedrock data automation projects and blueprints (created dynamically at runtime), 2) EventBridge managed rules created by Step Functions service for workflow orchestration, 3) IAM service-linked role management for Step Functions service integration. These wildcards are scoped to the account/region and necessary for Step Functions managed service functionality.",
                    "appliesTo": [
                        f"Resource::arn:aws:events:{region}:{account}:rule/*",
                        f"Resource::arn:aws:events:{region}:{account}:rule/StepFunctions-*",
                        f"Resource::arn:aws:iam::{account}:role/BDA-*-StepFunctions-Role-*"
                    ]
                }
            ]
        )

        # Note: CDK Nag suppressions for all wildcards are handled globally in app.py


    def create_lambda_functions(self, resource_name_prefix):
        """Create Lambda functions with environment-aware naming"""
        
        # Import config for external buckets
        import json
        try:
            # Use secure path construction to prevent path traversal
            config_dir = os.path.dirname(os.path.abspath(__file__))
            config_filename = 'config.json'
            # Validate filename to prevent path traversal
            if os.path.sep in config_filename or config_filename.startswith('..'):
                raise ValueError("Invalid config filename")
            config_path = os.path.join(config_dir, config_filename)
            # Ensure the resolved path is within the expected directory
            if not os.path.abspath(config_path).startswith(os.path.abspath(config_dir)):
                raise ValueError("Config path outside allowed directory")
            with open(config_path, 'r') as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            config = {}
            
        # PDF Page Checker Lambda
        self.BDA_PDF_PageChecker = lambda_.Function(
            self, "PDFPageChecker",
            function_name=f"{resource_name_prefix}-PDFPageChecker-{self.version}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("Lambda"),
            handler="BDA_PDF_PageChecker.lambda_handler",
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "POWERTOOLS_SERVICE_NAME": "BDAPDFPageChecker",
                "BUCKET_NAME": self.bucket_name,
                "STATUS_TABLE_NAME": self.processing_status_table.table_name,
                "ENVIRONMENT": self.deployment_env
            },
            layers=[self.python_deps_layer]
        )
        
        # Grant specific S3 permissions instead of broad grant_read
        self.BDA_PDF_PageChecker.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[f"{self.pdf_bucket.bucket_arn}/*"]
            )
        )
        self.processing_status_table.grant_write_data(self.BDA_PDF_PageChecker)
        
        # Grant access to external buckets from config
        self.grant_external_bucket_access(self.BDA_PDF_PageChecker, config)
        
        # Add CDK Nag suppressions for PDFPageChecker
        NagSuppressions.add_resource_suppressions(
            self.BDA_PDF_PageChecker.role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard permissions required for S3 operations and DynamoDB GSI access",
                    "appliesTo": [
                        "Action::s3:GetBucket*",
                        "Action::s3:GetObject*",
                        "Action::s3:List*",
                        "Resource::<DocumentBucketAE41E5A9.Arn>/*",
                        "Resource::<ProcessingStatusTableBB30F634.Arn>/index/*"
                    ]
                }
            ]
        )

        # Result Processor Lambda
        self.result_processor = lambda_.Function(
            self, "ResultProcessor",
            function_name=f"{resource_name_prefix}-ResultProcessor-{self.version}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("Lambda"),
            handler="BDA_Result_Processor.lambda_handler",
            timeout=Duration.minutes(5),
            memory_size=1024,
            environment={
                "STATUS_TABLE_NAME": self.processing_status_table.table_name,
                "TEXT_OUTPUT_PREFIX": self.text_output_prefix,
                "PAGE_OUTPUT_PREFIX": self.page_output_prefix,
                "MARKDOWN_OUTPUT_PREFIX": self.markdown_output_prefix,
                "POWERTOOLS_SERVICE_NAME": "BDAResultProcessor",
                "BUCKET_NAME": self.bucket_name,
                "ENVIRONMENT": self.deployment_env
            },
            layers=[self.python_deps_layer]
        )
        
        # Grant specific S3 permissions instead of broad grant_read_write
        self.result_processor.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject"],
                resources=[f"{self.pdf_bucket.bucket_arn}/*"]
            )
        )
        self.processing_status_table.grant_read_write_data(self.result_processor)
        
        # Grant access to external buckets
        self.grant_external_bucket_access(self.result_processor, config)
        
        # Suppress only necessary S3, DynamoDB, States, and Bedrock wildcards
        NagSuppressions.add_resource_suppressions(
            self.result_processor.role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcards required for S3 operations, DynamoDB GSI access, Step Functions, and Bedrock operations",
                    "appliesTo": [
                        "Action::s3:Abort*",
                        "Action::s3:DeleteObject*",
                        "Action::s3:GetBucket*",
                        "Action::s3:GetObject*",
                        "Action::s3:List*",
                        "Resource::<DocumentBucketAE41E5A9.Arn>/*",
                        "Resource::<ProcessingStatusTableBB30F634.Arn>/index/*",
                        f"Resource::arn:aws:states:{self.region}:{self.account}:*",
                        f"Resource::arn:aws:bedrock:{self.region}:{self.account}:*"
                    ]
                }
            ]
        )
        
        # Create EventBridge rule to trigger the Result Processor Lambda
        result_processor_rule = events.Rule(
            self, "ResultProcessorRule",
            rule_name=f"{resource_name_prefix}-ResultProcessor-Rule-{self.version}",
            description=f"Rule to trigger BDA Result Processor Lambda when Bedrock job completes ({self.deployment_env})",
            event_pattern=events.EventPattern(
                source=["aws.bedrock"],
                detail_type=["Bedrock Data Automation Job Succeeded", "Bedrock Data Automation Job Failed"]
            )
        )
        
        # Add the Lambda function as a target for the EventBridge rule
        result_processor_rule.add_target(
            targets.LambdaFunction(self.result_processor)
        )
        
        # Result Summary Lambda
        self.result_summary = lambda_.Function(
            self, "ResultSummary",
            function_name=f"{resource_name_prefix}-ResultSummary-{self.version}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("Lambda"),
            handler="BDA_Result_Summary.lambda_handler",
            timeout=Duration.minutes(5),
            memory_size=1024,
            environment={
                "STATUS_TABLE_NAME": self.processing_status_table.table_name,
                "METRICS_TABLE_NAME": self.metrics_table.table_name,
                "POWERTOOLS_SERVICE_NAME": "BDAResultSummary",
                "ENVIRONMENT": self.deployment_env
            },
            layers=[self.python_deps_layer]
        )
        
        self.processing_status_table.grant_read_data(self.result_summary)
        self.metrics_table.grant_write_data(self.result_summary)
        
        # Add CDK Nag suppressions for ResultSummary
        NagSuppressions.add_resource_suppressions(
            self.result_summary.role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard permissions required for DynamoDB GSI access",
                    "appliesTo": [
                        "Resource::<ProcessingStatusTableBB30F634.Arn>/index/*"
                    ]
                }
            ]
        )
        
        # Add SendTask permissions to Lambda - scoped to account
        self.result_processor.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "states:SendTaskSuccess",
                    "states:SendTaskFailure"
                ],
                resources=[f"arn:aws:states:{self.region}:{self.account}:*"]
            )
        )
        
        self.result_processor.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:GetFoundationModelDataAutomationJob",
                    "bedrock-dataautomationruntime:GetFoundationModelDataAutomationJob"
                ],
                resources=[f"arn:aws:bedrock:{self.region}:{self.account}:*"]
            )
        )
        
        # Export Lambda ARNs for use in other stacks
        CfnOutput(self, "PDFPageCheckerArn", 
                 value=self.BDA_PDF_PageChecker.function_arn,
                 description=f"PDF Page Checker Lambda ARN ({self.deployment_env})")
        
        CfnOutput(self, "ResultProcessorArn", 
                 value=self.result_processor.function_arn,
                 description=f"Result Processor Lambda ARN ({self.deployment_env})")
        
        CfnOutput(self, "ResultSummaryArn", 
                 value=self.result_summary.function_arn,
                 description=f"Result Summary Lambda ARN ({self.deployment_env})")

    def grant_external_bucket_access(self, lambda_function, config):
        """Grant access to external buckets from configuration"""
        if 'externalBuckets' in config:
            for bucket in config['externalBuckets']:
                lambda_function.add_to_role_policy(
                    iam.PolicyStatement(
                        actions=["s3:ListBucket"],
                        resources=[f"arn:aws:s3:::{bucket}"]
                    )
                )
                lambda_function.add_to_role_policy(
                    iam.PolicyStatement(
                        actions=["s3:GetObject", "s3:PutObject"],
                        resources=[f"arn:aws:s3:::{bucket}/*"]
                    )
                )