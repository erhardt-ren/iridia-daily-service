"""Newsletter generation and distribution with personalized unsubscribe links.

Generates daily newsletter from PubMed research papers and delivers to
subscribers with secure, personalized unsubscribe tokens using SES bulk API.
"""

import json
import boto3
import os
import re
from datetime import datetime

from .clients import PubMedClient, BedrockClient
from .email_generator import EmailGenerator
from . import monitoring
from .token_utils import generate_unsubscribe_token
from .logger import set_lambda_context, log_info, log_warning, log_error, log_metric

ses = boto3.client('ses', region_name='us-east-1')
ses_v2 = boto3.client('sesv2', region_name='us-east-1')

# Bulk send batch size (SES limit is 50)
BULK_BATCH_SIZE = 50

def get_api_url():
    """Get API Gateway URL from environment variable.

    Returns:
        str: Base API URL.

    Raises:
        ValueError: If API_URL environment variable is not set.
    """
    api_url = os.environ.get('API_URL', '').strip()
    
    if not api_url:
        raise ValueError(
            "API_URL environment variable is not set. "
            "Ensure template.yaml includes API_URL in Environment Variables."
        )
    
    return api_url

def lambda_handler(event, context):
    """Generate and send daily newsletter with personalized links.

    Args:
        event: Lambda event object.
        context: Lambda context object.

    Returns:
        dict: Response with status code, body, and delivery statistics.
    """
    set_lambda_context(context)
    log_info('newsletter_handler_started')
    start_time = datetime.now()

    contact_list_name = os.environ.get('CONTACT_LIST_NAME')
    sender_email = os.environ.get('SENDER_EMAIL')
    api_url = os.environ.get('API_URL', '')

    if not contact_list_name or not sender_email:
        log_error('config_error', 
                  missing_vars='CONTACT_LIST_NAME or SENDER_EMAIL')
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'ConfigError'}
        ])
        return {'statusCode': 500, 'body': 'Configuration error'}

    if not monitoring.verify_ses_sender(sender_email):
        log_error('sender_not_verified', sender_email=sender_email)
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'SenderNotVerified'}
        ])
        return {'statusCode': 500, 'body': 'Sender email not verified'}

    log_info('fetching_subscribers')
    subscribers = get_subscribers(contact_list_name)

    if not subscribers:
        log_warning('no_subscribers_found')
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'NoSubscribers'}
        ])
        return {'statusCode': 200, 'body': 'No subscribers'}

    log_info('subscribers_retrieved', count=len(subscribers))
    monitoring.put_metric('SubscriberCount', len(subscribers))

    valid_subscribers = [email for email in subscribers if is_valid_email(email)]
    if len(valid_subscribers) != len(subscribers):
        invalid_count = len(subscribers) - len(valid_subscribers)
        log_warning('invalid_emails_filtered', 
                    invalid_count=invalid_count)
        monitoring.put_metric('InvalidSubscriberEmails', invalid_count)

    if not valid_subscribers:
        log_error('no_valid_subscribers')
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'NoValidSubscribers'}
        ])
        return {'statusCode': 500, 'body': 'No valid subscribers'}

    log_info('fetching_papers')
    pubmed = PubMedClient()
    papers = pubmed.get_recent_papers(num_papers=5)

    if not papers:
        log_error('no_papers_found')
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'NoPapers'}
        ])
        return {'statusCode': 500, 'body': 'No papers found'}

    log_info('papers_retrieved', count=len(papers))
    monitoring.put_metric('PapersRetrieved', len(papers))

    log_info('generating_summaries')
    bedrock = BedrockClient()
    summaries = bedrock.generate_summaries(papers)

    # Validate that summary generation produced correct number of summaries
    # with acceptable quality. Do not proceed with newsletter if validation
    # fails to prevent sending incomplete or incorrect content.
    if not validate_summaries(summaries, papers):
        error_msg = (
            f"Summary generation validation failed. "
            f"Expected {len(papers)} summaries, received {len(summaries)}. "
            f"Newsletter distribution aborted to prevent sending incomplete "
            f"content to subscribers."
        )
        
        log_error('summary_validation_failed',
                  expected_count=len(papers),
                  received_count=len(summaries),
                  error_message=error_msg)
        
        # Publish CloudWatch metric for monitoring and alerting
        monitoring.put_metric('SummaryGenerationFailed', 1, dimensions=[
            {'Name': 'Reason', 'Value': 'CountMismatch'}
        ])
        
        # Send immediate SNS alert to operations team
        send_alert_notification(
            message=(
                f"{error_msg}\n\n"
                f"Papers retrieved: {len(papers)}\n"
                f"Summaries generated: {len(summaries)}\n"
                f"Timestamp: {datetime.now().isoformat()}"
            ),
            subject="🚨 Iridia Daily: Summary Generation Failed"
        )
        
        # Record failure in metrics and return error without sending newsletter
        monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
            {'Name': 'Status', 'Value': 'SummaryValidationFailed'}
        ])
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Summary generation validation failed',
                'expected_summaries': len(papers),
                'received_summaries': len(summaries)
            })
        }

    log_info('summary_validation_passed', count=len(summaries))

    while len(summaries) < len(papers):
        summaries.append("Breakthrough research published.")

    log_info('sending_bulk_newsletters', subscriber_count=len(valid_subscribers))
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

        log_info('newsletter_sent',
                 delivered=result['delivered'],
                 failed=result['failed'],
                 duration_seconds=round(duration, 2))
        
        log_metric('newsletter_duration',
                   value=duration,
                   unit='Seconds',
                   papers=len(papers),
                   subscribers=result['delivered'])
        
        monitoring.put_metric('NewsletterDelivered', result['delivered'])
        monitoring.put_metric('NewsletterGenerationTime', duration, unit='Seconds')

        if result['failed'] > 0:
            log_warning('delivery_failures',
                        failed_count=result['failed'],
                        sample_emails=result['failed_emails'][:5])
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
        log_error('newsletter_send_error',
                  error_type=type(e).__name__,
                  error_message=str(e))
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
        log_error('subscriber_retrieval_error',
                  error_type=type(e).__name__,
                  error_message=str(e))
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

        log_info('processing_batch',
                 batch_number=current_batch,
                 total_batches=total_batches,
                 batch_size=len(batch))

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
                log_error('email_preparation_error',
                          email=email,
                          error_type=type(e).__name__,
                          error_message=str(e))
                failed += 1
                failed_emails.append(email)

        if not bulk_entries:
            log_warning('batch_empty', batch_number=current_batch)
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

            batch_delivered = 0
            batch_failed = 0
            
            for idx, result in enumerate(response.get('BulkEmailEntryResults', [])):
                email = batch[idx] if idx < len(batch) else 'unknown'

                if result.get('Status') == 'SUCCESS':
                    delivered += 1
                    batch_delivered += 1
                else:
                    failed += 1
                    batch_failed += 1
                    failed_emails.append(email)
                    error_msg = result.get('Error', 'Unknown error')
                    log_warning('email_delivery_failed',
                                email=email,
                                error=error_msg)

            log_info('batch_complete',
                     batch_number=current_batch,
                     delivered=batch_delivered,
                     failed=batch_failed,
                     total_delivered=delivered,
                     total_failed=failed)

        except Exception as e:
            log_error('bulk_send_error',
                      batch_number=current_batch,
                      error_type=type(e).__name__,
                      error_message=str(e))
            failed += len(batch)
            failed_emails.extend(batch)

    if failed > 0:
        log_warning('total_delivery_failures',
                    failed_count=failed,
                    sample_failed_emails=failed_emails[:10])

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

