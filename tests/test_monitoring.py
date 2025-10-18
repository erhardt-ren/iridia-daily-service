"""Tests for monitoring utilities."""

import pytest
from unittest.mock import Mock, patch
import time


class TestMetrics:
    """Test CloudWatch metrics publishing."""
    
    @patch('iridia_daily.monitoring.cloudwatch')
    def test_put_metric_basic(self, mock_cloudwatch):
        """Test basic metric publishing."""
        from iridia_daily.monitoring import put_metric
        
        put_metric('TestMetric', 1)
        
        mock_cloudwatch.put_metric_data.assert_called_once()
        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]
        
        assert call_kwargs['Namespace'] == 'IridiaDaily'
        assert call_kwargs['MetricData'][0]['MetricName'] == 'TestMetric'
        assert call_kwargs['MetricData'][0]['Value'] == 1
        assert call_kwargs['MetricData'][0]['Unit'] == 'Count'
    
    @patch('iridia_daily.monitoring.cloudwatch')
    def test_put_metric_with_dimensions(self, mock_cloudwatch):
        """Test metric with dimensions."""
        from iridia_daily.monitoring import put_metric
        
        dimensions = [{'Name': 'Status', 'Value': 'Success'}]
        put_metric('TestMetric', 5, unit='Count', dimensions=dimensions)
        
        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]
        metric_data = call_kwargs['MetricData'][0]
        
        assert metric_data['Dimensions'] == dimensions
    
    @patch('iridia_daily.monitoring.cloudwatch')
    def test_put_metric_handles_error(self, mock_cloudwatch):
        """Test metric publishing handles errors gracefully."""
        from iridia_daily.monitoring import put_metric
        
        mock_cloudwatch.put_metric_data.side_effect = Exception("CloudWatch error")
        
        # Should not raise exception
        put_metric('TestMetric', 1)


class TestRetryLogic:
    """Test exponential backoff retry."""
    
    def test_retry_succeeds_first_attempt(self):
        """Test successful function on first attempt."""
        from iridia_daily.monitoring import retry_with_backoff
        
        mock_func = Mock(return_value='success')
        
        result = retry_with_backoff(mock_func, max_attempts=3)
        
        assert result == 'success'
        assert mock_func.call_count == 1
    
    def test_retry_succeeds_after_failures(self):
        """Test function succeeds after initial failures."""
        from iridia_daily.monitoring import retry_with_backoff
        
        mock_func = Mock(side_effect=[
            Exception("First failure"),
            Exception("Second failure"),
            'success'
        ])
        
        result = retry_with_backoff(mock_func, max_attempts=3, base_delay=0.01)
        
        assert result == 'success'
        assert mock_func.call_count == 3
    
    def test_retry_exhausts_attempts(self):
        """Test retry raises exception after max attempts."""
        from iridia_daily.monitoring import retry_with_backoff
        
        mock_func = Mock(side_effect=Exception("Always fails"))
        
        with pytest.raises(Exception, match="Always fails"):
            retry_with_backoff(mock_func, max_attempts=3, base_delay=0.01)
        
        assert mock_func.call_count == 3
    
    def test_retry_exponential_backoff(self):
        """Test exponential backoff timing."""
        from iridia_daily.monitoring import retry_with_backoff
        
        call_times = []
        
        def failing_func():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise Exception("Fail")
            return 'success'
        
        start = time.time()
        retry_with_backoff(failing_func, max_attempts=3, base_delay=0.1)
        duration = time.time() - start
        
        # Should take at least 0.1 + 0.2 = 0.3 seconds
        assert duration >= 0.3
        assert len(call_times) == 3


class TestSenderVerification:
    """Test SES sender verification."""
    
    @patch('iridia_daily.monitoring.boto3')
    def test_verify_sender_success(self, mock_boto3):
        """Test successful sender verification."""
        from iridia_daily.monitoring import verify_ses_sender
        
        mock_ses = Mock()
        mock_ses.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {
                'test@example.com': {
                    'VerificationStatus': 'Success'
                }
            }
        }
        mock_boto3.client.return_value = mock_ses
        
        result = verify_ses_sender('test@example.com')
        
        assert result is True
    
    @patch('iridia_daily.monitoring.boto3')
    def test_verify_sender_not_verified(self, mock_boto3):
        """Test sender not verified."""
        from iridia_daily.monitoring import verify_ses_sender
        
        mock_ses = Mock()
        mock_ses.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {
                'test@example.com': {
                    'VerificationStatus': 'Pending'
                }
            }
        }
        mock_boto3.client.return_value = mock_ses
        
        result = verify_ses_sender('test@example.com')
        
        assert result is False
    
    @patch('iridia_daily.monitoring.boto3')
    def test_verify_sender_not_found(self, mock_boto3):
        """Test sender not found in SES."""
        from iridia_daily.monitoring import verify_ses_sender
        
        mock_ses = Mock()
        mock_ses.get_identity_verification_attributes.return_value = {
            'VerificationAttributes': {}
        }
        mock_boto3.client.return_value = mock_ses
        
        result = verify_ses_sender('test@example.com')
        
        assert result is False
    
    @patch('iridia_daily.monitoring.boto3')
    def test_verify_sender_handles_error(self, mock_boto3):
        """Test sender verification handles errors."""
        from iridia_daily.monitoring import verify_ses_sender
        
        mock_ses = Mock()
        mock_ses.get_identity_verification_attributes.side_effect = Exception("SES error")
        mock_boto3.client.return_value = mock_ses
        
        result = verify_ses_sender('test@example.com')
        
        assert result is False