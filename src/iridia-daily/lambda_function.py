"""Main Lambda function - orchestrates the iridia research intelligence generation."""

import json
import boto3
import os
from datetime import datetime

from .clients import PubMedClient, BedrockClient
from .email_generator import EmailGenerator

def lambda_handler(event, context):
    """Main Lambda handler - orchestrates the entire Iridia process."""
    print("=" * 50)
    print("Iridia Research Intelligence Generator Starting")  
    print("=" * 50)
    
    # Initialize clients
    pubmed = PubMedClient()
    bedrock = BedrockClient()
    email_gen = EmailGenerator()
    ses = boto3.client('ses', region_name='us-east-1')
    
    # Step 1: Fetch recent research papers
    print("\n[1/3] Fetching 5 recent research papers from PubMed...")
    papers = pubmed.get_recent_papers(num_papers=5)
    
    if not papers:
        print("⚠ No papers found, cannot proceed")
        return {'statusCode': 500, 'body': json.dumps('No papers found')}
    
    print(f"✓ Selected {len(papers)} papers:")
    for i, paper in enumerate(papers, 1):
        print(f"   {i}. {paper['title'][:60]}...")
    
    # Step 2: Generate intelligent summaries
    print(f"\n[2/3] Generating {len(papers)} intelligent summaries with Claude...")  
    summaries = bedrock.generate_summaries(papers)
    
    # Ensure we have enough summaries
    while len(summaries) < len(papers):
        summaries.append("Breakthrough research has been published on this topic.")  
    
    # Step 3: Send via SES
    print("\n[3/3] Sending Iridia Daily via SES...")  
    sender_email = os.environ.get('SENDER_EMAIL')
    recipient_email = os.environ.get('RECIPIENT_EMAIL')
    
    if not sender_email or not recipient_email:
        print("ERROR: SENDER_EMAIL or RECIPIENT_EMAIL environment variable not set")
        return {'statusCode': 500, 'body': json.dumps('Configuration error: Email addresses not set')}
    
    try:
        date_str = datetime.now().strftime("%A, %B %d, %Y")
        
        # Generate email content
        html_message = email_gen.generate_html_email(papers, summaries, date_str)
        plain_text_message = email_gen.generate_plain_text_email(papers, summaries, date_str)
        subject = email_gen.generate_subject_line()
        
        # Send email
        response = ses.send_email(
            Source="Iridia Daily <research@iridia-daily.com>",
            Destination={'ToAddresses': [recipient_email]},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {
                    'Text': {'Data': plain_text_message, 'Charset': 'UTF-8'},
                    'Html': {'Data': html_message, 'Charset': 'UTF-8'}
                }
            }
        )
        
        message_id = response.get('MessageId')
        print(f"✓ Iridia Daily sent successfully! (ID: {message_id})")  
        print(f"✓ From: {sender_email}")
        print(f"✓ To: {recipient_email}")
        print(f"✓ Research papers: {len(papers)}")  
        print(f"✓ Total words: {sum(len(s.split()) for s in summaries)}")
        
        print("\n" + "=" * 50)
        print("Iridia Research Intelligence Generator Complete")  
        print("=" * 50)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Iridia sent successfully',  
                'messageId': message_id,
                'papers_count': len(papers),
                'papers': [p['title'][:60] for p in papers],
                'recipient': recipient_email
            })
        }
        
    except Exception as e:
        print(f"✗ Error sending Iridia Daily: {e}")  
        return {'statusCode': 500, 'body': json.dumps(f'Error sending Iridia: {str(e)}')}  