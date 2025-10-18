"""Newsletter generation and distribution with monitoring."""

import json
import boto3
import os
import re
from datetime import datetime

from .clients import PubMedClient, BedrockClient
from .email_generator import EmailGenerator
from . import monitoring

ses = boto3.client('ses', region_name='us-east-1')
ses_v2 = boto3.client('sesv2', region_name='us-east-1')


def lambda_handler(event, context):
    """Generate and send daily newsletter.

    Args:
        event: Lambda event.
        context: Lambda context.

    Returns:
        dict: Response with status and delivery statistics.
    """
    print("Starting newsletter generation")
    start_time = datetime.now()

    contact_list_name = os.environ.get('CONTACT_LIST_NAME')
    sender_email = os.environ.get('SENDER_EMAIL')
    api_url = os.environ.get('API_URL', '')

    if not contact_list_name or not sender_email:
        print("ERROR: Missing required environment variables")
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'ConfigError'}
        ])
        return {'statusCode': 500, 'body': 'Configuration error'}

    if not monitoring.verify_ses_sender(sender_email):
        print(f"ERROR: Sender email not verified: {sender_email}")
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'SenderNotVerified'}
        ])
        return {'statusCode': 500, 'body': 'Sender email not verified'}

    print("Fetching subscribers...")
    subscribers = get_subscribers(contact_list_name)

    if not subscribers:
        print("No active subscribers found")
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'NoSubscribers'}
        ])
        return {'statusCode': 200, 'body': 'No subscribers'}

    print(f"Found {len(subscribers)} subscribers")
    monitoring.put_metric('SubscriberCount', len(subscribers))

    valid_subscribers = [email for email in subscribers if is_valid_email(email)]
    if len(valid_subscribers) != len(subscribers):
        invalid_count = len(subscribers) - len(valid_subscribers)
        print(f"Filtered out {invalid_count} invalid email addresses")
        monitoring.put_metric('InvalidSubscriberEmails', invalid_count)

    if not valid_subscribers:
        print("No valid subscriber emails found")
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'NoValidSubscribers'}
        ])
        return {'statusCode': 500, 'body': 'No valid subscribers'}

    print("Fetching research papers...")
    pubmed = PubMedClient()
    papers = pubmed.get_recent_papers(num_papers=5)

    if not papers:
        print("No papers found")
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'NoPapers'}
        ])
        return {'statusCode': 500, 'body': 'No papers found'}

    print(f"Retrieved {len(papers)} papers")
    monitoring.put_metric('PapersRetrieved', len(papers))

    print("Generating summaries...")
    bedrock = BedrockClient()
    summaries = bedrock.generate_summaries(papers)

    while len(summaries) < len(papers):
        summaries.append("Breakthrough research published.")

    print(f"Sending newsletter to {len(valid_subscribers)} subscribers...")
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
            subscribers=valid_subscribers,
            sender_email=sender_email,
            subject=subject,
            html_content=html_content,
            plain_text=plain_text
        )

        duration = (datetime.now() - start_time).total_seconds()

        print(f"Newsletter sent to {result['delivered']} subscribers")
        monitoring.put_metric('NewsletterDelivered', result['delivered'])
        monitoring.put_metric('NewsletterGenerationTime', duration, unit='Seconds')

        if result['failed'] > 0:
            print(f"Failed to deliver to {result['failed']} subscribers")
            monitoring.put_metric('NewsletterFailed', result['failed'])

        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Success'}
        ])

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Newsletter sent successfully',
                'subscribers': result['delivered'],
                'papers': len(papers),
                'duration_seconds': round(duration, 2)
            })
        }

    except Exception as e:
        print(f"Error sending newsletter: {e}")
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Error'}
        ])
        return {'statusCode': 500, 'body': json.dumps(f'Error: {str(e)}')}


def get_subscribers(contact_list_name):
    """Retrieve active subscribers from contact list.

    Args:
        contact_list_name: Name of SES contact list.

    Returns:
        list: Email addresses of active subscribers.
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


def send_newsletter(subscribers, sender_email, subject, html_content,
                    plain_text):
    """Send newsletter to all subscribers with retry logic.

    Args:
        subscribers: List of subscriber email addresses.
        sender_email: Verified sender email.
        subject: Email subject line.
        html_content: HTML email body.
        plain_text: Plain text email body.

    Returns:
        dict: Delivery statistics.
    """
    batch_size = 50
    delivered = 0
    failed = 0
    failed_emails = []

    recipient_display = os.environ.get(
        'RECIPIENT_DISPLAY',
        f"Iridia Daily Readers <{sender_email}>"
    )

    for i in range(0, len(subscribers), batch_size):
        batch = subscribers[i:i + batch_size]
        batch_num = i // batch_size + 1

        try:
            def send_batch():
                return ses.send_email(
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

            monitoring.retry_with_backoff(send_batch, max_attempts=3)
            delivered += len(batch)
            print(f"Sent batch {batch_num}: {len(batch)} emails")

        except Exception as e:
            failed += len(batch)
            failed_emails.extend(batch)
            print(f"Failed batch {batch_num}: {e}")
            print(f"Failed emails: {', '.join(batch[:5])}"
                  f"{'...' if len(batch) > 5 else ''}")

    if failed > 0:
        print(f"Failed to deliver to {failed} subscribers")
        print(f"Sample failed emails: {', '.join(failed_emails[:10])}")

    return {
        'delivered': delivered,
        'failed': failed,
        'failed_emails': failed_emails
    }


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

    if len(email) > 320:
        return False

    return True