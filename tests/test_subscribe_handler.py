"""Tests for subscription handler."""

import json
import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def api_gateway_event():
    """API Gateway proxy event with requestContext."""
    return {
        'httpMethod': 'POST',
        'body': json.dumps({'email': 'test@example.com'}),
        'requestContext': {
            'apiId': 'abc123xyz',
            'domainName': 'abc123xyz.execute-api.us-east-1.amazonaws.com',
            'stage': 'prod'
        }
    }


class TestGetApiUrl:
    """Test API URL extraction from event."""

    def test_extracts_from_domain_name(self):
        """Test URL extraction using domainName."""
        from iridia_daily.subscribe_handler import get_api_url

        event = {
            'requestContext': {
                'domainName': 'abc123.execute-api.us-east-1.amazonaws.com',
                'stage': 'prod'
            }
        }

        url = get_api_url(event)

        assert url == 'https://abc123.execute-api.us-east-1.amazonaws.com/prod'

    def test_extracts_from_api_id(self, monkeypatch):
        """Test URL extraction using apiId when domainName missing."""
        from iridia_daily.subscribe_handler import get_api_url

        monkeypatch.setenv('AWS_REGION', 'us-east-1')

        event = {
            'requestContext': {
                'apiId': 'xyz789',
                'stage': 'prod'
            }
        }

        url = get_api_url(event)

        assert url == 'https://xyz789.execute-api.us-east-1.amazonaws.com/prod'

    def test_handles_missing_context(self):
        """Test graceful handling of missing requestContext."""
        from iridia_daily.subscribe_handler import get_api_url

        event = {}

        url = get_api_url(event)

        assert url == ""


class TestSubscribeHandler:
    """Test subscription request handling."""

    @patch('iridia_daily.subscribe_handler.generate_confirmation_token')
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_new_user(self, mock_ses_v2, mock_token,
                                api_gateway_event):
        """Test subscription for new user."""
        from iridia_daily.subscribe_handler import lambda_handler

        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )
        mock_token.return_value = 'test-token-123'
        mock_ses_v2.send_email.return_value = {'MessageId': 'msg-123'}

        result = lambda_handler(api_gateway_event, {})

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'check your email' in body['message'].lower()
        mock_ses_v2.send_email.assert_called_once()

    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_already_subscribed(self, mock_ses_v2,
                                          api_gateway_event):
        """Test subscription for already subscribed user."""
        from iridia_daily.subscribe_handler import lambda_handler

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

    def test_subscribe_invalid_email(self, api_gateway_event):
        """Test subscription with invalid email."""
        from iridia_daily.subscribe_handler import lambda_handler

        api_gateway_event['body'] = json.dumps({'email': 'not-an-email'})

        result = lambda_handler(api_gateway_event, {})

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'invalid' in body['error'].lower()

    def test_subscribe_options_request(self):
        """Test CORS preflight OPTIONS request."""
        from iridia_daily.subscribe_handler import lambda_handler

        event = {'httpMethod': 'OPTIONS'}

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in result['headers']

    @patch('iridia_daily.subscribe_handler.generate_confirmation_token')
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_confirmation_url_includes_token(self, mock_ses_v2, mock_token,
                                             api_gateway_event):
        """Test that confirmation email includes correct URL with token."""
        from iridia_daily.subscribe_handler import lambda_handler

        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )
        mock_token.return_value = 'secure-token-xyz'
        mock_ses_v2.send_email.return_value = {'MessageId': 'msg-123'}

        lambda_handler(api_gateway_event, {})

        call_kwargs = mock_ses_v2.send_email.call_args[1]
        html_body = call_kwargs['Content']['Simple']['Body']['Html']['Data']

        expected_url = 'https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod/confirm?token=secure-token-xyz'
        assert expected_url in html_body


class TestEmailValidation:
    """Test email validation."""

    @pytest.mark.parametrize("email,expected", [
        ("valid@example.com", True),
        ("user.name@example.co.uk", True),
        ("user+tag@example.com", True),
        ("not-an-email", False),
        ("@example.com", False),
        ("user@", False),
        ("", False),
    ])
    def test_email_validation(self, email, expected):
        """Test email validation function."""
        from iridia_daily.subscribe_handler import is_valid_email

        assert is_valid_email(email) == expected


class TestConfirmationEmail:
    """Test confirmation email sending."""

    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_send_confirmation_email(self, mock_ses_v2):
        """Test confirmation email is sent with correct content."""
        from iridia_daily.subscribe_handler import send_confirmation_email

        mock_ses_v2.send_email.return_value = {'MessageId': 'msg-123'}

        url = 'https://api.example.com/prod/confirm?token=abc123'
        send_confirmation_email('user@example.com', url)

        mock_ses_v2.send_email.assert_called_once()
        call_kwargs = mock_ses_v2.send_email.call_args[1]

        assert call_kwargs['Destination']['ToAddresses'] == [
            'user@example.com'
        ]
        assert 'Confirm' in call_kwargs['Content']['Simple']['Subject']['Data']

        html = call_kwargs['Content']['Simple']['Body']['Html']['Data']
        assert url in html
        assert 'IRIDIA DAILY' in html

    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_send_confirmation_email_handles_errors(self, mock_ses_v2):
        """Test confirmation email error handling."""
        from iridia_daily.subscribe_handler import send_confirmation_email

        mock_ses_v2.send_email.side_effect = Exception("SES Error")

        with pytest.raises(Exception):
            send_confirmation_email('user@example.com', 'https://test.com')


class TestCorsResponse:
    """Test CORS response builder."""

    def test_cors_headers_included(self):
        """Test CORS headers are included in response."""
        from iridia_daily.subscribe_handler import cors_response

        response = cors_response(200, {'message': 'test'})

        assert 'Access-Control-Allow-Origin' in response['headers']
        assert response['headers']['Access-Control-Allow-Origin'] == '*'

    def test_body_is_json(self):
        """Test response body is JSON serialized."""
        from iridia_daily.subscribe_handler import cors_response

        body_dict = {'message': 'test', 'count': 42}
        response = cors_response(200, body_dict)

        assert isinstance(response['body'], str)
        parsed = json.loads(response['body'])
        assert parsed == body_dict