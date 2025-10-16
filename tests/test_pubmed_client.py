"""Tests for PubMed API integration."""

import pytest
from unittest.mock import Mock, patch
import json


class TestPubMedClient:
    """Test PubMed paper fetching functionality."""
    
    @patch('urllib.request.urlopen')
    def test_get_recent_papers_success(self, mock_urlopen, mock_pubmed_search, 
                                       mock_pubmed_fetch, comprehensive_pubmed_xml):
        """Test successfully fetching papers from PubMed."""
        from iridia_daily.clients.pubmed_client import PubMedClient
        
        # Mock search returning 5 paper IDs
        pmids = ['12345678', '87654321', '11223344', '44556677', '99887766']
        mock_urlopen.side_effect = [
            mock_pubmed_search(pmids),
            mock_pubmed_fetch(comprehensive_pubmed_xml)
        ]
        
        client = PubMedClient()
        papers = client.get_recent_papers(num_papers=5)
        
        assert len(papers) == 5
        assert all('title' in p for p in papers)
        assert all('abstract' in p for p in papers)
        assert all('url' in p for p in papers)
        assert all('pubmed.ncbi.nlm.nih.gov' in p['url'] for p in papers)
    
    @patch('urllib.request.urlopen')
    def test_get_recent_papers_empty_results(self, mock_urlopen, mock_pubmed_search):
        """Test handling when no papers are found."""
        from iridia_daily.clients.pubmed_client import PubMedClient
        
        mock_urlopen.return_value = mock_pubmed_search([])
        
        client = PubMedClient()
        papers = client.get_recent_papers()
        
        assert papers == []
    
    @patch('urllib.request.urlopen')
    def test_get_recent_papers_api_timeout(self, mock_urlopen):
        """Test handling of PubMed API timeout."""
        from iridia_daily.clients.pubmed_client import PubMedClient
        import urllib.error
        
        mock_urlopen.side_effect = urllib.error.URLError('timeout')
        
        client = PubMedClient()
        papers = client.get_recent_papers()
        
        assert papers == []
    
    def test_parse_papers_xml_with_structured_abstract(self, comprehensive_pubmed_xml):
        """Test parsing XML with structured abstracts (Background, Methods, etc.)."""
        from iridia_daily.clients.pubmed_client import PubMedClient
        
        client = PubMedClient()
        papers = client._parse_papers_xml(comprehensive_pubmed_xml, num_papers=5)
        
        assert len(papers) == 5
        # Check structured abstract was parsed
        assert 'BACKGROUND' in papers[0]['abstract'] or 'Sleep is crucial' in papers[0]['abstract']
        assert papers[0]['pmid'] == '12345678'
        assert papers[0]['year'] == '2024'