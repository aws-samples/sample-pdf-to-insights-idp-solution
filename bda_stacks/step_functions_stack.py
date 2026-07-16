from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_iam as iam,
    aws_logs as logs,
    RemovalPolicy,
    aws_lambda as lambda_,
    aws_stepfunctions as sfn,
    aws_events as events,
    aws_events_targets as targets
)
import json
import uuid

from constructs import Construct
from cdk_nag import NagSuppressions

class BDAStepFunctionsStack(Stack):
    # amazonq-ignore-next-line
    def __init__(self, scope: Construct, construct_id: str, resources_stack, 
                 deployment_env='Dev', version='v1', deployment_id=None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Store deployment environment, version, and deployment ID
        self.deployment_env = deployment_env
        self.version = version
        self.deployment_id = deployment_id

        # Create resource name prefix for consistent naming
        # Include deployment ID if provided for complete isolation
        if deployment_id:
            resource_name_prefix = f"BDA-{deployment_env}-{deployment_id}"
        else:
            resource_name_prefix = f"BDA-{deployment_env}"

        # Import resources from the resources stack
        # Lambda functions - use direct references instead of imports to avoid warnings
        self.pdf_page_checker = resources_stack.BDA_PDF_PageChecker
        self.result_processor = resources_stack.result_processor
        self.result_summary = resources_stack.result_summary
        
        # Import the IAM role for Step Functions
        self.sfn_role = iam.Role.from_role_arn(
            self, "ImportedStepFunctionsRole",
            role_arn=resources_stack.sfn_role.role_arn,
            mutable=True  # Allow modifications to the imported role
        )

        # Add CDK Nag suppressions for any policies that get attached to the imported role
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/ImportedStepFunctionsRole",
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Imported Step Functions role requires wildcard permissions for Lambda invocation and state machine operations",
                    "appliesTo": ["Resource::*"]
                }
            ]
        )
        
        # Add policy to imported role for Lambda invocation
        self.sfn_role.attach_inline_policy(
            iam.Policy(
                self, "ImportedStepFunctionsRolePolicy",
                statements=[
                    iam.PolicyStatement(
                        actions=["lambda:InvokeFunction"],
                        resources=["*"]
                    )
                ]
            )
        )
        
        # Suppress the wildcard permission for the inline policy
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/ImportedStepFunctionsRolePolicy/Resource",
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Step Functions requires wildcard Lambda invocation permissions for dynamic function calls",
                    "appliesTo": ["Resource::*"]
                }
            ]
        )

        # Get the bucket name and table names from resources stack
        bucket_name = resources_stack.bucket_name
        processing_status_table_name = resources_stack.processing_status_table.table_name
        metrics_table_name = resources_stack.metrics_table.table_name

        # Load Step Function definitions from template JSON files
        try:
            with open('StateMachineDefinitions/Parent_StateMachine.json.template', 'r') as f:
                parent_definition_json = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise ValueError(f"Failed to load Parent State Machine template: {e}")
            
        try:
            with open('StateMachineDefinitions/Child_StateMachine.json.template', 'r') as f:
                child_definition_json = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise ValueError(f"Failed to load Child State Machine template: {e}")
        
        # Create Child State Machine first so we can get its ARN for the parent
        # Replace placeholders in child definition
        child_definition_json = self.replace_placeholders(child_definition_json, {
            "bucket_name": bucket_name,
            "pdf_page_checker_arn": resources_stack.BDA_PDF_PageChecker.function_arn,
            "result_processor_arn": resources_stack.result_processor.function_arn,
            "result_summary_arn": resources_stack.result_summary.function_arn,
            "processing_status_table_name": processing_status_table_name,
            "metrics_table_name": metrics_table_name,
            "account_id": self.account,
            "region": self.region,
            "data_automation_profile_arn": f"arn:aws:bedrock:{self.region}:{self.account}:data-automation-profile/us.data-automation-v1"
        })
        
        # Create Child State Machine with environment-aware naming
        child_log_group = logs.LogGroup(
            self, "ChildStateMachineLogGroup",
            log_group_name=f"/aws/vendedlogs/states/{resource_name_prefix}-ChildStateMachine-{version}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        child_definition = sfn.DefinitionBody.from_string(json.dumps(child_definition_json))
        
        # Create child state machine with environment-aware naming
        self.child_state_machine = sfn.StateMachine(
            self, "ChildStateMachine",
            state_machine_name=f"{resource_name_prefix}-ChildStateMachine-{version}",
            definition_body=child_definition,
            timeout=Duration.days(7),
            logs=sfn.LogOptions(
                destination=child_log_group,
                level=sfn.LogLevel.ALL
            ),
            tracing_enabled=True,
            role=self.sfn_role
        )
        
        # Now replace placeholders in parent definition with actual child ARN
        parent_definition_json = self.replace_placeholders(parent_definition_json, {
            "bucket_name": bucket_name,
            "pdf_page_checker_arn": resources_stack.BDA_PDF_PageChecker.function_arn,
            "result_processor_arn": resources_stack.result_processor.function_arn,
            "result_summary_arn": resources_stack.result_summary.function_arn,
            "processing_status_table_name": processing_status_table_name,
            "metrics_table_name": metrics_table_name,
            "account_id": self.account,
            "region": self.region,
            "child_state_machine_arn": self.child_state_machine.state_machine_arn
        })
        
        # Create Parent State Machine with environment-aware naming
        parent_log_group = logs.LogGroup(
            self, "ParentStateMachineLogGroup",
            log_group_name=f"/aws/vendedlogs/states/{resource_name_prefix}-ParentStateMachine-{version}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        parent_definition = sfn.DefinitionBody.from_string(json.dumps(parent_definition_json))
        
        self.parent_state_machine = sfn.StateMachine(
            self, "ParentStateMachine",
            state_machine_name=f"{resource_name_prefix}-ParentStateMachine-{version}",
            definition_body=parent_definition,
            timeout=Duration.days(7),
            logs=sfn.LogOptions(
                destination=parent_log_group,
                level=sfn.LogLevel.ALL
            ),
            tracing_enabled=True,
            role=self.sfn_role
        )
        
        # Create EventBridge rule for BDA completion events with environment-aware naming
        self.bda_completion_rule = events.Rule(
            self, "BDACompletionRule",
            rule_name=f"{resource_name_prefix}-BDACompletion-Rule-{version}",
            event_pattern=events.EventPattern(
                source=["aws.bedrock"],
                detail_type=["Bedrock Data Automation Job Succeeded", "Bedrock Data Automation Job Failed"]
            ),
            description=f"Rule for Bedrock Data Automation job completion events ({deployment_env})"
        )
        
        # Add target to the rule
        self.bda_completion_rule.add_target(targets.LambdaFunction(self.result_processor))
        
        # Add CDK Nag suppressions for Lambda environment warnings
        NagSuppressions.add_resource_suppressions(
            self.result_processor,
            [
                {
                    "id": "UnclearLambdaEnvironment",
                    "reason": "Lambda function is imported from another stack with resolved environment"
                }
            ]
        )
        
        # Add CDK Nag suppressions for EventBridge rule environment warnings
        NagSuppressions.add_resource_suppressions(
            self.bda_completion_rule,
            [
                {
                    "id": "@aws-cdk/aws-events:ruleUnresolvedEnvironment",
                    "reason": "EventBridge rule and target are in the same environment, cross-environment setup not needed"
                }
            ]
        )
        
        # Add suppression by path for the specific warning
        NagSuppressions.add_resource_suppressions_by_path(
            self,
            f"/{self.stack_name}/BDACompletionRule",
            [
                {
                    "id": "@aws-cdk/aws-events:ruleUnresolvedEnvironment",
                    "reason": "EventBridge rule and target are in the same environment, cross-environment setup not needed"
                }
            ]
        )
        
        # Export outputs with environment context
        CfnOutput(self, "ChildStateMachineArn", 
                 value=self.child_state_machine.state_machine_arn,
                 description=f"Child State Machine ARN ({deployment_env})")
        
        CfnOutput(self, "ParentStateMachineArn", 
                 value=self.parent_state_machine.state_machine_arn,
                 description=f"Parent State Machine ARN ({deployment_env})")
    
    def replace_placeholders(self, definition, replacements):
        """
        Comprehensive replacement of hardcoded values in Step Functions definition JSON.
        This function handles all the hardcoded account IDs, regions, and ARNs.
        """
        definition_str = json.dumps(definition)
        
        # Define all hardcoded patterns and their replacements
        replacement_patterns = {
            # Account ID replacements
            "274614053408": replacements.get("account_id", self.account),
            
            # Region replacements  
            "us-west-2": replacements.get("region", self.region),
            
            # Lambda function ARN replacements
            f"arn:aws:lambda:{replacements.get('region', self.region)}:{replacements.get('account_id', self.account)}:function:BDAPDFPageChecker:$LATEST": 
                replacements.get("pdf_page_checker_arn", ""),
            f"arn:aws:lambda:{replacements.get('region', self.region)}:{replacements.get('account_id', self.account)}:function:BDAResultProcessor:$LATEST": 
                replacements.get("result_processor_arn", ""),
            f"arn:aws:lambda:{replacements.get('region', self.region)}:{replacements.get('account_id', self.account)}:function:BDAResultSummary:$LATEST": 
                replacements.get("result_summary_arn", ""),
            
            # State Machine ARN replacements - handle both old and new naming
            f"arn:aws:states:{replacements.get('region', self.region)}:{replacements.get('account_id', self.account)}:stateMachine:BDA-Demo":
                replacements.get("child_state_machine_arn", ""),
            f"arn:aws:states:{replacements.get('region', self.region)}:{replacements.get('account_id', self.account)}:stateMachine:BDAChildStateMachine":
                replacements.get("child_state_machine_arn", ""),
            
            # Data Automation Profile ARN
            f"arn:aws:bedrock:{replacements.get('region', self.region)}:{replacements.get('account_id', self.account)}:data-automation-profile/us.data-automation-v1":
                replacements.get("data_automation_profile_arn", ""),
            
            # DynamoDB table name replacements
            '"TableName": "BDAProcessingStatus"': 
                f'"TableName": "{replacements.get("processing_status_table_name", "BDAProcessingStatus")}"',
        }
        
        # Apply all replacements
        for pattern, replacement in replacement_patterns.items():
            if replacement:  # Only replace if we have a valid replacement
                definition_str = definition_str.replace(pattern, replacement)
        
        # Handle any remaining hardcoded references that might follow different patterns
        # Replace any remaining account ID patterns
        if replacements.get("account_id"):
            definition_str = definition_str.replace("274614053408", replacements["account_id"])
        
        # Replace any remaining region patterns
        if replacements.get("region"):
            definition_str = definition_str.replace("us-west-2", replacements["region"])
        
        # Validate that the JSON is still valid after replacements
        try:
            parsed = json.loads(definition_str)
            return parsed
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON after replacements: {e}")
            print(f"Problematic JSON section: {definition_str[max(0, e.pos-50):e.pos+50]}")
            raise