"""Iridia Daily - Research Intelligence Newsletter System.

This package provides a serverless email newsletter service that delivers
scientific research insights using AWS Lambda, SES, and Bedrock.
"""

__version__ = '2.0.0'
__author__ = 'Iridia Daily Team'

from . import newsletter_handler
from . import subscribe_handler
from . import unsubscribe_handler
from . import email_generator
from . import monitoring
from . import utils
from . import config

__all__ = [
    'newsletter_handler',
    'subscribe_handler',
    'unsubscribe_handler',
    'email_generator',
    'monitoring',
    'utils',
    'config',
]