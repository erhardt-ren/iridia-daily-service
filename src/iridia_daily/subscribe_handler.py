"""Subscription request handler with double opt-in confirmation.

Handles subscription requests by sending confirmation emails with
secure tokens instead of immediately adding contacts to the list.
"""

import json
import boto3
import os
import re

from . import monitoring
from .token_utils import generate_confirmation_token

ses_v2 = boto3.client('sesv2', region_name='us-east-1')


def get_api_url(event):
    """Get API Gateway URL from environment or extract from event.
    
    Args:
        event: API Gateway Lambda proxy event.
        
    Returns:
        str: Base API URL.
    """
    # First try environment variable
    api_url = os.environ.get('API_URL', '')
    
    # If it's the placeholder or empty, extract from event
    if not api_url or api_url == 'PLACEHOLDER':
        request_context = event.get('requestContext', {})
        domain_name = request_context.get('domainName', '')
        stage = request_context.get('stage', 'Prod')
        
        if domain_name:
            return f"https://{domain_name}/{stage}"
        
        # Construct from region and API ID
        region = os.environ.get('AWS_REGION', 'us-east-1')
        api_id = request_context.get('apiId', '')
        if api_id:
            return f"https://{api_id}.execute-api.{region}.amazonaws.com/{stage}"
    
    return api_url


def lambda_handler(event, context):
    """Handle subscription requests with double opt-in.

    Args:
        event: API Gateway event.
        context: Lambda context.

    Returns:
        dict: API Gateway response with CORS headers.
    """
    if event.get('httpMethod') == 'OPTIONS':
        return cors_response(200, {'message': 'OK'})

    try:
        body = json.loads(event.get('body', '{}'))
        email = body.get('email', '').strip().lower()

        if not email or not is_valid_email(email):
            monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
                {'Name': 'Status', 'Value': 'InvalidEmail'}
            ])
            return cors_response(400, {'error': 'Invalid email address'})

        contact_list_name = os.environ.get('CONTACT_LIST_NAME')

        # Check if already subscribed
        try:
            existing = ses_v2.get_contact(
                ContactListName=contact_list_name,
                EmailAddress=email
            )

            topic_prefs = existing.get('TopicPreferences', [{}])[0]

            if topic_prefs.get('SubscriptionStatus') == 'OPT_IN':
                monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
                    {'Name': 'Status', 'Value': 'AlreadySubscribed'}
                ])
                return cors_response(200, {
                    'message': 'You are already subscribed!',
                    'email': email
                })

        except ses_v2.exceptions.NotFoundException:
            pass

        # Generate confirmation token and send email
        api_url = get_api_url(event)
        token = generate_confirmation_token(email, expiry_hours=24)
        confirm_url = f"{api_url}/confirm?token={token}"

        send_confirmation_email(email, confirm_url)

        monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'ConfirmationSent'}
        ])

        return cors_response(200, {
            'message': 'Please check your email to confirm your subscription',
            'email': email
        })

    except Exception as e:
        print(f"Subscription error: {e}")
        monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Error'}
        ])
        return cors_response(500, {'error': 'Internal server error'})


def send_confirmation_email(email, confirm_url):
    """Send double opt-in confirmation email.

    Args:
        email: Email address to send confirmation to.
        confirm_url: Full URL for confirmation link.
    """
    sender_email = os.environ.get('SENDER_EMAIL')

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
                 sans-serif; padding: 40px; background: #f8f9fa;">
        <div style="max-width: 500px; margin: 0 auto; background: white;
                    border-radius: 16px; padding: 40px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #0f2027; font-size: 28px; font-weight: 700;
                           letter-spacing: 2px; margin: 0;">
                    IRIDIA DAILY
                </h1>
                <p style="color: #6c757d; font-size: 14px; margin: 8px 0 0 0;
                          letter-spacing: 0.5px;">
                    Research Intelligence Daily
                </p>
            </div>

            <h2 style="color: #1a1a1a; margin: 0 0 20px 0; font-size: 24px;">
                Confirm Your Subscription
            </h2>

            <p style="color: #6c757d; line-height: 1.6; margin: 0 0 20px 0;">
                Thanks for your interest in Iridia Daily! Click the button below
                to confirm your subscription and start receiving fascinating
                scientific insights from recently published research papers.
            </p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{confirm_url}"
                   style="display: inline-block; padding: 14px 32px;
                          background: linear-gradient(135deg, #0f2027 0%, #2c5364 100%);
                          color: white; text-decoration: none; border-radius: 8px;
                          font-weight: 600; font-size: 16px;">
                    Confirm Subscription
                </a>
            </div>

            <div style="margin-top: 30px; padding: 20px; background: #f8f9fa;
                        border-radius: 8px; border-left: 4px solid #0f2027;">
                <p style="margin: 0; color: #6c757d; font-size: 14px;
                          line-height: 1.5;">
                    <strong style="color: #1a1a1a;">What to expect:</strong><br>
                    • Daily emails with 5 breakthrough research findings<br>
                    • Direct links to original research papers<br>
                    • Smart, accessible science communication
                </p>
            </div>

            <p style="color: #adb5bd; font-size: 12px; margin-top: 30px;
                      text-align: center; line-height: 1.5;">
                This confirmation link expires in 24 hours.<br>
                If you didn't request this, please ignore this email.
            </p>
        </div>
    </body>
    </html>
    """

    plain_text = f"""
IRIDIA DAILY - Confirm Your Subscription

Thanks for your interest in Iridia Daily!

Please confirm your subscription by visiting this link:
{confirm_url}

What to expect:
• Daily emails with 5 breakthrough research findings
• Direct links to original research papers
• Smart, accessible science communication

This confirmation link expires in 24 hours.
If you didn't request this, please ignore this email.

---
Iridia Daily - Research Intelligence Daily
    """

    try:
        def send_email():
            return ses_v2.send_email(
                FromEmailAddress=f"Iridia Daily <{sender_email}>",
                Destination={'ToAddresses': [email]},
                Content={
                    'Simple': {
                        'Subject': {
                            'Data': '🌊 Confirm Your Iridia Daily Subscription'
                        },
                        'Body': {
                            'Html': {'Data': html_body},
                            'Text': {'Data': plain_text}
                        }
                    }
                }
            )

        monitoring.retry_with_backoff(send_email, max_attempts=2)
        monitoring.put_metric('ConfirmationEmailSent', 1)

        print(f"Confirmation email sent to {email}")

    except Exception as e:
        print(f"Confirmation email error: {e}")
        monitoring.put_metric('ConfirmationEmailFailed', 1)
        raise


def is_valid_email(email):
    """Validate email format according to RFC 5321.

    Args:
        email: Email address to validate.

    Returns:
        bool: True if valid, False otherwise.
    """
    if not email or not isinstance(email, str):
        return False

    pattern = (r'^[a-zA-Z0-9][a-zA-Z0-9._%+-]*[a-zA-Z0-9]@'
               r'[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}$')

    if not re.match(pattern, email):
        return False

    if '..' in email or email.count('@') != 1:
        return False

    local, domain = email.split('@')

    if (len(local) > 64 or len(domain) > 255 or
            local[0] == '.' or local[-1] == '.' or
            domain[0] in '.--' or domain[-1] in '.--'):
        return False

    return True


def cors_response(status_code, body):
    """Return CORS-enabled API response.

    Args:
        status_code: HTTP status code.
        body: Response body dict.

    Returns:
        dict: API Gateway response.
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body)
    }