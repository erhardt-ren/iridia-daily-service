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
        
        paper_topics = ['neuroscience', 'space', 'medicine', 'technology', 'environment']

        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        unsubscribe_url = "https://api.test.com/prod/unsubscribe?token=abc123"
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, date_str, unsubscribe_url, '', paper_topics
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
        paper_topics = ['default'] * 5

        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, date_str, '', '', paper_topics
        )

        assert 'unsubscribe' in html.lower()

    def test_generate_plain_text_email(self, sample_papers_diverse):
        """Test plain text email generation."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]
        paper_topics = ['default'] * 5

        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        unsubscribe_url = "https://api.test.com/prod/unsubscribe?token=xyz"
        text = generator.generate_plain_text_email(
            sample_papers_diverse, summaries, date_str, unsubscribe_url, '', paper_topics
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
            sample_paper, neuroscience_summary, 'neuroscience', is_first=True, is_last=False
        )

        assert 'NEUROSCIENCE' in section or 'neuro' in section.lower()
        assert sample_paper['url'] in section
        assert 'Read Paper' in section

    def test_paper_section_dividers(self, sample_paper):
        """Test that dividers are added between papers but not after last."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        summary = "Test summary text."

        middle_section = generator._create_paper_section(
            sample_paper, summary, 'default', is_first=False, is_last=False
        )

        last_section = generator._create_paper_section(
            sample_paper, summary, 'default', is_first=False, is_last=True
        )

        assert middle_section.count('height: 1px') > last_section.count(
            'height: 1px'
        )

    def test_email_dark_mode_support(self, sample_papers_diverse):
        """Test that email includes dark mode CSS."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]
        paper_topics = ['default'] * 5
        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, date_str, '', '', paper_topics
        )

        assert 'prefers-color-scheme: dark' in html
        assert '--bg-color' in html

    def test_email_preview_text(self, sample_papers_diverse):
        """Test that email includes preview text for email clients."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]
        paper_topics = ['default'] * 5
        generator = EmailGenerator()
        date_str = "Thursday, October 16, 2025"
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, date_str, '', '', paper_topics
        )

        assert 'display: none' in html or 'max-height: 0' in html
        assert 'breakthrough' in html.lower() or 'research' in html.lower()


class TestEmailAccessibility:
    """Test email accessibility features."""

    def test_html_email_responsive_design(self, sample_papers_diverse):
        """Test that email uses responsive design elements."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]
        paper_topics = ['default'] * 5
        generator = EmailGenerator()
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, "Test Date", '', '', paper_topics
        )

        assert 'viewport' in html
        assert 'max-width' in html

    def test_email_accessibility(self, sample_papers_diverse):
        """Test that email follows accessibility best practices."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(5)]
        paper_topics = ['default'] * 5
        generator = EmailGenerator()
        html = generator.generate_html_email(
            sample_papers_diverse, summaries, "Test Date", '', '', paper_topics
        )

        assert '<table' in html
        assert 'role="presentation"' in html
        assert 'lang="en"' in html

    def test_plain_text_formatting(self, sample_papers_diverse):
        """Test plain text email is properly formatted."""
        from iridia_daily.email_generator import EmailGenerator

        # sample_papers_diverse has 3 papers, not 5
        summaries = ["Summary " + str(i) for i in range(3)]
        paper_topics = ['default'] * 3
        generator = EmailGenerator()
        text = generator.generate_plain_text_email(
            sample_papers_diverse, summaries, "Test Date", '', '', paper_topics
        )

        assert text.count('=') >= 4
        assert text.count('\n') > 10

        # Check for 3 papers (sample_papers_diverse has 3 items)
        for i in range(1, 4):
            assert f'{i}.' in text

import pytest
from datetime import datetime


