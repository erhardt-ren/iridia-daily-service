"""Tests for summary validation and alerting functionality."""

import pytest
from unittest.mock import Mock, patch


class TestValidateSummaries:
    """Test summary validation logic."""

    def test_validate_summaries_count_match(self):
        """Test validation passes when summary count matches paper count."""
        from iridia_daily.newsletter_handler import validate_summaries

        papers = [
            {'title': 'Paper 1', 'abstract': 'Abstract 1'},
            {'title': 'Paper 2', 'abstract': 'Abstract 2'},
            {'title': 'Paper 3', 'abstract': 'Abstract 3'}
        ]
        summaries = [
            'This is a valid summary with more than fifty characters here.',
            'Another valid summary that meets the minimum length requirement.',
            'Third summary also exceeds the fifty character minimum length.'
        ]

        result = validate_summaries(summaries, papers)

        assert result is True

    def test_validate_summaries_count_mismatch_fewer(self):
        """Test validation fails when fewer summaries than papers."""
        from iridia_daily.newsletter_handler import validate_summaries

        papers = [
            {'title': 'Paper 1'},
            {'title': 'Paper 2'},
            {'title': 'Paper 3'}
        ]
        summaries = [
            'Summary one with enough characters to pass quality check.',
            'Summary two also has sufficient length for validation.'
        ]

        result = validate_summaries(summaries, papers)

        assert result is False

    def test_validate_summaries_count_mismatch_more(self):
        """Test validation fails when more summaries than papers."""
        from iridia_daily.newsletter_handler import validate_summaries

        papers = [
            {'title': 'Paper 1'},
            {'title': 'Paper 2'}
        ]
        summaries = [
            'Summary one with enough characters to pass quality check.',
            'Summary two also has sufficient length for validation.',
            'Extra summary three that should not be here at all.'
        ]

        result = validate_summaries(summaries, papers)

        assert result is False

    def test_validate_summaries_empty_lists(self):
        """Test validation passes with empty lists."""
        from iridia_daily.newsletter_handler import validate_summaries

        result = validate_summaries([], [])

        assert result is True

    def test_validate_summaries_warns_short_summary(self, capfd):
        """Test validation warns but passes for short summaries."""
        from iridia_daily.newsletter_handler import validate_summaries

        papers = [{'title': 'Paper 1'}]
        summaries = ['Too short']  # Less than 50 characters

        result = validate_summaries(summaries, papers)

        assert result is True  # Still passes despite warning
        captured = capfd.readouterr()
        assert 'WARNING' in captured.out
        assert 'too short' in captured.out.lower()
        assert '9 characters' in captured.out

    def test_validate_summaries_warns_long_summary(self, capfd):
        """Test validation warns but passes for long summaries."""
        from iridia_daily.newsletter_handler import validate_summaries

        papers = [{'title': 'Paper 1'}]
        # Create a summary longer than 1000 characters
        long_summary = 'A' * 1001
        summaries = [long_summary]

        result = validate_summaries(summaries, papers)

        assert result is True  # Still passes despite warning
        captured = capfd.readouterr()
        assert 'WARNING' in captured.out
        assert 'too long' in captured.out.lower()
        assert '1001 characters' in captured.out

    def test_validate_summaries_multiple_quality_issues(self, capfd):
        """Test validation logs multiple quality warnings."""
        from iridia_daily.newsletter_handler import validate_summaries

        papers = [
            {'title': 'Paper 1'},
            {'title': 'Paper 2'},
            {'title': 'Paper 3'}
        ]
        summaries = [
            'Short',  # Too short
            'This is a perfectly fine summary with good length.',
            'B' * 1001  # Too long
        ]

        result = validate_summaries(summaries, papers)

        assert result is True  # Passes but with warnings
        captured = capfd.readouterr()
        assert captured.out.count('WARNING') == 2

    def test_validate_summaries_non_string_type(self, capfd):
        """Test validation warns for non-string summaries."""
        from iridia_daily.newsletter_handler import validate_summaries

        papers = [
            {'title': 'Paper 1'},
            {'title': 'Paper 2'}
        ]
        summaries = [
            'Valid string summary with sufficient length for checking.',
            123  # Not a string
        ]

        result = validate_summaries(summaries, papers)

        assert result is True  # Still passes
        captured = capfd.readouterr()
        assert 'WARNING' in captured.out
        assert 'not a string type' in captured.out.lower()

    def test_validate_summaries_edge_case_exactly_50_chars(self):
        """Test summary with exactly 50 characters passes without warning."""
        from iridia_daily.newsletter_handler import validate_summaries

        papers = [{'title': 'Paper 1'}]
        summaries = ['A' * 50]  # Exactly 50 characters

        result = validate_summaries(summaries, papers)

        assert result is True

    def test_validate_summaries_edge_case_exactly_1000_chars(self):
        """Test summary with exactly 1000 characters passes without warning."""
        from iridia_daily.newsletter_handler import validate_summaries

        papers = [{'title': 'Paper 1'}]
        summaries = ['A' * 1000]  # Exactly 1000 characters

        result = validate_summaries(summaries, papers)

        assert result is True


