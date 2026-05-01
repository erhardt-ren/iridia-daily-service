"""Iridia Daily - Research Intelligence Newsletter System.

This package provides a serverless email newsletter service that delivers
scientific research insights using AWS Lambda, SES, and Bedrock with secure
double opt-in confirmation, personalized unsubscribe tokens, and web archive.
"""

__version__ = '1.0.0'
__author__ = 'Alex Howell'

from . import newsletter_handler
from . import subscribe_handler
from . import unsubscribe_handler
from . import confirm_handler
from . import preferences_handler
from . import archive_handler
from . import email_generator
from . import monitoring
from . import utils
from . import config
from . import token_utils
from . import logger
from . import archive_db

__all__ = [
    'newsletter_handler',
    'subscribe_handler',
    'unsubscribe_handler',
    'confirm_handler',
    'preferences_handler',
    'archive_handler',
    'archive_db',
    'email_generator',
    'monitoring',
    'utils',
    'config',
    'token_utils',
    'logger',
]