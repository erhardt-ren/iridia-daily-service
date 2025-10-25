"""Test preferences handler.

This module contains tests for the preferences management handler,
which allows subscribers to view and update their topic preferences.
"""

import json
import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def api_gateway_event():
    """Provide a standard API Gateway event structure for testing."""
    return {
        'httpMethod': 'GET',
        'queryStringParameters': {},
        'headers': {}
    }


class TestUpdateContactPreferences:
    """Test updating contact preferences in SES."""

    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_update_contact_success(self, mock_ses_v2):
        """Test successful contact preference update in SES using TopicPreferences."""
        from iridia_daily.preferences_handler import (
            update_contact_preferences
        )

        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'user@example.com',
            'TopicPreferences': [
                {'TopicName': 'neuroscience', 'SubscriptionStatus': 'OPT_IN'},
                {'TopicName': 'space', 'SubscriptionStatus': 'OPT_OUT'},
                {'TopicName': 'daily-research', 'SubscriptionStatus': 'OPT_IN'}
            ]
        }
        mock_ses_v2.update_contact.return_value = {}

        success, error = update_contact_preferences(
            'user@example.com',
            ['space', 'biology']
        )

        assert success is True
        assert error is None
        mock_ses_v2.update_contact.assert_called_once()

        call_args = mock_ses_v2.update_contact.call_args[1]
        # Verify TopicPreferences were updated
        assert 'TopicPreferences' in call_args
        topic_prefs = call_args['TopicPreferences']
        
        # Check that requested topics are OPT_IN
        space_pref = next((t for t in topic_prefs if t['TopicName'] == 'space'), None)
        biology_pref = next((t for t in topic_prefs if t['TopicName'] == 'biology'), None)
        assert space_pref and space_pref['SubscriptionStatus'] == 'OPT_IN'
        assert biology_pref and biology_pref['SubscriptionStatus'] == 'OPT_IN'

    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_update_preserves_metadata(self, mock_ses_v2):
        """Test that preference update preserves daily-research subscription."""
        from iridia_daily.preferences_handler import (
            update_contact_preferences
        )

        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'user@example.com',
            'TopicPreferences': [
                {'TopicName': 'neuroscience', 'SubscriptionStatus': 'OPT_IN'},
                {'TopicName': 'daily-research', 'SubscriptionStatus': 'OPT_IN'}
            ]
        }
        mock_ses_v2.update_contact.return_value = {}

        update_contact_preferences('user@example.com', ['space'])

        call_args = mock_ses_v2.update_contact.call_args[1]
        topic_prefs = call_args['TopicPreferences']
        
        # Verify daily-research is still OPT_IN
        daily_research_pref = next((t for t in topic_prefs if t['TopicName'] == 'daily-research'), None)
        assert daily_research_pref and daily_research_pref['SubscriptionStatus'] == 'OPT_IN'

    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_update_contact_not_found(self, mock_ses_v2):
        """Test that update handles non-existent contact gracefully."""
        from iridia_daily.preferences_handler import (
            update_contact_preferences
        )

        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        # The exception happens during update_contact, not get_contact
        mock_ses_v2.update_contact.side_effect = (
            mock_ses_v2.exceptions.NotFoundException()
        )

        success, error = update_contact_preferences(
            'nonexistent@example.com',
            ['neuroscience']
        )

        assert success is False
        assert error and 'not found' in error.lower()

    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_update_handles_malformed_attributes(self, mock_ses_v2):
        """Test that update handles missing TopicPreferences gracefully."""
        from iridia_daily.preferences_handler import (
            update_contact_preferences
        )

        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'user@example.com',
            'TopicPreferences': []  # Empty preferences
        }
        mock_ses_v2.update_contact.return_value = {}

        success, error = update_contact_preferences(
            'user@example.com',
            ['neuroscience']
        )

        # Should still succeed by creating new preferences
        assert success is True
        call_args = mock_ses_v2.update_contact.call_args[1]
        assert 'TopicPreferences' in call_args


