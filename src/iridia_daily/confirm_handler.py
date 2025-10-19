"""Email confirmation handler with token verification.

Handles email confirmation requests from double opt-in flow.
Creates contact in SES only after email verification.
"""

import json
import boto3
import os
from datetime import datetime, timezone

from . import monitoring
from .token_utils import verify_confirmation_token
from .logger import set_lambda_context, log_info, log_warning, log_error

ses_v2 = boto3.client('sesv2', region_name='us-east-1')


def lambda_handler(event, context):
    """Process email confirmation request.
    
    Verifies token from confirmation link and creates SES contact.
    
    Args:
        event: API Gateway event with token in query parameters.
        context: Lambda context.
        
    Returns:
        dict: HTML response with confirmation status.
    """
    set_lambda_context(context)
    
    params = event.get('queryStringParameters', {}) or {}
    token = params.get('token', '').strip()
    
    log_info('confirmation_request', has_token=bool(token))
    
    if not token:
        log_warning('confirmation_missing_token')
        monitoring.put_metric('ConfirmationAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'InvalidRequest'}
        ])
        return render_html(400, 'Invalid Link',
                          '<h1>Invalid Confirmation Link</h1>'
                          '<p>This confirmation link is not valid.</p>')
    
    # Verify token and extract email
    email = verify_confirmation_token(token)
    
    if not email:
        log_warning('confirmation_invalid_token', token_length=len(token))
        monitoring.put_metric('ConfirmationAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'InvalidToken'}
        ])
        return render_html(400, 'Invalid or Expired',
                          '<h1>Link Invalid or Expired</h1>'
                          '<p>This confirmation link is invalid or has expired.</p>'
                          '<p>Please subscribe again to receive a new '
                          'confirmation email.</p>')
    
    log_info('confirmation_token_verified', email=email)
    
    contact_list_name = os.environ.get('CONTACT_LIST_NAME')
    
    try:
        # Check if already confirmed
        try:
            existing = ses_v2.get_contact(
                ContactListName=contact_list_name,
                EmailAddress=email
            )
            
            topic_prefs = existing.get('TopicPreferences', [{}])[0]
            
            if topic_prefs.get('SubscriptionStatus') == 'OPT_IN':
                log_info('already_confirmed', email=email)
                monitoring.put_metric('ConfirmationAttempt', 1, dimensions=[
                    {'Name': 'Status', 'Value': 'AlreadyConfirmed'}
                ])
                return render_html(200, 'Already Subscribed',
                                  '<h1>Already Subscribed! ✓</h1>'
                                  f'<p><strong>{email}</strong> is already '
                                  'subscribed to Iridia Daily.</p>'
                                  '<p>Your next newsletter will arrive soon.</p>')
            
            # Reactivate if previously unsubscribed
            def update_contact():
                return ses_v2.update_contact(
                    ContactListName=contact_list_name,
                    EmailAddress=email,
                    TopicPreferences=[{
                        'TopicName': 'daily-research',
                        'SubscriptionStatus': 'OPT_IN'
                    }]
                )
            
            monitoring.retry_with_backoff(update_contact, max_attempts=3)
            
            log_info('subscription_reactivated', email=email)
            monitoring.put_metric('ConfirmationAttempt', 1, dimensions=[
                {'Name': 'Status', 'Value': 'Reactivated'}
            ])
            
            return render_html(200, 'Subscription Confirmed',
                              '<h1>Subscription Confirmed! 🎉</h1>'
                              f'<p>Welcome back! <strong>{email}</strong> has been '
                              'reactivated.</p>'
                              '<p>You\'ll receive your daily research insights '
                              'starting tomorrow.</p>')
        
        except ses_v2.exceptions.NotFoundException:
            log_info('new_subscriber', email=email)
        
        # Create new contact
        def create_contact():
            return ses_v2.create_contact(
                ContactListName=contact_list_name,
                EmailAddress=email,
                TopicPreferences=[{
                    'TopicName': 'daily-research',
                    'SubscriptionStatus': 'OPT_IN'
                }],
                AttributesData=json.dumps({
                    'confirmed_at': datetime.now(timezone.utc).isoformat(),
                    'source': 'email_confirmation'
                })
            )
        
        monitoring.retry_with_backoff(create_contact, max_attempts=3)
        
        log_info('subscription_confirmed', email=email)
        monitoring.put_metric('ConfirmationAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Success'}
        ])
        monitoring.put_metric('NewSubscriber', 1)
        
        # Send welcome email
        send_welcome_email(email)
        
        return render_html(200, 'Subscription Confirmed',
                          '<h1>Subscription Confirmed! 🎉</h1>'
                          f'<p>Welcome to Iridia Daily, <strong>{email}</strong>!</p>'
                          '<p>You\'ll receive fascinating scientific insights '
                          'from recently published research papers every day.</p>'
                          '<div style="margin-top: 30px; padding: 20px; '
                          'background: #f8f9fa; border-radius: 8px;">'
                          '<p style="margin: 0; color: #6c757d; font-size: 14px;">'
                          '📬 Your first newsletter will arrive tomorrow morning.'
                          '</p></div>')
    
    except Exception as e:
        log_error('confirmation_error',
                  email=email,
                  error_type=type(e).__name__,
                  error_message=str(e))
        monitoring.put_metric('ConfirmationAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Error'}
        ])
        return render_html(500, 'Error',
                          '<h1>Something Went Wrong</h1>'
                          '<p>We couldn\'t complete your subscription. '
                          'Please try again later.</p>')


