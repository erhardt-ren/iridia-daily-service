"""Tests for newsletter generation and distribution."""

import json
import pytest
from unittest.mock import Mock, patch, call


class TestGetApiUrl:
    """Test API URL retrieval from environment."""

    def test_get_api_url_from_environment(self, monkeypatch):
        """Test API URL retrieval from environment variable."""
        from iridia_daily.newsletter_handler import get_api_url

        expected_url = 'https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod'
        monkeypatch.setenv('API_URL', expected_url)

        url = get_api_url()

        assert url == expected_url

    def test_get_api_url_missing_raises_error(self, monkeypatch):
        """Test that missing API_URL raises ValueError."""
        from iridia_daily.newsletter_handler import get_api_url

        monkeypatch.delenv('API_URL', raising=False)

        with pytest.raises(ValueError, match="API_URL environment variable is not set"):
            get_api_url()

    def test_get_api_url_strips_whitespace(self, monkeypatch):
        """Test that API URL is stripped of whitespace."""
        from iridia_daily.newsletter_handler import get_api_url

        monkeypatch.setenv('API_URL', '  https://api.example.com/prod  ')

        url = get_api_url()

        assert url == 'https://api.example.com/prod'

    def test_get_api_url_empty_string_raises_error(self, monkeypatch):
        """Test that empty API_URL raises ValueError."""
        from iridia_daily.newsletter_handler import get_api_url

        monkeypatch.setenv('API_URL', '   ')

        with pytest.raises(ValueError, match="API_URL environment variable is not set"):
            get_api_url()


@pytest.mark.integration
class TestNewsletterHandler:
    """Test newsletter generation and distribution."""

    @patch('iridia_daily.newsletter_handler.generate_unsubscribe_token')
    @patch('iridia_daily.newsletter_handler.boto3')
    @patch('iridia_daily.newsletter_handler.ses_v2')
    @patch('urllib.request.urlopen')
    def test_newsletter_complete_flow(
        self, mock_urlopen, mock_ses_v2, mock_boto3,
        mock_unsubscribe_token, mock_pubmed_search, mock_pubmed_fetch,
        comprehensive_pubmed_xml, monkeypatch
    ):
        """Test complete newsletter generation and sending with bulk API."""
        from iridia_daily.newsletter_handler import lambda_handler

        monkeypatch.setenv('AWS_REGION', 'us-east-1')
        monkeypatch.setenv('API_URL', 'https://api.test.com/prod')

        mock_unsubscribe_token.side_effect = lambda email: f'token-{email}'

        pmids = ['12345678', '87654321', '11223344', '44556677', '99887766']
        mock_urlopen.side_effect = [
            mock_pubmed_search(pmids),
            mock_pubmed_fetch(comprehensive_pubmed_xml)
        ]

        mock_ses_v2.list_contacts.return_value = {
            'Contacts': [
                {
                    'EmailAddress': 's1@test.com',
                    'TopicPreferences': [
                        {'SubscriptionStatus': 'OPT_IN'}
                    ]
                },
                {
                    'EmailAddress': 's2@test.com',
                    'TopicPreferences': [
                        {'SubscriptionStatus': 'OPT_IN'}
                    ]
                }
            ]
        }
        
        mock_ses_v2.send_bulk_email.return_value = {
            'BulkEmailEntryResults': [
                {'Status': 'SUCCESS', 'MessageId': 'msg-1'},
                {'Status': 'SUCCESS', 'MessageId': 'msg-2'}
            ]
        }

        def boto3_client_side_effect(service, **kwargs):
            if service == 'bedrock-runtime':
                mock_bedrock = Mock()
                mock_bedrock.invoke_model.return_value = {
                    'body': Mock(
                        read=lambda: json.dumps({
                            'content': [{
                                'text': (
                                    'Paper 1:\nSummary\n\n'
                                    'Paper 2:\nSummary\n\n'
                                    'Paper 3:\nSummary\n\n'
                                    'Paper 4:\nSummary\n\n'
                                    'Paper 5:\nSummary'
                                )
                            }]
                        }).encode()
                    )
                }
                return mock_bedrock
            return Mock()

        mock_boto3.client.side_effect = boto3_client_side_effect

        result = lambda_handler({}, {})

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['subscribers'] == 2
        assert body['papers'] == 5
        
        mock_ses_v2.send_bulk_email.assert_called_once()

    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_newsletter_no_subscribers(self, mock_ses_v2):
        """Test newsletter when no subscribers exist."""
        from iridia_daily.newsletter_handler import lambda_handler

        mock_ses_v2.list_contacts.return_value = {'Contacts': []}

        result = lambda_handler({}, {})

        assert result['statusCode'] == 200
        assert 'No subscribers' in result['body']


