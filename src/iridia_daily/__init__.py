"""Iridia Daily - Research Intelligence Newsletter System.

This package provides a serverless email newsletter service that delivers
scientific research insights using AWS Lambda, SES, and Bedrock with secure
double opt-in confirmation and personalized unsubscribe tokens.
"""

__version__ = '2.0.0'
__author__ = 'Iridia Daily Team'

from . import newsletter_handler
from . import subscribe_handler
from . import unsubscribe_handler
from . import confirm_handler
from . import email_generator
from . import monitoring
from . import utils
from . import config
from . import token_utils
from . import logger

__all__ = [
    'newsletter_handler',
    'subscribe_handler',
    'unsubscribe_handler',
    'confirm_handler',
    'email_generator',
    'monitoring',
    'utils',
    'config',
    'token_utils',
    'logger',
]