"""Confirmation handler that activates subscriptions.

UPDATED: Saves user topic preferences as SES TopicPreferences.
"""

import json
import boto3
import os
import base64
from datetime import datetime, timezone

from .token_utils import verify_confirmation_token
from .logger import set_lambda_context, log_info, log_warning, log_error
from .config import CATEGORY_MAPPING
from . import monitoring

ses_v2 = boto3.client('sesv2', region_name='us-east-1')


def build_topic_preferences(topics=None):
    """Build SES TopicPreferences from user's topic selections."""
    all_topics = [key for key in CATEGORY_MAPPING.keys() if key != 'default']
    
    # If no topics specified, opt into all
    if not topics:
        topics = all_topics
    
    # Build TopicPreferences
    topic_preferences = []
    for topic in all_topics:
        topic_preferences.append({
            'TopicName': topic,
            'SubscriptionStatus': 'OPT_IN' if topic in topics else 'OPT_OUT'
        })
    
    return topic_preferences


def lambda_handler(event, context):
    """Confirm subscription and save topic preferences."""
    set_lambda_context(context)
    
    try:
        params = event.get('queryStringParameters', {}) or {}
        token = params.get('token')
        topics_b64 = params.get('topics')
        
        if not token:
            log_warning('missing_confirmation_token')
            return error_response('Invalid confirmation link')
        
        # Decode email from token
        email = verify_confirmation_token(token)
        if not email:
            log_warning('invalid_confirmation_token')
            return error_response('Invalid or expired confirmation link')
        
        # Decode topics if provided
        topics = None
        if topics_b64:
            try:
                topics_json = base64.urlsafe_b64decode(topics_b64).decode()
                topics = json.loads(topics_json)
                log_info('topics_decoded', email=email, topics=topics)
            except Exception as e:
                log_warning('failed_to_decode_topics', email=email, error=str(e))
                # Continue without topics (will subscribe to all)
        
        contact_list_name = os.environ.get('CONTACT_LIST_NAME')
        
        # Build TopicPreferences
        topic_preferences = build_topic_preferences(topics)
        
        log_info('topic_preferences_built',
                email=email,
                selected_topics=topics,
                topic_preferences_count=len(topic_preferences))
        
        # Create or update contact with TopicPreferences
        try:
            ses_v2.create_contact(
                ContactListName=contact_list_name,
                EmailAddress=email,
                TopicPreferences=topic_preferences,
                AttributesData=json.dumps({
                    'confirmed_at': datetime.now(timezone.utc).isoformat(),
                    'source': 'email_confirmation',
                    'version': '1.0'
                })
            )
            log_info('contact_created', email=email)
        except ses_v2.exceptions.AlreadyExistsException:
            # Update existing contact
            ses_v2.update_contact(
                ContactListName=contact_list_name,
                EmailAddress=email,
                TopicPreferences=topic_preferences,
                AttributesData=json.dumps({
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                    'source': 'email_confirmation',
                    'version': '1.0'
                })
            )
            log_info('contact_updated', email=email)
        
        # Track metrics
        monitoring.put_metric('SubscriptionConfirmed', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Success'}
        ])
        
        if topics:
            for topic in topics:
                monitoring.put_metric('TopicSelection', 1, dimensions=[
                    {'Name': 'Topic', 'Value': topic},
                    {'Name': 'Stage', 'Value': 'Confirmed'}
                ])
        
        log_info('subscription_confirmed',
                email=email,
                topics=topics if topics else 'all',
                topic_count=len(topics) if topics else len(topic_preferences))
        
        return success_response()
        
    except Exception as e:
        log_error('confirmation_error', error_type=type(e).__name__, error=str(e))
        monitoring.put_metric('SubscriptionConfirmed', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Error'}
        ])
        return error_response('Failed to confirm subscription')


def success_response():
    """Return success HTML page."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Subscription Confirmed</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #0f2027 0%, #2c5364 100%);
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                max-width: 500px;
                text-align: center;
            }
            h1 { color: #2d3748; margin-bottom: 20px; }
            p { color: #4a5568; line-height: 1.6; }
            .checkmark {
                width: 80px;
                height: 80px;
                border-radius: 50%;
                background: #48bb78;
                margin: 0 auto 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 48px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="checkmark">✓</div>
            <h1>Subscription Confirmed!</h1>
            <p>Thank you for confirming your subscription to Iridia Daily.</p>
            <p>You'll receive your first newsletter with cutting-edge research insights soon.</p>
        </div>
    </body>
    </html>
    """
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html'},
        'body': html
    }


def error_response(message):
    """Return error HTML page."""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Error</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #0f2027 0%, #2c5364 100%);
            }}
            .container {{
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                max-width: 500px;
                text-align: center;
            }}
            h1 {{ color: #c53030; margin-bottom: 20px; }}
            p {{ color: #4a5568; line-height: 1.6; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Error</h1>
            <p>{message}</p>
        </div>
    </body>
    </html>
    """
    return {
        'statusCode': 400,
        'headers': {'Content-Type': 'text/html'},
        'body': html
    }