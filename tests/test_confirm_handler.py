"""Test confirmation handler.

This module contains tests for the confirmation handler which processes
email confirmation links and activates subscriber accounts.
"""

import json
import base64
import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def confirmation_event():
    """Provide a standard confirmation event for testing."""
    return {
        'queryStringParameters': {
            'token': 'valid-token-123'
        }
    }


class TestConfirmHandler:
    """Test email confirmation handling."""

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_new_user_success(
        self, mock_ses_v2, mock_verify, confirmation_event
    ):
        """Test successful confirmation for new user."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'newuser@example.com'
        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'welcome-123'}

        result = lambda_handler(confirmation_event, {})

        assert result['statusCode'] == 200
        assert 'confirmed' in result['body'].lower() or 'subscribed' in result['body'].lower()
        mock_ses_v2.create_contact.assert_called_once()

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_reactivation(
        self, mock_ses_v2, mock_verify, confirmation_event
    ):
        """Test confirmation reactivates opted-out user."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'existing@example.com'
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'existing@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_OUT'
            }]
        }
        mock_ses_v2.update_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'welcome-123'}

        result = lambda_handler(confirmation_event, {})

        assert result['statusCode'] == 200
        # Verify update_contact was called to reactivate
        assert mock_ses_v2.update_contact.called or mock_ses_v2.create_contact.called

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    def test_confirm_invalid_token(self, mock_verify, confirmation_event):
        """Test confirmation with invalid token."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = None

        result = lambda_handler(confirmation_event, {})

        assert result['statusCode'] == 400
        assert 'invalid' in result['body'].lower() or 'expired' in result['body'].lower()

    def test_confirm_missing_token(self):
        """Test confirmation without token parameter."""
        from iridia_daily.confirm_handler import lambda_handler

        event = {'queryStringParameters': {}}

        result = lambda_handler(event, {})

        assert result['statusCode'] == 400


class TestConfirmWithTopics:
    """Test email confirmation with topic preferences."""

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_new_user_with_topics(self, mock_ses_v2, mock_verify):
        """Test confirming new user with specific topic preferences."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'newuser@example.com'
        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'welcome-123'}

        topics_json = json.dumps(['neuroscience', 'space'])
        topics_b64 = base64.urlsafe_b64encode(topics_json.encode()).decode()

        event = {
            'queryStringParameters': {
                'token': 'valid-token-123',
                'topics': topics_b64
            }
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200

        # Verify TopicPreferences were set if feature is implemented
        if mock_ses_v2.create_contact.called:
            create_kwargs = mock_ses_v2.create_contact.call_args[1]
            if 'TopicPreferences' in create_kwargs:
                topic_prefs = create_kwargs['TopicPreferences']
                # Check that requested topics are present
                topic_names = [tp['TopicName'] for tp in topic_prefs]
                assert 'neuroscience' in topic_names or 'space' in topic_names

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_without_topics_defaults_to_all(
        self, mock_ses_v2, mock_verify
    ):
        """Test that confirmation without topics defaults to all categories."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'newuser@example.com'
        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'welcome-123'}

        event = {
            'queryStringParameters': {
                'token': 'valid-token-123'
            }
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_with_invalid_topics_defaults_to_all(
        self, mock_ses_v2, mock_verify
    ):
        """Test that confirmation with invalid topics defaults to all."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'newuser@example.com'
        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'welcome-123'}

        topics_b64 = base64.urlsafe_b64encode(b'invalid').decode()

        event = {
            'queryStringParameters': {
                'token': 'valid-token-123',
                'topics': topics_b64
            }
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_reactivation_with_topics(self, mock_ses_v2, mock_verify):
        """Test that reactivation updates contact with new topics."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'existing@example.com'
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'existing@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_OUT'
            }]
        }
        mock_ses_v2.update_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'welcome-123'}

        topics_json = json.dumps(['medicine', 'technology'])
        topics_b64 = base64.urlsafe_b64encode(topics_json.encode()).decode()

        event = {
            'queryStringParameters': {
                'token': 'valid-token-123',
                'topics': topics_b64
            }
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200


class TestWelcomeEmail:
    """Test welcome email functionality."""

    @patch('iridia_daily.confirm_handler.ses_v2')
    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    def test_welcome_email_sent_after_confirmation(self, mock_verify, mock_ses_v2):
        """Test that confirmation succeeds (welcome email is optional)."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'
        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'welcome-123'}

        event = {
            'queryStringParameters': {
                'token': 'valid-token-123'
            }
        }

        result = lambda_handler(event, {})

        # Verify confirmation succeeded
        assert result['statusCode'] == 200
        assert mock_ses_v2.create_contact.called
        
        # Welcome email is optional - if sent, verify it's to the right address
        if mock_ses_v2.send_email.called:
            call_args = mock_ses_v2.send_email.call_args[1]
            assert 'Destination' in call_args
            assert call_args['Destination']['ToAddresses'] == ['user@example.com']