def send_welcome_email(email):
    """Send welcome email after successful confirmation.
    
    Args:
        email: Confirmed subscriber email address.
    """
    sender_email = os.environ.get('SENDER_EMAIL')
    
    html_body = """
    <!DOCTYPE html>
    <html>
    <body style="font-family: -apple-system, sans-serif; padding: 40px;
                 background: #f8f9fa;">
        <div style="max-width: 500px; margin: 0 auto; background: white;
                    border-radius: 16px; padding: 40px;">
            <h1 style="color: #0f2027; margin: 0 0 20px 0;">
                Welcome to Iridia Daily! 🎉
            </h1>
            <p style="color: #6c757d; line-height: 1.6;">
                Thanks for confirming your subscription! You'll receive 
                fascinating scientific insights from recently published 
                research papers every day.
            </p>
            <p style="color: #6c757d; line-height: 1.6;">
                Your first newsletter will arrive tomorrow morning.
            </p>
            <div style="margin-top: 30px; padding: 20px; background: #f8f9fa;
                        border-radius: 8px;">
                <p style="margin: 0; color: #6c757d; font-size: 14px;">
                    <strong>What to expect:</strong><br>
                    • Daily emails with 5 breakthrough research findings<br>
                    • Direct links to original research papers<br>
                    • Smart, accessible science communication
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    try:
        def send_email():
            return ses_v2.send_email(
                FromEmailAddress=f"Iridia Daily <{sender_email}>",
                Destination={'ToAddresses': [email]},
                Content={
                    'Simple': {
                        'Subject': {'Data': '🌊 Welcome to Iridia Daily!'},
                        'Body': {'Html': {'Data': html_body}}
                    }
                }
            )
        
        monitoring.retry_with_backoff(send_email, max_attempts=2)
        monitoring.put_metric('WelcomeEmailSent', 1)
        
        log_info('welcome_email_sent', email=email)
        
    except Exception as e:
        log_error('welcome_email_failed',
                  email=email,
                  error_type=type(e).__name__,
                  error_message=str(e))
        monitoring.put_metric('WelcomeEmailFailed', 1)


def render_html(status_code, title, content):
    """Render HTML response page.
    
    Args:
        status_code: HTTP status code.
        title: Page title.
        content: HTML content to display.
        
    Returns:
        dict: API Gateway response with HTML body.
    """
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - Iridia Daily</title>
        <style>
            body {{
                margin: 0;
                padding: 40px 20px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
                             Arial, sans-serif;
                background: linear-gradient(135deg, #0f2027 0%, #2c5364 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            .container {{
                max-width: 500px;
                background: white;
                border-radius: 16px;
                padding: 40px;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
            }}
            h1 {{
                margin: 0 0 20px 0;
                color: #1a1a1a;
                font-size: 28px;
            }}
            p {{
                margin: 0 0 15px 0;
                color: #6c757d;
                font-size: 16px;
                line-height: 1.6;
            }}
            .logo {{
                text-align: center;
                margin-bottom: 30px;
                color: #0f2027;
                font-size: 24px;
                font-weight: 700;
                letter-spacing: 2px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">IRIDIA DAILY</div>
            {content}
        </div>
    </body>
    </html>
    """
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'text/html',
            'Cache-Control': 'no-cache'
        },
        'body': html
    }