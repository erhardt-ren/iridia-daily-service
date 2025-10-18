"""Tests for secure token generation and verification."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import time
import base64
import hmac
import hashlib


class TestSecretRetrieval:
    """Test secure secret retrieval from AWS Secrets Manager."""
    
    @patch('iridia_daily.token_utils.secrets_client')
    def test_get_hmac_secret_success(self, mock_secrets, monkeypatch):
        """Test successful secret retrieval."""
        from iridia_daily.token_utils import get_hmac_secret
        
        # Clear cache
        get_hmac_secret.cache_clear()
        
        monkeypatch.setenv('HMAC_SECRET_ARN', 'arn:aws:secretsmanager:us-east-1:123:secret:test')
        
        mock_secrets.get_secret_value.return_value = {
            'SecretString': '{"key": "test-secret-key-12345"}'
        }
        
        secret = get_hmac_secret()
        
        assert secret == 'test-secret-key-12345'
        mock_secrets.get_secret_value.assert_called_once()
    
    @patch('iridia_daily.token_utils.secrets_client')
    def test_get_hmac_secret_cached(self, mock_secrets, monkeypatch):
        """Test that secret is cached and not retrieved multiple times."""
        from iridia_daily.token_utils import get_hmac_secret
        
        # Clear cache
        get_hmac_secret.cache_clear()
        
        monkeypatch.setenv('HMAC_SECRET_ARN', 'arn:aws:secretsmanager:us-east-1:123:secret:test')
        
        mock_secrets.get_secret_value.return_value = {
            'SecretString': '{"key": "cached-secret"}'
        }
        
        # Call multiple times
        secret1 = get_hmac_secret()
        secret2 = get_hmac_secret()
        secret3 = get_hmac_secret()
        
        # Should only call Secrets Manager once due to caching
        assert mock_secrets.get_secret_value.call_count == 1
        assert secret1 == secret2 == secret3 == 'cached-secret'
    
    def test_get_hmac_secret_missing_arn(self, monkeypatch):
        """Test error when HMAC_SECRET_ARN not set."""
        from iridia_daily.token_utils import get_hmac_secret
        
        # Clear cache
        get_hmac_secret.cache_clear()
        
        monkeypatch.delenv('HMAC_SECRET_ARN', raising=False)
        
        with pytest.raises(ValueError, match="HMAC_SECRET_ARN"):
            get_hmac_secret()
    
    @patch('iridia_daily.token_utils.secrets_client')
    def test_get_hmac_secret_api_error(self, mock_secrets, monkeypatch):
        """Test handling of Secrets Manager API errors."""
        from iridia_daily.token_utils import get_hmac_secret
        
        # Clear cache
        get_hmac_secret.cache_clear()
        
        monkeypatch.setenv('HMAC_SECRET_ARN', 'arn:aws:secretsmanager:us-east-1:123:secret:test')
        
        mock_secrets.get_secret_value.side_effect = Exception("API Error")
        
        with pytest.raises(Exception):
            get_hmac_secret()


class TestConfirmationTokens:
    """Test confirmation token generation and verification."""
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_generate_confirmation_token_format(self, mock_secret):
        """Test that generated token has correct format."""
        from iridia_daily.token_utils import generate_confirmation_token
        
        mock_secret.return_value = 'test-secret-key'
        
        token = generate_confirmation_token('user@example.com')
        
        # Should be base64 encoded
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Should be URL-safe base64
        try:
            decoded = base64.urlsafe_b64decode(token)
            assert b'|' in decoded  # Contains separators
        except Exception:
            pytest.fail("Token is not valid base64")
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_verify_valid_confirmation_token(self, mock_secret):
        """Test verification of valid confirmation token."""
        from iridia_daily.token_utils import (
            generate_confirmation_token,
            verify_confirmation_token
        )
        
        mock_secret.return_value = 'test-secret-key'
        
        email = 'user@example.com'
        token = generate_confirmation_token(email)
        
        verified_email = verify_confirmation_token(token)
        
        assert verified_email == email
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_verify_expired_confirmation_token(self, mock_secret):
        """Test that expired tokens are rejected."""
        from iridia_daily.token_utils import verify_confirmation_token
        
        mock_secret.return_value = 'test-secret-key'
        
        # Manually create expired token
        email = 'user@example.com'
        expiry_timestamp = int(time.time()) - 3600  # 1 hour ago
        
        message = f"{email}|{expiry_timestamp}"
        signature = hmac.new(
            'test-secret-key'.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        token_data = f"{message}|{signature}"
        token = base64.urlsafe_b64encode(token_data.encode()).decode()
        
        verified_email = verify_confirmation_token(token)
        
        assert verified_email is None
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_verify_tampered_confirmation_token(self, mock_secret):
        """Test that tampered tokens are rejected."""
        from iridia_daily.token_utils import (
            generate_confirmation_token,
            verify_confirmation_token
        )
        
        mock_secret.return_value = 'test-secret-key'
        
        token = generate_confirmation_token('user@example.com')
        
        # Tamper with token
        decoded = base64.urlsafe_b64decode(token)
        tampered = decoded.replace(b'user@', b'hacker@')
        tampered_token = base64.urlsafe_b64encode(tampered).decode()
        
        verified_email = verify_confirmation_token(tampered_token)
        
        assert verified_email is None
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_verify_malformed_confirmation_token(self, mock_secret):
        """Test that malformed tokens are rejected."""
        from iridia_daily.token_utils import verify_confirmation_token
        
        mock_secret.return_value = 'test-secret-key'
        
        # Various malformed tokens
        malformed_tokens = [
            'not-base64!@#',
            base64.urlsafe_b64encode(b'no-separators').decode(),
            base64.urlsafe_b64encode(b'only|one').decode(),
            base64.urlsafe_b64encode(b'email|notanumber|sig').decode(),
            ''
        ]
        
        for token in malformed_tokens:
            assert verify_confirmation_token(token) is None
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_confirmation_token_email_normalization(self, mock_secret):
        """Test that emails are normalized in tokens."""
        from iridia_daily.token_utils import (
            generate_confirmation_token,
            verify_confirmation_token
        )
        
        mock_secret.return_value = 'test-secret-key'
        
        # Generate with uppercase
        token = generate_confirmation_token('User@EXAMPLE.COM')
        
        # Should verify as lowercase
        verified_email = verify_confirmation_token(token)
        
        assert verified_email == 'user@example.com'
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_confirmation_token_custom_expiry(self, mock_secret):
        """Test confirmation token with custom expiry."""
        from iridia_daily.token_utils import (
            generate_confirmation_token,
            verify_confirmation_token
        )
        
        mock_secret.return_value = 'test-secret-key'
        
        # Generate token with 48 hour expiry
        token = generate_confirmation_token('user@example.com', expiry_hours=48)
        
        # Should still be valid
        verified_email = verify_confirmation_token(token)
        
        assert verified_email == 'user@example.com'


class TestUnsubscribeTokens:
    """Test unsubscribe token generation and verification."""
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_generate_unsubscribe_token(self, mock_secret):
        """Test unsubscribe token generation."""
        from iridia_daily.token_utils import generate_unsubscribe_token
        
        mock_secret.return_value = 'test-secret-key'
        
        token = generate_unsubscribe_token('user@example.com')
        
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Should be valid base64
        try:
            base64.urlsafe_b64decode(token)
        except Exception:
            pytest.fail("Token is not valid base64")
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_verify_valid_unsubscribe_token(self, mock_secret):
        """Test verification of valid unsubscribe token."""
        from iridia_daily.token_utils import (
            generate_unsubscribe_token,
            verify_unsubscribe_token
        )
        
        mock_secret.return_value = 'test-secret-key'
        
        email = 'user@example.com'
        token = generate_unsubscribe_token(email)
        
        verified_email = verify_unsubscribe_token(token)
        
        assert verified_email == email
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_unsubscribe_token_no_expiration(self, mock_secret):
        """Test that unsubscribe tokens don't expire."""
        from iridia_daily.token_utils import (
            generate_unsubscribe_token,
            verify_unsubscribe_token
        )
        
        mock_secret.return_value = 'test-secret-key'
        
        # Generate token
        email = 'user@example.com'
        token = generate_unsubscribe_token(email)
        
        # Should be valid even after time passes
        # (In real scenario, this would be tested over time)
        verified_email = verify_unsubscribe_token(token)
        
        assert verified_email == email
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_verify_tampered_unsubscribe_token(self, mock_secret):
        """Test that tampered unsubscribe tokens are rejected."""
        from iridia_daily.token_utils import (
            generate_unsubscribe_token,
            verify_unsubscribe_token
        )
        
        mock_secret.return_value = 'test-secret-key'
        
        token = generate_unsubscribe_token('user@example.com')
        
        # Tamper with token
        decoded = base64.urlsafe_b64decode(token)
        tampered = decoded.replace(b'user@', b'hacker@')
        tampered_token = base64.urlsafe_b64encode(tampered).decode()
        
        verified_email = verify_unsubscribe_token(tampered_token)
        
        assert verified_email is None
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_verify_malformed_unsubscribe_token(self, mock_secret):
        """Test that malformed unsubscribe tokens are rejected."""
        from iridia_daily.token_utils import verify_unsubscribe_token
        
        mock_secret.return_value = 'test-secret-key'
        
        malformed_tokens = [
            'not-base64!@#',
            base64.urlsafe_b64encode(b'noseparator').decode(),
            base64.urlsafe_b64encode(b'too|many|parts').decode(),
            ''
        ]
        
        for token in malformed_tokens:
            assert verify_unsubscribe_token(token) is None


