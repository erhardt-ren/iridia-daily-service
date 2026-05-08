"""Newsletter generation handler with correct grouped newsletter logic."""

import json
import boto3
import os
from datetime import datetime
from collections import defaultdict

from . import monitoring
from .clients.bedrock_client import BedrockClient
from .clients.pubmed_client import PubMedClient
from .email_generator import EmailGenerator
from .token_utils import generate_unsubscribe_token
from .logger import set_lambda_context, log_info, log_warning, log_error, log_metric
from .utils import get_api_url_from_api_id
from .config import CATEGORY_MAPPING
from .archive_db import add_papers, upload_database_to_s3

ses_v2 = boto3.client('sesv2', region_name='us-east-1')
s3_client = boto3.client('s3')
BULK_BATCH_SIZE = 50
PAPERS_PER_TOPIC = 5
PAPERS_PER_NEWSLETTER = 5


def lambda_handler(event, context):
    """Generate and send personalized newsletters with correct group logic.

    Args:
        event: Lambda event (scheduled or manual invoke).
        context: Lambda context.

    Returns:
        Dictionary with delivery statistics.
    """
    set_lambda_context(context)
    start_time = datetime.now()

    log_info('newsletter_generation_started')
    monitoring.put_metric('NewsletterGeneration', 1, dimensions=[
        {'Name': 'Status', 'Value': 'Started'}
    ])

    try:
        contact_list_name = os.environ.get('CONTACT_LIST_NAME')
        subscribers = get_subscribers_with_preferences(contact_list_name)

        if not subscribers:
            log_warning('no_active_subscribers')
            return {'statusCode': 200, 'body': 'No active subscribers'}

        log_info('subscribers_fetched', count=len(subscribers))
        
        for i, sub in enumerate(subscribers[:3]):
            log_info('subscriber_detail',
                    index=i,
                    email=sub['email'],
                    topics=sub['topics'],
                    topics_type=type(sub['topics']).__name__)

        subscriber_groups = group_subscribers_by_preferences(subscribers)
        
        if not subscriber_groups:
            log_warning('no_subscriber_groups')
            return {'statusCode': 200, 'body': 'No valid subscriber groups'}
        
        log_info('subscriber_groups_created',
                num_groups=len(subscriber_groups),
                groups={str(k): len(v) for k, v in subscriber_groups.items()})

        all_needed_topics = get_all_needed_topics(subscriber_groups)
        
        log_info('all_topics_identified',
                topics=list(all_needed_topics),
                count=len(all_needed_topics))

        pubmed_client = PubMedClient()
        papers_by_topic, pmid_to_topic = pubmed_client.get_papers_for_multiple_topics(
            all_needed_topics,
            papers_per_topic=PAPERS_PER_TOPIC
        )

        if not papers_by_topic:
            log_warning('no_papers_found')
            return {'statusCode': 200, 'body': 'No papers found'}

        log_info('papers_fetched',
                topics=list(papers_by_topic.keys()),
                total_papers=sum(len(papers) for papers in papers_by_topic.values()))

        newsletters = build_newsletters_for_groups(subscriber_groups, papers_by_topic)
        
        if not newsletters:
            log_warning('no_newsletters_built')
            return {'statusCode': 200, 'body': 'No newsletters built'}
        
        log_info('newsletters_built', num_newsletters=len(newsletters))

        all_unique_papers = {}
        for newsletter in newsletters.values():
            for paper in newsletter['papers']:
                all_unique_papers[paper['pmid']] = paper
        
        log_info('unique_papers_for_summaries', count=len(all_unique_papers))

        bedrock_client = BedrockClient()
        papers_list = list(all_unique_papers.values())
        summaries_by_pmid = generate_summaries_for_papers(bedrock_client, papers_list)

        if not summaries_by_pmid:
            log_error('summary_generation_failed')
            return {'statusCode': 500, 'body': 'Summary generation failed'}

        log_info('summaries_generated', count=len(summaries_by_pmid))

        sender_email = os.environ.get('SENDER_EMAIL')
        result = send_newsletters(newsletters, summaries_by_pmid, pmid_to_topic, sender_email)

        archive_saved = save_to_archive(papers_list, summaries_by_pmid, pmid_to_topic)
        log_info('archive_save_attempted', success=archive_saved)

        duration = (datetime.now() - start_time).total_seconds()
        log_metric('NewsletterGenerationDuration', duration, unit='Seconds')
        log_info('newsletter_generation_completed', **result)

        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }

    except Exception as e:
        log_error('newsletter_generation_failed', error=str(e))
        raise


