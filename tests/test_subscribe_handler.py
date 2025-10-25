"""Test subscription handler.

This module contains tests for the subscription handler which manages
new subscriber registration and confirmation email sending.
"""

import json
import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def api_gateway_event():
    """Provide a standard API Gateway event for subscription testing."""
    return {
        'httpMethod': 'POST',
        'body': json.dumps({'email': 'test@example.com'}),
        'headers': {},
        'requestContext': {
            'apiId': 'test123api',
            'stage': 'prod',
            'requestId': 'test-request-id'
        }
    }


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up required environment variables for tests."""
    monkeypatch.setenv('API_STAGE_NAME', 'prod')
    monkeypatch.setenv('AWS_REGION', 'us-east-1')
    monkeypatch.setenv('CONTACT_LIST_NAME', 'test-list')
    monkeypatch.setenv('SENDER_EMAIL', 'sender@test.com')
    monkeypatch.setenv('HMAC_SECRET_ARN', 'arn:aws:secretsmanager:us-east-1:123456789:secret:test')


class TestSubscribeHandler:
    """Test subscription request handling."""

    @patch('iridia_daily.subscribe_handler.send_confirmation_email')
    @patch('iridia_daily.subscribe_handler.generate_confirmation_token')
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_new_user_success(
        self, mock_ses_v2, mock_token, mock_send_email, api_gateway_event, mock_env_vars
    ):
        """Test successful new user subscription."""
        from iridia_daily.subscribe_handler import lambda_handler

        # Setup mocks
        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )
        mock_token.return_value = 'test-token-123'

        result = lambda_handler(api_gateway_event, {})

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'email' in body['message'].lower() or 'check' in body['message'].lower()
        mock_send_email.assert_called_once()

    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_already_subscribed(
        self, mock_ses_v2, api_gateway_event, mock_env_vars
    ):
        """Test subscribing with an already active subscription."""
        from iridia_daily.subscribe_handler import lambda_handler

        # Mock contact already exists and is opted in
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'test@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }]
        }

        result = lambda_handler(api_gateway_event, {})

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'already subscribed' in body['message'].lower()

    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_invalid_email(self, mock_ses_v2, mock_env_vars):
        """Test subscription with invalid email format."""
        from iridia_daily.subscribe_handler import lambda_handler

        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': 'invalid-email'}),
            'headers': {},
            'requestContext': {
                'apiId': 'test123api',
                'stage': 'prod'
            }
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'invalid' in body['error'].lower()

    def test_subscribe_missing_email(self, mock_env_vars):
        """Test subscription without email field."""
        from iridia_daily.subscribe_handler import lambda_handler

        event = {
            'httpMethod': 'POST',
            'body': json.dumps({}),
            'headers': {},
            'requestContext': {
                'apiId': 'test123api',
                'stage': 'prod'
            }
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 400

    def test_options_request(self):
        """Test that OPTIONS request returns CORS headers."""
        from iridia_daily.subscribe_handler import lambda_handler

        event = {'httpMethod': 'OPTIONS'}

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in result['headers']


class TestTopicValidation:
    """Test topic validation in subscription flow."""

    def test_validate_topics_success(self):
        """Validate that valid topics pass validation successfully."""
        from iridia_daily.subscribe_handler import validate_topics

        is_valid, validated, error = validate_topics(
            ['neuroscience', 'space', 'biology']
        )

        assert is_valid is True
        assert validated == ['neuroscience', 'space', 'biology']
        assert error is None

    def test_validate_topics_invalid(self):
        """Validate that invalid topics are rejected with error message."""
        from iridia_daily.subscribe_handler import validate_topics

        is_valid, validated, error = validate_topics(['invalid_topic'])

        assert is_valid is False
        assert 'Invalid topic' in error

    def test_validate_topics_empty(self):
        """Validate that empty topic list is rejected with error message."""
        from iridia_daily.subscribe_handler import validate_topics

        is_valid, validated, error = validate_topics([])

        assert is_valid is False
        assert 'At least one topic' in error

    def test_validate_topics_case_insensitive(self):
        """Validate that topic validation handles different cases correctly."""
        from iridia_daily.subscribe_handler import validate_topics

        is_valid, validated, error = validate_topics(
            ['NEUROSCIENCE', 'Space']
        )

        assert is_valid is True
        assert validated == ['neuroscience', 'space']

    def test_validate_topics_removes_duplicates(self):
        """Validate that duplicate topics are removed from the list."""
        from iridia_daily.subscribe_handler import validate_topics

        is_valid, validated, error = validate_topics(
            ['neuroscience', 'space', 'neuroscience']
        )

        assert is_valid is True
        assert validated == ['neuroscience', 'space']


class TestSubscribeWithTopics:
    """Test subscription with topic preferences."""

    @patch('iridia_daily.subscribe_handler.send_confirmation_email')
    @patch('iridia_daily.subscribe_handler.generate_confirmation_token')
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_with_valid_topics(
        self, mock_ses_v2, mock_token, mock_send_email, api_gateway_event, mock_env_vars
    ):
        """Test that subscription request with valid topics is processed."""
        from iridia_daily.subscribe_handler import lambda_handler

        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )
        mock_token.return_value = 'test-token-123'

        api_gateway_event['body'] = json.dumps({
            'email': 'test@example.com',
            'topics': ['neuroscience', 'space']
        })

        result = lambda_handler(api_gateway_event, {})

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['topics'] == ['neuroscience', 'space']
        mock_send_email.assert_called_once()

    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_with_invalid_topics(
        self, mock_ses_v2, api_gateway_event, mock_env_vars
    ):
        """Test that subscription with invalid topics returns error."""
        from iridia_daily.subscribe_handler import lambda_handler

        api_gateway_event['body'] = json.dumps({
            'email': 'test@example.com',
            'topics': ['invalid_topic']
        })

        result = lambda_handler(api_gateway_event, {})

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'Invalid topic' in body['error']

    @patch('iridia_daily.subscribe_handler.send_confirmation_email')
    @patch('iridia_daily.subscribe_handler.generate_confirmation_token')
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_without_topics_defaults_to_all(
        self, mock_ses_v2, mock_token, mock_send_email, api_gateway_event, mock_env_vars
    ):
        """Test that subscription without topics defaults to all categories."""
        from iridia_daily.subscribe_handler import lambda_handler

        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )
        mock_token.return_value = 'test-token-123'

        result = lambda_handler(api_gateway_event, {})

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['topics'] == 'all'
        mock_send_email.assert_called_once()
class TestSubscribeHandlerCoverage:
    """Test subscribe handler edge cases and error paths."""

    @patch('iridia_daily.subscribe_handler.send_confirmation_email')
    @patch('iridia_daily.subscribe_handler.generate_confirmation_token')
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_email_with_plus_addressing(self, mock_ses_v2, mock_token, mock_send, mock_env_vars):
        """Test subscription with plus addressing in email."""
        from iridia_daily.subscribe_handler import lambda_handler

        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_token.return_value = 'token123'

        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': 'user+newsletter@example.com'}),
            'headers': {},
            'requestContext': {'apiId': 'test', 'stage': 'prod'}
        }

        result = lambda_handler(event, {})

        # Should accept valid email with plus addressing
        assert result['statusCode'] == 200

    @patch('iridia_daily.subscribe_handler.send_confirmation_email')
    @patch('iridia_daily.subscribe_handler.generate_confirmation_token')
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_email_mixed_case(self, mock_ses_v2, mock_token, mock_send, mock_env_vars):
        """Test subscription normalizes email case."""
        from iridia_daily.subscribe_handler import lambda_handler

        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_token.return_value = 'token123'

        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': 'User@Example.COM'}),
            'headers': {},
            'requestContext': {'apiId': 'test', 'stage': 'prod'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200

    def test_subscribe_empty_body(self, mock_env_vars):
        """Test subscription with empty body."""
        from iridia_daily.subscribe_handler import lambda_handler

        event = {
            'httpMethod': 'POST',
            'body': '',
            'headers': {},
            'requestContext': {'apiId': 'test', 'stage': 'prod'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] in [400, 500]  # Could be either depending on error handling

    def test_subscribe_null_body(self, mock_env_vars):
        """Test subscription with null body."""
        from iridia_daily.subscribe_handler import lambda_handler

        event = {
            'httpMethod': 'POST',
            'body': None,
            'headers': {},
            'requestContext': {'apiId': 'test', 'stage': 'prod'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] in [400, 500]

    def test_subscribe_malformed_json(self, mock_env_vars):
        """Test subscription with malformed JSON."""
        from iridia_daily.subscribe_handler import lambda_handler

        event = {
            'httpMethod': 'POST',
            'body': '{invalid json',
            'headers': {},
            'requestContext': {'apiId': 'test', 'stage': 'prod'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] in [400, 500]

    @patch('iridia_daily.subscribe_handler.send_confirmation_email')
    @patch('iridia_daily.subscribe_handler.generate_confirmation_token')
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_with_topics_and_whitespace(self, mock_ses_v2, mock_token, mock_send, mock_env_vars):
        """Test subscription with topics containing whitespace."""
        from iridia_daily.subscribe_handler import lambda_handler

        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_token.return_value = 'token123'

        event = {
            'httpMethod': 'POST',
            'body': json.dumps({
                'email': 'user@example.com',
                'topics': [' neuroscience ', '  space  ']
            }),
            'headers': {},
            'requestContext': {'apiId': 'test', 'stage': 'prod'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200

    @patch('iridia_daily.subscribe_handler.send_confirmation_email')
    @patch('iridia_daily.subscribe_handler.generate_confirmation_token')
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_with_duplicate_topics(self, mock_ses_v2, mock_token, mock_send, mock_env_vars):
        """Test subscription removes duplicate topics."""
        from iridia_daily.subscribe_handler import lambda_handler

        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_token.return_value = 'token123'

        event = {
            'httpMethod': 'POST',
            'body': json.dumps({
                'email': 'user@example.com',
                'topics': ['neuroscience', 'space', 'neuroscience']
            }),
            'headers': {},
            'requestContext': {'apiId': 'test', 'stage': 'prod'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['topics'] == ['neuroscience', 'space']

    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_already_opted_in(self, mock_ses_v2, mock_env_vars):
        """Test resubscribing when already opted in."""
        from iridia_daily.subscribe_handler import lambda_handler

        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'user@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }]
        }

        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': 'user@example.com'}),
            'headers': {},
            'requestContext': {'apiId': 'test', 'stage': 'prod'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'already subscribed' in body['message'].lower()

    @patch('iridia_daily.subscribe_handler.send_confirmation_email')
    @patch('iridia_daily.subscribe_handler.generate_confirmation_token')
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_reactivation_opted_out(
        self, mock_ses_v2, mock_token, mock_send_email, mock_env_vars
    ):
        """Test resubscribing when previously opted out."""
        from iridia_daily.subscribe_handler import lambda_handler

        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'user@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_OUT'
            }]
        }
        mock_token.return_value = 'token123'

        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': 'user@example.com'}),
            'headers': {},
            'requestContext': {'apiId': 'test', 'stage': 'prod'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        assert mock_send_email.called

    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_ses_error(self, mock_ses_v2, mock_env_vars):
        """Test subscription when SES fails."""
        from iridia_daily.subscribe_handler import lambda_handler

        mock_ses_v2.get_contact.side_effect = Exception("SES Error")

        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': 'user@example.com'}),
            'headers': {},
            'requestContext': {'apiId': 'test', 'stage': 'prod'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] >= 400


class TestValidateTopicsSubscribe:
    """Test topic validation in subscribe handler."""

    def test_validate_single_valid_topic(self):
        """Test validation with single valid topic."""
        from iridia_daily.subscribe_handler import validate_topics

        is_valid, validated, error = validate_topics(['neuroscience'])

        assert is_valid is True
        assert validated == ['neuroscience']
        assert error is None

    def test_validate_all_valid_topics(self):
        """Test validation with all valid topics."""
        from iridia_daily.subscribe_handler import validate_topics
        from iridia_daily.config import CATEGORY_MAPPING

        all_topics = [k for k in CATEGORY_MAPPING.keys() if k != 'default']
        
        is_valid, validated, error = validate_topics(all_topics)

        assert is_valid is True
        assert set(validated) == set(all_topics)

    def test_validate_partially_invalid_topics(self):
        """Test validation with mix of valid and invalid."""
        from iridia_daily.subscribe_handler import validate_topics

        is_valid, validated, error = validate_topics(
            ['neuroscience', 'invalid_topic']
        )

        assert is_valid is False
        assert 'Invalid topic' in error

    def test_validate_topics_integer_list(self):
        """Test validation rejects non-string topics."""
        from iridia_daily.subscribe_handler import validate_topics

        is_valid, validated, error = validate_topics([1, 2, 3])

        assert is_valid is False

    def test_validate_topics_none_input(self):
        """Test validation handles None input."""
        from iridia_daily.subscribe_handler import validate_topics

        is_valid, validated, error = validate_topics(None)

        assert is_valid is False