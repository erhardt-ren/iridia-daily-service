"""Unsubscribe request handler.

Processes unsubscribe requests and updates subscriber status.
"""

import json
import boto3
import os

ses_v2 = boto3.client('sesv2', region_name='us-east-1')


def lambda_handler(event, context):
    """Process unsubscribe request.
    
    Args:
        event: API Gateway event containing unsubscribe request
        context: Lambda context object
        
    Returns:
        dict: HTML response confirming unsubscribe status
    """
    params = event.get('queryStringParameters', {}) or {}
    email = params.get('email', '').strip().lower()
    
    if not email:
        return render_html(400, 'Invalid Request', 
            '<h1>Invalid Unsubscribe Link</h1>'
            '<p>Please provide an email address.</p>'
        )
    
    contact_list_name = os.environ.get('CONTACT_LIST_NAME')
    
    try:
        # Verify subscription exists
        try:
            contact = ses_v2.get_contact(
                ContactListName=contact_list_name,
                EmailAddress=email
            )
            
            topic_prefs = contact.get('TopicPreferences', [{}])[0]
            if topic_prefs.get('SubscriptionStatus') == 'OPT_OUT':
                return render_html(200, 'Already Unsubscribed', 
                    f'<h1>Already Unsubscribed</h1>'
                    f'<p><strong>{email}</strong> is not subscribed to Iridia Daily.</p>'
                )
            
        except ses_v2.exceptions.NotFoundException:
            return render_html(404, 'Not Found',
                '<h1>Subscription Not Found</h1>'
                '<p>We couldn\'t find a subscription for this email.</p>'
            )
        
        # Update subscription status
        ses_v2.update_contact(
            ContactListName=contact_list_name,
            EmailAddress=email,
            TopicPreferences=[{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_OUT'
            }]
        )
        
        print(f"Unsubscribed: {email}")
        
        return render_html(200, 'Unsubscribed',
            f'<h1>You\'ve Been Unsubscribed</h1>'
            f'<p>We\'ve removed <strong>{email}</strong> from Iridia Daily.</p>'
            f'<p>You won\'t receive any more emails from us.</p>'
            '<div style="margin-top: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px;">'
            '<p style="margin: 0; color: #6c757d; font-size: 14px;">'
            'Changed your mind? Resubscribe at iridia-daily.com'
            '</p></div>'
        )
        
    except Exception as e:
        print(f"Unsubscribe error: {e}")
        return render_html(500, 'Error',
            '<h1>Something Went Wrong</h1>'
            '<p>Please try again later.</p>'
        )


def render_html(status_code, title, content):
    """Render HTML response page.
    
    Args:
        status_code: HTTP status code
        title: Page title
        content: HTML content to display
        
    Returns:
        dict: API Gateway response with HTML body
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
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
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