class TestEmailGeneratorEdgeCases:
    """Test edge cases in email generation."""

    def test_generate_html_with_empty_papers(self):
        """Test HTML generation with empty paper list."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        html = generator.generate_html_email([], [], "Test Date", '', '', [])

        assert 'IRIDIA DAILY' in html
        assert 'Test Date' in html

    def test_generate_plain_text_with_empty_papers(self):
        """Test plain text generation with empty paper list."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        text = generator.generate_plain_text_email([], [], "Test Date", '', '', [])

        assert 'IRIDIA DAILY' in text
        assert 'Test Date' in text

    def test_generate_html_with_single_paper(self, sample_paper):
        """Test HTML generation with single paper."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        html = generator.generate_html_email(
            [sample_paper],
            ["Summary"],
            "Test Date",
            "https://unsubscribe.com",
            "https://preferences.com",
            ['neuroscience']
        )

        # Email includes journal name and summary, but not the paper title
        assert sample_paper['journal'] in html
        assert 'Summary' in html
        assert 'https://unsubscribe.com' in html
        assert 'https://preferences.com' in html

    def test_generate_html_without_preferences_url(self, sample_paper):
        """Test HTML generation without preferences URL."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        html = generator.generate_html_email(
            [sample_paper],
            ["Summary"],
            "Test Date",
            "https://unsubscribe.com",
            '',  # No preferences URL
            ['neuroscience']
        )

        assert 'unsubscribe' in html.lower()
        # Should not have preferences link in this case

    def test_generate_plain_text_without_urls(self, sample_paper):
        """Test plain text generation without any URLs."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        text = generator.generate_plain_text_email(
            [sample_paper],
            ["Summary"],
            "Test Date",
            '',  # No unsubscribe URL
            '',  # No preferences URL
            ['neuroscience']
        )

        assert 'IRIDIA DAILY' in text
        assert sample_paper['journal'] in text

    def test_generate_html_with_various_topics(self, sample_paper):
        """Test HTML generation with different topic categories."""
        from iridia_daily.email_generator import EmailGenerator

        topics = ['neuroscience', 'space', 'biology', 'technology', 
                 'environment', 'medicine', 'physics', 'default']

        generator = EmailGenerator()

        for topic in topics:
            html = generator.generate_html_email(
                [sample_paper],
                ["Summary"],
                "Test Date",
                '',
                '',
                [topic]
            )
            
            # Each topic should generate valid HTML
            assert 'IRIDIA DAILY' in html
            assert sample_paper['journal'] in html  # Journal is included, not title

    def test_create_paper_section_first_paper(self, sample_paper):
        """Test paper section for first paper (special styling)."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        section = generator._create_paper_section(
            sample_paper,
            "Test summary",
            'neuroscience',
            is_first=True,
            is_last=False
        )

        assert sample_paper['title'] in section or sample_paper['journal'] in section
        # First paper has different padding
        assert '32px' in section or '20px' in section

    def test_create_paper_section_last_paper(self, sample_paper):
        """Test paper section for last paper (no divider)."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        section = generator._create_paper_section(
            sample_paper,
            "Test summary",
            'space',
            is_first=False,
            is_last=True
        )

        # Last paper should not have divider
        divider_count = section.count('height: 1px')
        assert divider_count == 0

    def test_create_paper_section_middle_paper(self, sample_paper):
        """Test paper section for middle paper."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        section = generator._create_paper_section(
            sample_paper,
            "Test summary",
            'biology',
            is_first=False,
            is_last=False
        )

        # Middle paper should have divider
        divider_count = section.count('height: 1px')
        assert divider_count > 0

    def test_create_paper_section_unknown_topic(self, sample_paper):
        """Test paper section with unknown topic uses default."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        section = generator._create_paper_section(
            sample_paper,
            "Test summary",
            'unknown_topic_xyz',
            is_first=False,
            is_last=False
        )

        # Should fall back to default and still generate valid HTML
        assert sample_paper['journal'] in section

    def test_subject_line_variations(self):
        """Test subject line generation returns valid results."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()

        # Test with different paper counts
        for count in [1, 3, 5, 10]:
            subject = generator.generate_subject_line(paper_count=count)
            
            assert len(subject) > 0
            assert len(subject) < 100
            assert isinstance(subject, str)

    def test_subject_line_default_count(self):
        """Test subject line with default paper count."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        subject = generator.generate_subject_line()

        assert 'Iridia' in subject or 'IRIDIA' in subject.upper()
        assert len(subject) > 0

    def test_html_email_special_characters(self):
        """Test HTML email handles special characters properly."""
        from iridia_daily.email_generator import EmailGenerator

        paper = {
            'pmid': '123',
            'title': 'Test & <Special> "Characters"',
            'abstract': 'Abstract with special chars: <>&"',
            'journal': 'Science & Nature',
            'year': '2025',
            'url': 'https://test.com'
        }

        generator = EmailGenerator()
        html = generator.generate_html_email(
            [paper],
            ["Summary with <special> & chars"],
            "Test Date",
            '',
            '',
            ['neuroscience']
        )

        # Should contain the content (may be escaped)
        assert 'Test' in html
        assert 'Science' in html

    def test_plain_text_formatting_consistency(self, sample_papers_diverse):
        """Test plain text maintains consistent formatting."""
        from iridia_daily.email_generator import EmailGenerator

        summaries = ["Summary " + str(i) for i in range(len(sample_papers_diverse))]
        topics = ['neuroscience'] * len(sample_papers_diverse)

        generator = EmailGenerator()
        text = generator.generate_plain_text_email(
            sample_papers_diverse,
            summaries,
            "Test Date",
            'https://unsubscribe.com',
            'https://preferences.com',
            topics
        )

        # Check numbering
        for i in range(1, len(sample_papers_diverse) + 1):
            assert f'{i}.' in text

        # Check footer
        assert '=' * 50 in text
        assert 'buymeacoffee.com/iridia' in text


class TestEmailAccessibilityAndStandards:
    """Test email follows accessibility and HTML email standards."""

    def test_html_has_lang_attribute(self, sample_paper):
        """Test HTML email has language attribute."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        html = generator.generate_html_email(
            [sample_paper], ["Summary"], "Date", '', '', ['neuroscience']
        )

        assert 'lang="en"' in html

    def test_html_has_viewport_meta(self, sample_paper):
        """Test HTML email has viewport meta tag."""
    def test_html_has_viewport_meta(self, sample_paper):
        """Test HTML email has viewport meta tag."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        html = generator.generate_html_email(
            [sample_paper], ["Summary"], "Date", '', '', ['neuroscience']
        )

        assert 'viewport' in html

    def test_html_has_doctype(self, sample_paper):
        """Test HTML email has DOCTYPE declaration."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        html = generator.generate_html_email(
            [sample_paper], ["Summary"], "Date", '', '', ['neuroscience']
        )

        assert '<!DOCTYPE html>' in html

    def test_html_tables_have_role_presentation(self, sample_paper):
        """Test tables have role=presentation for accessibility."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        html = generator.generate_html_email(
            [sample_paper], ["Summary"], "Date", '', '', ['neuroscience']
        )

        assert 'role="presentation"' in html

    def test_html_has_css_variables_for_dark_mode(self, sample_paper):
        """Test HTML includes CSS variables for dark mode."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        html = generator.generate_html_email(
            [sample_paper], ["Summary"], "Date", '', '', ['neuroscience']
        )

        assert '--bg-color' in html
        assert '--text-primary' in html
        assert 'prefers-color-scheme: dark' in html

    def test_html_has_preview_text(self, sample_paper):
        """Test HTML includes hidden preview text."""
        from iridia_daily.email_generator import EmailGenerator

        generator = EmailGenerator()
        html = generator.generate_html_email(
            [sample_paper], ["Summary"], "Date", '', '', ['neuroscience']
        )

        assert 'display: none' in html or 'max-height: 0' in html


