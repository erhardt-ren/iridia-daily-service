"""Tests for newsletter generation and distribution."""

import json
import pytest
from unittest.mock import Mock, patch, call
from botocore.exceptions import ClientError


class TestGetApiUrl:
    """Test API Gateway URL discovery."""

    @patch('iridia_daily.newsletter_handler.boto3')
    def test_discovers_api_gateway(self, mock_boto3, monkeypatch):
        """Test API Gateway discovery via CloudFormation API."""
        from iridia_daily.newsletter_handler import get_api_url

        monkeypatch.setenv('AWS_REGION', 'us-east-1')
        monkeypatch.delenv('API_URL', raising=False)

        mock_cfn = Mock()
        mock_cfn.describe_stacks.return_value = {
            'Stacks': [
                {
                    'StackName': 'iridia-daily-stack',
                    'Outputs': [
                        {
                            'OutputKey': 'ApiUrl',
                            'OutputValue': 'https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod'
                        }
                    ]
                }
            ]
        }

        mock_boto3.client.return_value = mock_cfn

        url = get_api_url()

        expected = 'https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod'
        assert url == expected
        mock_cfn.describe_stacks.assert_called_once()

    @patch('iridia_daily.newsletter_handler.boto3')
    def test_uses_environment_variable(self, mock_boto3, monkeypatch):
        """Test that environment variable takes precedence."""
        from iridia_daily.newsletter_handler import get_api_url

        expected_url = 'https://myapi.example.com/prod'
        monkeypatch.setenv('API_URL', expected_url)

        url = get_api_url()

        assert url == expected_url
        mock_boto3.client.assert_not_called()

    @patch('iridia_daily.newsletter_handler.boto3')
    def test_handles_discovery_failure(self, mock_boto3, monkeypatch):
        """Test graceful handling of discovery failure."""
        from iridia_daily.newsletter_handler import get_api_url

        monkeypatch.setenv('AWS_REGION', 'us-east-1')
        monkeypatch.delenv('API_URL', raising=False)

        mock_cfn = Mock()
        mock_cfn.describe_stacks.return_value = {'Stacks': []}
        mock_boto3.client.return_value = mock_cfn

        url = get_api_url()

        assert url == ""


class TestEnsureEmailTemplate:
    """Test email template creation."""

    @patch('iridia_daily.newsletter_handler.ses')
    def test_template_already_exists(self, mock_ses):
        """Test when template already exists."""
        from iridia_daily.newsletter_handler import ensure_email_template

        mock_ses.get_template.return_value = {'Template': {}}

        ensure_email_template()

        mock_ses.get_template.assert_called_once_with(
            TemplateName='IridiaDailyNewsletter'
        )
        mock_ses.create_template.assert_not_called()

    @patch('iridia_daily.newsletter_handler.ses')
    def test_creates_template_when_missing(self, mock_ses):
        """Test template creation when it doesn't exist."""
        from iridia_daily.newsletter_handler import ensure_email_template

        # Mock TemplateDoesNotExist error
        error_response = {
            'Error': {
                'Code': 'TemplateDoesNotExist',
                'Message': 'Template not found'
            }
        }
        mock_ses.get_template.side_effect = ClientError(
            error_response, 'GetTemplate'
        )

        ensure_email_template()

        mock_ses.create_template.assert_called_once()
        call_args = mock_ses.create_template.call_args
        template = call_args[1]['Template']

        assert template['TemplateName'] == 'IridiaDailyNewsletter'
        assert '{{subject}}' in template['SubjectPart']
        assert '{{html_content}}' in template['HtmlPart']
        assert '{{text_content}}' in template['TextPart']


class TestGetApiUrl:
    """Test API Gateway URL discovery."""

    @patch('iridia_daily.newsletter_handler.boto3')
    def test_discovers_api_gateway(self, mock_boto3, monkeypatch):
        """Test API Gateway discovery via CloudFormation API."""
        from iridia_daily.newsletter_handler import get_api_url

        monkeypatch.setenv('AWS_REGION', 'us-east-1')
        monkeypatch.delenv('API_URL', raising=False)

        mock_cfn = Mock()
        mock_cfn.describe_stacks.return_value = {
            'Stacks': [
                {
                    'StackName': 'iridia-daily-stack',
                    'Outputs': [
                        {
                            'OutputKey': 'ApiUrl',
                            'OutputValue': 'https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod'
                        }
                    ]
                }
            ]
        }
        
        mock_boto3.client.return_value = mock_cfn

        url = get_api_url()

        expected = 'https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod'
        assert url == expected
        mock_cfn.describe_stacks.assert_called_once()

    @patch('iridia_daily.newsletter_handler.boto3')
    def test_uses_environment_variable(self, mock_boto3, monkeypatch):
        """Test that environment variable takes precedence."""
        from iridia_daily.newsletter_handler import get_api_url

        expected_url = 'https://myapi.example.com/prod'
        monkeypatch.setenv('API_URL', expected_url)

        url = get_api_url()

        assert url == expected_url
        mock_boto3.client.assert_not_called()

    @patch('iridia_daily.newsletter_handler.boto3')
    def test_handles_discovery_failure(self, mock_boto3, monkeypatch):
        """Test graceful handling of discovery failure."""
        from iridia_daily.newsletter_handler import get_api_url

        monkeypatch.setenv('AWS_REGION', 'us-east-1')
        monkeypatch.delenv('API_URL', raising=False)

        mock_cfn = Mock()
        mock_cfn.describe_stacks.return_value = {'Stacks': []}
        mock_boto3.client.return_value = mock_cfn

        url = get_api_url()

        assert url == ""


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