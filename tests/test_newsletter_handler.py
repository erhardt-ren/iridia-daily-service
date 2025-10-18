"""Tests for newsletter generation and distribution - FIXED VERSION."""

import pytest
from unittest.mock import Mock, patch
import json


@pytest.mark.integration
class TestNewsletterHandler:
    """Test newsletter generation and distribution workflow."""
    
    # Patch module-level clients
    @patch('iridia_daily.newsletter_handler.ses')
    @patch('iridia_daily.newsletter_handler.ses_v2')
    @patch('urllib.request.urlopen')
    def test_newsletter_handler_complete_success(
        self, mock_urlopen, mock_ses_v2, mock_ses,
        mock_pubmed_search, mock_pubmed_fetch,
        comprehensive_pubmed_xml
    ):
        """Test successful end-to-end newsletter generation and sending."""
        from iridia_daily.newsletter_handler import lambda_handler
        
        # Mock PubMed
        pmids = ['12345678', '87654321', '11223344', '44556677', '99887766']
        mock_urlopen.side_effect = [
            mock_pubmed_search(pmids),
            mock_pubmed_fetch(comprehensive_pubmed_xml)
        ]
        
        # Mock SES v2 paginator (KEY FIX)
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{
            'Contacts': [
                {'EmailAddress': 'subscriber1@test.com', 
                 'TopicPreferences': [{'SubscriptionStatus': 'OPT_IN'}]},
                {'EmailAddress': 'subscriber2@test.com',
                 'TopicPreferences': [{'SubscriptionStatus': 'OPT_IN'}]},
                {'EmailAddress': 'subscriber3@test.com',
                 'TopicPreferences': [{'SubscriptionStatus': 'OPT_IN'}]}
            ]
        }]
        mock_ses_v2.get_paginator.return_value = mock_paginator
        
        # Mock SES send
        mock_ses.send_email.return_value = {'MessageId': 'test-msg-123'}
        
        # Mock Bedrock via boto3.client (different pattern since it's created in function)
        with patch('boto3.client') as mock_boto3:
            mock_bedrock = Mock()
            mock_bedrock.invoke_model.return_value = {
                'body': Mock(read=lambda: json.dumps({
                    'content': [{'text': '''Paper 1:
Brain research reveals memory formation during sleep.

Paper 2:
Exoplanet discovery in habitable zone shows signs of water.

Paper 3:
CRISPR gene therapy breakthrough for sickle cell disease.

Paper 4:
Quantum computing advances with room temperature entanglement.

Paper 5:
Ocean ecosystems show resilience to climate change.'''}]
                }).encode())
            }
            mock_boto3.return_value = mock_bedrock
            
            # Execute
            result = lambda_handler({}, {})
        
        # Verify
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['message'] == 'Newsletter sent successfully'
        assert body['subscribers'] == 3
        assert body['papers'] == 5
        
        # Verify SES was called
        mock_ses.send_email.assert_called_once()
    
    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_newsletter_handler_no_subscribers(self, mock_ses_v2):
        """Test newsletter when no active subscribers exist."""
        from iridia_daily.newsletter_handler import lambda_handler
        
        # Mock empty subscriber list
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{'Contacts': []}]
        mock_ses_v2.get_paginator.return_value = mock_paginator
        
        result = lambda_handler({}, {})
        
        assert result['statusCode'] == 200
        assert 'No subscribers' in result['body']
    
    @patch('iridia_daily.newsletter_handler.ses_v2')
    @patch('urllib.request.urlopen')
    def test_newsletter_handler_no_papers_found(
        self, mock_urlopen, mock_ses_v2, mock_pubmed_search
    ):
        """Test newsletter when PubMed returns no papers."""
        from iridia_daily.newsletter_handler import lambda_handler
        
        # Mock empty PubMed results
        mock_urlopen.return_value = mock_pubmed_search([])
        
        # Mock subscribers
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{
            'Contacts': [
                {'EmailAddress': 'subscriber@test.com',
                 'TopicPreferences': [{'SubscriptionStatus': 'OPT_IN'}]}
            ]
        }]
        mock_ses_v2.get_paginator.return_value = mock_paginator
        
        result = lambda_handler({}, {})
        
        assert result['statusCode'] == 500
        assert 'No papers found' in result['body']
    
    @patch('iridia_daily.newsletter_handler.ses')
    @patch('iridia_daily.newsletter_handler.ses_v2')
    @patch('urllib.request.urlopen')
    def test_newsletter_handler_ses_send_error(
        self, mock_urlopen, mock_ses_v2, mock_ses,  # ← Added 'self'!
        mock_pubmed_search, mock_pubmed_fetch,
        comprehensive_pubmed_xml, sample_papers_diverse
    ):
        """Test newsletter handler when SES send fails."""
        from iridia_daily.newsletter_handler import lambda_handler
        
        # Mock PubMed
        pmids = ['12345678', '87654321', '11223344', '44556677', '99887766']
        mock_urlopen.side_effect = [
            mock_pubmed_search(pmids),
            mock_pubmed_fetch(comprehensive_pubmed_xml)
        ]
        
        # Mock SES v2 paginator
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{
            'Contacts': [
                {'EmailAddress': 'subscriber@test.com', 
                'TopicPreferences': [{'SubscriptionStatus': 'OPT_IN'}]}
            ]
        }]
        mock_ses_v2.get_paginator.return_value = mock_paginator
        
        # Mock SES to FAIL on send
        mock_ses.send_email.side_effect = Exception("SES Send Failed")
        
        # Mock Bedrock
        with patch('boto3.client') as mock_boto3:
            mock_bedrock = Mock()
            mock_bedrock.invoke_model.return_value = {
                'body': Mock(read=lambda: json.dumps({
                    'content': [{'text': '''Paper 1:
    Summary 1

    Paper 2:
    Summary 2

    Paper 3:
    Summary 3

    Paper 4:
    Summary 4

    Paper 5:
    Summary 5'''}]
                }).encode())
            }
            mock_boto3.return_value = mock_bedrock
            
            # Execute
            result = lambda_handler({}, {})
        
        # Verify
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['subscribers'] == 0
        assert body['papers'] == 5
    
    def test_newsletter_handler_missing_env_vars(self, monkeypatch):
        """Test newsletter when environment variables are missing."""
        from iridia_daily.newsletter_handler import lambda_handler
        
        # Remove required env vars
        monkeypatch.delenv('SENDER_EMAIL', raising=False)
        monkeypatch.delenv('CONTACT_LIST_NAME', raising=False)
        
        result = lambda_handler({}, {})
        
        assert result['statusCode'] == 500
        assert 'Configuration error' in result['body']


