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

ses_v2 = boto3.client('sesv2', region_name='us-east-1')
BULK_BATCH_SIZE = 50  # SES bulk email limit
PAPERS_PER_TOPIC = 5  # Papers to fetch per topic
PAPERS_PER_NEWSLETTER = 5  # Papers per newsletter


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
        # STEP 1: Get subscribers with preferences
        contact_list_name = os.environ.get('CONTACT_LIST_NAME')
        subscribers = get_subscribers_with_preferences(contact_list_name)

        if not subscribers:
            log_warning('no_active_subscribers')
            return {'statusCode': 200, 'body': 'No active subscribers'}

        log_info('subscribers_fetched', count=len(subscribers))
        
        # Log first few subscribers to debug preferences
        for i, sub in enumerate(subscribers[:3]):
            log_info('subscriber_detail',
                    index=i,
                    email=sub['email'],
                    topics=sub['topics'],
                    topics_type=type(sub['topics']).__name__)

        # STEP 2: Group subscribers by unique preference combinations
        subscriber_groups = group_subscribers_by_preferences(subscribers)
        
        if not subscriber_groups:
            log_warning('no_subscriber_groups')
            return {'statusCode': 200, 'body': 'No valid subscriber groups'}
        
        log_info('subscriber_groups_created',
                num_groups=len(subscriber_groups),
                groups={str(k): len(v) for k, v in subscriber_groups.items()})

        # STEP 3: Determine ALL topics needed across all groups
        all_needed_topics = get_all_needed_topics(subscriber_groups)
        
        log_info('all_topics_identified',
                topics=list(all_needed_topics),
                count=len(all_needed_topics))

        # STEP 4: Make ONE PubMed call for all topics
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

        # STEP 5: For each group, select 5 papers matching THEIR preferences
        newsletters = build_newsletters_for_groups(subscriber_groups, papers_by_topic)
        
        if not newsletters:
            log_warning('no_newsletters_built')
            return {'statusCode': 200, 'body': 'No newsletters built'}
        
        log_info('newsletters_built', num_newsletters=len(newsletters))

        # STEP 6: Collect ALL unique papers across all newsletters
        all_unique_papers = {}
        for newsletter in newsletters.values():
            for paper in newsletter['papers']:
                all_unique_papers[paper['pmid']] = paper
        
        log_info('unique_papers_for_summaries', count=len(all_unique_papers))

        # STEP 7: Generate summaries for all unique papers (ONE Bedrock call)
        bedrock_client = BedrockClient()
        papers_list = list(all_unique_papers.values())
        summaries_by_pmid = generate_summaries_for_papers(bedrock_client, papers_list)

        if not summaries_by_pmid:
            log_error('summary_generation_failed')
            return {'statusCode': 500, 'body': 'Summary generation failed'}

        log_info('summaries_generated', count=len(summaries_by_pmid))

        # STEP 8: Send individual newsletter to each group
        sender_email = os.environ.get('SENDER_EMAIL')
        result = send_newsletters(newsletters, summaries_by_pmid, pmid_to_topic, sender_email)

        # Log completion
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
        preference_key is either:
        - None (for subscribers wanting all topics)
        - tuple of sorted topic strings (e.g., ('space', 'technology'))
    """
    groups = defaultdict(list)
    
    for subscriber in subscribers:
        email = subscriber['email']
        topics = subscriber['topics']
        
        # Create preference key
        if topics is None:
            # Wants all topics - special group
            pref_key = None
            pref_display = 'all'
        else:
            # Specific topics - sorted tuple
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
            # This group wants all topics, so include all available
            all_topics.update(CATEGORY_MAPPING.keys())
            all_topics.discard('default')  # Don't fetch 'default'
        else:
            # This group wants specific topics
            all_topics.update(pref_key)
    
    return all_topics


def build_newsletters_for_groups(subscriber_groups, papers_by_topic):
    """Build newsletter for each subscriber group with balanced paper distribution.
    
    Papers are distributed evenly across requested topics using round-robin.
    This ensures users see a variety of topics rather than all papers from one topic.
    
    Args:
        subscriber_groups: Dict mapping preference_key to list of emails.
        papers_by_topic: Dict mapping topic to list of papers.
    
    Returns:
        Dict mapping preference_key to newsletter dict with:
        - 'papers': List of 5 papers with balanced topic distribution
        - 'recipients': List of email addresses
    """
    newsletters = {}
    
    for pref_key, recipients in subscriber_groups.items():
        # Collect papers matching THIS group's preferences
        group_papers_by_topic = {}
        
        if pref_key is None:
            # Wants ALL topics - include papers from all topics
            group_papers_by_topic = papers_by_topic.copy()
        else:
            # Wants SPECIFIC topics - only include papers from those topics
            for topic in pref_key:
                if topic in papers_by_topic:
                    group_papers_by_topic[topic] = papers_by_topic[topic]
        
        if not group_papers_by_topic:
            log_warning('no_papers_for_group',
                       preferences=list(pref_key) if pref_key else 'all',
                       recipients_count=len(recipients))
            continue
        
        # Distribute papers evenly using round-robin
        selected_papers = distribute_papers_evenly(
            group_papers_by_topic, 
            PAPERS_PER_NEWSLETTER
        )
        
        if not selected_papers:
            log_warning('no_papers_after_distribution',
                       preferences=list(pref_key) if pref_key else 'all',
                       recipients_count=len(recipients))
            continue
        
        newsletters[pref_key] = {
            'papers': selected_papers,
            'recipients': recipients
        }
        
        # Log topic distribution
        topic_counts = {}
        for paper in selected_papers:
            topic = paper.get('topic', 'unknown')
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        
        log_info('newsletter_built',
                preferences=list(pref_key) if pref_key else 'all',
                papers_count=len(selected_papers),
                recipients_count=len(recipients),
                topic_distribution=topic_counts)
    
    return newsletters


def distribute_papers_evenly(papers_by_topic, target_count):
    """Distribute papers evenly across topics using round-robin, then group by topic.
    
    First uses round-robin to ensure balanced representation, then sorts by topic
    so papers from the same topic appear together in the final newsletter.
    
    Args:
        papers_by_topic: Dict mapping topic to list of papers.
        target_count: Number of papers to select.
    
    Returns:
        List of papers with balanced topic distribution, grouped by topic.
    """
    if not papers_by_topic:
        return []
    
    # Create list of (topic, papers) sorted by topic name for consistency
    topic_papers_list = [(topic, papers[:]) for topic, papers in sorted(papers_by_topic.items())]
    
    selected = []
    round_num = 0
    
    # Round-robin: take one paper from each topic in turn
    while len(selected) < target_count:
        added_this_round = False
        
        for topic, papers in topic_papers_list:
            if len(selected) >= target_count:
                break
                
            # Take next paper from this topic if available
            if round_num < len(papers):
                paper = papers[round_num].copy()
                paper['topic'] = topic  # Add topic for tracking
                selected.append(paper)
                added_this_round = True
        
        # If no papers were added this round, we've exhausted all topics
        if not added_this_round:
            break
        
        round_num += 1
    
    # Sort papers by topic so all papers from same topic are grouped together
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
        
        # Map PMIDs to summaries
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
        
        # Filter to papers we have summaries for
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
        
        # Log what's being sent
        topic_dist = defaultdict(int)
        for topic in paper_topics:
            topic_dist[topic] += 1
        
        log_info('sending_newsletter',
                preferences=list(pref_key) if pref_key else 'all',
                papers_count=len(valid_papers),
                recipients_count=len(recipients),
                topics_in_newsletter=dict(topic_dist))
        
        # Generate subject
        subject_line = email_generator.generate_subject_line(paper_count=len(valid_papers))
        
        # Send to recipients in batches
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
    
    Reads preferences from TopicPreferences field which is always returned
    by list_contacts - no individual get_contact calls needed.

    Args:
        contact_list_name: SES contact list name.

    Returns:
        List of dicts with 'email' and 'topics' fields.
    """
    subscribers = []
    next_token = None

    try:
        while True:
            params = {
                'ContactListName': contact_list_name,
                'Filter': {
                    'FilteredStatus': 'OPT_IN'
                }
            }

            if next_token:
                params['NextToken'] = next_token

            response = ses_v2.list_contacts(**params)

            for contact in response.get('Contacts', []):
                email = contact['EmailAddress']
                
                # Read topics directly from TopicPreferences (always returned)
                topic_prefs = contact.get('TopicPreferences', [])
                
                # Extract topics where SubscriptionStatus is OPT_IN
                opted_in_topics = [
                    tp['TopicName'] 
                    for tp in topic_prefs 
                    if tp.get('SubscriptionStatus') == 'OPT_IN'
                ]
                
                # If no topics opted in OR all topics opted in, return None (gets all content)
                # Otherwise return the specific list of opted-in topics
                all_available_topics = set(CATEGORY_MAPPING.keys()) - {'default'}
                
                if not opted_in_topics or set(opted_in_topics) == all_available_topics:
                    topics = None  # Gets all topics
                else:
                    topics = opted_in_topics
                
                log_info('subscriber_fetched',
                        email=email,
                        opted_in_topics=opted_in_topics,
                        parsed_topics=topics)
                
                subscribers.append({
                    'email': email,
                    'topics': topics
                })

            next_token = response.get('NextToken')
            if not next_token:
                break

    except Exception as e:
        log_error('failed_to_fetch_subscribers', error=str(e))
        raise

    return subscribers


def parse_topic_preferences(attrs_json):
    """Parse topic preferences from SES AttributesData JSON.

    Args:
        attrs_json: JSON string from SES.

    Returns:
        List of topic strings, or None for all topics.
    """
    if not attrs_json:
        log_info('empty_attrs', result='returning None for all topics')
        return None

    try:
        attrs = json.loads(attrs_json)
        topics = attrs.get('topics')
        
        log_info('parsing_attrs',
                raw_json=attrs_json,
                parsed_dict=attrs,
                topics_key_value=topics,
                topics_is_list=isinstance(topics, list),
                topics_length=len(topics) if isinstance(topics, list) else 0)

        if isinstance(topics, list) and len(topics) > 0:
            log_info('valid_topics_found', topics=topics)
            return topics
        
        log_info('invalid_topics', topics=topics, reason='not a non-empty list')
        return None

    except json.JSONDecodeError as e:
        log_error('json_decode_error', attrs_json=attrs_json, error=str(e))
        return None


def log_preference_distribution(subscribers):
    """Log metrics about subscriber preferences (unused but kept for compatibility)."""
    pass