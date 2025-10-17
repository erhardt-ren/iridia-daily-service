"""Newsletter generation and distribution handler.

This module coordinates fetching research papers, generating summaries,
and distributing the newsletter to subscribers.
"""

import json
import boto3
import os
from datetime import datetime

from .clients import PubMedClient, BedrockClient
from .email_generator import EmailGenerator

ses = boto3.client('ses', region_name='us-east-1')
ses_v2 = boto3.client('sesv2', region_name='us-east-1')


def lambda_handler(event, context):
    """Generate and send the daily newsletter.
    
    Args:
        event: Lambda event object
        context: Lambda context object
        
    Returns:
        dict: Response with status code and body
    """
    print("Starting newsletter generation")
    
    contact_list_name = os.environ.get('CONTACT_LIST_NAME')
    sender_email = os.environ.get('SENDER_EMAIL')
    api_url = os.environ.get('API_URL', '')
    
    if not contact_list_name or not sender_email:
        print("ERROR: Missing required environment variables")
        return {'statusCode': 500, 'body': 'Configuration error'}
    
    # Get subscribers
    print("Fetching subscribers...")
    subscribers = get_subscribers(contact_list_name)
    
    if not subscribers:
        print("No active subscribers found")
        return {'statusCode': 200, 'body': 'No subscribers'}
    
    print(f"Found {len(subscribers)} subscribers")
    
    # Fetch papers
    print("Fetching research papers...")
    pubmed = PubMedClient()
    papers = pubmed.get_recent_papers(num_papers=5)
    
    if not papers:
        print("No papers found")
        return {'statusCode': 500, 'body': 'No papers found'}
    
    print(f"Retrieved {len(papers)} papers")
    
    # Generate summaries
    print("Generating summaries...")
    bedrock = BedrockClient()
    summaries = bedrock.generate_summaries(papers)
    
    while len(summaries) < len(papers):
        summaries.append("Breakthrough research published.")
    
    # Send newsletter
    print(f"Sending newsletter to {len(subscribers)} subscribers...")
    email_gen = EmailGenerator()
    
    try:
        date_str = datetime.now().strftime("%A, %B %d, %Y")
        subject = email_gen.generate_subject_line()
        
        html_content = email_gen.generate_html_email(
            papers, summaries, date_str, api_url
        )
        plain_text = email_gen.generate_plain_text_email(
            papers, summaries, date_str, api_url
        )
        
        result = send_newsletter(
            subscribers=subscribers,
            sender_email=sender_email,
            subject=subject,
            html_content=html_content,
            plain_text=plain_text
        )
        
        print(f"Newsletter sent to {result['delivered']} subscribers")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Newsletter sent successfully',
                'subscribers': result['delivered'],
                'papers': len(papers)
            })
        }
        
    except Exception as e:
        print(f"Error sending newsletter: {e}")
        return {'statusCode': 500, 'body': json.dumps(f'Error: {str(e)}')}


def get_subscribers(contact_list_name):
    """Retrieve active subscribers from contact list.
    
    Args:
        contact_list_name: Name of the SES contact list
        
    Returns:
        list: Email addresses of active subscribers
    """
    subscribers = []
    paginator = ses_v2.get_paginator('list_contacts')
    
    try:
        for page in paginator.paginate(ContactListName=contact_list_name):
            for contact in page.get('Contacts', []):
                topic_prefs = contact.get('TopicPreferences', [{}])[0]
                if topic_prefs.get('SubscriptionStatus') == 'OPT_IN':
                    subscribers.append(contact['EmailAddress'])
        
        return subscribers
        
    except Exception as e:
        print(f"Error retrieving subscribers: {e}")
        return []


def send_newsletter(subscribers, sender_email, subject, html_content, plain_text):
    """Send newsletter to all subscribers.
    
    Distributes newsletter efficiently by batching recipients.
    
    Args:
        subscribers: List of subscriber email addresses
        sender_email: Verified sender email address
        subject: Email subject line
        html_content: HTML email body
        plain_text: Plain text email body
        
    Returns:
        dict: Delivery statistics including delivered and failed counts
    """
    batch_size = 50
    delivered = 0
    failed = 0
    
    recipient_display = os.environ.get(
        'RECIPIENT_DISPLAY', 
        f"Iridia Daily Readers <{sender_email}>"
    )
    
    for i in range(0, len(subscribers), batch_size):
        batch = subscribers[i:i + batch_size]
        
        try:
            ses.send_email(
                Source=f"Iridia Daily <{sender_email}>",
                Destination={
                    'ToAddresses': [recipient_display],
                    'BccAddresses': batch
                },
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {
                        'Text': {'Data': plain_text, 'Charset': 'UTF-8'},
                        'Html': {'Data': html_content, 'Charset': 'UTF-8'}
                    }
                }
            )
            
            delivered += len(batch)
            
        except Exception as e:
            failed += len(batch)
            print(f"Failed to send to batch: {e}")
    
    if failed > 0:
        print(f"Warning: Failed to deliver to {failed} subscribers")
    
    return {
        'delivered': delivered,
        'failed': failed
    }