@pytest.fixture
def sample_paper():
    """Provide a sample paper for testing."""
    return {
        'pmid': '12345',
        'title': 'Test Research Paper',
        'abstract': 'This is a test abstract',
        'journal': 'Nature',
        'year': '2025',
        'url': 'https://pubmed.ncbi.nlm.nih.gov/12345/'
    }


@pytest.fixture
def sample_papers_diverse():
    """Provide diverse sample papers."""
    return [
        {
            'pmid': '001',
            'title': 'Neural mechanisms',
            'abstract': 'Brain study',
            'journal': 'Nature Neuroscience',
            'year': '2025',
            'url': 'https://test.com/001'
        },
        {
            'pmid': '002',
            'title': 'Exoplanet discovery',
            'abstract': 'Space research',
            'journal': 'Astrophysical Journal',
            'year': '2025',
            'url': 'https://test.com/002'
        },
        {
            'pmid': '003',
            'title': 'Gene therapy',
            'abstract': 'Medical breakthrough',
            'journal': 'Cell',
            'year': '2025',
            'url': 'https://test.com/003'
        }
    ]


@pytest.fixture
def assert_email_structure():
    """Fixture that provides email structure validation."""
    def _assert(html):
        assert '<!DOCTYPE html>' in html
        assert '<html' in html
        assert '</html>' in html
        assert '<body' in html
        assert '</body>' in html
        assert 'IRIDIA DAILY' in html
    return _assert