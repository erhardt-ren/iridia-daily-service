"""Subscribe handler - adds contacts to SES Contact List."""

import json
import boto3
import os
import re
from datetime import datetime

ses_v2 = boto3.client('sesv2', region_name='us-east-1')

def lambda_handler(event, context):
    """Handle subscription requests."""
    
    # CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return cors_response(200, {'message': 'OK'})
    
    try:
        body = json.loads(event.get('body', '{}'))
        email = body.get('email', '').strip().lower()
        
        if not email or not is_valid_email(email):
            return cors_response(400, {'error': 'Invalid email address'})
        
        contact_list_name = os.environ.get('CONTACT_LIST_NAME')
        
        # Check if already exists
        try:
            existing = ses_v2.get_contact(
                ContactListName=contact_list_name,
                EmailAddress=email
            )
            
            # Check if already subscribed
            if existing.get('TopicPreferences', [{}])[0].get('SubscriptionStatus') == 'OPT_IN':
                return cors_response(200, {
                    'message': 'You are already subscribed!',
                    'email': email
                })
            
            # Re-subscribe if previously unsubscribed
            ses_v2.update_contact(
                ContactListName=contact_list_name,
                EmailAddress=email,
                TopicPreferences=[{
                    'TopicName': 'daily-research',
                    'SubscriptionStatus': 'OPT_IN'
                }]
            )
            
            return cors_response(200, {
                'message': 'Successfully resubscribed!',
                'email': email
            })
            
        except ses_v2.exceptions.NotFoundException:
            pass
        
        # Create new contact
        ses_v2.create_contact(
            ContactListName=contact_list_name,
            EmailAddress=email,
            TopicPreferences=[{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }],
            AttributesData=json.dumps({
                'subscribed_at': datetime.utcnow().isoformat(),
                'source': body.get('source', 'web')
            })
        )
        
        print(f"✓ New subscriber: {email}")
        
        # Optional: Send welcome email
        send_welcome_email(email)
        
        return cors_response(200, {
            'message': 'Successfully subscribed! You\'ll receive your first newsletter soon.',
            'email': email
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return cors_response(500, {'error': 'Internal server error'})


def send_welcome_email(email):
    """Send welcome email to new subscriber."""
    sender_email = os.environ.get('SENDER_EMAIL')
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: -apple-system, sans-serif; padding: 40px; background: #f8f9fa;">
        <div style="max-width: 500px; margin: 0 auto; background: white; border-radius: 16px; padding: 40px;">
            <h1 style="color: #0f2027; margin: 0 0 20px 0;">Welcome to Iridia Daily! 🎉</h1>
            <p style="color: #6c757d; line-height: 1.6;">
                Thanks for subscribing! You'll receive fascinating scientific insights from recently published research papers every day.
            </p>
            <p style="color: #6c757d; line-height: 1.6;">
                Your first newsletter will arrive soon.
            </p>
        </div>
    </body>
    </html>
    """
    
    try:
        ses_v2.send_email(
            FromEmailAddress=f"Iridia Daily <{sender_email}>",
            Destination={'ToAddresses': [email]},
            Content={
                'Simple': {
                    'Subject': {'Data': '🌊 Welcome to Iridia Daily!'},
                    'Body': {'Html': {'Data': html_body}}
                }
            }
        )
    except Exception as e:
        print(f"Error sending welcome email: {e}")


def is_valid_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def cors_response(status_code, body):
    """Return CORS-enabled response."""
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