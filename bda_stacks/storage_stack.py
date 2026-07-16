import os
import json
import logging

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    CfnOutput,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_iam as iam
)
from constructs import Construct

# Configure logging
logger = logging.getLogger(__name__)

class BDAStorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, existing_bucket_name=None, 
                 custom_bucket_name=None, deployment_env='Dev', version='v1', 
                 deployment_id=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Store deployment environment, version, and deployment ID for use in resource naming
        # Using 'deployment_env' instead of 'environment' to avoid CDK reserved property
        self.deployment_env = deployment_env
        self.version = version
        self.deployment_id = deployment_id
        
        # Define output prefixes that will be used across the application
        # These are the source of truth for all file paths in the system
        self.text_output_prefix = "extracted-text"
        self.page_output_prefix = "extracted-pages"

        # Load configuration for consistent markdown prefix
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
            with open(config_path, 'r') as config_file:
                config = json.load(config_file)
            
            # Get markdown prefix from config if available
            kb_config = config.get('knowledgeBaseDataSourceConfig', {})
            self.markdown_output_prefix = kb_config.get('markdownPrefix', "extracted-Markdown")
        except Exception as e:
            # Fallback if config can't be loaded
            self.markdown_output_prefix = "extracted-Markdown"
            logger.warning(f"Using default markdown prefix due to config load error: {str(e)}", exc_info=True)

        # Create resource name prefix for consistent naming
        # Include deployment ID if provided for complete isolation
        if deployment_id:
            resource_name_prefix = f"BDA-{deployment_env}-{deployment_id}"
        else:
            resource_name_prefix = f"BDA-{deployment_env}"

        # Create or import S3 bucket based on the provided configuration
        if existing_bucket_name:
            # Option 1: Import an existing bucket
            self.pdf_bucket = s3.Bucket.from_bucket_name(
                self, "ImportedDocumentBucket", existing_bucket_name
            )
            # Store bucket name for cross-stack references
            self.bucket_name = existing_bucket_name
        elif custom_bucket_name:
            # Option 2: Use a custom bucket name provided by user
            self.pdf_bucket = s3.Bucket(
                self, "DocumentBucket",
                bucket_name=custom_bucket_name,
                removal_policy=RemovalPolicy.RETAIN,
                encryption=s3.BucketEncryption.S3_MANAGED,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                versioned=True,
                cors=[
                    s3.CorsRule(
                        allowed_headers=["*"],
                        allowed_methods=[
                            s3.HttpMethods.GET,
                            s3.HttpMethods.PUT,
                            s3.HttpMethods.POST,
                            s3.HttpMethods.DELETE,
                            s3.HttpMethods.HEAD
                        ],
                        allowed_origins=["*"],
                        exposed_headers=[
                            "ETag"
                        ],
                        max_age=3000
                    )
                ],
                lifecycle_rules=[
                    s3.LifecycleRule(
                        transitions=[
                            s3.Transition(
                                storage_class=s3.StorageClass.INTELLIGENT_TIERING,
                                transition_after=Duration.days(90)
                            )
                        ]
                    )
                ]
            )
            self.bucket_name = self.pdf_bucket.bucket_name
        else:
            # Option 3: Let CDK auto-generate a unique bucket name (RECOMMENDED)
            # This guarantees uniqueness across all deployments
            # Use DESTROY for Dev environment to allow clean redeployments
            removal_policy = RemovalPolicy.DESTROY if deployment_env == 'Dev' else RemovalPolicy.RETAIN
            
            self.pdf_bucket = s3.Bucket(
                self, "DocumentBucket",
                # No bucket_name specified - CDK will auto-generate
                removal_policy=removal_policy,
                # Auto-delete objects only in Dev environment for clean redeployments
                auto_delete_objects=(deployment_env == 'Dev'),
                encryption=s3.BucketEncryption.S3_MANAGED,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                versioned=True,
                cors=[
                    s3.CorsRule(
                        allowed_headers=["*"],
                        allowed_methods=[
                            s3.HttpMethods.GET,
                            s3.HttpMethods.PUT,
                            s3.HttpMethods.POST,
                            s3.HttpMethods.DELETE,
                            s3.HttpMethods.HEAD
                        ],
                        allowed_origins=["*"],
                        exposed_headers=[
                            "ETag"
                        ],
                        max_age=3000
                    )
                ],
                lifecycle_rules=[
                    s3.LifecycleRule(
                        transitions=[
                            s3.Transition(
                                storage_class=s3.StorageClass.INTELLIGENT_TIERING,
                                transition_after=Duration.days(90)
                            )
                        ]
                    )
                ]
            )
            self.bucket_name = self.pdf_bucket.bucket_name

        # Add SSL enforcement policy to the bucket (only for CDK-managed buckets)
        # Apply to all buckets we create or manage, but not imported ones
        if not existing_bucket_name:
            self._add_ssl_enforcement_policy()

        # DynamoDB Tables with environment-aware naming
        # The resource_name_prefix already includes deployment ID if provided
        processing_table_name = f"{resource_name_prefix}-ProcessingStatus-{version}"
        
        self.processing_status_table = dynamodb.Table(
            self, "ProcessingStatusTable",
            table_name=processing_table_name,
            partition_key=dynamodb.Attribute(
                name="doc_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            )
        )
        
        # Add GSI for execution_id
        self.processing_status_table.add_global_secondary_index(
            index_name="execution_id-index",
            partition_key=dynamodb.Attribute(
                name="execution_id", 
                type=dynamodb.AttributeType.STRING
            )
        )

        metrics_table_name = f"{resource_name_prefix}-ProcessingMetrics-{version}"
        
        self.metrics_table = dynamodb.Table(
            self, "ProcessingMetricsTable",
            table_name=metrics_table_name,
            partition_key=dynamodb.Attribute(
                name="execution_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            )
        )

        # Export resources for other stacks to use
        CfnOutput(self, "DocumentBucketName", 
                 value=self.bucket_name,
                 description=f"S3 bucket for document storage ({deployment_env})")
        
        CfnOutput(self, "ProcessingStatusTableName", 
                 value=self.processing_status_table.table_name,
                 description=f"DynamoDB table for processing status ({deployment_env})")
        
        CfnOutput(self, "MetricsTableName", 
                 value=self.metrics_table.table_name,
                 description=f"DynamoDB table for processing metrics ({deployment_env})")
        
        CfnOutput(self, "TextOutputPrefix", 
                 value=self.text_output_prefix,
                 description="S3 prefix for extracted text files")
        
        CfnOutput(self, "PageOutputPrefix", 
                 value=self.page_output_prefix,
                 description="S3 prefix for extracted page files")
        
        CfnOutput(self, "MarkdownOutputPrefix",
                 value=self.markdown_output_prefix,
                 description="S3 prefix for markdown files")
    
    def _add_ssl_enforcement_policy(self):
        """Add bucket policy to enforce SSL/HTTPS connections"""
        ssl_policy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    sid="DenyInsecureConnections",
                    effect=iam.Effect.DENY,
                    principals=[iam.AnyPrincipal()],
                    actions=["s3:*"],
                    resources=[
                        self.pdf_bucket.bucket_arn,
                        f"{self.pdf_bucket.bucket_arn}/*"
                    ],
                    conditions={
                        "Bool": {
                            "aws:SecureTransport": "false"
                        }
                    }
                )
            ]
        )
        
        # Apply the policy to the bucket
        self.pdf_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="DenyInsecureConnections",
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:*"],
                resources=[
                    self.pdf_bucket.bucket_arn,
                    f"{self.pdf_bucket.bucket_arn}/*"
                ],
                conditions={
                    "Bool": {
                        "aws:SecureTransport": "false"
                    }
                }
            )
        )