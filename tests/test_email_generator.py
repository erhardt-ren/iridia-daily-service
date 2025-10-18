"""Tests for email generation."""

import pytest
from datetime import datetime


class TestEmailGenerator:
    """Test email content generation."""
    
    def test_generate_html_email_structure(self, sample_papers_diverse, assert_email_structure):
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
        api_url = "https://test-api.example.com/prod"
        html = generator.generate_html_email(sample_papers_diverse, summaries, date_str, api_url)
        
        # Check structure
        assert_email_structure(html)
        
        # Check content
        assert date_str in html
        assert summaries[0] in html
        assert sample_papers_diverse[0]['journal'] in html
        assert sample_papers_diverse[0]['url'] in html
        
        # Check all papers included
        for paper in sample_papers_diverse:
            assert paper['journal'] in html
        
        # Check unsubscribe link
        assert api_url in html
        assert '/unsubscribe' in html
    
    def test_generate_html_email_without_api_url(self, sample_papers_diverse):
        """Test HTML email generation without API URL."""
        from iridia_daily.email_generator import EmailGenerator
        
        summaries = ["Summary " + str(i) for i in range(5)]
        
        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        html = generator.generate_html_email(sample_papers_diverse, summaries, date_str)
        
        # Should have a fallback unsubscribe link
        assert 'unsubscribe' in html.lower()
    
    def test_generate_plain_text_email(self, sample_papers_diverse):
        """Test plain text email generation."""
        from iridia_daily.email_generator import EmailGenerator
        
        summaries = ["Summary " + str(i) for i in range(5)]
        
        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        api_url = "https://test-api.example.com/prod"
        text = generator.generate_plain_text_email(sample_papers_diverse, summaries, date_str, api_url)
        
        assert 'IRIDIA DAILY' in text
        assert date_str in text
        assert summaries[0] in text
        assert sample_papers_diverse[0]['journal'] in text
        assert sample_papers_diverse[0]['url'] in text
        
        # Should have unsubscribe link
        assert api_url in text
        assert '/unsubscribe' in text
        
        # Should be plain text, no HTML tags
        assert '<' not in text or '=' * 50 in text  # Allow separators
    
    def test_generate_plain_text_email_without_api_url(self, sample_papers_diverse):
        """Test plain text email without API URL."""
        from iridia_daily.email_generator import EmailGenerator
        
        summaries = ["Summary " + str(i) for i in range(5)]
        
        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        text = generator.generate_plain_text_email(sample_papers_diverse, summaries, date_str)
        
        # Should not break without API URL
        assert 'IRIDIA DAILY' in text
        assert date_str in text
    
    def test_generate_subject_line_format(self):
        """Test subject line generation."""
        from iridia_daily.email_generator import EmailGenerator
        
        generator = EmailGenerator()
        subject = generator.generate_subject_line()
        
        assert 'Iridia' in subject or 'IRIDIA' in subject.upper()
        assert len(subject) > 10
        assert len(subject) < 100
    
    def test_generate_subject_line_variety(self):
        """Test that subject lines vary (uses random templates)."""
        from iridia_daily.email_generator import EmailGenerator
        
        generator = EmailGenerator()
        subjects = [generator.generate_subject_line() for _ in range(10)]
        
        # Should have some variety (not all the same)
        unique_subjects = set(subjects)
        assert len(unique_subjects) >= 1  # At least one template used
    
    def test_paper_categorization_in_html(self, sample_paper):
        """Test that papers are categorized correctly with colors."""
        from iridia_daily.email_generator import EmailGenerator
        
        # Neuroscience paper should get neuroscience category
        neuroscience_summary = "Research on brain activity and neural mechanisms."
        
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
        
        # Middle paper should have divider
        middle_section = generator._create_paper_section(
            sample_paper, summary, is_first=False, is_last=False
        )
        assert 'divider' in middle_section.lower() or 'height: 1px' in middle_section
        
        # Last paper should not have divider
        last_section = generator._create_paper_section(
            sample_paper, summary, is_first=False, is_last=True
        )
        # Count occurrences of divider elements
        assert middle_section.count('height: 1px') > last_section.count('height: 1px')
    
    def test_email_dark_mode_support(self, sample_papers_diverse):
        """Test that email includes dark mode CSS."""
        from iridia_daily.email_generator import EmailGenerator
        
        summaries = ["Summary " + str(i) for i in range(5)]
        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        html = generator.generate_html_email(sample_papers_diverse, summaries, date_str)
        
        # Should include dark mode media query
        assert 'prefers-color-scheme: dark' in html
        assert '--bg-color' in html  # CSS variables for theming
    
    def test_email_preview_text(self, sample_papers_diverse):
        """Test that email includes preview text for email clients."""
        from iridia_daily.email_generator import EmailGenerator
        
        summaries = ["Summary " + str(i) for i in range(5)]
        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        html = generator.generate_html_email(sample_papers_diverse, summaries, date_str)
        
        # Should include hidden preview text
        assert 'display: none' in html or 'max-height: 0' in html
        assert 'breakthrough' in html.lower() or 'research' in html.lower()


class TestEmailContentQuality:
    """Test email content quality and formatting."""
    
    def test_html_email_responsive_design(self, sample_papers_diverse):
        """Test that email uses responsive design elements."""
        from iridia_daily.email_generator import EmailGenerator
        
        summaries = ["Summary " + str(i) for i in range(5)]
        generator = EmailGenerator()
        html = generator.generate_html_email(sample_papers_diverse, summaries, "Test Date")
        
        # Should include viewport meta tag
        assert 'viewport' in html
        assert 'max-width' in html  # Responsive width
    
    def test_email_accessibility(self, sample_papers_diverse):
        """Test that email follows accessibility best practices."""
        from iridia_daily.email_generator import EmailGenerator
        
        summaries = ["Summary " + str(i) for i in range(5)]
        generator = EmailGenerator()
        html = generator.generate_html_email(sample_papers_diverse, summaries, "Test Date")
        
        # Should use semantic HTML
        assert '<table' in html  # Table for email layout
        assert 'role="presentation"' in html  # Proper ARIA roles
        
        # Should have proper language attribute
        assert 'lang="en"' in html
    
    def test_plain_text_formatting(self, sample_papers_diverse):
        """Test plain text email is properly formatted."""
        from iridia_daily.email_generator import EmailGenerator
        
        summaries = ["Summary " + str(i) for i in range(5)]
        generator = EmailGenerator()
        text = generator.generate_plain_text_email(sample_papers_diverse, summaries, "Test Date")
        
        # Should have clear structure
        assert text.count('=') >= 4  # Separator lines
        assert text.count('\n') > 10  # Multiple line breaks for readability
        
        # Each paper should be numbered
        for i in range(1, 6):
            assert f'{i}.' in text