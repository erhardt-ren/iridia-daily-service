"""PubMed API integration for fetching research papers."""

import json
import random
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from ..config import PUBMED_SEARCH_TERMS, PUBMED_BASE_URL

class PubMedClient:
    def __init__(self):
        pass
    
    def get_recent_papers(self, num_papers=5, days_back=7):
        """Fetch recent papers from PubMed API with batched requests."""
        time.sleep(0.34)  # Rate limiting
        try:
            pmids = self._search_papers(days_back)
            if not pmids:
                print("No papers found in date range")
                return []
            
            return self._fetch_paper_details(pmids, num_papers)
            
        except Exception as e:
            print(f"Error fetching papers from PubMed: {e}")
            return []
    
    def _search_papers(self, days_back):
        """Search for paper IDs in date range."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        date_range = f"{start_date.strftime('%Y/%m/%d')}:{end_date.strftime('%Y/%m/%d')}"
        
        query = urllib.parse.quote(f"{PUBMED_SEARCH_TERMS} AND {date_range}[PDAT]")
        search_url = f"{PUBMED_BASE_URL}/esearch.fcgi?db=pubmed&term={query}&retmax=100&retmode=json&sort=relevance"
        
        print(f"Searching PubMed for papers from {start_date.date()} to {end_date.date()}")
        
        with urllib.request.urlopen(search_url, timeout=10) as response:
            search_results = json.loads(response.read())
            return search_results.get('esearchresult', {}).get('idlist', [])
    
    def _fetch_paper_details(self, all_pmids, num_papers):
        """Fetch detailed paper information."""
        print(f"Found {len(all_pmids)} papers, selecting {num_papers}")
        
        selected_pmids = random.sample(all_pmids, min(num_papers * 3, len(all_pmids)))
        pmid_string = ",".join(selected_pmids)
        detail_url = f"{PUBMED_BASE_URL}/efetch.fcgi?db=pubmed&id={pmid_string}&retmode=xml"
        
        print(f"Fetching {len(selected_pmids)} papers in a single batch request...")
        
        with urllib.request.urlopen(detail_url, timeout=30) as response:
            xml_data = response.read().decode('utf-8')
        
        return self._parse_papers_xml(xml_data, num_papers)
    
    def _parse_papers_xml(self, xml_data, num_papers):
        """Parse XML response and extract paper information."""
        root = ET.fromstring(xml_data)
        papers = []
        
        for article in root.findall('.//PubmedArticle'):
            if len(papers) >= num_papers:
                break
                
            try:
                paper = self._extract_paper_info(article)
                if paper and len(paper.get('abstract', '')) >= 100:
                    papers.append(paper)
                    print(f"✓ Selected paper {len(papers)}/{num_papers}: {paper['title'][:50]}...")
            except Exception as e:
                print(f"Error parsing paper: {e}")
                continue
        
        print(f"Successfully retrieved {len(papers)} papers!")
        return papers
    
    def _extract_paper_info(self, article):
        """Extract paper information from XML article element."""
        pmid_elem = article.find('.//PMID')
        pmid = pmid_elem.text if pmid_elem is not None else "Unknown"
        
        title_elem = article.find('.//ArticleTitle')
        title = title_elem.text if title_elem is not None else "Unknown Title"
        
        # Extract abstract
        abstract_parts = []
        for abstract_elem in article.findall('.//AbstractText'):
            text = abstract_elem.text or ""
            label = abstract_elem.get('Label', '')
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        
        abstract = " ".join(abstract_parts) if abstract_parts else ""
        
        journal_elem = article.find('.//Journal/Title')
        journal = journal_elem.text if journal_elem is not None else "Unknown Journal"
        
        pub_date = article.find('.//PubDate')
        year = pub_date.find('Year').text if pub_date is not None and pub_date.find('Year') is not None else "2025"
        
        return {
            'pmid': pmid,
            'title': title,
            'abstract': abstract[:1500],
            'journal': journal,
            'year': year,
            'url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        }