def group_subscribers_by_preferences(subscribers):
    """Group subscribers by their unique topic preferences.
    
    Args:
        subscribers: List of dicts with 'email' and 'topics'.
    
    Returns:
        Dict mapping preference_key to list of emails.
    """
    groups = defaultdict(list)
    
    for subscriber in subscribers:
        email = subscriber['email']
        topics = subscriber['topics']
        
        if topics is None:
            pref_key = None
            pref_display = 'all'
        else:
            pref_key = tuple(sorted(topics))
            pref_display = list(pref_key)
        
        groups[pref_key].append(email)
        
        log_info('subscriber_grouped',
                email=email,
                topics_raw=topics,
                pref_key=str(pref_key),
                pref_display=pref_display)
    
    log_info('grouping_complete',
            num_groups=len(groups),
            group_keys=[str(k) if k else 'all' for k in groups.keys()])
    
    return dict(groups)


def get_all_needed_topics(subscriber_groups):
    """Get all unique topics needed across all subscriber groups.
    
    Args:
        subscriber_groups: Dict mapping preference_key to list of emails.
    
    Returns:
        Set of all unique topic strings needed.
    """
    all_topics = set()
    
    for pref_key in subscriber_groups.keys():
        if pref_key is None:
            all_topics.update(CATEGORY_MAPPING.keys())
            all_topics.discard('default')
        else:
            all_topics.update(pref_key)
    
    return all_topics


def build_newsletters_for_groups(subscriber_groups, papers_by_topic):
    """Build newsletter for each subscriber group with balanced paper distribution.
    
    Args:
        subscriber_groups: Dict mapping preference_key to list of emails.
        papers_by_topic: Dict mapping topic to list of papers.
    
    Returns:
        Dict mapping preference_key to newsletter dict.
    """
    newsletters = {}
    
    for pref_key, recipients in subscriber_groups.items():
        if pref_key is None:
            relevant_papers = papers_by_topic
        else:
            relevant_papers = {
                topic: papers
                for topic, papers in papers_by_topic.items()
                if topic in pref_key
            }
        
        if not relevant_papers:
            log_warning('no_papers_for_group',
                       preferences=list(pref_key) if pref_key else 'all')
            continue
        
        selected_papers = distribute_papers_evenly(
            relevant_papers,
            PAPERS_PER_NEWSLETTER
        )
        
        if selected_papers:
            newsletters[pref_key] = {
                'papers': selected_papers,
                'recipients': recipients
            }
            
            log_info('newsletter_built',
                    preferences=list(pref_key) if pref_key else 'all',
                    papers=len(selected_papers),
                    recipients=len(recipients))
    
    return newsletters


def distribute_papers_evenly(papers_by_topic, target_count):
    """Distribute papers evenly across topics using round-robin.
    
    Args:
        papers_by_topic: Dict mapping topic to list of papers.
        target_count: Number of papers to select.
    
    Returns:
        List of papers with balanced topic distribution.
    """
    if not papers_by_topic:
        return []
    
    topic_papers_list = [(topic, papers[:]) for topic, papers in sorted(papers_by_topic.items())]
    selected = []
    round_num = 0
    
    while len(selected) < target_count:
        added_this_round = False
        
        for topic, papers in topic_papers_list:
            if len(selected) >= target_count:
                break
                
            if round_num < len(papers):
                paper = papers[round_num].copy()
                paper['topic'] = topic
                selected.append(paper)
                added_this_round = True
        
        if not added_this_round:
            break
        
        round_num += 1
    
    selected.sort(key=lambda p: p.get('topic', 'zzz'))
    
    log_info('papers_distributed',
            target=target_count,
            actual=len(selected),
            topics=list(papers_by_topic.keys()),
            rounds=round_num,
            sorted_by_topic=True)
    
    return selected


def generate_summaries_for_papers(bedrock_client, papers):
    """Generate summaries for papers in ONE Bedrock call.

    Args:
        bedrock_client: BedrockClient instance.
        papers: List of paper dicts.

    Returns:
        Dict mapping PMID to summary string.
    """
    if not papers:
        return {}
    
    try:
        summaries = bedrock_client.generate_summaries(papers)
        
        if not summaries or len(summaries) != len(papers):
            log_error('summary_count_mismatch',
                     expected=len(papers),
                     got=len(summaries) if summaries else 0)
            if not summaries:
                return {}
        
        summaries_by_pmid = {}
        for paper, summary in zip(papers, summaries):
            summaries_by_pmid[paper['pmid']] = summary
        
        return summaries_by_pmid
        
    except Exception as e:
        log_error('summary_generation_failed', error=str(e))
        return {}


