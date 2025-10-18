"""Tests for email generation."""

import pytest
from datetime import datetime


class TestEmailGenerator:
    """Test email content generation."""

    def test_generate_html_email_structure(self, sample_papers_diverse,
                                           assert_email_structure):
        """Test HTML email has proper structure and content."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = [
            "Brain research shows memory consolidation during sleep.",
            "Exoplanet discovery in the habitable zone.",
            "Gene therapy breakthrough for sickle cell disease.",
            "Quantum computing advances at room temperature.",
            "Ocean ecosystems adapt to climate change."
        ]

        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        unsubscribe_url = "https://api.test.com/prod/unsubscribe?token=abc123"
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, date_str, unsubscribe_url
        )

        assert_email_structure(html)
        assert date_str in html
        assert summaries[0] in html
        assert sample_papers_diverse[0]['journal'] in html
        assert sample_papers_diverse[0]['url'] in html
        assert unsubscribe_url in html

    def test_generate_html_email_without_unsubscribe_url(
        self, sample_papers_diverse
    ):
        """Test HTML email generation without unsubscribe URL."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]

        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, date_str
        )

        assert 'unsubscribe' in html.lower()

    def test_generate_plain_text_email(self, sample_papers_diverse):
        """Test plain text email generation."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]

        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        unsubscribe_url = "https://api.test.com/prod/unsubscribe?token=xyz"
        text = generator.generate_plain_text_email(
            sample_papers_diverse, summaries, date_str, unsubscribe_url
        )

        assert 'IRIDIA DAILY' in text
        assert date_str in text
        assert summaries[0] in text
        assert sample_papers_diverse[0]['journal'] in text
        assert sample_papers_diverse[0]['url'] in text
        assert unsubscribe_url in text
        assert '<' not in text or '=' * 50 in text

    def test_generate_subject_line_format(self):
        """Test subject line generation."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        subject = generator.generate_subject_line()

        assert 'Iridia' in subject or 'IRIDIA' in subject.upper()
        assert len(subject) > 10
        assert len(subject) < 100

    def test_paper_categorization_in_html(self, sample_paper):
        """Test that papers are categorized correctly with colors."""
        from iridia_daily.email_generator import EmailGenerator

        neuroscience_summary = "Research on brain activity."

        generator = EmailGenerator()
        section = generator._create_paper_section(
            sample_paper, neuroscience_summary, is_first=True, is_last=False
        )

        assert 'NEUROSCIENCE' in section or '🧠' in section
        assert sample_paper['url'] in section
        assert 'Read Paper' in section

    def test_paper_section_dividers(self, sample_paper):
        """Test that dividers are added between papers but not after last."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        summary = "Test summary text."

        middle_section = generator._create_paper_section(
            sample_paper, summary, is_first=False, is_last=False
        )

        last_section = generator._create_paper_section(
            sample_paper, summary, is_first=False, is_last=True
        )

        assert middle_section.count('height: 1px') > last_section.count(
            'height: 1px'
        )

    def test_email_dark_mode_support(self, sample_papers_diverse):
        """Test that email includes dark mode CSS."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]
        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, date_str
        )

        assert 'prefers-color-scheme: dark' in html
        assert '--bg-color' in html

    def test_email_preview_text(self, sample_papers_diverse):
        """Test that email includes preview text for email clients."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]
        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, date_str
        )

        assert 'display: none' in html or 'max-height: 0' in html
        assert 'breakthrough' in html.lower() or 'research' in html.lower()


class TestEmailAccessibility:
    """Test email accessibility features."""

    def test_html_email_responsive_design(self, sample_papers_diverse):
        """Test that email uses responsive design elements."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]
        generator = EmailGenerator()
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, "Test Date"
        )

        assert 'viewport' in html
        assert 'max-width' in html

    def test_email_accessibility(self, sample_papers_diverse):
        """Test that email follows accessibility best practices."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]
        generator = EmailGenerator()
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, "Test Date"
        )

        assert '<table' in html
        assert 'role="presentation"' in html
        assert 'lang="en"' in html

    def test_plain_text_formatting(self, sample_papers_diverse):
        """Test plain text email is properly formatted."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]
        generator = EmailGenerator()
        text = generator.generate_plain_text_email(
            sample_papers_diverse, summaries, "Test Date"
        )

        assert text.count('=') >= 4
        assert text.count('\n') > 10

        for i in range(1, 6):
            assert f'{i}.' in text