class TestGetSubscribers:
    """Test subscriber retrieval."""

    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_filters_opted_in_only(self, mock_ses_v2):
        """Test only OPT_IN subscribers are returned."""
        from iridia_daily.newsletter_handler import get_subscribers

        mock_ses_v2.list_contacts.return_value = {
            'Contacts': [
                {
                    'EmailAddress': 'active@test.com',
                    'TopicPreferences': [
                        {'SubscriptionStatus': 'OPT_IN'}
                    ]
                },
                {
                    'EmailAddress': 'inactive@test.com',
                    'TopicPreferences': [
                        {'SubscriptionStatus': 'OPT_OUT'}
                    ]
                },
            ]
        }

        subscribers = get_subscribers('test-list')

        assert len(subscribers) == 1
        assert 'active@test.com' in subscribers
        assert 'inactive@test.com' not in subscribers

    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_handles_pagination(self, mock_ses_v2):
        """Test pagination with NextToken."""
        from iridia_daily.newsletter_handler import get_subscribers

        mock_ses_v2.list_contacts.side_effect = [
            {
                'Contacts': [
                    {
                        'EmailAddress': 'user1@test.com',
                        'TopicPreferences': [
                            {'SubscriptionStatus': 'OPT_IN'}
                        ]
                    }
                ],
                'NextToken': 'token123'
            },
            {
                'Contacts': [
                    {
                        'EmailAddress': 'user2@test.com',
                        'TopicPreferences': [
                            {'SubscriptionStatus': 'OPT_IN'}
                        ]
                    }
                ]
            }
        ]

        subscribers = get_subscribers('test-list')

        assert len(subscribers) == 2
        assert 'user1@test.com' in subscribers
        assert 'user2@test.com' in subscribers
        assert mock_ses_v2.list_contacts.call_count == 2