class TestSendAlertNotification:
    """Test SNS alert notification functionality."""

    @patch('iridia_daily.newsletter_handler.boto3')
    def test_send_alert_notification_success(self, mock_boto3, monkeypatch):
        """Test successful SNS alert sending."""
        from iridia_daily.newsletter_handler import send_alert_notification

        monkeypatch.setenv(
            'ALERT_TOPIC_ARN',
            'arn:aws:sns:us-east-1:123456789012:iridia-daily-alerts'
        )

        mock_sns = Mock()
        mock_sns.publish.return_value = {'MessageId': 'msg-123'}
        mock_boto3.client.return_value = mock_sns

        send_alert_notification(
            message='Test alert message',
            subject='Test Subject'
        )

        mock_boto3.client.assert_called_once_with(
            'sns',
            region_name='us-east-1'
        )
        mock_sns.publish.assert_called_once()
        call_kwargs = mock_sns.publish.call_args[1]
        assert call_kwargs['Message'] == 'Test alert message'
        assert call_kwargs['Subject'] == 'Test Subject'
        assert 'arn:aws:sns' in call_kwargs['TopicArn']

    @patch('iridia_daily.newsletter_handler.boto3')
    def test_send_alert_notification_missing_arn(
        self, mock_boto3, monkeypatch, capfd
    ):
        """Test alert skipped when ALERT_TOPIC_ARN not configured."""
        from iridia_daily.newsletter_handler import send_alert_notification

        monkeypatch.delenv('ALERT_TOPIC_ARN', raising=False)

        send_alert_notification('Test message')

        mock_boto3.client.assert_not_called()
        captured = capfd.readouterr()
        assert 'WARNING' in captured.out
        assert 'ALERT_TOPIC_ARN not configured' in captured.out

    @patch('iridia_daily.newsletter_handler.boto3')
    def test_send_alert_notification_sns_error(
        self, mock_boto3, monkeypatch, capfd
    ):
        """Test alert handles SNS publish errors gracefully."""
        from iridia_daily.newsletter_handler import send_alert_notification

        monkeypatch.setenv(
            'ALERT_TOPIC_ARN',
            'arn:aws:sns:us-east-1:123456789012:test-topic'
        )

        mock_sns = Mock()
        mock_sns.publish.side_effect = Exception('SNS API Error')
        mock_boto3.client.return_value = mock_sns

        # Should not raise exception
        send_alert_notification('Test message')

        captured = capfd.readouterr()
        assert 'ERROR' in captured.out
        assert 'Failed to send SNS alert' in captured.out

    @patch('iridia_daily.newsletter_handler.boto3')
    def test_send_alert_notification_default_subject(
        self, mock_boto3, monkeypatch
    ):
        """Test default subject is used when not specified."""
        from iridia_daily.newsletter_handler import send_alert_notification

        monkeypatch.setenv(
            'ALERT_TOPIC_ARN',
            'arn:aws:sns:us-east-1:123456789012:test-topic'
        )

        mock_sns = Mock()
        mock_boto3.client.return_value = mock_sns

        send_alert_notification('Test message')

        call_kwargs = mock_sns.publish.call_args[1]
        assert call_kwargs['Subject'] == 'Iridia Daily Alert'

    @patch('iridia_daily.newsletter_handler.boto3')
    def test_send_alert_notification_uses_us_east_1(
        self, mock_boto3, monkeypatch
    ):
        """Test SNS client uses us-east-1 region."""
        from iridia_daily.newsletter_handler import send_alert_notification

        monkeypatch.setenv(
            'ALERT_TOPIC_ARN',
            'arn:aws:sns:us-east-1:123456789012:test-topic'
        )

        mock_sns = Mock()
        mock_boto3.client.return_value = mock_sns

        send_alert_notification('Test message')

        mock_boto3.client.assert_called_once_with(
            'sns',
            region_name='us-east-1'
        )