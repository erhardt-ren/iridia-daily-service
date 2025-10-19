"""Shared pytest fixtures for Iridia Daily tests."""

import sys
import os
import pytest
from unittest.mock import Mock
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv('SENDER_EMAIL', 'research@iridia-daily.com')
    monkeypatch.setenv('CONTACT_LIST_NAME', 'iridia-daily-subscribers')
    monkeypatch.setenv('RECIPIENT_DISPLAY', 'Iridia Daily Readers <research@iridia-daily.com>')
    monkeypatch.setenv('AWS_BEDROCK_REGION', 'us-east-1')
    monkeypatch.setenv('AWS_REGION', 'us-east-1')
    monkeypatch.setenv('ALERT_TOPIC_ARN', 'arn:aws:sns:us-east-1:123456789012:iridia-daily-alerts')
    monkeypatch.setenv('HMAC_SECRET_ARN', 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret')


@pytest.fixture(autouse=True)
def mock_monitoring(request, monkeypatch):
    """Mock monitoring utilities to prevent actual AWS calls.
    
    Skips mocking for test_monitoring.py and tests that need real retry logic.
    """
    # Skip mocking if we're in the monitoring test file
    if 'test_monitoring' in request.node.nodeid:
        yield
        return
    
    # Skip mocking for specific tests that need real retry behavior
    if 'test_confirmation_with_retry_logic' in request.node.nodeid:
        # Mock CloudWatch to prevent actual AWS calls
        mock_cloudwatch = Mock()
        monkeypatch.setattr('iridia_daily.monitoring.cloudwatch', mock_cloudwatch)
        
        # Mock only metrics and sender verification, keep real retry
        def mock_put_metric(*args, **kwargs):
            pass
        
        def mock_verify_sender(*args, **kwargs):
            return True
        
        monkeypatch.setattr('iridia_daily.monitoring.put_metric', mock_put_metric)
        monkeypatch.setattr('iridia_daily.monitoring.verify_ses_sender', mock_verify_sender)
        # Don't mock retry_with_backoff - let it work normally
        
        yield
        return
    
    # For all other tests, mock the monitoring functions
    def mock_put_metric(*args, **kwargs):
        pass
    
    def mock_retry(func, *args, **kwargs):
        return func()
    
    def mock_verify_sender(*args, **kwargs):
        return True
    
    monkeypatch.setattr('iridia_daily.monitoring.put_metric', mock_put_metric)
    monkeypatch.setattr('iridia_daily.monitoring.retry_with_backoff', mock_retry)
    monkeypatch.setattr('iridia_daily.monitoring.verify_ses_sender', mock_verify_sender)
    
    yield


@pytest.fixture
def sample_paper():
    """Single sample research paper."""
    return {
        'pmid': '12345678',
        'title': 'Neural mechanisms underlying memory consolidation during sleep',
        'abstract': 'This study investigates how sleep stages contribute to memory formation through hippocampal-cortical dialogue.',
        'journal': 'Nature Neuroscience',
        'year': '2024',
        'url': 'https://pubmed.ncbi.nlm.nih.gov/12345678/'
    }


@pytest.fixture
def sample_papers_diverse():
    """Five diverse research papers covering different categories."""
    return [
        {
            'pmid': '12345678',
            'title': 'Neural mechanisms of memory consolidation',
            'abstract': 'Study on brain and memory during sleep states.',
            'journal': 'Nature Neuroscience',
            'year': '2024',
            'url': 'https://pubmed.ncbi.nlm.nih.gov/12345678/'
        },
        {
            'pmid': '87654321',
            'title': 'Exoplanet discovery in habitable zone',
            'abstract': 'Discovery of Earth-like planet orbiting distant star.',
            'journal': 'The Astrophysical Journal',
            'year': '2024',
            'url': 'https://pubmed.ncbi.nlm.nih.gov/87654321/'
        },
        {
            'pmid': '11223344',
            'title': 'CRISPR gene therapy for sickle cell disease',
            'abstract': 'Clinical trial results for gene editing treatment.',
            'journal': 'New England Journal of Medicine',
            'year': '2024',
            'url': 'https://pubmed.ncbi.nlm.nih.gov/11223344/'
        },
        {
            'pmid': '44556677',
            'title': 'Quantum entanglement breakthrough',
            'abstract': 'New advances in quantum computing and physics.',
            'journal': 'Physical Review Letters',
            'year': '2024',
            'url': 'https://pubmed.ncbi.nlm.nih.gov/44556677/'
        },
        {
            'pmid': '99887766',
            'title': 'Ocean ecosystem response to climate change',
            'abstract': 'Research on environmental impact on marine life.',
            'journal': 'Science',
            'year': '2024',
            'url': 'https://pubmed.ncbi.nlm.nih.gov/99887766/'
        }
    ]


@pytest.fixture
def comprehensive_pubmed_xml():
    """Realistic PubMed XML response with 5 valid papers."""
    return """<?xml version="1.0"?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345678</PMID>
      <Article>
        <ArticleTitle>Neural mechanisms underlying memory consolidation during sleep</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Sleep is crucial for memory consolidation and learning processes in the human brain.</AbstractText>
          <AbstractText Label="METHODS">We studied brain activity during different sleep stages using fMRI and EEG recordings in healthy adults.</AbstractText>
          <AbstractText Label="RESULTS">Slow-wave sleep enhances memory consolidation through coordinated hippocampal-cortical dialogue mechanisms.</AbstractText>
        </Abstract>
        <Journal>
          <Title>Nature Neuroscience</Title>
        </Journal>
      </Article>
      <PubDate>
        <Year>2024</Year>
        <Month>10</Month>
      </PubDate>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>87654321</PMID>
      <Article>
        <ArticleTitle>Discovery of Earth-like exoplanet in habitable zone</ArticleTitle>
        <Abstract>
          <AbstractText>We report the discovery of a rocky exoplanet orbiting within the habitable zone of a nearby star system. Spectroscopic analysis reveals the presence of water vapor in its atmosphere, making this one of the most promising candidates for extraterrestrial life discovered to date.</AbstractText>
        </Abstract>
        <Journal>
          <Title>The Astrophysical Journal</Title>
        </Journal>
      </Article>
      <PubDate>
        <Year>2024</Year>
        <Month>09</Month>
      </PubDate>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>11223344</PMID>
      <Article>
        <ArticleTitle>CRISPR-based gene therapy shows promise for sickle cell disease</ArticleTitle>
        <Abstract>
          <AbstractText>Clinical trial results demonstrate successful gene editing in patients with sickle cell disease using CRISPR-Cas9 technology. Modified stem cells produced healthy hemoglobin with minimal off-target effects, offering hope for a potential cure for this genetic disorder.</AbstractText>
        </Abstract>
        <Journal>
          <Title>New England Journal of Medicine</Title>
        </Journal>
      </Article>
      <PubDate>
        <Year>2024</Year>
        <Month>10</Month>
      </PubDate>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>44556677</PMID>
      <Article>
        <ArticleTitle>Quantum entanglement breakthrough enables new computing paradigm</ArticleTitle>
        <Abstract>
          <AbstractText>Researchers achieved stable quantum entanglement at room temperature, a breakthrough that could revolutionize quantum computing. The new method maintains coherence for unprecedented durations, opening new possibilities for practical quantum computing applications in cryptography and drug discovery.</AbstractText>
        </Abstract>
        <Journal>
          <Title>Physical Review Letters</Title>
        </Journal>
      </Article>
      <PubDate>
        <Year>2024</Year>
        <Month>10</Month>
      </PubDate>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>99887766</PMID>
      <Article>
        <ArticleTitle>Ocean ecosystem shows unexpected resilience to climate change</ArticleTitle>
        <Abstract>
          <AbstractText>Long-term study reveals marine ecosystems adapting to warming waters through novel symbiotic relationships between coral and algae. These findings suggest greater resilience than previously thought and provide insights for conservation strategies in the face of ongoing climate change.</AbstractText>
        </Abstract>
        <Journal>
          <Title>Science</Title>
        </Journal>
      </Article>
      <PubDate>
        <Year>2024</Year>
        <Month>10</Month>
      </PubDate>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""


@pytest.fixture
def mock_pubmed_search():
    """Factory for mocking PubMed search responses."""
    def create_mock(pmids):
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'esearchresult': {'idlist': pmids}
        }).encode()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        return mock_response
    return create_mock


@pytest.fixture
def mock_pubmed_fetch():
    """Factory for mocking PubMed fetch responses."""
    def create_mock(xml_content):
        mock_response = Mock()
        mock_response.read.return_value = xml_content.encode()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        return mock_response
    return create_mock


@pytest.fixture
def mock_ses_subscribers():
    """Factory for mocking SES subscriber list."""
    def create_mock(emails, all_opted_in=True):
        mock_paginator = Mock()
        contacts = []
        for email in emails:
            contacts.append({
                'EmailAddress': email,
                'TopicPreferences': [{
                    'TopicName': 'daily-research',
                    'SubscriptionStatus': 'OPT_IN' if all_opted_in else 'OPT_OUT'
                }],
                'CreatedTimestamp': '2024-01-01T00:00:00Z'
            })
        
        mock_paginator.paginate.return_value = [{'Contacts': contacts}]
        return mock_paginator
    return create_mock


@pytest.fixture
def assert_email_structure():
    """Validate email HTML structure."""
    def _assert(html):
        assert '<!DOCTYPE html>' in html
        assert 'IRIDIA DAILY' in html
        assert 'Research Intelligence Daily' in html
        assert '© 2025 Iridia Daily' in html or '@2025 Iridia Daily' in html
        assert '<html' in html and '</html>' in html
        assert '<body' in html and '</body>' in html
    return _assert


@pytest.fixture
def assert_cors_headers():
    """Validate CORS headers in API response."""
    def _assert(response):
        headers = response.get('headers', {})
        assert 'Access-Control-Allow-Origin' in headers
        assert headers['Access-Control-Allow-Origin'] == '*'
        assert 'Access-Control-Allow-Methods' in headers
        assert 'Content-Type' in headers
    return _assert


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "e2e: end-to-end tests")
    config.addinivalue_line("markers", "slow: slow running tests")
    config.addinivalue_line("markers", "integration: integration tests requiring AWS mocks")