class TestSubscriberManagement:
    """Test subscriber list management functions."""
    
    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_get_subscribers_filters_opted_in(self, mock_ses_v2):
        """Test that get_subscribers returns only opted-in contacts."""
        from iridia_daily.newsletter_handler import get_subscribers
        
        # Mock paginator with mixed contacts
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [{
            'Contacts': [
                {
                    'EmailAddress': 'active1@test.com',
                    'TopicPreferences': [{'SubscriptionStatus': 'OPT_IN'}]
                },
                {
                    'EmailAddress': 'inactive@test.com',
                    'TopicPreferences': [{'SubscriptionStatus': 'OPT_OUT'}]
                },
                {
                    'EmailAddress': 'active2@test.com',
                    'TopicPreferences': [{'SubscriptionStatus': 'OPT_IN'}]
                }
            ]
        }]
        mock_ses_v2.get_paginator.return_value = mock_paginator
        
        subscribers = get_subscribers('test-list')
        
        assert len(subscribers) == 2
        assert 'active1@test.com' in subscribers
        assert 'active2@test.com' in subscribers
        assert 'inactive@test.com' not in subscribers
    
    @patch('iridia_daily.newsletter_handler.ses')
    def test_send_newsletter_batching(self, mock_ses):
        """Test that send_newsletter properly batches large subscriber lists."""
        from iridia_daily.newsletter_handler import send_newsletter
        
        mock_ses.send_email.return_value = {'MessageId': 'test-123'}
        
        # Create 125 subscribers (should result in 3 batches of 50)
        subscribers = [f'user{i}@test.com' for i in range(125)]
        
        result = send_newsletter(
            subscribers=subscribers,
            sender_email='research@iridia-daily.com',
            subject='Test Subject',
            html_content='<html>Test</html>',
            plain_text='Test'
        )
        
        # Should have made 3 API calls for 3 batches
        assert mock_ses.send_email.call_count == 3
        assert result['delivered'] == 125
        assert result['failed'] == 0
    
    @patch('iridia_daily.newsletter_handler.ses')
    def test_send_newsletter_handles_partial_failure(self, mock_ses):
        """Test newsletter sending with some batch failures."""
        from iridia_daily.newsletter_handler import send_newsletter
        
        # First two batches succeed, third fails
        mock_ses.send_email.side_effect = [
            {'MessageId': 'msg-1'},
            {'MessageId': 'msg-2'},
            Exception("Network error")
        ]
        
        subscribers = [f'user{i}@test.com' for i in range(125)]
        
        result = send_newsletter(
            subscribers=subscribers,
            sender_email='research@iridia-daily.com',
            subject='Test',
            html_content='<html>Test</html>',
            plain_text='Test'
        )
        
        assert result['delivered'] == 100  # 2 successful batches
        assert result['failed'] == 25  # 1 failed batch