class TestSendBulkNewsletters:
    """Test bulk newsletter sending with personalization."""

    @patch('iridia_daily.newsletter_handler.generate_unsubscribe_token')
    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_generates_unique_tokens(self, mock_ses_v2, mock_token):
        """Test unique unsubscribe token per subscriber."""
        from iridia_daily.newsletter_handler import send_bulk_newsletters
        from iridia_daily.email_generator import EmailGenerator

        mock_ses_v2.send_bulk_email.return_value = {
            'BulkEmailEntryResults': [
                {'Status': 'SUCCESS', 'MessageId': 'msg-1'},
                {'Status': 'SUCCESS', 'MessageId': 'msg-2'}
            ]
        }
        mock_token.side_effect = ['token1', 'token2']

        subscribers = ['user1@test.com', 'user2@test.com']
        papers = [{'title': 'T', 'abstract': 'A', 'journal': 'J',
                   'year': '2024', 'url': 'http://test'}]
        summaries = ['Summary']

        result = send_bulk_newsletters(
            subscribers, 'sender@test.com', 'Subject', papers,
            summaries, 'Date', 'https://api.test.com', EmailGenerator()
        )

        assert result['delivered'] == 2
        assert result['failed'] == 0
        assert mock_token.call_count == 2
        mock_ses_v2.send_bulk_email.assert_called_once()

    @patch('iridia_daily.newsletter_handler.generate_unsubscribe_token')
    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_batches_subscribers(self, mock_ses_v2, mock_token):
        """Test subscribers are batched correctly at 50 per batch."""
        from iridia_daily.newsletter_handler import send_bulk_newsletters
        from iridia_daily.email_generator import EmailGenerator

        mock_token.side_effect = lambda email: f'token-{email}'
        
        # First batch: 50 results, Second batch: 25 results
        mock_ses_v2.send_bulk_email.side_effect = [
            {
                'BulkEmailEntryResults': [
                    {'Status': 'SUCCESS', 'MessageId': f'msg-{i}'}
                    for i in range(50)
                ]
            },
            {
                'BulkEmailEntryResults': [
                    {'Status': 'SUCCESS', 'MessageId': f'msg-{i}'}
                    for i in range(25)
                ]
            }
        ]

        subscribers = [f'user{i}@test.com' for i in range(75)]
        papers = [{'title': 'T', 'abstract': 'A', 'journal': 'J',
                   'year': '2024', 'url': 'http://test'}]
        summaries = ['Summary']

        result = send_bulk_newsletters(
            subscribers, 'sender@test.com', 'Subject', papers,
            summaries, 'Date', 'https://api.test.com', EmailGenerator()
        )

        assert result['delivered'] == 75
        assert result['failed'] == 0
        assert mock_ses_v2.send_bulk_email.call_count == 2
        
        first_call_entries = mock_ses_v2.send_bulk_email.call_args_list[0][1]['BulkEmailEntries']
        assert len(first_call_entries) == 50
        
        second_call_entries = mock_ses_v2.send_bulk_email.call_args_list[1][1]['BulkEmailEntries']
        assert len(second_call_entries) == 25

    @patch('iridia_daily.newsletter_handler.generate_unsubscribe_token')
    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_handles_partial_failures(self, mock_ses_v2, mock_token):
        """Test handling of partial failures in bulk send."""
        from iridia_daily.newsletter_handler import send_bulk_newsletters
        from iridia_daily.email_generator import EmailGenerator

        mock_token.side_effect = lambda email: f'token-{email}'
        mock_ses_v2.send_bulk_email.return_value = {
            'BulkEmailEntryResults': [
                {'Status': 'SUCCESS', 'MessageId': 'msg-1'},
                {'Status': 'FAILED', 'Error': 'Mailbox full'},
                {'Status': 'SUCCESS', 'MessageId': 'msg-3'}
            ]
        }

        subscribers = ['user1@test.com', 'user2@test.com', 'user3@test.com']
        papers = [{'title': 'T', 'abstract': 'A', 'journal': 'J',
                   'year': '2024', 'url': 'http://test'}]
        summaries = ['Summary']

        result = send_bulk_newsletters(
            subscribers, 'sender@test.com', 'Subject', papers,
            summaries, 'Date', 'https://api.test.com', EmailGenerator()
        )

        assert result['delivered'] == 2
        assert result['failed'] == 1
        assert 'user2@test.com' in result['failed_emails']

    @patch('iridia_daily.newsletter_handler.generate_unsubscribe_token')
    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_includes_personalized_unsubscribe_urls(
        self, mock_ses_v2, mock_token
    ):
        """Test each email contains personalized unsubscribe URL."""
        from iridia_daily.newsletter_handler import send_bulk_newsletters
        from iridia_daily.email_generator import EmailGenerator

        mock_token.side_effect = ['token1', 'token2']
        mock_ses_v2.send_bulk_email.return_value = {
            'BulkEmailEntryResults': [
                {'Status': 'SUCCESS', 'MessageId': 'msg-1'},
                {'Status': 'SUCCESS', 'MessageId': 'msg-2'}
            ]
        }

        subscribers = ['user1@test.com', 'user2@test.com']
        papers = [{'title': 'T', 'abstract': 'A', 'journal': 'J',
                   'year': '2024', 'url': 'http://test'}]
        summaries = ['Summary']

        send_bulk_newsletters(
            subscribers, 'sender@test.com', 'Subject', papers,
            summaries, 'Date', 'https://api.test.com', EmailGenerator()
        )

        call_args = mock_ses_v2.send_bulk_email.call_args
        bulk_entries = call_args[1]['BulkEmailEntries']

        first_data = json.loads(
            bulk_entries[0]['ReplacementEmailContent']
            ['ReplacementTemplate']['ReplacementTemplateData']
        )
        second_data = json.loads(
            bulk_entries[1]['ReplacementEmailContent']
            ['ReplacementTemplate']['ReplacementTemplateData']
        )

        expected_url_1 = 'https://api.test.com/unsubscribe?token=token1'
        expected_url_2 = 'https://api.test.com/unsubscribe?token=token2'

        assert expected_url_1 in first_data['html_content']
        assert expected_url_2 in second_data['html_content']

    @patch('iridia_daily.newsletter_handler.generate_unsubscribe_token')
    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_handles_batch_api_failure(self, mock_ses_v2, mock_token):
        """Test handling when entire batch API call fails."""
        from iridia_daily.newsletter_handler import send_bulk_newsletters
        from iridia_daily.email_generator import EmailGenerator

        mock_token.side_effect = lambda email: f'token-{email}'
        mock_ses_v2.send_bulk_email.side_effect = Exception('API Error')

        subscribers = ['user1@test.com', 'user2@test.com']
        papers = [{'title': 'T', 'abstract': 'A', 'journal': 'J',
                   'year': '2024', 'url': 'http://test'}]
        summaries = ['Summary']

        result = send_bulk_newsletters(
            subscribers, 'sender@test.com', 'Subject', papers,
            summaries, 'Date', 'https://api.test.com', EmailGenerator()
        )

        assert result['delivered'] == 0
        assert result['failed'] == 2
        assert len(result['failed_emails']) == 2


