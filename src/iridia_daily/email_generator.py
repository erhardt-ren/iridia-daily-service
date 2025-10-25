"""Email content generation for newsletter distribution.

Generates HTML and plain text email content with proper formatting,
personalized unsubscribe links, and preferences management links.
"""

import random
from datetime import datetime
from .config import SUBJECT_TEMPLATES, CATEGORY_MAPPING


class EmailGenerator:
    """Generates email content for newsletter distribution."""

    def generate_html_email(self, papers, summaries, date_str, unsubscribe_url='', preferences_url='', paper_topics=None):
        """Generate HTML email content with personalized links.

        Args:
            papers: List of paper dictionaries with metadata.
            summaries: List of generated summaries for papers.
            date_str: Formatted date string for newsletter.
            unsubscribe_url: Full unsubscribe URL with secure token.
            preferences_url: Full preferences URL with secure token.
            paper_topics: List of topic strings (e.g., 'neuroscience', 'space') for each paper.

        Returns:
            str: Complete HTML email content.
        """
        # Use paper_topics if provided, otherwise fall back to 'default'
        if paper_topics is None:
            paper_topics = ['default'] * len(papers)
        
        paper_sections = "".join([
            self._create_paper_section(paper, summary, topic, i == 0, i == len(papers) - 1)
            for i, (paper, summary, topic) in enumerate(zip(papers, summaries, paper_topics))
        ])

        return self._build_html_template(paper_sections, date_str, len(papers), unsubscribe_url, preferences_url)

    def generate_plain_text_email(self, papers, summaries, date_str, unsubscribe_url='', preferences_url='', paper_topics=None):
        """Generate plain text email content with personalized links.

        Args:
            papers: List of paper dictionaries with metadata.
            summaries: List of generated summaries for papers.
            date_str: Formatted date string for newsletter.
            unsubscribe_url: Full unsubscribe URL with secure token.
            preferences_url: Full preferences URL with secure token.
            paper_topics: List of topic strings for each paper (not used in plain text).

        Returns:
            str: Complete plain text email content.
        """
        lines = [
            f"IRIDIA DAILY RESEARCH INTELLIGENCE\n{date_str}",
            "=" * 50
        ]

        for i, (paper, summary) in enumerate(zip(papers, summaries), 1):
            lines.extend([
                f"\n{i}. {summary}",
                f"   Source: {paper['journal']} ({paper['year']})",
                f"   {paper['url']}\n"
            ])

        lines.extend([
            "=" * 50,
            "\n© 2025 Iridia Daily. Intelligence worth sharing.",
            ""
        ])
        
        # Add support link with coffee emoji
        lines.append("☕ Support: https://buymeacoffee.com/iridia")

        # Add footer links
        footer_links = []
        if preferences_url:
            footer_links.append(f"Preferences: {preferences_url}")
        if unsubscribe_url:
            footer_links.append(f"Unsubscribe: {unsubscribe_url}")
        
        if footer_links:
            lines.append("")
            lines.extend(footer_links)

        return "\n".join(lines)

    def generate_subject_line(self, paper_count=5):
        """Generate random subject line for newsletter.

        Args:
            paper_count: Number of papers in the newsletter.

        Returns:
            str: Formatted subject line.
        """
        today = datetime.now()
        return random.choice(SUBJECT_TEMPLATES).format(
            day=today.strftime('%A'),
            count=paper_count,
            date=today.strftime('%B %d')
        )

    def _create_paper_section(self, paper, summary, topic, is_first, is_last):
        """Create HTML section for a single paper.

        Args:
            paper: Paper metadata dictionary.
            summary: Generated summary text.
            topic: Topic string (e.g., 'neuroscience', 'space').
            is_first: Whether this is the first paper.
            is_last: Whether this is the last paper.

        Returns:
            str: HTML section for paper.
        """
        # Get category info from CATEGORY_MAPPING using the assigned topic
        if topic in CATEGORY_MAPPING:
            accent_color, category_label, _ = CATEGORY_MAPPING[topic]
        else:
            accent_color, category_label, _ = CATEGORY_MAPPING['default']

        divider = "" if is_last else """
        <tr><td style="padding: 24px 40px;">
            <div style="height: 1px; background: linear-gradient(to right, transparent, var(--border-color), transparent);"></div>
        </td></tr>"""

        return f"""
        <tr>
            <td style="padding: {'32px 40px 20px 40px' if is_first else '20px 40px'};">
                <table cellpadding="0" cellspacing="0" border="0" role="presentation">
                    <tr><td>
                        <div style="display: inline-block; background: linear-gradient(135deg, {accent_color}1A, {accent_color}0D); border: 1.5px solid {accent_color}40; color: {accent_color}; padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 12px;">
                            {category_label}
                        </div>
                    </td></tr>
                </table>
                <p style="margin: 0 0 16px 0; padding: 0; color: var(--text-primary); font-size: 17px; line-height: 1.7; font-weight: 400;">
                    {summary}
                </p>
                <p style="margin: 0; padding: 0; color: var(--text-secondary); font-size: 13px;">
                    <strong style="color: var(--text-primary);">{paper['journal']}</strong> ({paper['year']}) • 
                    <a href="{paper['url']}" style="color: {accent_color}; text-decoration: none; font-weight: 500;">Read Paper →</a>
                </p>
            </td>
        </tr>
        {divider}"""

    def _build_html_template(self, paper_sections, date_str, num_papers, unsubscribe_url, preferences_url):
        """Build complete HTML email template with personalized links.

        Args:
            paper_sections: Combined HTML for all paper sections.
            date_str: Formatted date string.
            num_papers: Number of papers included.
            unsubscribe_url: Full unsubscribe URL with secure token.
            preferences_url: Full preferences URL with secure token.

        Returns:
            str: Complete HTML email template.
        """
        unsubscribe_link = unsubscribe_url if unsubscribe_url else "#"
        preferences_link = preferences_url if preferences_url else "#"

        # Build footer links section
        footer_links = []
        if preferences_url:
            footer_links.append(f'<a href="{preferences_link}" style="color: #6c757d; text-decoration: none; padding: 0 8px;">Preferences</a>')
        footer_links.append(f'<a href="{unsubscribe_link}" style="color: #6c757d; text-decoration: none; padding: 0 8px;">Unsubscribe</a>')
        
        footer_links_html = '<span style="color: #dee2e6;">|</span>'.join(footer_links)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light dark">
    <title>Iridia Daily Research Intelligence</title>
    <style>
        :root {{
            color-scheme: light dark;
            --primary-gradient-start: #0f2027;
            --primary-gradient-end: #2c5364;
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-primary: #1a1a1a;
            --text-secondary: #6c757d;
            --border-color: #e9ecef;
            --shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg-color: #1a1a1a;
                --card-bg: #2d2d2d;
                --text-primary: #ffffff;
                --text-secondary: #b0b0b0;
                --border-color: #404040;
                --shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            }}
        }}
        body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; background-color: var(--bg-color); }}
    </style>
