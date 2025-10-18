"""Tests for email confirmation handler."""

import pytest
from unittest.mock import Mock, patch
import json


class TestConfirmHandler:
    """Test email confirmation request handling."""
    
    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_success_new_user(self, mock_ses_v2, mock_verify):
        """Test successful confirmation for new user."""
        from iridia_daily.confirm_handler import lambda_handler
        
        # Setup mocks
        mock_verify.return_value = 'newuser@example.com'
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'welcome-123'}
        
        event = {
            'queryStringParameters': {'token': 'valid-token-123'}
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200
        assert 'Confirmed' in result['body']
        assert 'newuser@example.com' in result['body']
        mock_ses_v2.create_contact.assert_called_once()
        mock_verify.assert_called_once_with('valid-token-123')
    
    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_already_confirmed(self, mock_ses_v2, mock_verify):
        """Test confirmation when user already confirmed."""
        from iridia_daily.confirm_handler import lambda_handler
        
        mock_verify.return_value = 'existing@example.com'
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'existing@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }]
        }
        
        event = {
            'queryStringParameters': {'token': 'valid-token-123'}
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200
        assert 'Already Subscribed' in result['body']
        mock_ses_v2.create_contact.assert_not_called()
    
    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_reactivate_unsubscribed(self, mock_ses_v2, mock_verify):
        """Test reactivating a previously unsubscribed user."""
        from iridia_daily.confirm_handler import lambda_handler
        
        mock_verify.return_value = 'comeback@example.com'
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'comeback@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_OUT'
            }]
        }
        mock_ses_v2.update_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'welcome-123'}
        
        event = {
            'queryStringParameters': {'token': 'valid-token-123'}
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200
        assert 'Confirmed' in result['body'] or 'reactivated' in result['body'].lower()
        mock_ses_v2.update_contact.assert_called_once()
    
    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    def test_confirm_invalid_token(self, mock_verify):
        """Test confirmation with invalid token."""
        from iridia_daily.confirm_handler import lambda_handler
        
        mock_verify.return_value = None  # Invalid token
        
        event = {
            'queryStringParameters': {'token': 'invalid-token'}
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        assert 'Invalid' in result['body'] or 'Expired' in result['body']
    
    def test_confirm_missing_token(self):
        """Test confirmation without token parameter."""
        from iridia_daily.confirm_handler import lambda_handler
        
        event = {
            'queryStringParameters': {}
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        assert 'Invalid' in result['body']
    
    def test_confirm_null_query_params(self):
        """Test confirmation with null query parameters."""
        from iridia_daily.confirm_handler import lambda_handler
        
        event = {
            'queryStringParameters': None
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
    
    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirm_ses_error(self, mock_ses_v2, mock_verify):
        """Test handling of SES errors during confirmation."""
        from iridia_daily.confirm_handler import lambda_handler
        
        mock_verify.return_value = 'error@example.com'
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_ses_v2.create_contact.side_effect = Exception("SES Error")
        
        event = {
            'queryStringParameters': {'token': 'valid-token-123'}
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 500
        assert 'Wrong' in result['body'] or 'Error' in result['body']


class TestWelcomeEmail:
    """Test welcome email functionality."""
    
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_send_welcome_email_success(self, mock_ses_v2):
        """Test successful welcome email sending."""
        from iridia_daily.confirm_handler import send_welcome_email
        
        mock_ses_v2.send_email.return_value = {'MessageId': 'welcome-123'}
        
        send_welcome_email('newuser@example.com')
        
        mock_ses_v2.send_email.assert_called_once()
        call_kwargs = mock_ses_v2.send_email.call_args[1]
        
        assert call_kwargs['Destination']['ToAddresses'] == ['newuser@example.com']
        assert 'Welcome' in call_kwargs['Content']['Simple']['Subject']['Data']
        assert 'Iridia Daily' in call_kwargs['FromEmailAddress']
    
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_send_welcome_email_handles_errors(self, mock_ses_v2):
        """Test that welcome email errors don't break confirmation."""
        from iridia_daily.confirm_handler import send_welcome_email
        
        mock_ses_v2.send_email.side_effect = Exception("Email send failed")
        
        # Should not raise exception
        send_welcome_email('user@example.com')
    
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_welcome_email_content(self, mock_ses_v2):
        """Test welcome email content is appropriate."""
        from iridia_daily.confirm_handler import send_welcome_email
        
        mock_ses_v2.send_email.return_value = {'MessageId': 'test-123'}
        
        send_welcome_email('user@example.com')
        
        call_kwargs = mock_ses_v2.send_email.call_args[1]
        html_body = call_kwargs['Content']['Simple']['Body']['Html']['Data']
        
        # Should mention key features
        assert 'research' in html_body.lower()
        assert 'daily' in html_body.lower()
        assert 'tomorrow' in html_body.lower() or 'first newsletter' in html_body.lower()


class TestRenderHTML:
    """Test HTML rendering functionality."""
    
    def test_render_html_structure(self):
        """Test that rendered HTML has proper structure."""
        from iridia_daily.confirm_handler import render_html
        
        result = render_html(200, 'Test', '<p>Content</p>')
        
        assert result['statusCode'] == 200
        assert 'Content-Type' in result['headers']
        assert result['headers']['Content-Type'] == 'text/html'
        
        body = result['body']
        assert '<!DOCTYPE html>' in body
        assert '<p>Content</p>' in body
        assert 'IRIDIA DAILY' in body
    
    def test_render_html_includes_styles(self):
        """Test that rendered HTML includes styling."""
        from iridia_daily.confirm_handler import render_html
        
        result = render_html(200, 'Test', '<p>Content</p>')
        
        body = result['body']
        assert '<style>' in body
        assert 'linear-gradient' in body
    
    @pytest.mark.parametrize("status_code,title", [
        (200, "Success"),
        (400, "Bad Request"),
        (404, "Not Found"),
        (500, "Server Error"),
    ])
    def test_render_html_status_codes(self, status_code, title):
        """Test render_html with various status codes."""
        from iridia_daily.confirm_handler import render_html
        
        result = render_html(status_code, title, '<p>Test</p>')
        
        assert result['statusCode'] == status_code
        assert title in result['body']
    
    def test_render_html_cache_control(self):
        """Test that cache control headers are set."""
        from iridia_daily.confirm_handler import render_html
        
        result = render_html(200, 'Test', '<p>Content</p>')
        
        assert 'Cache-Control' in result['headers']
        assert result['headers']['Cache-Control'] == 'no-cache'


class TestConfirmationIntegration:
    """Integration tests for complete confirmation workflow."""
    
    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_complete_confirmation_flow(self, mock_ses_v2, mock_verify):
        """Test complete confirmation flow from request to response."""
        from iridia_daily.confirm_handler import lambda_handler
        
        # Setup
        email = 'complete@example.com'
        token = 'valid-confirmation-token'
        
        mock_verify.return_value = email
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        mock_ses_v2.create_contact.return_value = {}
        mock_ses_v2.send_email.return_value = {'MessageId': 'test-123'}
        
        # Execute
        event = {
            'queryStringParameters': {'token': token}
        }
        result = lambda_handler(event, {})
        
        # Verify flow
        assert result['statusCode'] == 200
        
        # Verify token was checked
        mock_verify.assert_called_once_with(token)
        
        # Verify contact lookup
        mock_ses_v2.get_contact.assert_called_once_with(
            ContactListName='iridia-daily-subscribers',
            EmailAddress=email
        )
        
        # Verify contact creation
        mock_ses_v2.create_contact.assert_called_once()
        create_kwargs = mock_ses_v2.create_contact.call_args[1]
        assert create_kwargs['EmailAddress'] == email
        assert create_kwargs['TopicPreferences'][0]['SubscriptionStatus'] == 'OPT_IN'
        
        # Verify welcome email sent
        mock_ses_v2.send_email.assert_called_once()
        
        # Verify HTML response
        assert 'Confirmed' in result['body']
        assert email in result['body']
    
    @patch('iridia_daily.confirm_handler.verify_confirmation_token')
    @patch('iridia_daily.confirm_handler.ses_v2')
    def test_confirmation_with_retry_logic(self, mock_ses_v2, mock_verify):
        """Test that retry logic works for transient failures."""
        from iridia_daily.confirm_handler import lambda_handler
        
        mock_verify.return_value = 'retry@example.com'
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        
        # First attempt fails, second succeeds
        mock_ses_v2.create_contact.side_effect = [
            Exception("Transient error"),
            {}
        ]
        mock_ses_v2.send_email.return_value = {'MessageId': 'test-123'}
        
        event = {
            'queryStringParameters': {'token': 'valid-token'}
        }
        
        result = lambda_handler(event, {})
        
        # Should eventually succeed after retry
        assert result['statusCode'] == 200
        # create_contact should be called twice due to retry (first fails, second succeeds)
        assert mock_ses_v2.create_contact.call_count == 2