def send_newsletters(newsletters, summaries_by_pmid, pmid_to_topic, sender_email):
    """Send individual newsletter to each subscriber group.

    Args:
        newsletters: Dict mapping preference_key to newsletter dict.
        summaries_by_pmid: Dict mapping PMID to summary.
        pmid_to_topic: Dict mapping PMID to topic.
        sender_email: Sender email address.

    Returns:
        Dict with delivery statistics.
    """
    api_url = get_api_url_from_api_id()
    total_sent = 0
    email_generator = EmailGenerator()
    date_str = datetime.now().strftime('%B %d, %Y')
    
    for pref_key, newsletter in newsletters.items():
        papers = newsletter['papers']
        recipients = newsletter['recipients']
        
        valid_papers = []
        valid_summaries = []
        paper_topics = []
        
        for paper in papers:
            pmid = paper['pmid']
            if pmid in summaries_by_pmid:
                valid_papers.append(paper)
                valid_summaries.append(summaries_by_pmid[pmid])
                paper_topics.append(pmid_to_topic.get(pmid, 'default'))
        
        if not valid_papers:
            log_warning('no_valid_papers_for_group',
                       preferences=list(pref_key) if pref_key else 'all')
            continue
        
        topic_dist = defaultdict(int)
        for topic in paper_topics:
            topic_dist[topic] += 1
        
        log_info('sending_newsletter',
                preferences=list(pref_key) if pref_key else 'all',
                papers_count=len(valid_papers),
                recipients_count=len(recipients),
                topics_in_newsletter=dict(topic_dist))
        
        subject_line = email_generator.generate_subject_line(paper_count=len(valid_papers))
        
        for i in range(0, len(recipients), BULK_BATCH_SIZE):
            batch_emails = recipients[i:i + BULK_BATCH_SIZE]
            
            destinations = []
            for email in batch_emails:
                token = generate_unsubscribe_token(email)
                unsubscribe_url = f"{api_url}/unsubscribe?token={token}"
                preferences_url = f"{api_url}/preferences?token={token}"
                
                html_body = email_generator.generate_html_email(
                    valid_papers,
                    valid_summaries,
                    date_str,
                    unsubscribe_url,
                    preferences_url,
                    paper_topics
                )
                text_body = email_generator.generate_plain_text_email(
                    valid_papers,
                    valid_summaries,
                    date_str,
                    unsubscribe_url,
                    preferences_url,
                    paper_topics
                )
                
                destinations.append({
                    'Destination': {'ToAddresses': [email]},
                    'ReplacementEmailContent': {
                        'ReplacementTemplate': {
                            'ReplacementTemplateData': json.dumps({
                                'subject': subject_line,
                                'html_content': html_body,
                                'text_content': text_body
                            })
                        }
                    }
                })
            
            try:
                ses_v2.send_bulk_email(
                    FromEmailAddress=f"Iridia Daily <{sender_email}>",
                    DefaultContent={
                        'Template': {
                            'TemplateName': 'IridiaDailyNewsletter',
                            'TemplateData': json.dumps({
                                'subject': 'Iridia Daily Newsletter',
                                'html_content': '<html><body>Default</body></html>',
                                'text_content': 'Default'
                            })
                        }
                    },
                    BulkEmailEntries=destinations
                )
                total_sent += len(batch_emails)
                log_info('batch_sent', size=len(batch_emails))
                
            except Exception as e:
                log_error('batch_failed', error=str(e), size=len(batch_emails))
    
    return {
        'total_sent': total_sent,
        'unique_newsletters': len(newsletters)
    }


