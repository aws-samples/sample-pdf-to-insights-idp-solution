from aws_cdk import (
    Stack,
    aws_cognito as cognito,
    aws_iam as iam,
    CfnOutput,
    RemovalPolicy
)
from cdk_nag import NagSuppressions
from constructs import Construct

class BDAAuthStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, storage_stack, environment: str, version: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Store reference to storage stack
        self.storage_stack = storage_stack
        
        # User Pool
        self.user_pool = cognito.UserPool(
            self, f"BDA-{environment}-UserPool-{version}",
            user_pool_name=f"BDA-{environment}-UserPool-{version}",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(
                username=True,
                email=True
            ),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            mfa=cognito.Mfa.REQUIRED,
            mfa_second_factor=cognito.MfaSecondFactor(
                sms=True,
                otp=True
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True
            ),
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # User Pool Client
        self.user_pool_client = cognito.UserPoolClient(
            self, f"BDA-{environment}-UserPoolClient-{version}",
            user_pool=self.user_pool,
            user_pool_client_name=f"BDA-{environment}-WebClient-{version}",
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                user_password=True
            ),
            generate_secret=False
        )
        
        # Identity Pool
        self.identity_pool = cognito.CfnIdentityPool(
            self, f"BDA-{environment}-IdentityPool-{version}",
            identity_pool_name=f"BDA-{environment}-IdentityPool-{version}",
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[
                cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                    client_id=self.user_pool_client.user_pool_client_id,
                    provider_name=self.user_pool.user_pool_provider_name
                )
            ]
        )
        
        # Authenticated Role with S3 permissions
        self.authenticated_role = iam.Role(
            self, f"BDA-{environment}-AuthenticatedRole-{version}",
            role_name=f"BDA-{environment}-AuthenticatedRole-{version}",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": self.identity_pool.ref
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated"
                    }
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity"
            )
        )
        
        # Create a custom managed policy for user S3 access
        bucket_arn = storage_stack.pdf_bucket.bucket_arn

        # Create a managed policy for authenticated user S3 access
        user_s3_policy = iam.ManagedPolicy(
            self, f"BDA-{environment}-UserS3Policy-{version}",
            managed_policy_name=f"BDA-{environment}-UserS3Policy-{version}",
            description="S3 permissions for authenticated users",
            statements=[
                # Grant bucket-level access
                iam.PolicyStatement(
                    sid="S3BucketAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:ListBucket",
                        "s3:GetBucketLocation"
                    ],
                    resources=[bucket_arn]
                ),
                # Grant object-level access to user-specific prefix
                iam.PolicyStatement(
                    sid="S3ObjectAccess",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:PutObject",
                        "s3:GetObject",
                        "s3:DeleteObject",
                        "s3:PutObjectTagging",
                        "s3:GetObjectTagging"
                    ],
                    resources=[f"{bucket_arn}/uploads/${{cognito-identity.amazonaws.com:sub}}/*"]
                )
            ]
        )

        # Attach the managed policy to the role
        self.authenticated_role.add_managed_policy(user_s3_policy)

        # Suppress wildcard permission warning for user-specific S3 prefix
        # Note: The bucket logical ID is DocumentBucketAE41E5A9 - this is stable and won't change
        # unless the construct ID or path changes in storage_stack.py
        NagSuppressions.add_resource_suppressions(
            user_s3_policy,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard required for user-specific S3 prefix pattern. Users can only access objects under uploads/${cognito-identity.amazonaws.com:sub}/* which is scoped to their own identity",
                    "appliesTo": ["Resource::<DocumentBucketAE41E5A9.Arn>/uploads/<cognito-identity.amazonaws.com:sub>/*"]
                }
            ]
        )
        
        # Suppress Advanced Security warning since Plus plan is required
        NagSuppressions.add_resource_suppressions(
            self.user_pool,
            [
                {
                    "id": "AwsSolutions-COG3",
                    "reason": "Advanced Security Mode requires Cognito Plus plan which is not available in basic tier. MFA is enabled instead for enhanced security."
                }
            ]
        )

        # Suppress SMS role warning - Cognito automatically creates this role for SMS MFA
        # The role needs wildcard permissions to send SMS messages via SNS
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/BDA-{environment}-UserPool-{version}/smsRole",
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Cognito-managed SMS role requires wildcard permissions for SNS operations to send MFA codes",
                    "appliesTo": ["Resource::*"]
                }
            ]
        )

        
        # Add DynamoDB read permissions for both processing status and metrics tables
        self.authenticated_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:Query",
                    "dynamodb:GetItem",
                    "dynamodb:Scan"
                ],
                resources=[
                    storage_stack.processing_status_table.table_arn,
                    f"{storage_stack.processing_status_table.table_arn}/index/*",
                    storage_stack.metrics_table.table_arn,
                    f"{storage_stack.metrics_table.table_arn}/index/*"
                ]
            )
        )

        # Suppress wildcard permission warning for DynamoDB GSI access
        NagSuppressions.add_resource_suppressions(
            self.authenticated_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard required for DynamoDB GSI access on ProcessingMetricsTable",
                    "appliesTo": [
                        "Resource::<ProcessingMetricsTable2C5065E7.Arn>/index/*"
                    ]
                }
            ],
            apply_to_children=True
        )

        # Add Bedrock AgentCore permissions for chat functionality
        account = Stack.of(self).account
        region = Stack.of(self).region

        self.authenticated_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockAgentCoreAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime"
                ],
                resources=[
                    # Allow access to all AgentCore runtimes in the account/region
                    f"arn:aws:bedrock-agentcore:{region}:{account}:runtime/*"
                ]
            )
        )

        # Suppress wildcard permission for AgentCore runtimes
        NagSuppressions.add_resource_suppressions(
            self.authenticated_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard required for AgentCore runtime access. Users need to invoke various agent runtimes (coordinator, analyst, etc.) dynamically.",
                    "appliesTo": [
                        f"Resource::arn:aws:bedrock-agentcore:<AWS::Region>:<AWS::AccountId>:runtime/*"
                    ]
                }
            ],
            apply_to_children=True
        )

        # Attach role to identity pool
        cognito.CfnIdentityPoolRoleAttachment(
            self, f"BDA-{environment}-IdentityPoolRoleAttachment-{version}",
            identity_pool_id=self.identity_pool.ref,
            roles={
                "authenticated": self.authenticated_role.role_arn
            }
        )
        
        # Outputs
        CfnOutput(
            self, "UserPoolId",
            value=self.user_pool.user_pool_id,
            description="Cognito User Pool ID"
        )
        
        CfnOutput(
            self, "UserPoolClientId", 
            value=self.user_pool_client.user_pool_client_id,
            description="Cognito User Pool Client ID"
        )
        
        CfnOutput(
            self, "IdentityPoolId",
            value=self.identity_pool.ref,
            description="Cognito Identity Pool ID"
        )
