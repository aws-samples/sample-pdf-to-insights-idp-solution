#!/usr/bin/env python3
"""
CloudWatch Logs Handler for AgentCore Runtime
Sends logs directly to CloudWatch using boto3 with enhanced observability
"""

import boto3
import logging
import json
import time
import os
from datetime import datetime
from typing import Optional, Dict, Any
from collections import defaultdict
import threading

class CloudWatchLogHandler(logging.Handler):
    """Enhanced CloudWatch handler with structured logging and metrics"""
    
    def __init__(self, log_group: str, log_stream: str, region: str = None):
        super().__init__()
        self.log_group = log_group
        self.log_stream = log_stream
        self.region = region or os.environ.get('AWS_DEFAULT_REGION') or os.environ.get('AWS_REGION')
        if not self.region:
            raise ValueError("AWS region must be set")
        
        # Initialize CloudWatch clients
        self.logs_client = boto3.client('logs', region_name=region)
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=region)
        self.sequence_token = None
        
        # Metrics tracking
        self.metrics = defaultdict(int)
        self.metrics_lock = threading.Lock()
        self.last_metrics_push = time.time()
        
        # Ensure log group and stream exist
        self._ensure_log_group_exists()
        self._ensure_log_stream_exists()
        
        # Start metrics publishing thread
        self._start_metrics_publisher()
        
    def _ensure_log_group_exists(self):
        """Create log group if it doesn't exist with retention policy"""
        try:
            self.logs_client.create_log_group(logGroupName=self.log_group)
            # Set retention policy (default 30 days)
            retention_days = int(os.environ.get('CLOUDWATCH_LOG_RETENTION_DAYS', '30'))
            self.logs_client.put_retention_policy(
                logGroupName=self.log_group,
                retentionInDays=retention_days
            )
        except self.logs_client.exceptions.ResourceAlreadyExistsException:
            pass
        except Exception as e:
            print(f"Error creating log group: {e}")
    
    def _ensure_log_stream_exists(self):
        """Create log stream if it doesn't exist"""
        try:
            self.logs_client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=self.log_stream
            )
        except self.logs_client.exceptions.ResourceAlreadyExistsException:
            # Get the sequence token for existing stream
            self._get_sequence_token()
        except Exception as e:
            print(f"Error creating log stream: {e}")
    
    def _get_sequence_token(self):
        """Get the sequence token for the log stream"""
        try:
            response = self.logs_client.describe_log_streams(
                logGroupName=self.log_group,
                logStreamNamePrefix=self.log_stream,
                limit=1
            )
            if response['logStreams']:
                self.sequence_token = response['logStreams'][0].get('uploadSequenceToken')
        except Exception as e:
            print(f"Error getting sequence token: {e}")
    
    def emit(self, record):
        """Send enhanced log record to CloudWatch with structured data"""
        try:
            # Track metrics
            with self.metrics_lock:
                self.metrics['log_count'] += 1
                self.metrics[f'log_level_{record.levelname}'] += 1
            
            # Extract structured data from record
            structured_data = {
                'timestamp': datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
                'level': record.levelname,
                'logger': record.name,
                'message': self.format(record),
                'agent_type': os.environ.get('AGENT_TYPE', 'unknown'),
                'runtime_id': os.environ.get('RUNTIME_ID', 'unknown'),
                'session_id': getattr(record, 'session_id', None),
                'trace_id': getattr(record, 'trace_id', None),
                'span_id': getattr(record, 'span_id', None),
                'request_id': getattr(record, 'request_id', None),
                'correlation_id': getattr(record, 'correlation_id', None)
            }
            
            # Add performance metrics if available
            if hasattr(record, 'latency_ms'):
                structured_data['latency_ms'] = record.latency_ms
                with self.metrics_lock:
                    self.metrics['total_latency_ms'] += record.latency_ms
                    self.metrics['request_count'] += 1
            
            # Add token usage if available
            if hasattr(record, 'token_usage'):
                structured_data['token_usage'] = record.token_usage
                with self.metrics_lock:
                    self.metrics['total_tokens'] += record.token_usage
            
            # Add error details if this is an error log
            if record.levelname in ['ERROR', 'CRITICAL']:
                if hasattr(record, 'exc_info') and record.exc_info:
                    import traceback
                    structured_data['error_details'] = {
                        'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                        'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                        'traceback': traceback.format_exception(*record.exc_info) if record.exc_info else None
                    }
                with self.metrics_lock:
                    self.metrics['error_count'] += 1
            
            # Format the log entry
            log_entry = {
                'timestamp': int(record.created * 1000),  # CloudWatch expects milliseconds
                'message': json.dumps(structured_data)
            }
            
            # Send to CloudWatch
            kwargs = {
                'logGroupName': self.log_group,
                'logStreamName': self.log_stream,
                'logEvents': [log_entry]
            }
            
            if self.sequence_token:
                kwargs['sequenceToken'] = self.sequence_token
            
            response = self.logs_client.put_log_events(**kwargs)
            self.sequence_token = response.get('nextSequenceToken')
            
            # Publish metrics periodically
            if time.time() - self.last_metrics_push > 60:  # Every minute
                self._publish_metrics()
            
        except Exception as e:
            # Don't raise exceptions in logging handler
            print(f"CloudWatch logging error: {e}")

    def _start_metrics_publisher(self):
        """Start background thread to publish metrics to CloudWatch"""
        def publish_loop():
            while True:
                time.sleep(60)  # Publish every minute
                self._publish_metrics()
        
        thread = threading.Thread(target=publish_loop, daemon=True)
        thread.start()
    
    def _publish_metrics(self):
        """Publish accumulated metrics to CloudWatch"""
        try:
            with self.metrics_lock:
                if not self.metrics:
                    return
                
                # Prepare metric data
                metric_data = []
                agent_type = os.environ.get('AGENT_TYPE', 'unknown')
                namespace = 'AgentCore/Production'
                
                # Add each metric
                for metric_name, value in self.metrics.items():
                    if value > 0:
                        metric_data.append({
                            'MetricName': metric_name,
                            'Value': value,
                            'Unit': 'Count' if 'count' in metric_name.lower() else 'None',
                            'Timestamp': datetime.utcnow(),
                            'Dimensions': [
                                {'Name': 'AgentType', 'Value': agent_type},
                                {'Name': 'Environment', 'Value': os.environ.get('ENVIRONMENT', 'production')}
                            ]
                        })
                
                # Calculate and add average latency
                if self.metrics.get('request_count', 0) > 0:
                    avg_latency = self.metrics.get('total_latency_ms', 0) / self.metrics['request_count']
                    metric_data.append({
                        'MetricName': 'average_latency_ms',
                        'Value': avg_latency,
                        'Unit': 'Milliseconds',
                        'Timestamp': datetime.utcnow(),
                        'Dimensions': [
                            {'Name': 'AgentType', 'Value': agent_type},
                            {'Name': 'Environment', 'Value': os.environ.get('ENVIRONMENT', 'production')}
                        ]
                    })
                
                # Publish metrics in batches (CloudWatch limit is 20 per call)
                for i in range(0, len(metric_data), 20):
                    batch = metric_data[i:i+20]
                    self.cloudwatch_client.put_metric_data(
                        Namespace=namespace,
                        MetricData=batch
                    )
                
                # Reset metrics after publishing
                self.metrics.clear()
                self.last_metrics_push = time.time()
                
        except Exception as e:
            print(f"Error publishing metrics: {e}")

def setup_cloudwatch_logging(agent_type: str):
    """Setup CloudWatch logging for an agent"""
    
    # Get runtime ID from environment or generate one
    runtime_id = os.environ.get('RUNTIME_ID', f"{agent_type}-{int(time.time())}")
    
    # Create CloudWatch handler
    log_group = f"/aws/bedrock-agentcore/custom/{agent_type}"
    log_stream = f"{runtime_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    cw_handler = CloudWatchLogHandler(
        log_group=log_group,
        log_stream=log_stream,
        region=os.environ.get('AWS_DEFAULT_REGION') or os.environ.get('AWS_REGION')
    )
    
    # Set formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    cw_handler.setFormatter(formatter)
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(cw_handler)
    
    # Also keep console output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    root_logger.setLevel(logging.INFO)
    
    return cw_handler