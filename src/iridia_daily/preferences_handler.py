"""Subscription preference management handler.

UPDATED: Saves and reads topic preferences from SES TopicPreferences.
"""

import json
import boto3
import os
from datetime import datetime, timezone

from . import monitoring
from .token_utils import verify_unsubscribe_token
from .logger import set_lambda_context, log_info, log_warning, log_error
from .templates import template_loader
from .config import CATEGORY_MAPPING

ses_v2 = boto3.client('sesv2', region_name='us-east-1')


def validate_topics(topics):
    """Validate topic preferences against configured categories."""
    if not isinstance(topics, list):
        return False, [], "Topics must be a list"

    valid_topics = {key for key in CATEGORY_MAPPING.keys() if key != 'default'}

    validated = []
    for topic in topics:
        if not isinstance(topic, str):
            return False, [], f"Invalid topic type: {type(topic).__name__}"

        topic_lower = topic.lower().strip()
        if topic_lower not in valid_topics:
            return False, [], (f"Invalid topic: {topic}. "
                             f"Valid topics: {', '.join(sorted(valid_topics))}")

        validated.append(topic_lower)

    validated = list(dict.fromkeys(validated))

    if not validated:
        return False, [], "At least one topic must be selected"

    return True, validated, None


def update_contact_preferences(email, topics):
    """Update subscriber's topic preferences in SES TopicPreferences.

    Args:
        email: Subscriber email address.
        topics: List of validated topic strings.

    Returns:
        tuple: (success, error_message).
            - success: Boolean indicating if update succeeded.
            - error_message: Error description if update failed, None otherwise.
    """
    contact_list_name = os.environ.get('CONTACT_LIST_NAME')

    try:
        # Get all available topics
        all_topics = [key for key in CATEGORY_MAPPING.keys() if key != 'default']
        
        # Build TopicPreferences - opt in to selected topics, opt out of others
        topic_preferences = []
        for topic in all_topics:
            topic_preferences.append({
                'TopicName': topic,
                'SubscriptionStatus': 'OPT_IN' if topic in topics else 'OPT_OUT'
            })
        
        # Always keep daily-research as OPT_IN (for subscription management)
        topic_preferences.append({
            'TopicName': 'daily-research',
            'SubscriptionStatus': 'OPT_IN'
        })
        
        # Update contact in SES
        def update_operation():
            return ses_v2.update_contact(
                ContactListName=contact_list_name,
                EmailAddress=email,
                TopicPreferences=topic_preferences,
                AttributesData=json.dumps({
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                    'version': '1.0'
                })
            )

        monitoring.retry_with_backoff(update_operation, max_attempts=3)

        log_info('preferences_updated',
                email=email,
                topics=topics,
                topic_count=len(topics))

        # Track metric for each topic
        for topic in topics:
            monitoring.put_metric('PreferenceUpdate', 1, dimensions=[
                {'Name': 'Topic', 'Value': topic},
                {'Name': 'Action', 'Value': 'Selected'}
            ])

        return True, None

    except ses_v2.exceptions.NotFoundException:
        log_warning('contact_not_found', email=email)
        return False, "Email address not found in subscriber list"

    except Exception as e:
        log_error('preference_update_error',
                 email=email,
                 error_type=type(e).__name__,
                 error_message=str(e))
        return False, f"Error updating preferences: {str(e)}"


def get_current_preferences(email):
    """Fetch subscriber's current topic preferences from SES TopicPreferences.

    Args:
        email: Subscriber email address.

    Returns:
        list or None: List of opted-in topics, or None if no preferences stored
            or if contact not found.
    """
    contact_list_name = os.environ.get('CONTACT_LIST_NAME')

    try:
        contact = ses_v2.get_contact(
            ContactListName=contact_list_name,
            EmailAddress=email
        )

        # Read from TopicPreferences
        topic_prefs = contact.get('TopicPreferences', [])
        
        # Extract topics where SubscriptionStatus is OPT_IN
        opted_in_topics = [
            tp['TopicName'] 
            for tp in topic_prefs 
            if tp.get('SubscriptionStatus') == 'OPT_IN'
        ]
        
        # Return None if no topics or all topics (user gets all content)
        if not opted_in_topics:
            return None
        
        return opted_in_topics

    except ses_v2.exceptions.NotFoundException:
        log_warning('contact_not_found_for_preferences', email=email)
        return None

    except Exception as e:
        log_error('get_preferences_error',
                 email=email,
                 error_type=type(e).__name__,
                 error_message=str(e))
        return None


