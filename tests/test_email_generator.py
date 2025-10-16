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
        html = generator.generate_html_email(sample_papers_diverse, summaries, date_str)
        
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
    
    def test_generate_plain_text_email(self, sample_papers_diverse):
        """Test plain text email generation."""
        from iridia_daily.email_generator import EmailGenerator
        
        summaries = ["Summary " + str(i) for i in range(5)]
        
        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        text = generator.generate_plain_text_email(sample_papers_diverse, summaries, date_str)
        
        assert 'IRIDIA DAILY' in text
        assert date_str in text
        assert summaries[0] in text
        assert sample_papers_diverse[0]['journal'] in text
        assert sample_papers_diverse[0]['url'] in text
        # Should be plain text, no HTML tags
        assert '<' not in text or '=' * 50 in text  # Allow separators
    
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
        
        # Neuroscience paper should get neuroscience category
        neuroscience_summary = "Research on brain activity and neural mechanisms."
        
        generator = EmailGenerator()
        section = generator._create_paper_section_html(
            sample_paper, neuroscience_summary, is_first=True, is_last=False
        )
        
        assert 'NEUROSCIENCE' in section or '🧠' in section
        assert sample_paper['url'] in section
        assert 'Read Paper' in section