def validate_summaries(summaries, papers):
    """Validate generated summaries against papers.
    
    Ensures each paper has a corresponding summary and checks quality
    metrics. Logs warnings for summaries outside recommended bounds but
    only fails validation if count mismatch occurs.
    
    Args:
        summaries: List of generated summary strings.
        papers: List of paper dictionaries.
    
    Returns:
        bool: True if summary count matches paper count, False otherwise.
    """
    # Critical validation: count must match exactly
    if len(summaries) != len(papers):
        log_error('summary_count_mismatch',
                  expected=len(papers),
                  received=len(summaries))
        return False
    
    # Quality checks: log warnings but don't fail
    for i, summary in enumerate(summaries):
        if not isinstance(summary, str):
            log_warning('summary_not_string',
                        summary_index=i + 1,
                        summary_type=type(summary).__name__)
            continue
            
        summary_len = len(summary)
        
        if summary_len < 50:
            log_warning('summary_too_short',
                        summary_index=i + 1,
                        length=summary_len,
                        min_recommended=50,
                        preview=summary[:30])
        
        if summary_len > 1000:
            log_warning('summary_too_long',
                        summary_index=i + 1,
                        length=summary_len,
                        max_recommended=1000,
                        preview=summary[:50])
    
    return True


def send_alert_notification(message, subject="Iridia Daily Alert"):
    """Send SNS alert notification for critical failures.
    
    Publishes alert message to configured SNS topic for operational
    monitoring. Handles errors gracefully to avoid blocking the main
    execution flow.
    
    Args:
        message: Alert message content describing the failure.
        subject: Alert subject line (default: "Iridia Daily Alert").
    """
    alert_topic_arn = os.environ.get('ALERT_TOPIC_ARN')
    
    if not alert_topic_arn:
        log_warning('alert_topic_not_configured')
        return
    
    try:
        sns = boto3.client('sns', region_name='us-east-1')
        sns.publish(
            TopicArn=alert_topic_arn,
            Message=message,
            Subject=subject
        )
        log_info('alert_sent', topic_arn=alert_topic_arn)
    except Exception as e:
        log_error('alert_send_failed',
                  error_type=type(e).__name__,
                  error_message=str(e))