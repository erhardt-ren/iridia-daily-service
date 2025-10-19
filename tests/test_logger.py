"""Tests for structured JSON logging module."""

import pytest
import json
from unittest.mock import Mock
from datetime import datetime


class TestLogEvent:
    """Test core log_event function."""

    def test_log_event_basic_output(self, capsys):
        """Test basic log event produces valid JSON."""
        from iridia_daily.logger import log_event

        log_event('test_event', level='INFO', key1='value1', key2=42)

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry['level'] == 'INFO'
        assert log_entry['event_type'] == 'test_event'
        assert log_entry['key1'] == 'value1'
        assert log_entry['key2'] == 42
        assert 'timestamp' in log_entry

    def test_log_event_timestamp_format(self, capsys):
        """Test timestamp is in ISO format."""
        from iridia_daily.logger import log_event

        log_event('test_event')

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        # Should be valid ISO format timestamp
        timestamp = datetime.fromisoformat(log_entry['timestamp'].replace('Z', '+00:00'))
        assert isinstance(timestamp, datetime)

    def test_log_event_with_request_id(self, capsys):
        """Test log includes request ID when Lambda context is set."""
        from iridia_daily.logger import set_lambda_context, log_event

        mock_context = Mock()
        mock_context.aws_request_id = 'test-request-123'

        set_lambda_context(mock_context)
        log_event('test_event')

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry['request_id'] == 'test-request-123'

    def test_log_event_without_context(self, capsys):
        """Test log works without Lambda context."""
        from iridia_daily.logger import log_event, _lambda_context

        # Clear any existing context
        import iridia_daily.logger as logger_module
        logger_module._lambda_context = None

        log_event('test_event')

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert 'request_id' not in log_entry

    def test_log_event_multiple_kwargs(self, capsys):
        """Test log event with many kwargs."""
        from iridia_daily.logger import log_event

        log_event('complex_event',
                  level='WARNING',
                  user='test@example.com',
                  count=100,
                  duration=12.34,
                  success=True,
                  tags=['tag1', 'tag2'])

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry['event_type'] == 'complex_event'
        assert log_entry['level'] == 'WARNING'
        assert log_entry['user'] == 'test@example.com'
        assert log_entry['count'] == 100
        assert log_entry['duration'] == 12.34
        assert log_entry['success'] is True
        assert log_entry['tags'] == ['tag1', 'tag2']


class TestConvenienceFunctions:
    """Test log_info, log_warning, log_error convenience functions."""

    def test_log_info(self, capsys):
        """Test log_info sets correct level."""
        from iridia_daily.logger import log_info

        log_info('info_event', detail='test')

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry['level'] == 'INFO'
        assert log_entry['event_type'] == 'info_event'
        assert log_entry['detail'] == 'test'

    def test_log_warning(self, capsys):
        """Test log_warning sets correct level."""
        from iridia_daily.logger import log_warning

        log_warning('warning_event', reason='test warning')

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry['level'] == 'WARNING'
        assert log_entry['event_type'] == 'warning_event'
        assert log_entry['reason'] == 'test warning'

    def test_log_error(self, capsys):
        """Test log_error sets correct level."""
        from iridia_daily.logger import log_error

        log_error('error_event',
                  error_type='ValueError',
                  error_message='Invalid input')

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry['level'] == 'ERROR'
        assert log_entry['event_type'] == 'error_event'
        assert log_entry['error_type'] == 'ValueError'
        assert log_entry['error_message'] == 'Invalid input'


class TestLogMetric:
    """Test log_metric function for performance tracking."""

    def test_log_metric_basic(self, capsys):
        """Test basic metric logging."""
        from iridia_daily.logger import log_metric

        log_metric('response_time', 1.234, unit='Seconds')

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry['event_type'] == 'metric_recorded'
        assert log_entry['metric_name'] == 'response_time'
        assert log_entry['metric_value'] == 1.234
        assert log_entry['metric_unit'] == 'Seconds'

    def test_log_metric_with_context(self, capsys):
        """Test metric logging with additional context."""
        from iridia_daily.logger import log_metric

        log_metric('emails_sent',
                   value=150,
                   unit='Count',
                   campaign='newsletter',
                   batch_id=5)

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry['metric_name'] == 'emails_sent'
        assert log_entry['metric_value'] == 150
        assert log_entry['metric_unit'] == 'Count'
        assert log_entry['campaign'] == 'newsletter'
        assert log_entry['batch_id'] == 5

    def test_log_metric_default_unit(self, capsys):
        """Test metric logging with default unit."""
        from iridia_daily.logger import log_metric

        log_metric('counter', 42)

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry['metric_unit'] == 'None'


