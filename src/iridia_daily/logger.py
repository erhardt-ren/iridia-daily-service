"""Structured JSON logging for AWS Lambda functions.

Provides structured logging capabilities with automatic context enrichment
for CloudWatch Insights queries. Supports log levels (INFO, WARNING, ERROR)
and arbitrary contextual data via kwargs.

Example:
    >>> from iridia_daily.logger import set_lambda_context, log_info
    >>> 
    >>> def lambda_handler(event, context):
    ...     set_lambda_context(context)
    ...     log_info('newsletter_started', papers=5, subscribers=100)
"""

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Global context storage for Lambda request ID
_lambda_context = None


def set_lambda_context(context):
    """Set Lambda context for including request ID in logs.
    
    Call this at the start of your Lambda handler to enrich all
    subsequent logs with the AWS request ID.
    
    Args:
        context: AWS Lambda context object.
    
    Example:
        >>> def lambda_handler(event, context):
        ...     set_lambda_context(context)
        ...     log_info('handler_started')
    """
    global _lambda_context
    _lambda_context = context


def log_event(event_type: str, level: str = 'INFO', **kwargs):
    """Log structured event as JSON to stdout.
    
    Creates a structured log entry with timestamp, level, event type,
    and any additional contextual data. Automatically includes Lambda
    request ID if context has been set.
    
    Args:
        event_type: Type of event (e.g., 'newsletter_generated',
            'subscription_confirmed', 'email_sent').
        level: Log level - must be 'INFO', 'WARNING', or 'ERROR'.
        **kwargs: Additional contextual data to include in log entry.
            Common examples: papers=5, subscribers=100, duration_ms=1234.
    
    Example:
        >>> log_event('newsletter_generated', 
        ...           level='INFO',
        ...           papers=5, 
        ...           subscribers=100,
        ...           duration_ms=1234)
    """
    log_entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'level': level,
        'event_type': event_type,
    }
    
    # Add Lambda request ID if available
    if _lambda_context and hasattr(_lambda_context, 'aws_request_id'):
        log_entry['request_id'] = _lambda_context.aws_request_id
    
    # Add all kwargs as additional fields
    log_entry.update(kwargs)
    
    # Print JSON to stdout (CloudWatch captures this)
    print(json.dumps(log_entry), file=sys.stdout, flush=True)


def log_info(event_type: str, **kwargs):
    """Log INFO level event.
    
    Convenience function for logging informational events.
    
    Args:
        event_type: Type of event.
        **kwargs: Additional contextual data.
    
    Example:
        >>> log_info('papers_fetched', count=5, source='pubmed')
    """
    log_event(event_type, level='INFO', **kwargs)


def log_warning(event_type: str, **kwargs):
    """Log WARNING level event.
    
    Convenience function for logging warnings that don't prevent
    execution but may indicate issues.
    
    Args:
        event_type: Type of event.
        **kwargs: Additional contextual data.
    
    Example:
        >>> log_warning('summary_short', summary_length=45, min_length=50)
    """
    log_event(event_type, level='WARNING', **kwargs)


def log_error(event_type: str, **kwargs):
    """Log ERROR level event.
    
    Convenience function for logging errors and exceptions.
    
    Args:
        event_type: Type of event.
        **kwargs: Additional contextual data.
    
    Example:
        >>> log_error('api_failure', 
        ...           service='ses',
        ...           error_message=str(e))
    """
    log_event(event_type, level='ERROR', **kwargs)


def log_metric(metric_name: str, value: float, unit: str = 'None', **kwargs):
    """Log metric data for analysis.
    
    Specialized logging function for metrics and measurements.
    
    Args:
        metric_name: Name of the metric.
        value: Metric value.
        unit: Unit of measurement (e.g., 'Seconds', 'Count', 'Milliseconds').
        **kwargs: Additional contextual data.
    
    Example:
        >>> log_metric('newsletter_duration', 
        ...            value=1.234,
        ...            unit='Seconds',
        ...            papers=5)
    """
    log_event('metric_recorded',
              level='INFO',
              metric_name=metric_name,
              metric_value=value,
              metric_unit=unit,
              **kwargs)