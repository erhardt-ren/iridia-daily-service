"""Template loading utilities for HTML rendering."""

import os

# Get the templates directory path
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__))


def load_template(template_name):
    """Load HTML template from file.
    
    Args:
        template_name: Name of template file (e.g., 'base.html')
        
    Returns:
        str: Template content
        
    Raises:
        FileNotFoundError: If template file doesn't exist
    """
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read()


def render_template(template_name, **kwargs):
    """Render template with variable substitution.
    
    Uses simple string replacement instead of .format() to avoid
    conflicts with CSS curly braces.
    
    Args:
        template_name: Name of template file
        **kwargs: Variables to substitute in template
        
    Returns:
        str: Rendered template
    """
    template_content = load_template(template_name)
    
    # Use simple string replacement for each variable
    result = template_content
    for key, value in kwargs.items():
        placeholder = '{' + key + '}'
        result = result.replace(placeholder, value)
    
    return result


def render_base_template(title, content):
    """Render base HTML template with title and content.
    
    Args:
        title: Page title
        content: HTML content to insert
        
    Returns:
        str: Complete HTML page
    """
    return render_template(
        'base.html',
        title=title,
        content=content
    )