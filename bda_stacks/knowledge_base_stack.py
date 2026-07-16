from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_s3 as s3,
    RemovalPolicy,
    aws_opensearchserverless as os_serverless,
    aws_bedrock as bedrock,
    custom_resources,
    CustomResource,
    aws_events as events,
    aws_events_targets as targets
)
import json
import os
import logging
from constructs import Construct
from cdk_nag import NagSuppressions

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class BDAKnowledgeBaseStack(Stack):
    """
    Stack for Bedrock Knowledge Base resources only.
    This provides the knowledge base functionality needed by Strand Agents
    without the traditional Bedrock agents.
    """
    
    def __init__(self, scope: Construct, construct_id: str, storage_stack, 
                 deployment_env='Dev', version='v1', deployment_id=None, **kwargs) -> None:
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
        
        # Get references from storage stack
        self.pdf_bucket = storage_stack.pdf_bucket
        self.bucket_name = storage_stack.bucket_name
        
        # Get output prefixes from storage stack
        self.text_output_prefix = storage_stack.text_output_prefix
        self.page_output_prefix = storage_stack.page_output_prefix
        self.markdown_output_prefix = storage_stack.markdown_output_prefix

        # Create resource name prefix for consistent naming
        # Include deployment ID if provided for complete isolation
        if deployment_id:
            resource_name_prefix = f"BDA-{deployment_env}-{deployment_id}"
        else:
            resource_name_prefix = f"BDA-{deployment_env}"

        # Load configuration
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)

        # Define parameters for knowledge base
        knowledge_base_name = f"{config['knowledgeBaseName']}{unique_suffix}"
        knowledge_base_description = config['knowledgeBaseDescription']
        embedding_model_id = config['embeddingModelId']
        data_source_name = f"{config['knowledgeBaseDataSourceName']}{unique_suffix}"
        
        # Define deterministic OpenSearch resource names
        collection_name = f'bda-vector-col-{deployment_env.lower()}'
        vector_index_name = f'bedrock-kb-{deployment_env.lower()}'
        
        # Get the embedding model ARN
        embedding_model_arn = bedrock.FoundationModel.from_foundation_model_id(
            self, 'EmbeddingsModel',
            foundation_model_id=bedrock.FoundationModelIdentifier(embedding_model_id)
        ).model_arn

        # Get KB source configuration
        kb_config = config.get('knowledgeBaseDataSourceConfig', {})
        use_external_bucket = kb_config.get('useExternalBucket', False)
        markdown_prefix = kb_config.get('markdownPrefix', self.markdown_output_prefix)

        # Determine which bucket to use for KB data source
        external_buckets = config.get('externalBuckets', [])
        kb_bucket_arn = self.pdf_bucket.bucket_arn  # Default to main bucket
        kb_bucket_name = self.bucket_name

        if use_external_bucket and external_buckets:
            # Use the first external bucket if configured to do so
            kb_bucket_name = external_buckets[0]
            kb_bucket_arn = f"arn:aws:s3:::{kb_bucket_name}"
            logger.info(f"Using external bucket for KB data source: {kb_bucket_name}")

        # Create IAM role for knowledge base
        kb_role = iam.Role(
            self, 'KnowledgeBaseRole',
            assumed_by=iam.ServicePrincipal('bedrock.amazonaws.com'),
            description='Role for Bedrock Knowledge Base to access S3 and OpenSearch'
        )

        # Create Lambda roles for index creation and KB sync
        base_lambda_policy = iam.ManagedPolicy.from_aws_managed_policy_name(
            managed_policy_name='service-role/AWSLambdaBasicExecutionRole'
        )
        
        index_lambda_role = iam.Role(
            self, 'IndexCreatorLambdaRole',
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
            managed_policies=[base_lambda_policy]
        )

        kb_lambda_role = iam.Role(
            self, 'KBSyncLambdaRole',
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
            managed_policies=[base_lambda_policy]
        )

        # Add CloudFormation access permissions to index Lambda
        index_lambda_role.add_to_policy(iam.PolicyStatement(
            sid='CloudFormationSignal',
            effect=iam.Effect.ALLOW,
            actions=[
                'cloudformation:SignalResource',
                'cloudformation:DescribeStacks',
                's3:PutObject',
                'aoss:BatchGetCollection',
                'aoss:CreateIndex',
                'aoss:DeleteIndex',
                'aoss:UpdateIndex',
                'aoss:ListIndices',
                'aoss:DescribeIndex',
                'aoss:ReadDocument',
                'aoss:WriteDocument',
                'aoss:APIAccessAll'
            ],
            resources=['*']
        ))

        # Add specific permissions for WaitCondition signaling
        index_lambda_role.add_to_policy(iam.PolicyStatement(
            sid='WaitConditionSignaling',
            effect=iam.Effect.ALLOW,
            actions=[
                'cloudformation:SignalResource',
                'cloudformation:PutSignal'
            ],
            resources=[
                f"arn:aws:cloudformation:{self.region}:{self.account}:stack/{self.stack_name}/*"
            ]
        ))

        # Add CDK Nag suppressions for index Lambda role
        NagSuppressions.add_resource_suppressions(
            index_lambda_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard required for OpenSearch Serverless and CloudFormation operations",
                    "appliesTo": [
                        "Resource::*"
                    ]
                }
            ]
        )

        # Add specific suppression for CloudFormation stack wildcard
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/IndexCreatorLambdaRole/DefaultPolicy/Resource",
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Knowledge Base setup Lambda requires CloudFormation wildcard permissions for WaitCondition signaling during OpenSearch Serverless index creation. This is necessary for the custom resource to signal back to CloudFormation that the knowledge base setup has completed successfully. The wildcard is scoped to the specific CloudFormation stack.",
                    "appliesTo": [
                        f"Resource::arn:aws:cloudformation:{self.region}:{self.account}:stack/{self.stack_name}/*"
                    ]
                }
            ]
        )

        # Grant S3 object access to knowledge base role
        # Use resource ARN pattern to restrict to markdown prefix only
        kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="KnowledgeBaseS3ObjectAccess",
                actions=["s3:GetObject"],
                resources=[f"{self.pdf_bucket.bucket_arn}/{markdown_prefix}/*"]
            )
        )

        # Grant bucket-level permissions with prefix condition
        kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="KnowledgeBaseS3BucketAccess",
                actions=["s3:ListBucket", "s3:GetBucketLocation"],
                resources=[self.pdf_bucket.bucket_arn],
                conditions={
                    "StringLike": {
                        "s3:prefix": [f"{markdown_prefix}/*"]
                    }
                }
            )
        )

        # Grant permissions for external bucket if used - FIXED
        if use_external_bucket and external_buckets:
            for bucket_name in external_buckets:
                # Create a valid SID by replacing hyphens and limiting length
                safe_bucket_name = bucket_name.replace('-', '').replace('_', '')[:24]
                # Bucket-level permissions
                kb_role.add_to_policy(iam.PolicyStatement(
                    sid=f"ExternalBucketList{safe_bucket_name}",
                    effect=iam.Effect.ALLOW,
                    resources=[f"arn:aws:s3:::{bucket_name}"],  # Bucket ARN only
                    actions=['s3:ListBucket', 's3:GetBucketLocation']
                ))
                # Object-level permissions  
                kb_role.add_to_policy(iam.PolicyStatement(
                    sid=f"ExternalBucketObjects{safe_bucket_name}",
                    effect=iam.Effect.ALLOW,
                    resources=[f"arn:aws:s3:::{bucket_name}/*"],  # Fixed: Add /* for objects
                    actions=['s3:GetObject']
                ))
        
        # Create OpenSearch Serverless collection for vector store
        collection = os_serverless.CfnCollection(
            self, 'VectorCollection',
            name=collection_name,
            description='BDA Knowledge Base Embeddings Store',
            standby_replicas='DISABLED',
            type='VECTORSEARCH'
        )
        
        # Create encryption policy
        encryption_policy_document = json.dumps(
            {'Rules': [{'ResourceType': 'collection',
                      'Resource': [f'collection/{collection_name}']}],
             'AWSOwnedKey': True},
            separators=(',', ':'))
            
        encryption_policy = os_serverless.CfnSecurityPolicy(
            self, 'CollectionEncryptionPolicy',
            name=f'bda-kb-enc-policy{short_suffix}',
            type='encryption',
            policy=encryption_policy_document
        )
            
        collection.add_dependency(encryption_policy)

        # Create network policy
        network_policy_document = json.dumps(
            [{'Rules': [{'Resource': [f'collection/{collection_name}'],
                       'ResourceType': 'dashboard'},
                      {'Resource': [f'collection/{collection_name}'],
                       'ResourceType': 'collection'}],
              'AllowFromPublic': True}], separators=(',', ':'))
              
        network_policy = os_serverless.CfnSecurityPolicy(
            self, 'CollectionNetworkPolicy',
            name=f'bda-kb-net-policy{short_suffix}',
            type='network',
            policy=network_policy_document
        )
            
        collection.add_dependency(network_policy)
        
        # Create Lambda Layer for Python dependencies
        python_deps_layer = lambda_.LayerVersion(
            self, "PythonDependenciesLayer",
            code=lambda_.Code.from_asset("lambda_layers/python-deps"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Layer with dependencies for OpenSearch and Bedrock"
        )
        
        # Create Lambda function for index creation
        index_lambda = lambda_.Function(
            self, 'CollectionIndexCreator',
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset('Lambda/collections'),
            handler='index.handler',  # Fixed: Match the actual function name in Lambda file
            timeout=Duration.seconds(900),  # Increased to 15 minutes
            role=index_lambda_role,
            layers=[python_deps_layer],
            environment={
                'COLLECTION_NAME': collection_name,
                'COLLECTION_ENDPOINT': collection.attr_collection_endpoint,
                'VECTOR_INDEX_NAME': vector_index_name  # Add for debugging
            }
        )
        
        # Use Provider framework for proper CloudFormation Custom Resource lifecycle
        # This ensures CloudFormation waits for the Lambda to complete before proceeding
        index_provider = custom_resources.Provider(
            self, 'IndexCreatorProvider',
            on_event_handler=index_lambda
        )

        # Add CDK Nag suppression for the Provider framework Lambda
        NagSuppressions.add_resource_suppressions(
            index_provider,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Provider framework requires wildcard permissions to invoke the index creator Lambda",
                    "appliesTo": [
                        f"Resource::<CollectionIndexCreatorB4D84E58.Arn>:*"
                    ]
                }
            ],
            apply_to_children=True
        )

        # Create Custom Resource - CloudFormation will block until this completes
        index_creator = CustomResource(
            self, 'IndexCreatorInvocation',
            service_token=index_provider.service_token,
            properties={
                'collection': collection_name,
                'endpoint': collection.attr_collection_endpoint,
                'vector_index_name': vector_index_name,
                'vector_size': 1024,
                'metadata_field': 'AMAZON_BEDROCK_METADATA',
                'text_field': 'AMAZON_BEDROCK_TEXT',
                'vector_field': 'bedrock-knowledge-base-default-vector',
                'wait_for_index': True
            }
        )

        # Ensure index creation happens after collection is ready
        index_creator.node.add_dependency(collection)
        
        # Grant permission to access the OSS collection
        kb_role.add_to_policy(iam.PolicyStatement(
            sid='OpenSearchServerlessAPIAccessAllStatement',
            effect=iam.Effect.ALLOW,
            resources=[collection.attr_arn],
            actions=[
                'aoss:APIAccessAll',
                'aoss:CreateIndex',
                'aoss:DeleteIndex',
                'aoss:UpdateIndex',
                'aoss:DescribeIndex',
                'aoss:ReadDocument',
                'aoss:WriteDocument',
                'aoss:BatchGetCollection'
            ]
        ))
        
        # Grant permission to invoke the embedding model
        kb_role.add_to_policy(iam.PolicyStatement(
            sid='BedrockInvokeModelStatement',
            effect=iam.Effect.ALLOW,
            resources=[embedding_model_arn],
            actions=['bedrock:InvokeModel']
        ))
        
        # Create OpenSearch data access policy
        policy = json.dumps(
            [{'Rules':
              [{'Resource': [f'collection/{collection_name}'],
                'Permission': ['aoss:CreateCollectionItems',
                               'aoss:DeleteCollectionItems',
                               'aoss:UpdateCollectionItems',
                               'aoss:DescribeCollectionItems'
                               ],
                'ResourceType': 'collection'},
               {'Resource': [f'index/{collection_name}/*'],
                'Permission': ['aoss:CreateIndex',
                               'aoss:DeleteIndex',
                               'aoss:UpdateIndex',
                               'aoss:DescribeIndex',
                               'aoss:ReadDocument',
                               'aoss:WriteDocument'],
                'ResourceType': 'index'}],
              'Principal': [kb_role.role_arn, index_lambda_role.role_arn, kb_lambda_role.role_arn],
              'Description': 'Knowledge base data policy'}], separators=(',', ':'))
              
        data_access_policy = os_serverless.CfnAccessPolicy(
            self, 'DataAccessPolicy',
            name=f'bda-kb-data-policy{short_suffix}',
            type='data',
            policy=policy
        )
            
        collection.add_dependency(data_access_policy)
        
        # Create the knowledge base
        knowledge_base = bedrock.CfnKnowledgeBase(
            self, 'KnowledgeBase',
            name=knowledge_base_name,
            description=knowledge_base_description,
            role_arn=kb_role.role_arn,
            knowledge_base_configuration={
                'type': 'VECTOR',
                'vectorKnowledgeBaseConfiguration': {
                    'embeddingModelArn': embedding_model_arn
                }
            },
            storage_configuration={
                'type': 'OPENSEARCH_SERVERLESS',
                'opensearchServerlessConfiguration': {
                    'collectionArn': collection.attr_arn,
                    'vectorIndexName': vector_index_name,
                    'fieldMapping': {
                        'metadataField': 'AMAZON_BEDROCK_METADATA',
                        'textField': 'AMAZON_BEDROCK_TEXT',
                        'vectorField': 'bedrock-knowledge-base-default-vector'
                    }
                }
            }
        )
        
        # Set removal policy for easier cleanup
        knowledge_base.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # Add proper dependencies - wait for index creation to fully complete
        knowledge_base.node.add_dependency(collection)
        knowledge_base.node.add_dependency(data_access_policy)
        knowledge_base.node.add_dependency(index_creator)  # Wait for index creation completion
        
        # Create KB datasource using the configured bucket and prefix
        datasource = bedrock.CfnDataSource(
            self, 'KBDataSource',
            name=data_source_name,
            knowledge_base_id=knowledge_base.attr_knowledge_base_id,
            data_source_configuration={
                's3Configuration': {
                    'bucketArn': kb_bucket_arn,
                    'inclusionPrefixes': [f"{markdown_prefix}/"]
                },
                'type': 'S3'
            },
            # Set data deletion policy - 'RETAIN' prevents vector store deletion issues
            data_deletion_policy='RETAIN',
            # Add vector ingestion configuration with hierarchical chunking and overlap
            vector_ingestion_configuration={
                'chunkingConfiguration': {
                    'chunkingStrategy': 'HIERARCHICAL',
                    'hierarchicalChunkingConfiguration': {
                        'levelConfigurations': [
                            {'maxTokens': 500},  # Level 1 (e.g., titles, headings)
                            {'maxTokens': 300}   # Level 2 (e.g., paragraphs, sections)
                        ],
                        'overlapTokens': 50
                    }
                }
            }
        )
        
        # Set removal policy for easier cleanup
        datasource.apply_removal_policy(RemovalPolicy.DESTROY)
        
        # CRITICAL: For deletion, data source must be deleted BEFORE knowledge base
        # Add custom deletion order using DependsOn (CloudFormation handles reverse order on delete)
        datasource.add_dependency(knowledge_base)
        
        # Create KB sync Lambda
        kb_lambda_role.add_to_policy(iam.PolicyStatement(
            sid='SyncKBPolicy',
            effect=iam.Effect.ALLOW,
            resources=[knowledge_base.attr_knowledge_base_arn],
            actions=['bedrock:StartIngestionJob']
        ))
        
        kb_sync_lambda = lambda_.Function(
            self, 'KBSyncLambda',
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset('Lambda'),
            handler='BDA_KB_Sync.lambda_handler',
            timeout=Duration.seconds(900),
            role=kb_lambda_role,
            layers=[python_deps_layer],
            environment={
                'KNOWLEDGE_BASE_ID': knowledge_base.attr_knowledge_base_id,
                'DATA_SOURCE_ID': datasource.attr_data_source_id,
                'EXTRACTED_TEXT_PREFIX': markdown_prefix,
                'BUCKET_NAME': kb_bucket_name
            }
        )
        
        # Grant specific S3 permissions to the Lambda
        # Use resource ARN pattern to restrict to markdown prefix only
        kb_sync_lambda.add_to_role_policy(
            iam.PolicyStatement(
                sid="KBSyncS3ObjectAccess",
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject"],
                resources=[f"{self.pdf_bucket.bucket_arn}/{markdown_prefix}/*"]
            )
        )

        # Grant bucket-level permissions for the KB sync Lambda
        kb_sync_lambda.add_to_role_policy(
            iam.PolicyStatement(
                sid="KBSyncS3BucketAccess",
                effect=iam.Effect.ALLOW,
                actions=["s3:ListBucket", "s3:GetBucketLocation"],
                resources=[self.pdf_bucket.bucket_arn],
                conditions={
                    "StringLike": {
                        "s3:prefix": [f"{markdown_prefix}/*"]
                    }
                }
            )
        )

        # If using external bucket, grant permissions to the Lambda - FIXED
        if use_external_bucket and external_buckets:
            for bucket_name in external_buckets:
                # Bucket-level permissions
                kb_sync_lambda.add_to_role_policy(iam.PolicyStatement(
                    sid=f"ExtBucket{bucket_name.replace('-', '')[:15]}List",
                    effect=iam.Effect.ALLOW,
                    resources=[f"arn:aws:s3:::{bucket_name}"],  # Bucket ARN only
                    actions=['s3:ListBucket', 's3:GetBucketLocation']
                ))
                # Object-level permissions
                kb_sync_lambda.add_to_role_policy(iam.PolicyStatement(
                    sid=f"ExtBucket{bucket_name.replace('-', '')[:15]}Objects",
                    effect=iam.Effect.ALLOW,
                    resources=[f"arn:aws:s3:::{bucket_name}/*"],  # Fixed: Add /* for objects
                    actions=['s3:GetObject']
                ))
        
        # Enable EventBridge notifications on the bucket to trigger KB sync
        # This ensures EventBridge can capture S3 events
        if hasattr(self.pdf_bucket, "enable_event_bridge_notification"):
            self.pdf_bucket.enable_event_bridge_notification()
        
        # Create EventBridge rule to trigger KB sync when markdown files are created
        # This automates the ingestion process whenever new markdown content is generated
        self.kb_sync_rule = events.Rule(
            self, "KBSyncRule",
            rule_name=f"{resource_name_prefix}-KBSync-Rule-{version}",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": [kb_bucket_name]},
                    "object": {
                        "key": [{"prefix": f"{markdown_prefix}/"}]
                    }
                }
            ),
            description=f"Trigger KB sync when markdown files are created in {markdown_prefix}/ ({deployment_env})"
        )
        
        # Add the KB sync Lambda as the target for the EventBridge rule
        self.kb_sync_rule.add_target(targets.LambdaFunction(kb_sync_lambda))
        
        # Store important attributes for use by other stacks
        self.knowledge_base_id = knowledge_base.attr_knowledge_base_id
        self.knowledge_base_arn = knowledge_base.attr_knowledge_base_arn
        self.kb_sync_lambda = kb_sync_lambda
        
        # Output resources
        CfnOutput(self, 'KnowledgeBaseName', value=knowledge_base.name)
        CfnOutput(self, 'KnowledgeBaseId', value=knowledge_base.attr_knowledge_base_id)
        CfnOutput(self, 'KnowledgeBaseArn', value=knowledge_base.attr_knowledge_base_arn)
        CfnOutput(self, 'DataSourceName', value=data_source_name)
        CfnOutput(self, 'DataSourceId', value=datasource.attr_data_source_id)
        CfnOutput(self, 'CollectionName', value=collection_name)
        CfnOutput(self, 'VectorIndexName', value=vector_index_name)
        CfnOutput(self, 'KBSyncLambdaArn', value=kb_sync_lambda.function_arn)