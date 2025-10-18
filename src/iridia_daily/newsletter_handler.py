"""Newsletter generation and distribution with personalized unsubscribe links.

Generates daily newsletter from PubMed research papers and delivers to
subscribers with secure, personalized unsubscribe tokens using SES bulk API.
"""

import json
import boto3
import os
import re
from datetime import datetime
from botocore.exceptions import ClientError

from .clients import PubMedClient, BedrockClient
from .email_generator import EmailGenerator
from . import monitoring
from .token_utils import generate_unsubscribe_token

ses = boto3.client('ses', region_name='us-east-1')
ses_v2 = boto3.client('sesv2', region_name='us-east-1')

# Bulk send batch size (SES limit is 50)
BULK_BATCH_SIZE = 50


def get_api_url():
    """Get API Gateway URL from environment or discover it.

    Returns:
        str: Base API URL or empty string if not found.
    """
    api_url = os.environ.get('API_URL', '')
    
    if not api_url or api_url == 'PLACEHOLDER':
        region = os.environ.get('AWS_REGION', 'us-east-1')
        
        try:
            cfn = boto3.client('cloudformation', region_name=region)
            stacks = cfn.describe_stacks()
            for stack in stacks.get('Stacks', []):
                stack_name = stack.get('StackName', '')
                if 'iridia' in stack_name.lower():
                    for output in stack.get('Outputs', []):
                        if output.get('OutputKey') == 'ApiUrl':
                            return output.get('OutputValue', '')
        except Exception as e:
            print(f"Could not discover API URL: {e}")
        
        return ""
    
    return api_url


def ensure_email_template():
    """Ensure the SES email template exists for bulk sending.

    Creates a simple pass-through template if it doesn't exist.
    Template uses {{html_content}}, {{text_content}}, and {{subject}}
    placeholders.
    """
    template_name = 'IridiaDailyNewsletter'

    try:
        ses.get_template(TemplateName=template_name)
        print(f"Template '{template_name}' already exists")
    except ClientError as e:
        if e.response['Error']['Code'] == 'TemplateDoesNotExist':
            print(f"Creating template '{template_name}'")
            try:
                ses.create_template(
                    Template={
                        'TemplateName': template_name,
                        'SubjectPart': '{{subject}}',
                        'HtmlPart': '{{html_content}}',
                        'TextPart': '{{text_content}}'
                    }
                )
                print(f"Template '{template_name}' created successfully")
            except Exception as create_error:
                print(f"Error creating template: {create_error}")
                raise
        else:
            print(f"Error checking template: {e}")
            raise


def lambda_handler(event, context):
    """Generate and send daily newsletter with personalized links.

    Args:
        event: Lambda event object.
        context: Lambda context object.

    Returns:
        dict: Response with status code, body, and delivery statistics.
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

    ensure_email_template()

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

    print(f"Sending bulk newsletters to {len(valid_subscribers)} subscribers...")
    email_gen = EmailGenerator()

    try:
        date_str = datetime.now().strftime("%A, %B %d, %Y")
        subject = email_gen.generate_subject_line()

        result = send_bulk_newsletters(
            subscribers=valid_subscribers,
            sender_email=sender_email,
            subject=subject,
            papers=papers,
            summaries=summaries,
            date_str=date_str,
            api_url=api_url,
            email_gen=email_gen
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
        contact_list_name (str): Name of SES contact list.

    Returns:
        list: Email addresses of active subscribers.
    """
    subscribers = []
    next_token = None

    try:
        while True:
            params = {'ContactListName': contact_list_name}
            if next_token:
                params['NextToken'] = next_token

            response = ses_v2.list_contacts(**params)

            for contact in response.get('Contacts', []):
                topic_prefs = contact.get('TopicPreferences', [{}])[0]
                if topic_prefs.get('SubscriptionStatus') == 'OPT_IN':
                    subscribers.append(contact['EmailAddress'])

            next_token = response.get('NextToken')
            if not next_token:
                break

        return subscribers

    except Exception as e:
        print(f"Error retrieving subscribers: {e}")
        return []


