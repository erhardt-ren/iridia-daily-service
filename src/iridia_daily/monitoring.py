"""Monitoring and retry utilities for Iridia Daily."""

import time
import boto3
from botocore.exceptions import ClientError

cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')


def put_metric(metric_name, value, unit='Count', dimensions=None):
    """Publish metric to CloudWatch.

    Args:
        metric_name (str): Name of the metric.
        value (float): Metric value.
        unit (str): CloudWatch unit type.
        dimensions (list): Optional list of dimension dicts.
    """
    try:
        metric_data = {
            'MetricName': metric_name,
            'Value': value,
            'Unit': unit,
            'Timestamp': time.time()
        }

        if dimensions:
            metric_data['Dimensions'] = dimensions

        cloudwatch.put_metric_data(
            Namespace='IridiaDaily',
            MetricData=[metric_data]
        )
    except Exception as e:
        print(f"Metric publishing error: {e}")


def retry_with_backoff(func, max_attempts=3, base_delay=1):
    """Retry function with exponential backoff.

    Args:
        func (callable): Function to retry.
        max_attempts (int): Maximum retry attempts.
        base_delay (int): Initial delay in seconds.

    Returns:
        Function result if successful.

    Raises:
        Exception: Last exception if all attempts fail.
    """
    last_exception = None

    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            last_exception = e
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Attempt {attempt + 1} failed: {e}. "
                      f"Retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"All {max_attempts} attempts failed")

    raise last_exception


def verify_ses_sender(sender_email):
    """Verify sender email or domain is verified in SES.

    Checks if either the specific email address OR its domain is verified.
    When a domain is verified in SES, all email addresses at that domain
    are authorized to send, even if they don't physically exist.

    Args:
        sender_email (str): Email address to verify.

    Returns:
        bool: True if email or domain is verified, False otherwise.
    """
    ses = boto3.client('ses', region_name='us-east-1')

    try:
        if '@' not in sender_email:
            print(f"Invalid email format: {sender_email}")
            return False

        domain = sender_email.split('@')[1]

        response = ses.get_identity_verification_attributes(
            Identities=[sender_email, domain]
        )

        attributes = response.get('VerificationAttributes', {})

        email_status = attributes.get(sender_email, {})
        if email_status.get('VerificationStatus') == 'Success':
            print(f"Email address verified: {sender_email}")
            return True

        domain_status = attributes.get(domain, {})
        if domain_status.get('VerificationStatus') == 'Success':
            print(f"Domain verified: {domain} (allows {sender_email})")
            return True

        print(f"Neither email nor domain verified for: {sender_email}")
        email_ver = email_status.get('VerificationStatus', 'Not found')
        domain_ver = domain_status.get('VerificationStatus', 'Not found')
        print(f"  - Email status: {email_ver}")
        print(f"  - Domain status: {domain_ver}")
        return False

    except Exception as e:
        print(f"Sender verification error: {e}")
        return False