"""Secure token generation and verification using HMAC with AWS Secrets Manager.

Provides stateless, tamper-proof tokens for email confirmation and unsubscribe
links. Secrets are stored securely in AWS Secrets Manager, not environment variables.
"""

import hmac
import hashlib
import base64
import json
import time
import boto3
from functools import lru_cache

secrets_client = boto3.client('secretsmanager', region_name='us-east-1')


@lru_cache(maxsize=1)
def get_hmac_secret():
    """Retrieve HMAC secret from AWS Secrets Manager with caching.
    
    Uses LRU cache to minimize API calls during Lambda warm starts.
    
    Returns:
        str: HMAC secret key.
        
    Raises:
        Exception: If secret cannot be retrieved.
    """
    import os
    
    secret_arn = os.environ.get('HMAC_SECRET_ARN')
    
    if not secret_arn:
        raise ValueError("HMAC_SECRET_ARN environment variable not set")
    
    try:
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        
        # Secret is stored as JSON with 'key' field
        secret_data = json.loads(response['SecretString'])
        return secret_data['key']
        
    except Exception as e:
        print(f"Failed to retrieve HMAC secret: {e}")
        raise


def generate_confirmation_token(email, expiry_hours=24):
    """Generate secure confirmation token for email verification.
    
    Token format: base64(email|timestamp|hmac_signature)
    - Stateless: No database storage required
    - Tamper-proof: Any modification invalidates signature
    - Expiring: Automatic expiration after specified hours
    
    Args:
        email: Email address to encode in token.
        expiry_hours: Token validity period in hours (default: 24).
        
    Returns:
        str: URL-safe base64-encoded token.
    """
    secret = get_hmac_secret()
    
    expiry_timestamp = int(time.time()) + (expiry_hours * 3600)
    
    # Create message: email|expiry_timestamp
    message = f"{email.lower()}|{expiry_timestamp}"
    
    # Generate HMAC signature
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Combine message and signature
    token_data = f"{message}|{signature}"
    
    # Base64 encode for URL safety
    token = base64.urlsafe_b64encode(token_data.encode()).decode()
    
    return token


def verify_confirmation_token(token):
    """Verify and extract email from confirmation token.
    
    Validates:
    - Token format is correct
    - HMAC signature matches (not tampered)
    - Token has not expired
    
    Args:
        token: URL-safe base64-encoded token from email link.
        
    Returns:
        str: Verified email address if valid, None if invalid/expired.
    """
    try:
        secret = get_hmac_secret()
        
        # Decode from base64
        token_data = base64.urlsafe_b64decode(token.encode()).decode()
        
        # Parse token: email|timestamp|signature
        parts = token_data.split('|')
        if len(parts) != 3:
            print("Invalid token format: wrong number of parts")
            return None
        
        email, expiry_str, provided_signature = parts
        
        # Verify timestamp is valid integer
        try:
            expiry_timestamp = int(expiry_str)
        except ValueError:
            print("Invalid token format: bad timestamp")
            return None
        
        # Check expiration
        if time.time() > expiry_timestamp:
            print(f"Token expired for {email}")
            return None
        
        # Recompute expected signature
        message = f"{email}|{expiry_str}"
        expected_signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(expected_signature, provided_signature):
            print(f"Invalid signature for {email}")
            return None
        
        # All checks passed
        return email.lower()
        
    except Exception as e:
        print(f"Token verification error: {e}")
        return None


def generate_unsubscribe_token(email):
    """Generate secure unsubscribe token.
    
    Similar to confirmation token but with no expiration.
    Allows users to unsubscribe at any time via link.
    
    Args:
        email: Email address to encode in token.
        
    Returns:
        str: URL-safe base64-encoded token.
    """
    secret = get_hmac_secret()
    
    # No expiration for unsubscribe links
    message = email.lower()
    
    # Generate HMAC signature
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Combine email and signature
    token_data = f"{message}|{signature}"
    
    # Base64 encode for URL safety
    token = base64.urlsafe_b64encode(token_data.encode()).decode()
    
    return token


def verify_unsubscribe_token(token):
    """Verify and extract email from unsubscribe token.
    
    Args:
        token: URL-safe base64-encoded token from unsubscribe link.
        
    Returns:
        str: Verified email address if valid, None if invalid.
    """
    try:
        secret = get_hmac_secret()
        
        # Decode from base64
        token_data = base64.urlsafe_b64decode(token.encode()).decode()
        
        # Parse token: email|signature
        parts = token_data.split('|')
        if len(parts) != 2:
            print("Invalid unsubscribe token format")
            return None
        
        email, provided_signature = parts
        
        # Recompute expected signature
        expected_signature = hmac.new(
            secret.encode(),
            email.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison
        if not hmac.compare_digest(expected_signature, provided_signature):
            print(f"Invalid unsubscribe signature for {email}")
            return None
        
        return email.lower()
        
    except Exception as e:
        print(f"Unsubscribe token verification error: {e}")
        return None