"""Monitoring and retry utilities for Iridia Daily."""

import time
import boto3
from botocore.exceptions import ClientError

cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')


def put_metric(metric_name, value, unit='Count', dimensions=None):
    """Publish metric to CloudWatch.

    Args:
        metric_name: Name of the metric.
        value: Metric value.
        unit: CloudWatch unit type.
        dimensions: Optional list of dimension dicts.
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
        func: Function to retry.
        max_attempts: Maximum retry attempts.
        base_delay: Initial delay in seconds.

    Returns:
        Function result if successful.

    Raises:
        Last exception if all attempts fail.
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
    """Verify sender email is configured in SES.

    Args:
        sender_email: Email address to verify.

    Returns:
        bool: True if verified, False otherwise.
    """
    ses = boto3.client('ses', region_name='us-east-1')

    try:
        response = ses.get_identity_verification_attributes(
            Identities=[sender_email]
        )

        attributes = response.get('VerificationAttributes', {})
        sender_status = attributes.get(sender_email, {})

        if sender_status.get('VerificationStatus') == 'Success':
            return True

        print(f"Sender email not verified: {sender_email}")
        return False

    except Exception as e:
        print(f"Sender verification error: {e}")
        return False