class TestLambdaContext:
    """Test Lambda context management."""

    def test_set_lambda_context_stores_context(self):
        """Test setting Lambda context."""
        from iridia_daily.logger import set_lambda_context
        import iridia_daily.logger as logger_module

        mock_context = Mock()
        mock_context.aws_request_id = 'abc-123'

        set_lambda_context(mock_context)

        assert logger_module._lambda_context == mock_context

    def test_set_lambda_context_multiple_times(self, capsys):
        """Test updating Lambda context."""
        from iridia_daily.logger import set_lambda_context, log_info

        context1 = Mock()
        context1.aws_request_id = 'request-1'

        set_lambda_context(context1)
        log_info('event1')

        captured = capsys.readouterr()
        log_entry1 = json.loads(captured.out.strip())
        assert log_entry1['request_id'] == 'request-1'

        # Update context
        context2 = Mock()
        context2.aws_request_id = 'request-2'

        set_lambda_context(context2)
        log_info('event2')

        captured = capsys.readouterr()
        log_entry2 = json.loads(captured.out.strip())
        assert log_entry2['request_id'] == 'request-2'

    def test_context_without_request_id(self, capsys):
        """Test context object without request_id attribute."""
        from iridia_daily.logger import set_lambda_context, log_info

        mock_context = Mock(spec=[])  # No attributes

        set_lambda_context(mock_context)
        log_info('test_event')

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert 'request_id' not in log_entry


class TestJSONFormat:
    """Test JSON output format and validity."""

    def test_json_is_single_line(self, capsys):
        """Test log output is single line JSON."""
        from iridia_daily.logger import log_info

        log_info('test')

        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')

        assert len(lines) == 1

    def test_json_is_parseable(self, capsys):
        """Test all log output is valid JSON."""
        from iridia_daily.logger import log_info, log_warning, log_error

        log_info('event1', data='test')
        log_warning('event2', count=42)
        log_error('event3', error='test error')

        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')

        for line in lines:
            # Should not raise exception
            log_entry = json.loads(line)
            assert isinstance(log_entry, dict)

    def test_special_characters_escaped(self, capsys):
        """Test special characters are properly escaped in JSON."""
        from iridia_daily.logger import log_info

        log_info('test',
                 message='Line 1\nLine 2\tTabbed',
                 path='C:\\Users\\test',
                 quote='He said "hello"')

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry['message'] == 'Line 1\nLine 2\tTabbed'
        assert log_entry['path'] == 'C:\\Users\\test'
        assert log_entry['quote'] == 'He said "hello"'


class TestIntegrationScenarios:
    """Test real-world usage scenarios."""

    def test_newsletter_generation_flow(self, capsys):
        """Test typical newsletter generation log flow."""
        from iridia_daily.logger import (
            set_lambda_context, log_info, log_warning,
            log_error, log_metric
        )

        # Simulate Lambda handler
        mock_context = Mock()
        mock_context.aws_request_id = 'newsletter-123'

        set_lambda_context(mock_context)

        # Simulate newsletter flow
        log_info('newsletter_started', papers=5)
        log_info('subscribers_retrieved', count=100)
        log_warning('invalid_emails_filtered', invalid_count=2)
        log_info('papers_retrieved', count=5)
        log_metric('newsletter_duration', value=12.5, unit='Seconds')

        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')

        assert len(lines) == 5

        # Verify all have request_id
        for line in lines:
            entry = json.loads(line)
            assert entry['request_id'] == 'newsletter-123'

    def test_error_handling_flow(self, capsys):
        """Test error logging with context."""
        from iridia_daily.logger import log_error

        try:
            raise ValueError("Invalid email format")
        except Exception as e:
            log_error('validation_error',
                      error_type=type(e).__name__,
                      error_message=str(e),
                      email='invalid@',
                      step='email_validation')

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry['level'] == 'ERROR'
        assert log_entry['event_type'] == 'validation_error'
        assert log_entry['error_type'] == 'ValueError'
        assert log_entry['error_message'] == 'Invalid email format'
        assert log_entry['email'] == 'invalid@'
        assert log_entry['step'] == 'email_validation'

    def test_multiple_events_same_request(self, capsys):
        """Test multiple log events for same request."""
        from iridia_daily.logger import set_lambda_context, log_info

        mock_context = Mock()
        mock_context.aws_request_id = 'shared-request-id'

        set_lambda_context(mock_context)

        log_info('step1', status='started')
        log_info('step2', status='processing')
        log_info('step3', status='completed')

        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')

        assert len(lines) == 3

        # All should have same request_id
        request_ids = [json.loads(line)['request_id'] for line in lines]
        assert all(rid == 'shared-request-id' for rid in request_ids)

        # Timestamps should be sequential
        timestamps = [json.loads(line)['timestamp'] for line in lines]
        assert timestamps[0] <= timestamps[1] <= timestamps[2]