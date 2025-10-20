"""Health check endpoint for monitoring service dependencies.

Performs active health checks on all critical dependencies and returns
detailed status with response times for monitoring and alerting.
"""

import json
import os
import time
import boto3
import urllib.request
import urllib.error
from datetime import datetime, timezone

from .monitoring import verify_ses_sender
from .logger import set_lambda_context, log_info, log_warning, log_error


def check_ses_sender(sender_email):
    """Check if SES sender email is verified.
    
    Args:
        sender_email: Email address to verify.
        
    Returns:
        tuple: (success: bool, response_time_ms: int, error: str or None)
    """
    start = time.time()
    try:
        is_verified = verify_ses_sender(sender_email)
        elapsed_ms = int((time.time() - start) * 1000)
        
        if is_verified:
            return True, elapsed_ms, None
        else:
            return False, elapsed_ms, "Sender email not verified"
            
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return False, elapsed_ms, str(e)


def check_pubmed_api():
    """Check if PubMed API is accessible.
    
    Returns:
        tuple: (success: bool, response_time_ms: int, error: str or None)
    """
    start = time.time()
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=test&retmode=json"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'IridiaDaily/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            elapsed_ms = int((time.time() - start) * 1000)
            
            if 'esearchresult' in data:
                return True, elapsed_ms, None
            else:
                return False, elapsed_ms, "Invalid response format"
                
    except urllib.error.URLError as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return False, elapsed_ms, f"URLError: {str(e)}"
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return False, elapsed_ms, str(e)


def check_bedrock_api():
    """Check if Bedrock API is accessible with minimal token invocation.
    
    Returns:
        tuple: (success: bool, response_time_ms: int, error: str or None)
    """
    start = time.time()
    
    try:
        bedrock = boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        
        model_id = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 10,
            "messages": [
                {
                    "role": "user",
                    "content": "Hi"
                }
            ]
        })
        
        response = bedrock.invoke_model(
            modelId=model_id,
            body=body
        )
        
        elapsed_ms = int((time.time() - start) * 1000)
        
        response_body = json.loads(response['body'].read())
        
        if 'content' in response_body:
            return True, elapsed_ms, None
        else:
            return False, elapsed_ms, "Invalid response format"
            
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return False, elapsed_ms, str(e)


def check_secrets_manager(secret_arn):
    """Check if Secrets Manager is accessible.
    
    Args:
        secret_arn: ARN of secret to retrieve.
        
    Returns:
        tuple: (success: bool, response_time_ms: int, error: str or None)
    """
    start = time.time()
    
    try:
        secrets = boto3.client('secretsmanager', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        
        response = secrets.get_secret_value(SecretId=secret_arn)
        elapsed_ms = int((time.time() - start) * 1000)
        
        if 'SecretString' in response:
            return True, elapsed_ms, None
        else:
            return False, elapsed_ms, "Secret not found"
            
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return False, elapsed_ms, str(e)


def lambda_handler(event, context):
    """Health check handler that tests all service dependencies.
    
    Performs active checks on SES sender verification, PubMed API,
    Bedrock API, and Secrets Manager. Returns 200 if all healthy,
    503 if any checks fail.
    
    Args:
        event: API Gateway event.
        context: Lambda context.
        
    Returns:
        dict: API Gateway response with health status and check details.
    """
    set_lambda_context(context)
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    sender_email = os.environ.get('SENDER_EMAIL')
    hmac_secret_arn = os.environ.get('HMAC_SECRET_ARN')
    
    if not sender_email or not hmac_secret_arn:
        log_error('health_check_config_error',
                  missing_sender=not sender_email,
                  missing_secret=not hmac_secret_arn)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'status': 'error',
                'timestamp': timestamp,
                'error': 'Missing required environment variables'
            })
        }
    
    log_info('health_check_started')
    
    checks = {}
    all_healthy = True
    
    log_info('checking_ses_sender')
    ses_ok, ses_time, ses_error = check_ses_sender(sender_email)
    checks['ses_sender'] = {
        'status': ses_ok,
        'response_time_ms': ses_time
    }
    if ses_error:
        checks['ses_sender']['error'] = ses_error
    if not ses_ok:
        all_healthy = False
        log_warning('ses_check_failed', error=ses_error, response_time_ms=ses_time)
    else:
        log_info('ses_check_passed', response_time_ms=ses_time)
    
    log_info('checking_pubmed_api')
    pubmed_ok, pubmed_time, pubmed_error = check_pubmed_api()
    checks['pubmed_api'] = {
        'status': pubmed_ok,
        'response_time_ms': pubmed_time
    }
    if pubmed_error:
        checks['pubmed_api']['error'] = pubmed_error
    if not pubmed_ok:
        all_healthy = False
        log_warning('pubmed_check_failed', error=pubmed_error, response_time_ms=pubmed_time)
    else:
        log_info('pubmed_check_passed', response_time_ms=pubmed_time)
    
    log_info('checking_bedrock_api')
    bedrock_ok, bedrock_time, bedrock_error = check_bedrock_api()
    checks['bedrock_api'] = {
        'status': bedrock_ok,
        'response_time_ms': bedrock_time
    }
    if bedrock_error:
        checks['bedrock_api']['error'] = bedrock_error
    if not bedrock_ok:
        all_healthy = False
        log_warning('bedrock_check_failed', error=bedrock_error, response_time_ms=bedrock_time)
    else:
        log_info('bedrock_check_passed', response_time_ms=bedrock_time)
    
    log_info('checking_secrets_manager')
    secrets_ok, secrets_time, secrets_error = check_secrets_manager(hmac_secret_arn)
    checks['secrets_manager'] = {
        'status': secrets_ok,
        'response_time_ms': secrets_time
    }
    if secrets_error:
        checks['secrets_manager']['error'] = secrets_error
    if not secrets_ok:
        all_healthy = False
        log_warning('secrets_check_failed', error=secrets_error, response_time_ms=secrets_time)
    else:
        log_info('secrets_check_passed', response_time_ms=secrets_time)
    
    status = 'healthy' if all_healthy else 'degraded'
    status_code = 200 if all_healthy else 503
    
    log_info('health_check_completed',
             status=status,
             ses_status=ses_ok,
             pubmed_status=pubmed_ok,
             bedrock_status=bedrock_ok,
             secrets_status=secrets_ok)
    
    response_body = {
        'status': status,
        'timestamp': timestamp,
        'checks': checks
    }
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Cache-Control': 'no-cache, no-store, must-revalidate'
        },
        'body': json.dumps(response_body, indent=2)
    }