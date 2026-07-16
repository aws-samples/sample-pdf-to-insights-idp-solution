from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3_deployment as s3deploy,
    aws_iam as iam,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct
from cdk_nag import NagSuppressions
import json
import os

class BDAFrontendStack(Stack):
    def __init__(self, scope: Construct, construct_id: str,
                 storage_stack=None, auth_stack=None, deployment_env: str = "Dev",
                 version='v1', deployment_id=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Store deployment environment, version, and deployment ID
        self.deployment_env = deployment_env
        self.version = version
        self.deployment_id = deployment_id

        # Generate deterministic suffixes based on environment and deployment ID
        # This ensures consistent resource names across deployments
        if deployment_id:
            unique_suffix = f"-{deployment_env.lower()}-{deployment_id}"
            short_suffix = f"-{deployment_env[:3].lower()}-{deployment_id[:3]}"
        else:
            unique_suffix = f"-{deployment_env.lower()}"
            short_suffix = f"-{deployment_env[:3].lower()}"

        # S3 bucket for hosting static website
        self.frontend_bucket = s3.Bucket(
            self, "FrontendBucket",
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.HEAD, s3.HttpMethods.PUT, s3.HttpMethods.POST, s3.HttpMethods.DELETE],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    exposed_headers=["ETag"],
                    max_age=3000
                )
            ],
        )
        
        # Create OAC using L1 construct
        oac = cloudfront.CfnOriginAccessControl(self, "CloudFrontOAC",
            origin_access_control_config=cloudfront.CfnOriginAccessControl.OriginAccessControlConfigProperty(
                name="BDA-Frontend-OAC",
                origin_access_control_origin_type="s3",
                signing_behavior="always",
                signing_protocol="sigv4"
            )
        )

        # S3 bucket for CloudFront access logs
        log_bucket = s3.Bucket(
            self, "CloudFrontLogsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_PREFERRED  # Enable ACLs for CloudFront logging
        )

        # Grant CloudFront service permission to write logs to the bucket
        log_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:PutBucketAcl", "s3:GetBucketAcl"],
                resources=[log_bucket.bucket_arn],
                principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")]
            )
        )
        
        # CloudFront distribution with access logging enabled
        self.distribution = cloudfront.Distribution(
            self, "FrontendDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    self.frontend_bucket,
                    origin_access_identity=None  # OAC is used instead of OAI
                ),
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html"
                )
            ],
            enable_logging=True,
            log_bucket=log_bucket,
            log_file_prefix="cloudfront-access-logs/",
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021
        )
        
        # Add CDK Nag suppressions for CloudFront distribution
        NagSuppressions.add_resource_suppressions(
            self.distribution,
            [
                {
                    "id": "AwsSolutions-CFR1",
                    "reason": "Geo restrictions not required for this internal application"
                },
                {
                    "id": "AwsSolutions-CFR2",
                    "reason": "WAF integration not required for this development/internal application"
                },
                {
                    "id": "AwsSolutions-CFR4",
                    "reason": "TLS 1.2 minimum protocol version is configured"
                },
                {
                    "id": "AwsSolutions-CFR7",
                    "reason": "Origin Access Control (OAC) is configured via L1 construct override - see OriginAccessControlId property"
                }
            ]
        )

        # Configure OAC using L1 construct overrides
        cfn_distribution = self.distribution.node.default_child
        cfn_distribution.add_property_override("DistributionConfig.Origins.0.S3OriginConfig", {
            "OriginAccessIdentity": ""
        })
        cfn_distribution.add_property_override("DistributionConfig.Origins.0.OriginAccessControlId", oac.attr_id)

        # Add bucket policy for OAC after distribution is created
        self.frontend_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[f"{self.frontend_bucket.bucket_arn}/*"],
                principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
                conditions={"StringEquals": {"AWS:SourceArn": f"arn:aws:cloudfront::{self.account}:distribution/{self.distribution.distribution_id}"}}
            )
        )

        # Generate runtime configuration file
        config_data = self._generate_runtime_config(storage_stack, auth_stack)

        # Deploy runtime config (always deployed, fast and small)
        config_deployment = s3deploy.BucketDeployment(
            self, "DeployConfig",
            sources=[s3deploy.Source.data("config.json", json.dumps(config_data, indent=2))],
            destination_bucket=self.frontend_bucket,
            distribution=self.distribution,
            distribution_paths=["/config.json"],
            prune=False  # Don't delete other files
        )

        # Deploy UI files (optional - can be skipped for fast deployments)
        # Check if dist folder exists before deploying
        dist_path = "./bda-cloudscape-ui/dist"
        if os.path.exists(dist_path):
            deployment = s3deploy.BucketDeployment(
                self, "DeployUI",
                sources=[s3deploy.Source.asset(dist_path)],
                destination_bucket=self.frontend_bucket,
                distribution=self.distribution,
                distribution_paths=["/*"],
                prune=False  # Don't delete config.json
            )
            deployment.node.add_dependency(config_deployment)
        
        # Add CDK Nag suppressions for bucket deployment at stack level
        # Note: BucketDeployment custom resource IDs are generated and cannot be predicted
        NagSuppressions.add_stack_suppressions(
            self,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard permissions required for CDK bucket deployment operations",
                    "appliesTo": [
                        "Resource::arn:aws:s3:::cdk-*/*",
                        f"Resource::arn:aws:s3:::cdk-hnb659fds-assets-{self.account}-{self.region}/*",
                        "Resource::<FrontendBucketEFE2E19C.Arn>/*"
                    ]
                }
            ]
        )

        # Outputs
        CfnOutput(self, "CloudFrontURL", value=f"https://{self.distribution.distribution_domain_name}")

    def _generate_runtime_config(self, storage_stack, auth_stack):
        """Generate runtime configuration from CDK stack resources"""
        config = {
            "region": self.region,
            "cognito": {
                "userPoolId": "",
                "userPoolClientId": "",
                "identityPoolId": ""
            },
            "s3": {
                "bucket": ""
            },
            "dynamodb": {
                "processingStatusTable": "",
                "metricsTable": ""
            },
            "agentCore": {
                "runtimeArn": ""
            },
            "knowledgeBase": {
                "id": "",
                "dataSourceId": "",
                "name": ""
            }
        }

        # Populate from storage stack if provided
        if storage_stack:
            if hasattr(storage_stack, 'pdf_bucket'):
                config["s3"]["bucket"] = storage_stack.pdf_bucket.bucket_name
            if hasattr(storage_stack, 'processing_status_table'):
                config["dynamodb"]["processingStatusTable"] = storage_stack.processing_status_table.table_name
            if hasattr(storage_stack, 'metrics_table'):
                config["dynamodb"]["metricsTable"] = storage_stack.metrics_table.table_name

        # Populate from auth stack if provided
        if auth_stack:
            if hasattr(auth_stack, 'user_pool'):
                config["cognito"]["userPoolId"] = auth_stack.user_pool.user_pool_id
            if hasattr(auth_stack, 'user_pool_client'):
                config["cognito"]["userPoolClientId"] = auth_stack.user_pool_client.user_pool_client_id
            if hasattr(auth_stack, 'identity_pool'):
                config["cognito"]["identityPoolId"] = auth_stack.identity_pool.ref

        return config