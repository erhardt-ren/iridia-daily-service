"""Subscription request handler with double opt-in confirmation.

UPDATED: Uses SES TopicPreferences to store user topic selections.
"""

import json
import boto3
import os
import re
import base64
from datetime import datetime, timezone

from . import monitoring
from .token_utils import generate_confirmation_token  # ← ONLY THIS IMPORT
from .logger import set_lambda_context, log_info, log_warning, log_error
from .config import CATEGORY_MAPPING
from .utils import get_api_url_from_event

ses_v2 = boto3.client('sesv2', region_name='us-east-1')


def validate_topics(topics):
    """Validate topic preferences against configured categories."""
    if not isinstance(topics, list):
        return False, [], "Topics must be a list"
    
    valid_topics = {key for key in CATEGORY_MAPPING.keys() if key != 'default'}
    
    validated = []
    for topic in topics:
        if not isinstance(topic, str):
            return False, [], f"Invalid topic type: {type(topic).__name__}"
        
        topic_lower = topic.lower().strip()
        if topic_lower not in valid_topics:
            return False, [], f"Invalid topic: {topic}. Valid topics: {', '.join(sorted(valid_topics))}"
        
        validated.append(topic_lower)
    
    validated = list(dict.fromkeys(validated))
    
    if not validated:
        return False, [], "At least one topic must be selected"
    
    return True, validated, None


def lambda_handler(event, context):
    """Handle subscription requests with topic preferences stored in SES TopicPreferences."""
    set_lambda_context(context)
    
    if event.get('httpMethod') == 'OPTIONS':
        log_info('cors_preflight_request')
        return cors_response(200, {'message': 'OK'})

    try:
        body = json.loads(event.get('body', '{}'))
        email = body.get('email', '').strip().lower()
        topics = body.get('topics')
        source = body.get('source', 'api')

        log_info('subscription_request', 
                 email=email, 
                 source=source,
                 topics_provided=topics is not None,
                 topic_count=len(topics) if topics else 0)

        if not email or not is_valid_email(email):
            log_warning('invalid_email_format', email=email)
            monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
                {'Name': 'Status', 'Value': 'InvalidEmail'}
            ])
            return cors_response(400, {'error': 'Invalid email address'})

        if topics is not None:
            is_valid, validated_topics, error_msg = validate_topics(topics)
            if not is_valid:
                log_warning('invalid_topics', email=email, topics=topics, error=error_msg)
                monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
                    {'Name': 'Status', 'Value': 'InvalidTopics'}
                ])
                return cors_response(400, {'error': error_msg})
            topics = validated_topics
            log_info('topics_validated', email=email, topics=topics, count=len(topics))
        else:
            log_info('no_topics_specified', email=email, action='subscribing_to_all')

        contact_list_name = os.environ.get('CONTACT_LIST_NAME')

        # Check if already subscribed
        try:
            existing = ses_v2.get_contact(
                ContactListName=contact_list_name,
                EmailAddress=email
            )

            topic_prefs = existing.get('TopicPreferences', [])
            
            # Check if ANY topic is opted in
            is_subscribed = any(
                tp.get('SubscriptionStatus') == 'OPT_IN' 
                for tp in topic_prefs
            )

            if is_subscribed:
                log_info('already_subscribed', email=email)
                monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
                    {'Name': 'Status', 'Value': 'AlreadySubscribed'}
                ])
                return cors_response(200, {
                    'message': 'You are already subscribed! Check your email for daily research insights.'
                })

        except ses_v2.exceptions.NotFoundException:
            pass

        # Generate confirmation token
        token = generate_confirmation_token(email)
        api_url = get_api_url_from_event(event)
        
        # Encode topics in URL
        topics_param = ''
        if topics:
            topics_json = json.dumps(topics)
            topics_b64 = base64.urlsafe_b64encode(topics_json.encode()).decode()
            topics_param = f"&topics={topics_b64}"
        
        confirmation_url = f"{api_url}/confirm?token={token}{topics_param}"

        send_confirmation_email(email, confirmation_url)

        log_info('confirmation_email_sent', email=email, has_topics=topics is not None)
        monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'ConfirmationSent'}
        ])

        if topics:
            for topic in topics:
                monitoring.put_metric('TopicSelection', 1, dimensions=[
                    {'Name': 'Topic', 'Value': topic},
                    {'Name': 'Stage', 'Value': 'InitialRequest'}
                ])

        return cors_response(200, {
            'message': 'Please check your email to confirm your subscription!',
            'topics': topics if topics else 'all'
        })

    except Exception as e:
        log_error('subscription_error', error_type=type(e).__name__, error_message=str(e))
        monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Error'}
        ])
        return cors_response(500, {'error': 'Internal server error'})


def is_valid_email(email):
    """Validate email format using regex."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def send_confirmation_email(email, confirmation_url):
    """Send double opt-in confirmation email."""
    sender_email = os.environ.get('SENDER_EMAIL')

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
                   line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .container {{ background: #f8f9fa; padding: 30px; border-radius: 8px; }}
            .button {{ display: inline-block; padding: 12px 30px; background: #0f2027; 
                      color: white; text-decoration: none; border-radius: 5px; 
                      font-weight: 600; margin: 20px 0; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; 
                      font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Confirm Your Iridia Daily Subscription</h2>
            <p>Thank you for subscribing to Iridia Daily! We're excited to share cutting-edge research insights with you.</p>
            <p>To complete your subscription, please confirm your email address:</p>
            <p style="text-align: center;">
                <a href="{confirmation_url}" class="button">Confirm Subscription</a>
            </p>
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #666; font-size: 12px;">{confirmation_url}</p>
            <p>This link will expire in 24 hours.</p>
            <div class="footer">
                <p><strong>Iridia Daily</strong> - Research Intelligence Daily</p>
                <p>© 2025 Iridia Daily. Intelligence worth sharing.</p>
            </div>
        </div>
    </body>
    </html>
    """

    text_body = f"""
    CONFIRM YOUR IRIDIA DAILY SUBSCRIPTION

    Thank you for subscribing to Iridia Daily!

    To complete your subscription, please click this link:
    {confirmation_url}

    This link will expire in 24 hours.

    ---
    Iridia Daily - Research Intelligence Daily
    © 2025 Iridia Daily. Intelligence worth sharing.
    """

    ses_v2.send_email(
        FromEmailAddress=f"Iridia Daily <{sender_email}>",
        Destination={'ToAddresses': [email]},
        Content={
            'Simple': {
                'Subject': {'Data': 'Confirm Your Iridia Daily Subscription'},
                'Body': {
                    'Text': {'Data': text_body},
                    'Html': {'Data': html_body}
                }
            }
        }
    )


def cors_response(status_code, body):
    """Create API Gateway response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body)
    }