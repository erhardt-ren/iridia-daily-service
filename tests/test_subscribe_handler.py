"""Tests for subscription handler."""

import pytest
from unittest.mock import Mock, patch
import json


class TestSubscribeHandler:
    """Test subscription request handling."""
    
    @patch('iridia_daily.subscribe_handler.ses_v2')  # Patch module-level client
    def test_subscribe_new_user_success(self, mock_ses_v2):
        """Test successful new user subscription."""
        from iridia_daily.subscribe_handler import lambda_handler
        
        # Setup mocks
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'test'}
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': 'newuser@example.com'})
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'subscribed' in body['message'].lower()
        mock_ses_v2.create_contact.assert_called_once()
    
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_already_subscribed(self, mock_ses_v2):
        """Test subscribing with an already active subscription."""
        from iridia_daily.subscribe_handler import lambda_handler
        
        # Mock existing OPT_IN contact
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'existing@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }]
        }
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': 'existing@example.com'})
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'already subscribed' in body['message'].lower()
    
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_resubscribe_previously_unsubscribed(self, mock_ses_v2):
        """Test resubscribing a previously unsubscribed user."""
        from iridia_daily.subscribe_handler import lambda_handler
        
        # Mock existing OPT_OUT contact
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'comeback@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_OUT'
            }]
        }
        mock_ses_v2.update_contact.return_value = {}
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': 'comeback@example.com'})
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'resubscribed' in body['message'].lower()
        mock_ses_v2.update_contact.assert_called_once()
    
    def test_subscribe_invalid_email_format(self):
        """Test subscription with invalid email format."""
        from iridia_daily.subscribe_handler import lambda_handler
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': 'not-an-email'})
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'invalid' in body['error'].lower()
    
    def test_subscribe_missing_email(self):
        """Test subscription without email field."""
        from iridia_daily.subscribe_handler import lambda_handler
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps({})
        }
        
        result = lambda_handler(event, {})
        
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
    
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_ses_error(self, mock_ses_v2):
        """Test handling of SES API errors."""
        from iridia_daily.subscribe_handler import lambda_handler
        
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_ses_v2.create_contact.side_effect = Exception("SES Error")
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': 'error@example.com'})
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 500
    
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_subscribe_email_normalization(self, mock_ses_v2):
        """Test that emails are normalized to lowercase."""
        from iridia_daily.subscribe_handler import lambda_handler
        
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'test'}
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps({'email': '  Test.User@EXAMPLE.COM  '})
        }
        
        lambda_handler(event, {})
        
        # Verify email was normalized
        call_kwargs = mock_ses_v2.create_contact.call_args[1]
        assert call_kwargs['EmailAddress'] == 'test.user@example.com'


class TestEmailValidation:
    """Test email validation logic."""
    
    @pytest.mark.parametrize("email,expected", [
        ("valid@example.com", True),
        ("user.name@example.co.uk", True),
        ("user+tag@example.com", True),
        ("not-an-email", False),
        ("@example.com", False),
        ("user@", False),
        ("user space@example.com", False),
        ("", False),
    ])
    def test_is_valid_email(self, email, expected):
        """Test email validation function."""
        from iridia_daily.subscribe_handler import is_valid_email
        
        assert is_valid_email(email) == expected


class TestWelcomeEmail:
    """Test welcome email functionality."""
    
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_send_welcome_email(self, mock_ses_v2):
        """Test that welcome email is sent to new subscribers."""
        from iridia_daily.subscribe_handler import send_welcome_email
        
        mock_ses_v2.send_email.return_value = {'MessageId': 'welcome-123'}
        
        send_welcome_email('newuser@example.com')
        
        # Verify email was sent
        mock_ses_v2.send_email.assert_called_once()
        call_kwargs = mock_ses_v2.send_email.call_args[1]
        
        assert call_kwargs['Destination']['ToAddresses'] == ['newuser@example.com']
        assert 'Welcome' in call_kwargs['Content']['Simple']['Subject']['Data']
        assert 'Iridia Daily' in call_kwargs['FromEmailAddress']
    
    @patch('iridia_daily.subscribe_handler.ses_v2')
    def test_send_welcome_email_handles_errors(self, mock_ses_v2):
        """Test that welcome email errors don't break subscription."""
        from iridia_daily.subscribe_handler import send_welcome_email
        
        mock_ses_v2.send_email.side_effect = Exception("Email send failed")
        
        # Should not raise exception
        send_welcome_email('user@example.com')