def lambda_handler(event, context):
    """Handle preference update requests.

    Supports both POST requests with JSON body and GET requests for
    displaying the preferences form.

    POST /preferences?token=<token>
    Body: {"topics": ["neuroscience", "space", "biology"]}

    GET /preferences?token=<token>
    Returns: HTML form for preference management

    Args:
        event: API Gateway event.
        context: Lambda context.

    Returns:
        dict: API Gateway response (JSON for POST, HTML for GET).
    """
    set_lambda_context(context)

    http_method = event.get('httpMethod', 'POST')

    # Handle CORS preflight
    if http_method == 'OPTIONS':
        return cors_response(200, {'message': 'OK'})

    # Extract and verify token
    params = event.get('queryStringParameters', {}) or {}
    token = params.get('token', '')

    if not token:
        log_warning('missing_preferences_token')
        monitoring.put_metric('PreferenceUpdate', 1, dimensions=[
            {'Name': 'Status', 'Value': 'MissingToken'}
        ])
        if http_method == 'GET':
            return render_html(400, 'Invalid Link',
                             '<h1>Invalid Preferences Link</h1>'
                             '<p>This link is invalid or has expired.</p>')
        return cors_response(400, {'error': 'Missing token parameter'})

    # Verify token and extract email
    email = verify_unsubscribe_token(token)

    if not email:
        log_warning('invalid_preferences_token', token_prefix=token[:10])
        monitoring.put_metric('PreferenceUpdate', 1, dimensions=[
            {'Name': 'Status', 'Value': 'InvalidToken'}
        ])
        if http_method == 'GET':
            return render_html(400, 'Invalid Token',
                             '<h1>Invalid or Expired Link</h1>'
                             '<p>This preferences link is invalid or has expired.</p>')
        return cors_response(400, {'error': 'Invalid token'})

    # GET request - return preferences form
    if http_method == 'GET':
        return handle_get_preferences_form(email, token)

    # POST request - update preferences
    try:
        body = json.loads(event.get('body', '{}'))
        topics = body.get('topics', [])

        log_info('preference_update_request',
                email=email,
                topics=topics,
                topic_count=len(topics) if isinstance(topics, list) else 0)

        # Validate topics
        is_valid, validated_topics, error_msg = validate_topics(topics)
        if not is_valid:
            log_warning('invalid_topics_in_update',
                       email=email,
                       topics=topics,
                       error=error_msg)
            monitoring.put_metric('PreferenceUpdate', 1, dimensions=[
                {'Name': 'Status', 'Value': 'InvalidTopics'}
            ])
            return cors_response(400, {'error': error_msg})

        # Update preferences in SES
        success, error_msg = update_contact_preferences(email, validated_topics)

        if not success:
            monitoring.put_metric('PreferenceUpdate', 1, dimensions=[
                {'Name': 'Status', 'Value': 'UpdateFailed'}
            ])
            return cors_response(500, {'error': error_msg})

        monitoring.put_metric('PreferenceUpdate', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Success'}
        ])

        return cors_response(200, {
            'message': 'Preferences updated successfully',
            'email': email,
            'topics': validated_topics
        })

    except json.JSONDecodeError:
        log_warning('invalid_json_body', email=email)
        return cors_response(400, {'error': 'Invalid JSON in request body'})

    except Exception as e:
        log_error('preferences_handler_error',
                 email=email,
                 error_type=type(e).__name__,
                 error_message=str(e))
        monitoring.put_metric('PreferenceUpdate', 1, dimensions=[
            {'Name': 'Status', 'Value': 'Error'}
        ])
        return cors_response(500, {'error': 'Internal server error'})