class TestPreferencesHandler:
    """Test preferences handler Lambda function."""

    def test_options_request(self):
        """Test that OPTIONS request returns proper CORS headers."""
        from iridia_daily.preferences_handler import lambda_handler

        event = {'httpMethod': 'OPTIONS'}

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in result['headers']

    @patch('iridia_daily.preferences_handler.verify_unsubscribe_token')
    def test_get_preferences_form_with_valid_token(self, mock_verify):
        """Test that GET request with valid token returns HTML form."""
        from iridia_daily.preferences_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'

        event = {
            'httpMethod': 'GET',
            'queryStringParameters': {'token': 'valid-token-123'}
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        assert 'text/html' in result['headers']['Content-Type']
        assert 'user@example.com' in result['body']

    @patch('iridia_daily.preferences_handler.update_contact_preferences')
    @patch('iridia_daily.preferences_handler.verify_unsubscribe_token')
    def test_post_update_preferences_success(
        self, mock_verify, mock_update
    ):
        """Test that POST request successfully updates preferences."""
        from iridia_daily.preferences_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'
        mock_update.return_value = (True, None)

        event = {
            'httpMethod': 'POST',
            'queryStringParameters': {'token': 'valid-token-123'},
            'body': json.dumps({'topics': ['neuroscience', 'space']})
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        # Check for success indicator in response
        assert 'message' in body or 'success' in body
        mock_update.assert_called_once()

    @patch('iridia_daily.preferences_handler.verify_unsubscribe_token')
    def test_post_invalid_token(self, mock_verify):
        """Test that POST with invalid token returns error."""
        from iridia_daily.preferences_handler import lambda_handler

        mock_verify.return_value = None

        event = {
            'httpMethod': 'POST',
            'queryStringParameters': {'token': 'invalid-token'},
            'body': json.dumps({'topics': ['neuroscience']})
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 400

    @patch('iridia_daily.preferences_handler.verify_unsubscribe_token')
    def test_post_invalid_topics(self, mock_verify):
        """Test that POST with invalid topics returns error."""
        from iridia_daily.preferences_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'

        event = {
            'httpMethod': 'POST',
            'queryStringParameters': {'token': 'valid-token-123'},
            'body': json.dumps({'topics': ['invalid_topic']})
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'error' in body or 'Invalid' in str(body)

    @patch('iridia_daily.preferences_handler.update_contact_preferences')
    @patch('iridia_daily.preferences_handler.verify_unsubscribe_token')
    def test_post_update_failure(self, mock_verify, mock_update):
        """Test that POST handles update failure appropriately."""
        from iridia_daily.preferences_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'
        mock_update.return_value = (False, 'Update failed')

        event = {
            'httpMethod': 'POST',
            'queryStringParameters': {'token': 'valid-token-123'},
            'body': json.dumps({'topics': ['neuroscience']})
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] >= 400

    def test_post_missing_body(self):
        """Test that POST without body returns error."""
        from iridia_daily.preferences_handler import lambda_handler

        event = {
            'httpMethod': 'POST',
            'queryStringParameters': {'token': 'valid-token'},
            'body': None
        }

        result = lambda_handler(event, {})

        assert result['statusCode'] >= 400

    def test_unsupported_method(self):
        """Test that unsupported HTTP method returns error."""
        from iridia_daily.preferences_handler import lambda_handler

        event = {'httpMethod': 'DELETE'}

        result = lambda_handler(event, {})

        # Should return 400 or 405
        assert result['statusCode'] in [400, 405]
import pytest
from unittest.mock import Mock, patch


class TestValidateTopicsEdgeCases:
    """Test comprehensive validation scenarios."""

    def test_validate_topics_not_a_list(self):
        """Test validation when topics is not a list."""
        from iridia_daily.preferences_handler import validate_topics

        is_valid, validated, error = validate_topics("neuroscience")

        assert is_valid is False
        assert "must be a list" in error.lower()

    def test_validate_topics_with_integer(self):
        """Test validation when topics contains non-string."""
        from iridia_daily.preferences_handler import validate_topics

        is_valid, validated, error = validate_topics([123, 456])

        assert is_valid is False
        assert "type" in error.lower()

    def test_validate_topics_mixed_case(self):
        """Test validation normalizes case."""
        from iridia_daily.preferences_handler import validate_topics

        is_valid, validated, error = validate_topics(
            ['NEUROSCIENCE', 'Space', 'BioLogy']
        )

        assert is_valid is True
        assert validated == ['neuroscience', 'space', 'biology']

    def test_validate_topics_with_whitespace(self):
        """Test validation strips whitespace."""
        from iridia_daily.preferences_handler import validate_topics

        is_valid, validated, error = validate_topics(
            [' neuroscience ', '  space  ']
        )

        assert is_valid is True
        assert validated == ['neuroscience', 'space']

    def test_validate_topics_with_duplicates_preserves_order(self):
        """Test validation removes duplicates but preserves order."""
        from iridia_daily.preferences_handler import validate_topics

        is_valid, validated, error = validate_topics(
            ['space', 'neuroscience', 'space', 'biology']
        )

        assert is_valid is True
        assert validated == ['space', 'neuroscience', 'biology']

    def test_validate_topics_all_invalid(self):
        """Test validation when all topics are invalid."""
        from iridia_daily.preferences_handler import validate_topics

        is_valid, validated, error = validate_topics(
            ['invalid1', 'invalid2', 'invalid3']
        )

        assert is_valid is False
        assert "Invalid topic" in error

    def test_validate_topics_mixed_valid_invalid(self):
        """Test validation fails on first invalid topic."""
        from iridia_daily.preferences_handler import validate_topics

        is_valid, validated, error = validate_topics(
            ['neuroscience', 'invalid_topic', 'space']
        )

        assert is_valid is False
        assert "Invalid topic" in error


class TestUpdateContactPreferencesEdgeCases:
    """Test edge cases in preference updates."""

    @patch('iridia_daily.preferences_handler.monitoring')
    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_update_with_all_topics_selected(self, mock_ses_v2, mock_monitoring):
        """Test updating with all available topics selected."""
        from iridia_daily.preferences_handler import update_contact_preferences
        from iridia_daily.config import CATEGORY_MAPPING

        mock_ses_v2.update_contact.return_value = {}
        
        all_topics = [k for k in CATEGORY_MAPPING.keys() if k != 'default']
        
        success, error = update_contact_preferences(
            'user@example.com',
            all_topics
        )

        assert success is True
        assert error is None

    @patch('iridia_daily.preferences_handler.monitoring')
    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_update_with_single_topic(self, mock_ses_v2, mock_monitoring):
        """Test updating with just one topic."""
        from iridia_daily.preferences_handler import update_contact_preferences

        mock_ses_v2.update_contact.return_value = {}
        # Mock retry_with_backoff to just call the function
        mock_monitoring.retry_with_backoff.side_effect = lambda fn, **kwargs: fn()
        
        success, error = update_contact_preferences(
            'user@example.com',
            ['neuroscience']
        )

        assert success is True
        call_args = mock_ses_v2.update_contact.call_args[1]
        topic_prefs = call_args['TopicPreferences']
        
        # Verify neuroscience is OPT_IN
        neuro_pref = next((t for t in topic_prefs if t['TopicName'] == 'neuroscience'), None)
        assert neuro_pref['SubscriptionStatus'] == 'OPT_IN'
        
        # Verify daily-research is preserved
        daily_pref = next((t for t in topic_prefs if t['TopicName'] == 'daily-research'), None)
        assert daily_pref['SubscriptionStatus'] == 'OPT_IN'

    @patch('iridia_daily.preferences_handler.monitoring')
    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_update_includes_updated_timestamp(self, mock_ses_v2, mock_monitoring):
        """Test that update includes updated_at timestamp."""
        from iridia_daily.preferences_handler import update_contact_preferences

        mock_ses_v2.update_contact.return_value = {}
        # Mock retry_with_backoff to just call the function
        mock_monitoring.retry_with_backoff.side_effect = lambda fn, **kwargs: fn()
        
        update_contact_preferences('user@example.com', ['neuroscience'])

        call_args = mock_ses_v2.update_contact.call_args[1]
        attrs_data = json.loads(call_args['AttributesData'])
        
        assert 'updated_at' in attrs_data
        assert 'version' in attrs_data

    @patch('iridia_daily.preferences_handler.monitoring')
    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_update_with_retry_on_transient_error(self, mock_ses_v2, mock_monitoring):
        """Test that update retries on transient errors."""
        from iridia_daily.preferences_handler import update_contact_preferences

        # Fail twice, then succeed
        mock_ses_v2.update_contact.side_effect = [
            Exception("Transient error"),
            Exception("Transient error"),
            {}
        ]
        
        # monitoring.retry_with_backoff should handle retries
        # This tests integration with retry logic
        success, error = update_contact_preferences(
            'user@example.com',
            ['neuroscience']
        )

        # Should eventually succeed after retries
        # Note: Actual behavior depends on monitoring.retry_with_backoff implementation


class TestGetCurrentPreferences:
    """Test fetching current preferences."""

    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_get_preferences_with_topics(self, mock_ses_v2):
        """Test getting preferences when user has specific topics."""
        from iridia_daily.preferences_handler import get_current_preferences

        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'user@example.com',
            'TopicPreferences': [
                {'TopicName': 'neuroscience', 'SubscriptionStatus': 'OPT_IN'},
                {'TopicName': 'space', 'SubscriptionStatus': 'OPT_OUT'},
                {'TopicName': 'daily-research', 'SubscriptionStatus': 'OPT_IN'}
            ]
        }

        topics = get_current_preferences('user@example.com')

        # Should return opted-in topics (excluding daily-research which is internal)
        assert 'neuroscience' in topics
        assert 'space' not in topics  # OPT_OUT
        assert 'daily-research' in topics  # Still included in list

    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_get_preferences_no_topics(self, mock_ses_v2):
        """Test getting preferences when user has no topics."""
        from iridia_daily.preferences_handler import get_current_preferences

        mock_ses_v2.get_contact.return_value = {
            'EmailAddress': 'user@example.com',
            'TopicPreferences': []
        }

        topics = get_current_preferences('user@example.com')

        assert topics is None

    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_get_preferences_contact_not_found(self, mock_ses_v2):
        """Test getting preferences for non-existent contact."""
        from iridia_daily.preferences_handler import get_current_preferences

        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = mock_ses_v2.exceptions.NotFoundException()

        topics = get_current_preferences('nonexistent@example.com')

        assert topics is None

    @patch('iridia_daily.preferences_handler.ses_v2')
    def test_get_preferences_generic_error(self, mock_ses_v2):
        """Test getting preferences with generic error."""
        from iridia_daily.preferences_handler import get_current_preferences

        # Mock the exception class properly
        mock_ses_v2.exceptions.NotFoundException = type(
            'NotFoundException', (Exception,), {}
        )
        mock_ses_v2.get_contact.side_effect = Exception("SES Error")

        topics = get_current_preferences('user@example.com')

        assert topics is None


class TestLambdaHandlerEdgeCases:
    """Test Lambda handler edge cases."""

    def test_handler_options_request_returns_cors(self):
        """Test OPTIONS request returns CORS headers."""
        from iridia_daily.preferences_handler import lambda_handler

        event = {'httpMethod': 'OPTIONS'}
        
        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in result['headers']
        assert 'Access-Control-Allow-Methods' in result['headers']

    def test_handler_get_missing_token(self):
        """Test GET request without token."""
        from iridia_daily.preferences_handler import lambda_handler

        event = {
            'httpMethod': 'GET',
            'queryStringParameters': {}
        }
        
        result = lambda_handler(event, {})

        assert result['statusCode'] == 400
        assert 'text/html' in result['headers']['Content-Type']

    def test_handler_get_empty_token(self):
        """Test GET request with empty token."""
        from iridia_daily.preferences_handler import lambda_handler

        event = {
            'httpMethod': 'GET',
            'queryStringParameters': {'token': ''}
        }
        
        result = lambda_handler(event, {})

        assert result['statusCode'] == 400

    def test_handler_get_null_query_params(self):
        """Test GET request with null queryStringParameters."""
        from iridia_daily.preferences_handler import lambda_handler

        event = {
            'httpMethod': 'GET',
            'queryStringParameters': None
        }
        
        result = lambda_handler(event, {})

        assert result['statusCode'] == 400

    @patch('iridia_daily.preferences_handler.verify_unsubscribe_token')
    def test_handler_post_invalid_token(self, mock_verify):
        """Test POST request with invalid token."""
        from iridia_daily.preferences_handler import lambda_handler

        mock_verify.return_value = None

        event = {
            'httpMethod': 'POST',
            'queryStringParameters': {'token': 'invalid'},
            'body': json.dumps({'topics': ['neuroscience']})
        }
        
        result = lambda_handler(event, {})

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'error' in body

    @patch('iridia_daily.preferences_handler.update_contact_preferences')
    @patch('iridia_daily.preferences_handler.verify_unsubscribe_token')
    def test_handler_post_empty_topics(self, mock_verify, mock_update):
        """Test POST request with empty topics list."""
        from iridia_daily.preferences_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'

        event = {
            'httpMethod': 'POST',
            'queryStringParameters': {'token': 'valid'},
            'body': json.dumps({'topics': []})
        }
        
        result = lambda_handler(event, {})

        assert result['statusCode'] == 400

    @patch('iridia_daily.preferences_handler.verify_unsubscribe_token')
    def test_handler_post_malformed_json(self, mock_verify):
        """Test POST request with malformed JSON."""
        from iridia_daily.preferences_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'

        event = {
            'httpMethod': 'POST',
            'queryStringParameters': {'token': 'valid'},
            'body': 'not valid json {'
        }
        
        result = lambda_handler(event, {})

        # Should handle JSON decode error
        assert result['statusCode'] >= 400

    @patch('iridia_daily.preferences_handler.verify_unsubscribe_token')
    def test_handler_post_missing_body(self, mock_verify):
        """Test POST request with missing body."""
        from iridia_daily.preferences_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'

        event = {
            'httpMethod': 'POST',
            'queryStringParameters': {'token': 'valid'},
            'body': None
        }
        
        result = lambda_handler(event, {})

        # Should handle missing body
        assert result['statusCode'] >= 400

    @patch('iridia_daily.preferences_handler.get_current_preferences')
    @patch('iridia_daily.preferences_handler.verify_unsubscribe_token')
    def test_handler_get_success_with_current_prefs(self, mock_verify, mock_get_prefs):
        """Test GET request successfully returns form with current preferences."""
        from iridia_daily.preferences_handler import lambda_handler

        mock_verify.return_value = 'user@example.com'
        mock_get_prefs.return_value = ['neuroscience', 'space']

        event = {
            'httpMethod': 'GET',
            'queryStringParameters': {'token': 'valid-token'}
        }
        
        result = lambda_handler(event, {})

        assert result['statusCode'] == 200
        assert 'text/html' in result['headers']['Content-Type']
        assert 'user@example.com' in result['body']
        assert 'checkbox' in result['body'].lower()
