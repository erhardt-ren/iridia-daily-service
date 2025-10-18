"""Subscription request handler with monitoring."""

import json
import boto3
import os
import re
from datetime import datetime, timezone

from . import monitoring

ses_v2 = boto3.client('sesv2', region_name='us-east-1')


def lambda_handler(event, context):
    """Handle subscription requests.

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

        try:
            existing = ses_v2.get_contact(
                ContactListName=contact_list_name,
                EmailAddress=email
            )

            if existing.get('TopicPreferences', [{}])[0].get(
                'SubscriptionStatus'
            ) == 'OPT_IN':
                monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
                    {'Name': 'Status', 'Value': 'AlreadySubscribed'}
                ])
                return cors_response(200, {
                    'message': 'You are already subscribed!',
                    'email': email
                })

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

            print(f"Resubscribed: {email}")
            monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
                {'Name': 'Status', 'Value': 'Resubscribed'}
            ])

            return cors_response(200, {
                'message': 'Successfully resubscribed!',
                'email': email
            })

        except ses_v2.exceptions.NotFoundException:
            pass

        try:
            def create_contact():
                return ses_v2.create_contact(
                    ContactListName=contact_list_name,
                    EmailAddress=email,
                    TopicPreferences=[{
                        'TopicName': 'daily-research',
                        'SubscriptionStatus': 'OPT_IN'
                    }],
                    AttributesData=json.dumps({
                        'subscribed_at': datetime.now(timezone.utc).isoformat(),
                        'source': body.get('source', 'web')
                    })
                )

            monitoring.retry_with_backoff(create_contact, max_attempts=3)

            print(f"New subscriber: {email}")
            monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
                {'Name': 'Status', 'Value': 'Success'}
            ])

            send_welcome_email(email)

            return cors_response(200, {
                'message': 'Successfully subscribed! Check your email.',
                'email': email
            })

        except ses_v2.exceptions.AlreadyExistsException:
            print(f"Race condition handled: {email}")
            monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
                {'Name': 'Status', 'Value': 'RaceCondition'}
            ])
            return cors_response(200, {
                'message': 'Successfully subscribed!',
                'email': email
            })

    except Exception as e:
        print(f"Subscription error: {e}")
        monitoring.put_metric('SubscriptionAttempt', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Error'}
        ])
        return cors_response(500, {'error': 'Internal server error'})


def send_welcome_email(email):
    """Send welcome email to new subscriber.

    Args:
        email: Subscriber email address.
    """
    sender_email = os.environ.get('SENDER_EMAIL')

    html_body = f"""
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
                Thanks for subscribing! You'll receive fascinating scientific
                insights from recently published research papers every day.
            </p>
            <p style="color: #6c757d; line-height: 1.6;">
                Your first newsletter will arrive soon.
            </p>
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

    except Exception as e:
        print(f"Welcome email error: {e}")
        monitoring.put_metric('WelcomeEmailFailed', 1)


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