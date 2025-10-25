"""Utility functions."""

import os
import boto3
from .logger import log_warning, log_error
from .config import CATEGORY_MAPPING

def get_category_info(text):
    """Determine category color and label based on content."""
    text_lower = text.lower()
    for category, (color, label, keywords) in CATEGORY_MAPPING.items():
        if category != 'default' and any(word in text_lower for word in keywords):
            return color, label
    return CATEGORY_MAPPING['default'][:2]

def get_api_url_from_event(event):
    """Construct API URL from API Gateway event context.
    
    Use this when Lambda is invoked by API Gateway (most handlers).
    
    Args:
        event: API Gateway event with requestContext.
        
    Returns:
        str: Full API URL (e.g., https://abc123.execute-api.us-east-1.amazonaws.com/prod)
        
    Raises:
        ValueError: If event doesn't contain required API Gateway context.
    """
    request_context = event.get('requestContext', {})
    
    if not request_context:
        raise ValueError("Event does not contain requestContext (not invoked by API Gateway)")
    
    api_id = request_context.get('apiId')
    if not api_id:
        raise ValueError("requestContext missing apiId")
    
    region = os.environ.get('AWS_REGION', 'us-east-1')
    stage = os.environ.get('API_STAGE_NAME', 'prod')
    
    return f"https://{api_id}.execute-api.{region}.amazonaws.com/{stage}"


def get_api_url_from_api_id():
    """Construct API URL from API_ID environment variable.
    
    Use this when Lambda is NOT invoked by API Gateway (e.g., scheduled events).
    Requires API_ID to be set as an environment variable.
    
    Returns:
        str: Full API URL.
        
    Raises:
        ValueError: If API_ID environment variable is not set.
    """
    api_id = os.environ.get('API_ID', '').strip()
    
    if not api_id:
        raise ValueError(
            "API_ID environment variable is not set. "
            "Required for scheduled Lambda functions."
        )
    
    region = os.environ.get('AWS_REGION', 'us-east-1')
    stage = os.environ.get('API_STAGE_NAME', 'prod')
    
    return f"https://{api_id}.execute-api.{region}.amazonaws.com/{stage}"


def get_api_id_by_name(api_name='IridiaDailyApi'):
    """Query API Gateway to find API ID by name.
    
    Fallback method when API_ID is not available in environment.
    This adds latency (~50-100ms) so prefer environment variables.
    
    Args:
        api_name: Name of the API Gateway to find.
        
    Returns:
        str or None: API ID if found, None otherwise.
    """
    try:
        region = os.environ.get('AWS_REGION', 'us-east-1')
        client = boto3.client('apigateway', region_name=region)
        
        # List APIs and find by name
        paginator = client.get_paginator('get_rest_apis')
        for page in paginator.paginate():
            for api in page.get('items', []):
                if api.get('name') == api_name:
                    return api.get('id')
        
        log_warning('api_not_found_by_name', api_name=api_name)
        return None
        
    except Exception as e:
        log_error('api_lookup_failed',
                 api_name=api_name,
                 error_type=type(e).__name__,
                 error_message=str(e))
        return None


def get_api_url_with_fallback(event=None):
    """Get API URL with multiple fallback strategies.
    
    Tries in order:
    1. From event context (if provided)
    2. From API_ID environment variable
    3. By querying API Gateway by name (slowest)
    
    Args:
        event: Optional API Gateway event.
        
    Returns:
        str: API URL.
        
    Raises:
        ValueError: If URL cannot be constructed with any method.
    """
    # Try event context first
    if event and 'requestContext' in event:
        try:
            return get_api_url_from_event(event)
        except ValueError:
            pass
    
    # Try API_ID environment variable
    try:
        return get_api_url_from_api_id()
    except ValueError:
        pass
    
    # Last resort: query API Gateway
    api_id = get_api_id_by_name()
    if api_id:
        region = os.environ.get('AWS_REGION', 'us-east-1')
        stage = os.environ.get('API_STAGE_NAME', 'prod')
        return f"https://{api_id}.execute-api.{region}.amazonaws.com/{stage}"
    
    raise ValueError(
        "Cannot construct API URL. Ensure either: "
        "(1) Lambda invoked by API Gateway, "
        "(2) API_ID environment variable set, or "
        "(3) API Gateway named 'IridiaDailyApi' exists"
    )