def send_bulk_newsletters(subscribers, sender_email, subject, papers,
                          summaries, date_str, api_url, email_gen):
    """Send newsletters using SES bulk API with personalized content.

    Each subscriber receives a personalized email with their own secure
    unsubscribe token. Emails are sent in batches of 50 (SES limit) for
    optimal performance while maintaining per-recipient personalization.
    Uses fully custom content without requiring SES templates.

    Args:
        subscribers (list): Subscriber email addresses.
        sender_email (str): Verified sender email address.
        subject (str): Email subject line.
        papers (list): Research papers to include.
        summaries (list): Paper summaries.
        date_str (str): Formatted date string.
        api_url (str): Base API URL for unsubscribe links.
        email_gen (EmailGenerator): Email generator instance.

    Returns:
        dict: Delivery statistics with 'delivered', 'failed', and
            'failed_emails' keys.
    """
    delivered = 0
    failed = 0
    failed_emails = []

    template_name = 'IridiaDailyNewsletter'
    total_batches = ((len(subscribers) + BULK_BATCH_SIZE - 1)
                     // BULK_BATCH_SIZE)

    for batch_num in range(0, len(subscribers), BULK_BATCH_SIZE):
        batch = subscribers[batch_num:batch_num + BULK_BATCH_SIZE]
        current_batch = (batch_num // BULK_BATCH_SIZE) + 1

        print(f"Processing batch {current_batch}/{total_batches} "
              f"({len(batch)} subscribers)")

        bulk_entries = []

        for email in batch:
            try:
                unsubscribe_token = generate_unsubscribe_token(email)
                unsubscribe_url = (f"{api_url}/unsubscribe?"
                                   f"token={unsubscribe_token}")

                html_content = email_gen.generate_html_email(
                    papers, summaries, date_str, unsubscribe_url
                )
                plain_text = email_gen.generate_plain_text_email(
                    papers, summaries, date_str, unsubscribe_url
                )

                bulk_entries.append({
                    'Destination': {
                        'ToAddresses': [email]
                    },
                    'ReplacementEmailContent': {
                        'ReplacementTemplate': {
                            'ReplacementTemplateData': json.dumps({
                                'subject': subject,
                                'html_content': html_content,
                                'text_content': plain_text
                            })
                        }
                    }
                })

            except Exception as e:
                print(f"Error preparing email for {email}: {e}")
                failed += 1
                failed_emails.append(email)

        if not bulk_entries:
            print(f"Batch {current_batch}: No valid entries to send")
            continue

        try:
            response = ses_v2.send_bulk_email(
                FromEmailAddress=f"Iridia Daily <{sender_email}>",
                DefaultContent={
                    'Template': {
                        'TemplateName': template_name,
                        'TemplateData': json.dumps({
                            'subject': subject,
                            'html_content': '',
                            'text_content': ''
                        })
                    }
                },
                BulkEmailEntries=bulk_entries
            )

            for idx, result in enumerate(response.get('BulkEmailEntryResults', [])):
                email = batch[idx] if idx < len(batch) else 'unknown'

                if result.get('Status') == 'SUCCESS':
                    delivered += 1
                else:
                    failed += 1
                    failed_emails.append(email)
                    error_msg = result.get('Error', 'Unknown error')
                    print(f"Failed to send to {email}: {error_msg}")

            print(f"Batch {current_batch} complete: "
                  f"{delivered} delivered, {failed} failed so far")

        except Exception as e:
            print(f"Bulk send failed for batch {current_batch}: {e}")
            failed += len(batch)
            failed_emails.extend(batch)

    if failed > 0:
        print(f"Total delivery failures: {failed}")
        print(f"Sample failed emails: {', '.join(failed_emails[:10])}")

    return {
        'delivered': delivered,
        'failed': failed,
        'failed_emails': failed_emails
    }


def is_valid_email(email):
    """Validate email address format.

    Checks email format according to RFC 5321 standards, including
    local part rules, domain format, and length restrictions.

    Args:
        email (str): Email address to validate.

    Returns:
        bool: True if email format is valid, False otherwise.
    """
    if not email or not isinstance(email, str):
        return False

    # Check email format with regex
    pattern = (r'^[a-zA-Z0-9][a-zA-Z0-9._%+-]*[a-zA-Z0-9]@'
               r'[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}$')

    if not re.match(pattern, email):
        return False

    if '..' in email or email.count('@') != 1:
        return False

    if len(email) > 320:
        return False

    return True