</head>
<body>
    <div style="display: none; max-height: 0; overflow: hidden;">Today's {num_papers} breakthrough research insights...</div>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: var(--bg-color); padding: 40px 20px;">
        <tr><td align="center">
            <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; background-color: var(--card-bg); border-radius: 16px; overflow: hidden; box-shadow: var(--shadow);">
                
                <tr><td style="background: linear-gradient(135deg, var(--primary-gradient-start) 0%, var(--primary-gradient-end) 100%); padding: 48px 40px; text-align: center;">
                    <h1 style="margin: 0; color: #F0F8FF; font-size: 42px; font-weight: 700; letter-spacing: 2px;">IRIDIA DAILY</h1>
                    <p style="margin: 12px 0 0 0; color: rgba(255, 255, 255, 0.9); font-size: 15px; letter-spacing: 0.5px;">Research Intelligence Daily</p>
                </td></tr>
                
                <tr><td style="background: linear-gradient(to right, rgba(15, 32, 39, 0.05), rgba(44, 83, 100, 0.05)); padding: 16px 40px; border-bottom: 1px solid var(--border-color);">
                    <p style="margin: 0; color: var(--text-secondary); font-size: 13px; font-weight: 500; text-align: center; letter-spacing: 0.5px; text-transform: uppercase;">{date_str}</p>
                </td></tr>
                
                {paper_sections}
                
                <tr><td style="padding: 32px 40px; background-color: var(--card-bg); border-top: 1px solid var(--border-color);">
                    <p style="margin: 0 0 20px 0; color: var(--text-secondary); font-size: 13px; line-height: 1.6;">
                        <strong style="color: var(--text-primary);">Iridia Daily</strong> delivers breakthrough research intelligence daily. Powered by AI, designed for curious minds.
                    </p>
                    
                    <p style="margin: 0 0 16px 0;">
                        <a href="https://buymeacoffee.com/iridia" style="color: #6c757d; text-decoration: none; font-size: 13px;">
                            ☕ <span style="border-bottom: 1px solid #dee2e6;">Support Iridia Daily</span>
                        </a>
                    </p>
                    
                    <p style="margin: 0 0 12px 0; color: var(--text-secondary); font-size: 11px;">© 2025 Iridia Daily. Intelligence worth sharing.</p>
                    <p style="margin: 0; color: #6c757d; font-size: 11px; line-height: 1.8;">
                        {footer_links_html}
                    </p>
                </td></tr>
                
            </table>
        </td></tr>
    </table>
</body>
</html>"""