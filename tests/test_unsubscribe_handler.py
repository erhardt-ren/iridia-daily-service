"""Tests for unsubscribe handler."""

import pytest
from unittest.mock import Mock, patch


class TestUnsubscribeHandler:
    """Test unsubscribe request handling."""

    @patch('iridia_daily.unsubscribe_handler.verify_unsubscribe_token')
    @patch('iridia_daily.unsubscribe_handler.ses_v2')
    def test_unsubscribe_success(self, mock_ses_v2, mock_verify):
        """Test successful unsubscribe."""
        from iridia_daily.unsubscribe_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'user@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }]
        }
        mock_ses_v2.update_contact.return_value = {}

        event = {
            'queryStringParameters': {'token': 'valid-token-abc123'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        assert 'Unsubscribed' in result['body']
        assert 'user@example.com' in result['body']
        mock_ses_v2.update_contact.assert_called_once()
        mock_verify.assert_called_once_with('valid-token-abc123')

    @patch('iridia_daily.unsubscribe_handler.verify_unsubscribe_token')
    @patch('iridia_daily.unsubscribe_handler.ses_v2')
    def test_unsubscribe_already_unsubscribed(self, mock_ses_v2, mock_verify):
        """Test unsubscribing when already unsubscribed."""
        from iridia_daily.unsubscribe_handler import lambda_handler

        mock_verify.return_value = 'already@example.com'
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'already@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_OUT'
            }]
        }

        event = {
            'queryStringParameters': {'token': 'valid-token-xyz'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        assert 'Already Unsubscribed' in result['body']

    @patch('iridia_daily.unsubscribe_handler.verify_unsubscribe_token')
    def test_unsubscribe_invalid_token(self, mock_verify):
        """Test unsubscribe with invalid token."""
        from iridia_daily.unsubscribe_handler import lambda_handler

        mock_verify.return_value = None

        event = {
            'queryStringParameters': {'token': 'invalid-token'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 400
        assert 'Invalid' in result['body']

    @patch('iridia_daily.unsubscribe_handler.verify_unsubscribe_token')
    @patch('iridia_daily.unsubscribe_handler.ses_v2')
    def test_unsubscribe_user_not_found(self, mock_ses_v2, mock_verify):
        """Test unsubscribing non-existent user."""
        from iridia_daily.unsubscribe_handler import lambda_handler

        mock_verify.return_value = 'notfound@example.com'
        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )

        event = {
            'queryStringParameters': {'token': 'valid-token'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 404
        assert 'Not Found' in result['body']

    def test_unsubscribe_missing_token(self):
        """Test unsubscribe without token parameter."""
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

    @patch('iridia_daily.unsubscribe_handler.verify_unsubscribe_token')
    @patch('iridia_daily.unsubscribe_handler.ses_v2')
    def test_unsubscribe_ses_error(self, mock_ses_v2, mock_verify):
        """Test handling of SES errors during unsubscribe."""
        from iridia_daily.unsubscribe_handler import lambda_handler

        mock_verify.return_value = 'error@example.com'
        mock_ses_v2.get_contact.side_effect = Exception("SES Error")

        event = {
            'queryStringParameters': {'token': 'valid-token'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 500
        assert 'Wrong' in result['body'] or 'Error' in result['body']

    @patch('iridia_daily.unsubscribe_handler.verify_unsubscribe_token')
    def test_unsubscribe_tampered_token(self, mock_verify):
        """Test unsubscribe with tampered token."""
        from iridia_daily.unsubscribe_handler import lambda_handler

        mock_verify.return_value = None

        event = {
            'queryStringParameters': {'token': 'tampered-token-12345'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 400
        mock_verify.assert_called_once_with('tampered-token-12345')


class TestRenderHTML:
    """Test HTML rendering functionality."""

    def test_render_html_structure(self):
        """Test that rendered HTML has proper structure."""
        from iridia_daily.unsubscribe_handler import render_html

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
        from iridia_daily.unsubscribe_handler import render_html

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

    @patch('iridia_daily.unsubscribe_handler.verify_unsubscribe_token')
    @patch('iridia_daily.unsubscribe_handler.ses_v2')
    def test_unsubscribe_complete_workflow(self, mock_ses_v2, mock_verify):
        """Test complete unsubscribe workflow with token."""
        from iridia_daily.unsubscribe_handler import lambda_handler

        mock_verify.return_value = 'workflow@example.com'
        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'workflow@example.com',
            'TopicPreferences': [{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }]
        }
        mock_ses_v2.update_contact.return_value = {}

        event = {
            'queryStringParameters': {'token': 'secure-token-abc123'}
        }
        result = lambda_handler(event, {})

        assert result['statusCode'] == 200

        mock_verify.assert_called_once_with('secure-token-abc123')

        mock_ses_v2.get_contact.assert_called_once_with(
            ContactListName='iridia-daily-subscribers',
            EmailAddress='workflow@example.com'
        )

        mock_ses_v2.update_contact.assert_called_once()
        update_kwargs = mock_ses_v2.update_contact.call_args[1]
        assert update_kwargs['EmailAddress'] == 'workflow@example.com'
        assert (update_kwargs['TopicPreferences'][0]['SubscriptionStatus']
                == 'OPT_OUT')

        assert 'Unsubscribed' in result['body']
        assert 'workflow@example.com' in result['body']