class TestTokenSecurity:
    """Test security properties of token system."""
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_different_secrets_produce_different_tokens(self, mock_secret):
        """Test that different secrets produce different tokens."""
        from iridia_daily.token_utils import generate_confirmation_token
        
        email = 'user@example.com'
        
        mock_secret.return_value = 'secret-1'
        token1 = generate_confirmation_token(email)
        
        mock_secret.return_value = 'secret-2'
        token2 = generate_confirmation_token(email)
        
        assert token1 != token2
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_same_email_produces_different_tokens(self, mock_secret):
        """Test that same email produces different tokens due to timestamp."""
        from iridia_daily.token_utils import generate_confirmation_token
        
        mock_secret.return_value = 'test-secret'
        
        email = 'user@example.com'
        token1 = generate_confirmation_token(email)
        
        time.sleep(1)  # Wait to get different timestamp
        
        token2 = generate_confirmation_token(email)
        
        # Tokens should be different due to different timestamps
        assert token1 != token2
    
    @patch('iridia_daily.token_utils.get_hmac_secret')
    def test_cross_validation_fails(self, mock_secret):
        """Test that confirmation token can't be used as unsubscribe token."""
        from iridia_daily.token_utils import (
            generate_confirmation_token,
            verify_unsubscribe_token
        )
        
        mock_secret.return_value = 'test-secret'
        
        # Generate confirmation token
        confirmation_token = generate_confirmation_token('user@example.com')
        
        # Try to use as unsubscribe token
        verified = verify_unsubscribe_token(confirmation_token)
        
        # Should fail because formats are different
        assert verified is None