class TestEmailValidation:
    """Test email validation."""

    @pytest.mark.parametrize("email,expected", [
        ("valid@example.com", True),
        ("user.name+tag@example.co.uk", True),
        ("test123@test-domain.com", True),
        ("not-an-email", False),
        ("@example.com", False),
        ("user@", False),
        ("", False),
        (None, False),
        ("user..name@example.com", False),
        ("user@example", False),
        ("a" * 321, False),
    ])
    def test_is_valid_email(self, email, expected):
        """Test email validation with various formats."""
        from iridia_daily.newsletter_handler import is_valid_email

        assert is_valid_email(email) == expected


class TestNewsletterValidation:
    """Test newsletter validation and error handling."""

    @patch('iridia_daily.newsletter_handler.send_alert_notification')
    @patch('iridia_daily.newsletter_handler.BedrockClient')
    @patch('iridia_daily.newsletter_handler.PubMedClient')
    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_newsletter_fails_on_summary_count_mismatch(
        self, mock_ses_v2, mock_pubmed_class, mock_bedrock_class,
        mock_alert, sample_papers_diverse, monkeypatch
    ):
        """Test newsletter fails when summary count doesn't match papers."""
        from iridia_daily.newsletter_handler import lambda_handler

        monkeypatch.setenv('API_URL', 'https://api.test.com/prod')

        # Mock PubMed to return 5 papers
        mock_pubmed = Mock()
        mock_pubmed.get_recent_papers.return_value = sample_papers_diverse
        mock_pubmed_class.return_value = mock_pubmed

        # Mock Bedrock to return ONLY 3 summaries (mismatch!)
        mock_bedrock = Mock()
        mock_bedrock.generate_summaries.return_value = [
            'Summary one with sufficient length for validation here.',
            'Summary two also has enough characters for the check.',
            'Summary three is the last one but we need five total.'
        ]
        mock_bedrock_class.return_value = mock_bedrock

        mock_ses_v2.list_contacts.return_value = {
            'Contacts': [
                {
                    'EmailAddress': 'test@example.com',
                    'TopicPreferences': [{'SubscriptionStatus': 'OPT_IN'}]
                }
            ]
        }

        result = lambda_handler({}, {})

        assert result['statusCode'] == 500
        # Parse JSON body and check structure
        body = json.loads(result['body'])
        assert body['error'] == 'Summary generation validation failed'
        assert body['expected_summaries'] == 5
        assert body['received_summaries'] == 3
        mock_alert.assert_called_once()