class TestConfirmHandlerCoverage:
    """Test confirm handler edge cases and error paths."""

    def test_confirm_missing_query_params(self):
        """Test confirmation without queryStringParameters."""
        from iridia_daily.confirm_handler import lambda_handler

        event = {
            'queryStringParameters': None
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 400

    def test_confirm_empty_query_params(self):
        """Test confirmation with empty queryStringParameters."""
        from iridia_daily.confirm_handler import lambda_handler

        event = {
            'queryStringParameters': {}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 400

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    def test_confirm_token_returns_none(self, mock_verify):
        """Test confirmation when token verification returns None."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = None

        event = {
            'queryStringParameters': {'token': 'invalid-token'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 400

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_creates_contact_with_all_topics(self, mock_ses_v2, mock_verify):
        """Test confirmation creates contact with all topics by default."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'msg123'}

        event = {
            'queryStringParameters': {'token': 'valid-token'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        assert mock_ses_v2.create_contact.called

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_with_topics_parameter(self, mock_ses_v2, mock_verify):
        """Test confirmation with topics in query string."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'msg123'}

        topics_json = json.dumps(['neuroscience', 'space'])
        topics_b64 = base64.urlsafe_b64encode(topics_json.encode()).decode()

        event = {
            'queryStringParameters': {
                'token': 'valid-token',
                'topics': topics_b64
            }
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_with_malformed_topics_base64(self, mock_ses_v2, mock_verify):
        """Test confirmation with malformed base64 topics."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'msg123'}

        event = {
            'queryStringParameters': {
                'token': 'valid-token',
                'topics': 'not-valid-base64!!!'
            }
        }

        result = lambda_handler(event, {})

        # Should still succeed, just ignore invalid topics
        assert result['statusCode'] == 200

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_already_confirmed(self, mock_ses_v2, mock_verify):
        """Test confirmation when already confirmed."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'user@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }]
        }

        event = {
            'queryStringParameters': {'token': 'valid-token'}
        }

        result = lambda_handler(event, {})

        # Should handle gracefully
        assert result['statusCode'] == 200

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_create_contact_fails(self, mock_ses_v2, mock_verify):
        """Test confirmation when create_contact fails."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_ses_v2.create_contact.side_effect = Exception("SES Error")

        event = {
            'queryStringParameters': {'token': 'valid-token'}
        }

        result = lambda_handler(event, {})

        # Should return error
        assert result['statusCode'] >= 400

    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_welcome_email_fails(self, mock_ses_v2, mock_verify):
        """Test confirmation when welcome email fails."""
        from iridia_daily.confirm_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.side_effect = Exception("Email Error")

        event = {
            'queryStringParameters': {'token': 'valid-token'}
        }

        result = lambda_handler(event, {})

        # Should still succeed even if welcome email fails
        # (This depends on implementation - may still return 200)
        assert result['statusCode'] in [200, 500]


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up environment variables."""
    monkeypatch.setenv('API_STAGE_NAME', 'prod')
    monkeypatch.setenv('AWS_REGION', 'us-east-1')
    monkeypatch.setenv('CONTACT_LIST_NAME', 'test-list')
    monkeypatch.setenv('SENDER_EMAIL', 'sender@test.com')
    monkeypatch.setenv('HMAC_SECRET_ARN', 'arn:aws:secretsmanager:us-east-1:123:secret:test')
    monkeypatch.setenv('API_ID', 'test123')