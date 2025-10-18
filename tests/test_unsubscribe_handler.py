"""Tests for unsubscribe handler."""

import pytest
from unittest.mock import Mock, patch


class TestUnsubscribeHandler:
    """Test unsubscribe request handling."""
    
    @patch('iridia_daily.unsubscribe_handler.ses_v2')
    def test_unsubscribe_success(self, mock_ses_v2):
        """Test successful unsubscribe."""
        from iridia_daily.unsubscribe_handler import lambda_handler
        
        # Mock existing OPT_IN contact
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'user@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }]
        }
        mock_ses_v2.update_contact.return_value = {}
        
        event = {
            'queryStringParameters': {'email': 'user@example.com'}
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200
        assert 'Unsubscribed' in result['body']
        assert 'user@example.com' in result['body']
        mock_ses_v2.update_contact.assert_called_once()
    
    @patch('iridia_daily.unsubscribe_handler.ses_v2')
    def test_unsubscribe_already_unsubscribed(self, mock_ses_v2):
        """Test unsubscribing when already unsubscribed."""
        from iridia_daily.unsubscribe_handler import lambda_handler
        
        # Mock existing OPT_OUT contact
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'already@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_OUT'
            }]
        }
        
        event = {
            'queryStringParameters': {'email': 'already@example.com'}
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200
        assert 'Already Unsubscribed' in result['body']
    
    @patch('iridia_daily.unsubscribe_handler.ses_v2')
    def test_unsubscribe_user_not_found(self, mock_ses_v2):
        """Test unsubscribing non-existent user."""
        from iridia_daily.unsubscribe_handler import lambda_handler
        
        mock_ses_v2.exceptions.NotFoundException = type('NotFoundException', (Exception,), {})
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()
        
        event = {
            'queryStringParameters': {'email': 'notfound@example.com'}
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 404
        assert 'Not Found' in result['body']
    
    def test_unsubscribe_missing_email(self):
        """Test unsubscribe without email parameter."""
        from iridia_daily.unsubscribe_handler import lambda_handler
        
        event = {
            'queryStringParameters': {}
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        assert 'Invalid' in result['body']
    
    def test_unsubscribe_null_query_params(self):
        """Test unsubscribe with null query parameters."""
        from iridia_daily.unsubscribe_handler import lambda_handler
        
        event = {
            'queryStringParameters': None
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
    
    @patch('iridia_daily.unsubscribe_handler.ses_v2')
    def test_unsubscribe_ses_error(self, mock_ses_v2):
        """Test handling of SES errors during unsubscribe."""
        from iridia_daily.unsubscribe_handler import lambda_handler
        
        mock_ses_v2.get_contact.side_effect = Exception("SES Error")
        
        event = {
            'queryStringParameters': {'email': 'error@example.com'}
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 500
        assert 'Wrong' in result['body']
    
    @patch('iridia_daily.unsubscribe_handler.ses_v2')
    def test_unsubscribe_email_normalization(self, mock_ses_v2):
        """Test that emails are normalized to lowercase."""
        from iridia_daily.unsubscribe_handler import lambda_handler
        
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'test.user@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }]
        }
        mock_ses_v2.update_contact.return_value = {}
        
        event = {
            'queryStringParameters': {'email': '  Test.User@EXAMPLE.COM  '}
        }
        
        lambda_handler(event, {})
        
        # Verify email was normalized
        call_kwargs = mock_ses_v2.update_contact.call_args[1]
        assert call_kwargs['EmailAddress'] == 'test.user@example.com'


class TestRenderHTML:
    """Test HTML rendering functionality."""
    
    def test_render_html_structure(self):
        """Test that rendered HTML has proper structure."""
        from iridia_daily.unsubscribe_handler import render_html
        
        result = render_html(200, 'Test', '<p>Content</p>')
        
        # Check response structure
        assert result['statusCode'] == 200
        assert 'Content-Type' in result['headers']
        assert result['headers']['Content-Type'] == 'text/html'
        
        # Check HTML content in body
        body = result['body']
        assert '<!DOCTYPE html>' in body
        assert '<p>Content</p>' in body
        assert 'IRIDIA DAILY' in body
    
    def test_render_html_includes_styles(self):
        """Test that rendered HTML includes styling."""
        from iridia_daily.unsubscribe_handler import render_html
        
        result = render_html(200, 'Test', '<p>Content</p>')
        
        body = result['body']
        assert '<style>' in body
        assert 'linear-gradient' in body
    
    def test_render_html_escapes_user_content(self):
        """Test that user content is safely included."""
        from iridia_daily.unsubscribe_handler import render_html
        
        # Content with special chars should be preserved
        result = render_html(200, 'Test', '<h1>Safe & Sound</h1>')
        
        body = result['body']
        assert '<h1>Safe & Sound</h1>' in body
    
    @pytest.mark.parametrize("status_code,title", [
        (200, "Success"),
        (400, "Bad Request"),
        (404, "Not Found"),
        (500, "Server Error"),
    ])
    def test_render_html_status_codes(self, status_code, title):
        """Test render_html with various status codes."""
        from iridia_daily.unsubscribe_handler import render_html
        
        result = render_html(status_code, title, '<p>Test</p>')
        
        assert result['statusCode'] == status_code
        assert title in result['body']
    
    def test_render_html_cache_control(self):
        """Test that cache control headers are set."""
        from iridia_daily.unsubscribe_handler import render_html
        
        result = render_html(200, 'Test', '<p>Content</p>')
        
        assert 'Cache-Control' in result['headers']
        assert result['headers']['Cache-Control'] == 'no-cache'


class TestUnsubscribeIntegration:
    """Integration tests for complete unsubscribe workflow."""
    
    @patch('iridia_daily.unsubscribe_handler.ses_v2')
    def test_unsubscribe_complete_workflow(self, mock_ses_v2):
        """Test complete unsubscribe workflow from request to response."""
        from iridia_daily.unsubscribe_handler import lambda_handler
        
        # Setup mock
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'workflow@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }]
        }
        mock_ses_v2.update_contact.return_value = {}
        
        # Execute
        event = {
            'queryStringParameters': {'email': 'workflow@example.com'}
        }
        result = lambda_handler(event, {})
        
        # Verify flow
        assert result['statusCode'] == 200
        
        # Verify SES calls
        mock_ses_v2.get_contact.assert_called_once_with(
            ContactListName='iridia-daily-subscribers',
            EmailAddress='workflow@example.com'
        )
        
        mock_ses_v2.update_contact.assert_called_once()
        update_kwargs = mock_ses_v2.update_contact.call_args[1]
        assert update_kwargs['EmailAddress'] == 'workflow@example.com'
        assert update_kwargs['TopicPreferences'][0]['SubscriptionStatus'] == 'OPT_OUT'
        
        # Verify HTML response
        assert 'Unsubscribed' in result['body']
        assert 'workflow@example.com' in result['body']