def handle_get_preferences_form(email, token):
    """Generate HTML form for managing preferences."""
    # Get current preferences
    current_topics = get_current_preferences(email) or []
    
    # Get all available topics
    all_topics = [key for key in CATEGORY_MAPPING.keys() if key != 'default']
    
    # Generate checkboxes
    checkboxes_html = ""
    for topic in sorted(all_topics):
        checked = "checked" if topic in current_topics else ""
        topic_display = topic.replace('_', ' ').title()
        checkboxes_html += f"""
                <label class="topic-checkbox">
                    <input type="checkbox" name="topics" value="{topic}" {checked}>
                    <span class="topic-label">{topic_display}</span>
                </label>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Update Your Preferences - Iridia Daily</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                line-height: 1.6;
                color: #1a1a1a;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            .container {{
                background: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            .logo {{
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 2px;
                color: #666;
                text-align: center;
                margin-bottom: 20px;
            }}
            h1 {{
                color: #0f2027;
                margin: 0 0 10px 0;
                font-size: 28px;
            }}
            .subtitle {{
                color: #666;
                margin-bottom: 30px;
                font-size: 14px;
            }}
            .topic-checkbox {{
                display: flex;
                align-items: center;
                padding: 12px 15px;
                margin-bottom: 8px;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.2s;
            }}
            .topic-checkbox:hover {{
                background: #e9ecef;
                border-color: #0f2027;
            }}
            .topic-checkbox input {{
                margin-right: 10px;
            }}
            .topic-label {{
                font-size: 15px;
                font-weight: 500;
                color: #1a1a1a;
            }}
            .button {{
                display: block;
                width: 100%;
                padding: 14px;
                background: #0f2027;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                margin-top: 20px;
                transition: background 0.2s;
            }}
            .button:hover:not(:disabled) {{
                background: #1a2f3a;
            }}
            .button:disabled {{
                background: #ccc;
                cursor: not-allowed;
            }}
            .message {{
                padding: 12px 15px;
                margin: 15px 0;
                border-radius: 8px;
                display: none;
                font-size: 14px;
            }}
            .message.success {{
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }}
            .message.error {{
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }}
            .info {{
                color: #6c757d;
                font-size: 13px;
                margin-top: 15px;
                line-height: 1.5;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">IRIDIA DAILY</div>
            <h1>Update Your Preferences</h1>
            <p class="subtitle">Managing preferences for <strong>{email}</strong></p>

            <div id="message" class="message"></div>

            <form id="preferences-form">
                <p style="margin: 0 0 12px 0; font-weight: 500; color: #1a1a1a; font-size: 15px;">
                    Select the topics you're interested in:
                </p>

                {checkboxes_html}

                <button type="submit" class="button">Save Preferences</button>
            </form>

            <p class="info">
                You'll only receive papers matching your selected topics.
                Select at least one topic to continue receiving newsletters.
            </p>
        </div>

        <script>
            const form = document.getElementById('preferences-form');
            const messageDiv = document.getElementById('message');

            form.addEventListener('submit', async (e) => {{
                e.preventDefault();

                // Get selected topics
                const checkboxes = form.querySelectorAll('input[name="topics"]:checked');
                const topics = Array.from(checkboxes).map(cb => cb.value);

                if (topics.length === 0) {{
                    showMessage('Please select at least one topic', 'error');
                    return;
                }}

                // Disable button during request
                const button = form.querySelector('button');
                button.disabled = true;
                button.textContent = 'Saving...';

                try {{
                    const response = await fetch(
                        window.location.pathname + window.location.search,
                        {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                            }},
                            body: JSON.stringify({{ topics: topics }})
                        }}
                    );

                    const data = await response.json();

                    if (response.ok) {{
                        showMessage('✓ Preferences updated successfully!', 'success');
                        button.textContent = 'Saved!';
                    }} else {{
                        showMessage('Error: ' + (data.error || 'Failed to update preferences'), 'error');
                        button.disabled = false;
                        button.textContent = 'Save Preferences';
                    }}
                }} catch (error) {{
                    showMessage('Error: Failed to connect to server', 'error');
                    button.disabled = false;
                    button.textContent = 'Save Preferences';
                }}
            }});

            function showMessage(text, type) {{
                messageDiv.textContent = text;
                messageDiv.className = 'message ' + type;
                messageDiv.style.display = 'block';

                if (type === 'success') {{
                    setTimeout(() => {{
                        messageDiv.style.display = 'none';
                    }}, 5000);
                }}
            }}
        </script>
    </body>
    </html>
    """

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html'},
        'body': html
    }


def render_html(status_code, title, content):
    """Render HTML response for error pages using template."""
    html = template_loader.render_base_template(title, content)
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'text/html'},
        'body': html
    }


def cors_response(status_code, body):
    """Create API Gateway response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body)
    }