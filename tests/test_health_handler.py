"""Unit tests for health check handler."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


class TestHealthCheckIndividualChecks:
    """Test individual dependency checks.
    
    These tests explicitly mock all dependencies to be completely
    self-contained and independent of conftest auto-mocking.
    """
    
    @patch('iridia_daily.health_handler.time.time')
    @patch('iridia_daily.health_handler.verify_ses_sender')
    def test_check_ses_sender_success(self, mock_verify, mock_time):
        """Test successful SES sender verification."""
        from iridia_daily.health_handler import check_ses_sender
        
        # Explicitly mock time and verify_ses_sender
        mock_time.side_effect = [0, 0.045]
        mock_verify.return_value = True
        
        success, response_time, error = check_ses_sender('test@example.com')
        
        assert success is True
        assert response_time == 45
        assert error is None
        mock_verify.assert_called_once_with('test@example.com')
    
    @patch('iridia_daily.health_handler.time.time')
    @patch('iridia_daily.health_handler.verify_ses_sender')
    def test_check_ses_sender_not_verified(self, mock_verify, mock_time):
        """Test SES sender not verified."""
        from iridia_daily.health_handler import check_ses_sender
        
        mock_time.side_effect = [0, 0.042]
        mock_verify.return_value = False
        
        success, response_time, error = check_ses_sender('test@example.com')
        
        assert success is False
        assert response_time == 42
        assert error == "Sender email not verified"
    
    @patch('iridia_daily.health_handler.time.time')
    @patch('iridia_daily.health_handler.verify_ses_sender')
    def test_check_ses_sender_exception(self, mock_verify, mock_time):
        """Test SES check with exception."""
        from iridia_daily.health_handler import check_ses_sender
        
        mock_time.side_effect = [0, 0.050]
        mock_verify.side_effect = Exception("SES API error")
        
        success, response_time, error = check_ses_sender('test@example.com')
        
        assert success is False
        assert response_time == 50
        assert "SES API error" in error
    
    @patch('iridia_daily.health_handler.time.time')
    @patch('iridia_daily.health_handler.urllib.request.urlopen')
    def test_check_pubmed_api_success(self, mock_urlopen, mock_time):
        """Test successful PubMed API check."""
        from iridia_daily.health_handler import check_pubmed_api
        
        mock_time.side_effect = [0, 0.120]
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'esearchresult': {'count': '5'}
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        success, response_time, error = check_pubmed_api()
        
        assert success is True
        assert response_time == 120
        assert error is None
    
    @patch('iridia_daily.health_handler.time.time')
    @patch('iridia_daily.health_handler.urllib.request.urlopen')
    def test_check_pubmed_api_timeout(self, mock_urlopen, mock_time):
        """Test PubMed API timeout."""
        from iridia_daily.health_handler import check_pubmed_api
        import urllib.error
        
        mock_time.side_effect = [0, 0.200]
        mock_urlopen.side_effect = urllib.error.URLError("timeout")
        
        success, response_time, error = check_pubmed_api()
        
        assert success is False
        assert response_time == 200
        assert "URLError" in error
    
    @patch('iridia_daily.health_handler.time.time')
    @patch('iridia_daily.health_handler.urllib.request.urlopen')
    def test_check_pubmed_api_invalid_response(self, mock_urlopen, mock_time):
        """Test PubMed API with invalid response format."""
        from iridia_daily.health_handler import check_pubmed_api
        
        mock_time.side_effect = [0, 0.115]
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'invalid': 'response'
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        success, response_time, error = check_pubmed_api()
        
        assert success is False
        assert response_time == 115
        assert "Invalid response format" in error
    
    @patch('iridia_daily.health_handler.time.time')
    @patch('iridia_daily.health_handler.boto3.client')
    def test_check_bedrock_api_success(self, mock_boto3, mock_time):
        """Test successful Bedrock API check."""
        from iridia_daily.health_handler import check_bedrock_api
        
        mock_time.side_effect = [0, 0.890]
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=lambda: json.dumps({
                'content': [{'text': 'Hello'}]
            }).encode('utf-8'))
        }
        mock_boto3.return_value = mock_bedrock
        
        success, response_time, error = check_bedrock_api()
        
        assert success is True
        assert response_time == 890
        assert error is None
    
    @patch('iridia_daily.health_handler.time.time')
    @patch('iridia_daily.health_handler.boto3.client')
    def test_check_bedrock_api_access_denied(self, mock_boto3, mock_time):
        """Test Bedrock API access denied."""
        from iridia_daily.health_handler import check_bedrock_api
        
        mock_time.side_effect = [0, 0.100]
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.side_effect = Exception("Access Denied")
        mock_boto3.return_value = mock_bedrock
        
        success, response_time, error = check_bedrock_api()
        
        assert success is False
        assert response_time == 100
        assert "Access Denied" in error
    
    @patch('iridia_daily.health_handler.time.time')
    @patch('iridia_daily.health_handler.boto3.client')
    def test_check_secrets_manager_success(self, mock_boto3, mock_time):
        """Test successful Secrets Manager check."""
        from iridia_daily.health_handler import check_secrets_manager
        
        mock_time.side_effect = [0, 0.030]
        mock_secrets = Mock()
        mock_secrets.get_secret_value.return_value = {
            'SecretString': '{"key":"value"}'
        }
        mock_boto3.return_value = mock_secrets
        
        success, response_time, error = check_secrets_manager('arn:aws:secretsmanager:us-east-1:123456789012:secret:test')
        
        assert success is True
        assert response_time == 30
        assert error is None
    
    @patch('iridia_daily.health_handler.time.time')
    @patch('iridia_daily.health_handler.boto3.client')
    def test_check_secrets_manager_not_found(self, mock_boto3, mock_time):
        """Test Secrets Manager secret not found."""
        from iridia_daily.health_handler import check_secrets_manager
        
        mock_time.side_effect = [0, 0.028]
        mock_secrets = Mock()
        mock_secrets.get_secret_value.side_effect = Exception("ResourceNotFoundException")
        mock_boto3.return_value = mock_secrets
        
        success, response_time, error = check_secrets_manager('arn:aws:secretsmanager:us-east-1:123456789012:secret:test')
        
        assert success is False
        assert response_time == 28
        assert "ResourceNotFoundException" in error


class TestHealthCheckHandler:
    """Test health check Lambda handler.
    
    These tests mock the check functions directly to test handler logic
    without triggering actual AWS API calls. All mocking is explicit.
    Environment variables are provided by conftest.setup_env fixture.
    """
    
    @patch('iridia_daily.health_handler.check_secrets_manager')
    @patch('iridia_daily.health_handler.check_bedrock_api')
    @patch('iridia_daily.health_handler.check_pubmed_api')
    @patch('iridia_daily.health_handler.check_ses_sender')
    def test_lambda_handler_all_healthy(self, mock_ses, mock_pubmed, 
                                       mock_bedrock, mock_secrets):
        """Test handler with all checks passing."""
        from iridia_daily.health_handler import lambda_handler
        
        # Explicitly mock all check functions
        mock_ses.return_value = (True, 45, None)
        mock_pubmed.return_value = (True, 120, None)
        mock_bedrock.return_value = (True, 890, None)
        mock_secrets.return_value = (True, 30, None)
        
        event = {}
        context = Mock()
        context.aws_request_id = 'test-request-123'
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 200
        assert 'Content-Type' in response['headers']
        
        body = json.loads(response['body'])
        assert body['status'] == 'healthy'
        assert 'timestamp' in body
        assert len(body['checks']) == 4
        assert body['checks']['ses_sender']['status'] is True
        assert body['checks']['pubmed_api']['status'] is True
        assert body['checks']['bedrock_api']['status'] is True
        assert body['checks']['secrets_manager']['status'] is True
    
    @patch('iridia_daily.health_handler.check_secrets_manager')
    @patch('iridia_daily.health_handler.check_bedrock_api')
    @patch('iridia_daily.health_handler.check_pubmed_api')
    @patch('iridia_daily.health_handler.check_ses_sender')
    def test_lambda_handler_ses_failed(self, mock_ses, mock_pubmed,
                                       mock_bedrock, mock_secrets):
        """Test handler with SES check failing."""
        from iridia_daily.health_handler import lambda_handler
        
        mock_ses.return_value = (False, 42, "Sender email not verified")
        mock_pubmed.return_value = (True, 115, None)
        mock_bedrock.return_value = (True, 850, None)
        mock_secrets.return_value = (True, 28, None)
        
        event = {}
        context = Mock()
        context.aws_request_id = 'test-request-123'
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 503
        
        body = json.loads(response['body'])
        assert body['status'] == 'degraded'
        assert body['checks']['ses_sender']['status'] is False
        assert 'error' in body['checks']['ses_sender']
        assert body['checks']['pubmed_api']['status'] is True
    
    @patch('iridia_daily.health_handler.check_secrets_manager')
    @patch('iridia_daily.health_handler.check_bedrock_api')
    @patch('iridia_daily.health_handler.check_pubmed_api')
    @patch('iridia_daily.health_handler.check_ses_sender')
    def test_lambda_handler_multiple_failures(self, mock_ses, mock_pubmed,
                                             mock_bedrock, mock_secrets):
        """Test handler with multiple checks failing."""
        from iridia_daily.health_handler import lambda_handler
        
        mock_ses.return_value = (False, 42, "Not verified")
        mock_pubmed.return_value = (False, 5000, "Timeout")
        mock_bedrock.return_value = (True, 850, None)
        mock_secrets.return_value = (True, 28, None)
        
        event = {}
        context = Mock()
        context.aws_request_id = 'test-request-123'
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 503
        
        body = json.loads(response['body'])
        assert body['status'] == 'degraded'
        assert body['checks']['ses_sender']['status'] is False
        assert body['checks']['pubmed_api']['status'] is False
        assert body['checks']['bedrock_api']['status'] is True
        assert body['checks']['secrets_manager']['status'] is True
    
    def test_lambda_handler_missing_env_vars(self, monkeypatch):
        """Test handler with missing environment variables."""
        from iridia_daily.health_handler import lambda_handler
        
        # Delete env vars after conftest.setup_env sets them
        monkeypatch.delenv('SENDER_EMAIL')
        monkeypatch.delenv('HMAC_SECRET_ARN')
        
        event = {}
        context = Mock()
        context.aws_request_id = 'test-request-missing-env'
        
        response = lambda_handler(event, context)
        
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['status'] == 'error'
        assert 'error' in body
    
    @patch('iridia_daily.health_handler.check_secrets_manager')
    @patch('iridia_daily.health_handler.check_bedrock_api')
    @patch('iridia_daily.health_handler.check_pubmed_api')
    @patch('iridia_daily.health_handler.check_ses_sender')
    def test_lambda_handler_response_times_present(self, mock_ses, mock_pubmed,
                                                mock_bedrock, mock_secrets):
        """Test that all response times are included in response."""
        from iridia_daily.health_handler import lambda_handler
        
        mock_ses.return_value = (True, 45, None)
        mock_pubmed.return_value = (True, 120, None)
        mock_bedrock.return_value = (True, 890, None)
        mock_secrets.return_value = (True, 30, None)
        
        event = {}
        context = Mock()
        context.aws_request_id = 'test-request-response-times'
        
        response = lambda_handler(event, context)
        body = json.loads(response['body'])
        
        assert body['checks']['ses_sender']['response_time_ms'] == 45
        assert body['checks']['pubmed_api']['response_time_ms'] == 120
        assert body['checks']['bedrock_api']['response_time_ms'] == 890
        assert body['checks']['secrets_manager']['response_time_ms'] == 30

class TestHealthCheckLogging:
    """Test structured logging in health checks.
    
    These tests verify that proper structured logs are emitted.
    Note: conftest.mock_logger is skipped for health_handler tests.
    """
    
    @patch('iridia_daily.health_handler.check_secrets_manager')
    @patch('iridia_daily.health_handler.check_bedrock_api')
    @patch('iridia_daily.health_handler.check_pubmed_api')
    @patch('iridia_daily.health_handler.check_ses_sender')
    def test_logging_on_success(self, mock_ses, mock_pubmed,
                                mock_bedrock, mock_secrets, capsys):
        """Test structured logging when all checks pass."""
        from iridia_daily.health_handler import lambda_handler
        
        # Explicitly mock all check functions
        mock_ses.return_value = (True, 45, None)
        mock_pubmed.return_value = (True, 120, None)
        mock_bedrock.return_value = (True, 890, None)
        mock_secrets.return_value = (True, 30, None)
        
        event = {}
        context = Mock()
        context.aws_request_id = 'test-request-123'
        
        lambda_handler(event, context)
        
        captured = capsys.readouterr()
        logs = [json.loads(line) for line in captured.out.strip().split('\n') if line]
        
        event_types = [log['event_type'] for log in logs]
        assert 'health_check_started' in event_types
        assert 'health_check_completed' in event_types
        assert 'ses_check_passed' in event_types
        assert 'pubmed_check_passed' in event_types
    
    @patch('iridia_daily.health_handler.check_secrets_manager')
    @patch('iridia_daily.health_handler.check_bedrock_api')
    @patch('iridia_daily.health_handler.check_pubmed_api')
    @patch('iridia_daily.health_handler.check_ses_sender')
    def test_logging_on_failure(self, mock_ses, mock_pubmed,
                               mock_bedrock, mock_secrets, capsys):
        """Test structured logging when checks fail."""
        from iridia_daily.health_handler import lambda_handler
        
        # Explicitly mock check functions with one failure
        mock_ses.return_value = (False, 42, "Not verified")
        mock_pubmed.return_value = (True, 120, None)
        mock_bedrock.return_value = (True, 890, None)
        mock_secrets.return_value = (True, 30, None)
        
        event = {}
        context = Mock()
        context.aws_request_id = 'test-request-123'
        
        lambda_handler(event, context)
        
        captured = capsys.readouterr()
        logs = [json.loads(line) for line in captured.out.strip().split('\n') if line]
        
        event_types = [log['event_type'] for log in logs]
        assert 'ses_check_failed' in event_types
        
        failed_log = next(log for log in logs if log['event_type'] == 'ses_check_failed')
        assert 'error' in failed_log
        assert failed_log['level'] == 'WARNING'