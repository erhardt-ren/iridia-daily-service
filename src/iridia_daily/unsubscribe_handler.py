"""Unsubscribe request handler with secure token verification.

UPDATED: Works with new TopicPreferences structure. Sets all content topics to OPT_OUT.
"""

import json
import boto3
import os

from . import monitoring
from .token_utils import verify_unsubscribe_token
from .logger import set_lambda_context, log_info, log_warning, log_error
from .templates import template_loader
from .config import CATEGORY_MAPPING

ses_v2 = boto3.client('sesv2', region_name='us-east-1')


def lambda_handler(event, context):
    """Process unsubscribe request with token verification.

    Args:
        event: API Gateway event.
        context: Lambda context.

    Returns:
        dict: HTML response with status.
    """
    set_lambda_context(context)
    
    params = event.get('queryStringParameters', {}) or {}
    token = params.get('token', '').strip()

    log_info('unsubscribe_request', has_token=bool(token))

    if not token:
        log_warning('unsubscribe_missing_token')
        monitoring.put_metric('UnsubscribeAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'InvalidRequest'}
        ])
        return render_html(400, 'Invalid Request',
                           '<h1>Invalid Unsubscribe Link</h1>'
                           '<p>This unsubscribe link is not valid. '
                           'Please use the link from your newsletter email.</p>')

    # Verify token and extract email
    email = verify_unsubscribe_token(token)

    if not email:
        log_warning('unsubscribe_invalid_token', token_length=len(token))
        monitoring.put_metric('UnsubscribeAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'InvalidToken'}
        ])
        return render_html(400, 'Invalid Link',
                           '<h1>Invalid Unsubscribe Link</h1>'
                           '<p>This unsubscribe link is invalid or has been '
                           'tampered with.</p>'
                           '<p>Please use the unsubscribe link from your most '
                           'recent newsletter email.</p>')

    log_info('unsubscribe_token_verified', email=email)
    
    contact_list_name = os.environ.get('CONTACT_LIST_NAME')

    try:
        try:
            def get_contact():
                return ses_v2.get_contact(
                    ContactListName=contact_list_name,
                    EmailAddress=email
                )

            contact = monitoring.retry_with_backoff(get_contact, max_attempts=3)

            # Check if already unsubscribed (all topics are OPT_OUT)
            topic_prefs = contact.get('TopicPreferences', [])
            
            # Check if ANY topic is still OPT_IN
            is_subscribed = any(
                tp.get('SubscriptionStatus') == 'OPT_IN' 
                for tp in topic_prefs
            )

            if not is_subscribed:
                log_info('already_unsubscribed', email=email)
                monitoring.put_metric('UnsubscribeAttempt', 1, dimensions=[
                    {'Name': 'Status', 'Value': 'AlreadyUnsubscribed'}
                ])
                return render_html(200, 'Already Unsubscribed',
                                   '<h1>Already Unsubscribed</h1>'
                                   f'<p><strong>{email}</strong> is not '
                                   'subscribed to Iridia Daily.</p>')

            # Build TopicPreferences with all topics set to OPT_OUT
            all_topics = [key for key in CATEGORY_MAPPING.keys() if key != 'default']
            all_topics.append('daily-research')  # Include main topic
            
            topic_preferences = []
            for topic in all_topics:
                topic_preferences.append({
                    'TopicName': topic,
                    'SubscriptionStatus': 'OPT_OUT'
                })

            def update_contact():
                return ses_v2.update_contact(
                    ContactListName=contact_list_name,
                    EmailAddress=email,
                    TopicPreferences=topic_preferences
                )

            monitoring.retry_with_backoff(update_contact, max_attempts=3)

            log_info('unsubscribe_success', email=email)
            monitoring.put_metric('UnsubscribeAttempt', 1, dimensions=[
                {'Name': 'Status', 'Value': 'Success'}
            ])

            return render_html(200, 'Unsubscribed',
                               '<h1>You\'ve Been Unsubscribed</h1>'
                               f'<p>We\'ve removed <strong>{email}</strong> '
                               'from Iridia Daily.</p>'
                               '<p>You won\'t receive any more emails from us.</p>'
                               '<div style="margin-top: 30px; padding: 20px; '
                               'background: #f8f9fa; border-radius: 8px;">'
                               '<p style="margin: 0; color: #6c757d; '
                               'font-size: 14px;">'
                               'Changed your mind? You can resubscribe at '
                               'iridia-daily.com'
                               '</p></div>')

        except ses_v2.exceptions.NotFoundException:
            log_warning('unsubscribe_not_found', email=email)
            monitoring.put_metric('UnsubscribeAttempt', 1, dimensions=[
                {'Name': 'Status', 'Value': 'NotFound'}
            ])
            return render_html(404, 'Not Found',
                               '<h1>Subscription Not Found</h1>'
                               '<p>We couldn\'t find a subscription for '
                               'this email address.</p>')

    except Exception as e:
        log_error('unsubscribe_error',
                  email=email,
                  error_type=type(e).__name__,
                  error_message=str(e))
        monitoring.put_metric('UnsubscribeAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Error'}
        ])
        return render_html(500, 'Error',
                           '<h1>Something Went Wrong</h1>'
                           '<p>We couldn\'t complete your unsubscribe request. '
                           'Please try again later.</p>')


def render_html(status_code, title, content):
    """Render HTML response page using template.
    
    Args:
        status_code: HTTP status code.
        title: Page title.
        content: HTML content to display.
        
    Returns:
        dict: API Gateway response with HTML body.
    """
    
    html = template_loader.render_base_template(title, content)
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'text/html',
            'Cache-Control': 'no-cache'
        },
        'body': html
    }