def get_subscribers_with_preferences(contact_list_name):
    """Fetch subscribers with their topic preferences from SES.
    
    Args:
        contact_list_name: Name of the SES contact list.
        
    Returns:
        list: List of subscriber dicts with 'email' and 'topics' keys.
    """
    try:
        subscribers = []
        next_token = None
        
        while True:
            params = {'ContactListName': contact_list_name}
            if next_token:
                params['NextToken'] = next_token
            
            response = ses_v2.list_contacts(**params)
            
            for contact in response.get('Contacts', []):
                topic_prefs = contact.get('TopicPreferences', [])
                
                opted_in_topics = [
                    tp['TopicName']
                    for tp in topic_prefs
                    if tp.get('SubscriptionStatus') == 'OPT_IN'
                ]
                
                if not opted_in_topics:
                    continue
                
                all_content_topics = set(CATEGORY_MAPPING.keys()) - {'default'}
                opted_in_set = set(opted_in_topics)
                
                if 'daily-research' in opted_in_set:
                    if opted_in_set - {'daily-research'} == all_content_topics:
                        topics = None
                    else:
                        topics = sorted(list(opted_in_set - {'daily-research'}))
                else:
                    topics = sorted(list(opted_in_set))
                
                if topics is None or len(topics) > 0:
                    subscribers.append({
                        'email': contact['EmailAddress'],
                        'topics': topics
                    })
            
            next_token = response.get('NextToken')
            if not next_token:
                break
        
        return subscribers
        
    except Exception as e:
        log_error('fetch_subscribers_failed', error=str(e))
        raise


def parse_topic_preferences(attrs_json):
    """Parse topic preferences from contact attributes.
    
    Args:
        attrs_json: JSON string of contact attributes.
        
    Returns:
        list or None: List of topic strings, or None for all topics.
    """
    try:
        if not attrs_json:
            return None
            
        attrs = json.loads(attrs_json)
        topics = attrs.get('topics')
        
        if not topics or not isinstance(topics, list) or len(topics) == 0:
            return None
        
        return topics
        
    except Exception:
        return None


def log_preference_distribution(subscribers):
    """Log distribution of topic preferences.
    
    Args:
        subscribers: List of subscriber dicts.
    """
    topic_counts = defaultdict(int)
    all_topics_count = 0
    
    for sub in subscribers:
        if sub['topics'] is None:
            all_topics_count += 1
        else:
            for topic in sub['topics']:
                topic_counts[topic] += 1
    
    log_info('preference_distribution',
             all_topics=all_topics_count,
             topic_counts=dict(topic_counts))


def save_to_archive(papers, summaries_by_pmid, pmid_to_topic):
    """Save newsletter content to SQLite database in S3.
    
    This replaces the previous JSON file approach with SQLite storage,
    providing efficient querying and proper pagination support.
    
    Workflow:
        1. Download SQLite database from S3 (or use cached version)
        2. Add new papers to database using SQL INSERT
        3. Upload updated database back to S3
        4. S3 upload is atomic - if it fails, old version is preserved
    
    Args:
        papers: List of paper dictionaries from PubMed.
        summaries_by_pmid: Dict mapping PMID to generated summary text.
        pmid_to_topic: Dict mapping PMID to topic category.
        
    Returns:
        bool: True if save successful, False otherwise.
    """
    bucket_name = os.environ.get('ARCHIVE_BUCKET_NAME')
    
    if not bucket_name:
        log_warning('archive_bucket_not_configured')
        monitoring.put_metric('ArchiveSaved', 1, dimensions=[
            {'Name': 'Status', 'Value': 'NotConfigured'}
        ])
        return False
    
    # Filter out papers without summaries
    valid_papers = [
        paper for paper in papers
        if paper.get('pmid') in summaries_by_pmid
    ]
    
    if not valid_papers:
        log_warning('no_valid_papers_to_archive',
                   total_papers=len(papers))
        monitoring.put_metric('ArchiveSaved', 1, dimensions=[
            {'Name': 'Status', 'Value': 'NoValidPapers'}
        ])
        return False
    
    log_info('archiving_papers_to_sqlite',
             paper_count=len(valid_papers),
             bucket=bucket_name)
    
    try:
        # Add papers to SQLite database
        # Database is downloaded from S3 (if not cached) automatically
        inserted_count = add_papers(
            papers=valid_papers,
            summaries_by_pmid=summaries_by_pmid,
            pmid_to_topic=pmid_to_topic
        )
        
        log_info('papers_inserted_into_database',
                 inserted=inserted_count,
                 total=len(valid_papers))
        
        # Upload updated database back to S3
        upload_database_to_s3()
        
        date_str = datetime.now().strftime('%Y-%m-%d')
        
        log_info('archive_saved_successfully',
                 date=date_str,
                 papers_count=inserted_count,
                 bucket=bucket_name)
        
        monitoring.put_metric('ArchiveSaved', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Success'}
        ])
        monitoring.put_metric('PapersArchived', inserted_count)
        
        return True
        
    except Exception as e:
        log_error('archive_save_failed',
                 error=str(e),
                 error_type=type(e).__name__,
                 paper_count=len(valid_papers))
        
        monitoring.put_metric('ArchiveSaved', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Failed'}
        ])
        
        return False