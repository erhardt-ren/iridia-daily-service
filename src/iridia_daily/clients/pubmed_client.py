"""PubMed API integration for fetching research papers."""

import json
import random
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict
from ..config import PUBMED_SEARCH_TERMS, PUBMED_BASE_URL, CATEGORY_MAPPING


class PubMedClient:
    """Client for interacting with PubMed E-utilities API."""

    def __init__(self):
        """Initialize PubMed client."""
        pass
    
    def get_papers_for_multiple_topics(self, topics, papers_per_topic=5, days_back=7):
        """Fetch papers for multiple topics in ONE PubMed call with smart categorization.
        
        Args:
            topics: Set/list of topic strings to fetch papers for.
            papers_per_topic: Target number of papers per topic.
            days_back: Number of days to look back for papers.
            
        Returns:
            Tuple of (papers_by_topic, pmid_to_topic):
            - papers_by_topic: Dictionary mapping topic to list of papers
            - pmid_to_topic: Dictionary mapping PMID to its assigned topic
            Example: (
                {'neuroscience': [paper1, paper2], 'space': [paper3, paper4]},
                {'12345': 'neuroscience', '67890': 'neuroscience', '11111': 'space', ...}
            )
        """
        time.sleep(0.34)  # Rate limiting
        
        if not topics:
            return {}, {}
        
        try:
            # Step 1: Build combined query for ALL topics at once
            date_range = self._get_date_range(days_back)
            
            topic_queries = []
            topic_to_keywords = {}
            
            for topic in topics:
                if topic not in CATEGORY_MAPPING:
                    print(f"Unknown topic: {topic}")
                    continue
                
                _, _, keywords = CATEGORY_MAPPING[topic]
                topic_to_keywords[topic] = keywords
                
                # Build keyword query for this topic
                keyword_terms = ' OR '.join([f'"{kw}"[Title/Abstract]' for kw in keywords])
                topic_queries.append(f"({keyword_terms})")
            
            if not topic_queries:
                return {}, {}
            
            # Combine all topics with OR
            combined_query = ' OR '.join(topic_queries)
            full_query = f"({combined_query}) AND {date_range}[PDAT]"
            
            # Step 2: ONE search for papers matching ANY topic
            query_encoded = urllib.parse.quote(full_query)
            max_results = len(topics) * papers_per_topic * 4  # Fetch extra for better distribution
            search_url = f"{PUBMED_BASE_URL}/esearch.fcgi?db=pubmed&term={query_encoded}&retmax={max_results}&retmode=json&sort=pub_date"
            
            print(f"Searching PubMed for {len(topics)} topics in ONE call...")
            
            with urllib.request.urlopen(search_url, timeout=10) as response:
                search_results = json.loads(response.read())
                pmids = search_results.get('esearchresult', {}).get('idlist', [])
            
            if not pmids:
                print("No papers found for any topics")
                return {}, {}
            
            print(f"Found {len(pmids)} papers across all topics")
            
            # Step 3: Fetch paper details in ONE batch
            papers = self._fetch_paper_details(pmids, len(pmids))
            
            if not papers:
                return {}, {}
            
            # Step 4: Intelligently categorize papers by topic AND build pmid_to_topic map
            papers_by_topic, pmid_to_topic = self._categorize_papers_smart(
                papers, topic_to_keywords, papers_per_topic
            )
            
            return papers_by_topic, pmid_to_topic
            
        except Exception as e:
            print(f"Error fetching papers for multiple topics: {e}")
            return {}, {}
    
    def _categorize_papers_smart(self, papers, topic_to_keywords, papers_per_topic):
        """Intelligently categorize papers into topics with improved scoring.
        
        Uses weighted scoring that prioritizes:
        - Title matches over abstract matches (4x weight)
        - Multi-word exact phrase matches (bonus points)
        - Primary assignment (each paper goes to best topic only)
        - Prevents ambiguous categorization (e.g., "neural networks" → technology not neuroscience)
        
        Args:
            papers: List of paper dictionaries.
            topic_to_keywords: Dictionary mapping topic to its keywords.
            papers_per_topic: Target number of papers per topic.
            
        Returns:
            Tuple of (papers_by_topic, pmid_to_topic):
            - papers_by_topic: Dictionary mapping topic to list of papers
            - pmid_to_topic: Dictionary mapping PMID to its assigned topic
        """
        papers_by_topic = defaultdict(list)
        pmid_to_topic = {}  # Track which topic each paper was assigned to
        
        # Score each paper for each topic
        for paper in papers:
            # Handle None values defensively
            title = (paper.get('title') or '').lower()
            abstract = (paper.get('abstract') or '').lower()
            
            # Skip papers with no title or abstract
            if not title and not abstract:
                continue
            
            best_topic = None
            best_score = 0
            
            for topic, keywords in topic_to_keywords.items():
                score = 0
                
                for keyword in keywords:
                    kw_lower = keyword.lower()
                    
                    # Calculate separate scores for title and abstract
                    title_score = 0
                    abstract_score = 0
                    
                    # Title matching (4x weight - most important signal)
                    if kw_lower in title:
                        # Exact word boundary match in title (8x total)
                        if self._is_exact_word_match(kw_lower, title):
                            title_score += 8
                        else:
                            title_score += 4
                    
                    # Abstract matching (1x weight)
                    if kw_lower in abstract:
                        # Exact word boundary match in abstract (2x total)
                        if self._is_exact_word_match(kw_lower, abstract):
                            abstract_score += 2
                        else:
                            abstract_score += 1
                    
                    score += title_score + abstract_score
                
                # Track best matching topic
                if score > best_score:
                    best_score = score
                    best_topic = topic
            
            # Only assign if score is above threshold (avoid random assignments)
            # Lower threshold to 1 to be more inclusive for sparse topics
            if best_topic and best_score >= 1:
                papers_by_topic[best_topic].append({
                    'paper': paper,
                    'score': best_score
                })
                # Track the topic assignment for this paper's PMID
                pmid_to_topic[paper['pmid']] = best_topic
            elif best_score > 0:
                # Log papers that scored but didn't meet threshold
                print(f"  Paper scored {best_score} for '{best_topic}' but below threshold: {paper['title'][:60]}...")
        
        # Sort by score and limit to papers_per_topic
        result = {}
        for topic in topic_to_keywords.keys():
            if topic in papers_by_topic:
                # Sort by score (highest first)
                sorted_papers = sorted(
                    papers_by_topic[topic], 
                    key=lambda x: x['score'], 
                    reverse=True
                )
                
                # Take top N papers, extract just the paper dict
                top_papers = sorted_papers[:papers_per_topic]
                result[topic] = [item['paper'] for item in top_papers]
                
                scores = [item['score'] for item in top_papers]
                titles_preview = [item['paper']['title'][:40] + '...' for item in top_papers[:2]]
                
                print(f"✓ Topic '{topic}': {len(result[topic])} papers")
                print(f"  Scores: {scores}")
                print(f"  Sample titles: {titles_preview}")
            else:
                print(f"✗ Topic '{topic}': No papers found (no papers scored >= 2)")
        
        return result, pmid_to_topic
    
    def _is_exact_word_match(self, keyword, text):
        """Check if keyword appears as a complete word/phrase in text.
        
        Args:
            keyword: Keyword string to search for.
            text: Text to search in.
            
        Returns:
            bool: True if keyword is a complete word/phrase match.
        """
        # Add spaces around text for boundary checking
        padded_text = f" {text} "
        padded_keyword = f" {keyword} "
        
        # Check if keyword appears as a complete word/phrase
        return padded_keyword in padded_text
    
    def _get_date_range(self, days_back):
        """Generate PubMed date range string.
        
        Args:
            days_back: Number of days to look back.
            
        Returns:
            Date range string in PubMed format.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        return f"{start_date.strftime('%Y/%m/%d')}:{end_date.strftime('%Y/%m/%d')}"
    
    def get_recent_papers(self, num_papers=5, days_back=7):
        """Fetch recent papers from PubMed API with batched requests.
        
        Args:
            num_papers: Number of papers to return.
            days_back: Number of days to look back for papers.
            
        Returns:
            List of paper dictionaries with metadata.
        """
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
    
    def get_papers_by_topic(self, keywords, max_results=5, days_back=7):
        """Fetch papers for a specific topic using keywords.
        
        Args:
            keywords: List of keyword strings for this topic.
            max_results: Maximum number of papers to fetch for this topic.
            days_back: Number of days to look back for papers.
            
        Returns:
            List of paper dictionaries matching the topic.
        """
        time.sleep(0.34)  # Rate limiting
        try:
            pmids = self._search_papers_by_keywords(keywords, days_back, max_results)
            if not pmids:
                print(f"No papers found for keywords: {keywords}")
                return []
            
            return self._fetch_paper_details(pmids, max_results)
            
        except Exception as e:
            print(f"Error fetching papers by topic: {e}")
            return []
    
    def _search_papers(self, days_back):
        """Search for paper IDs in date range.
        
        Args:
            days_back: Number of days to look back.
            
        Returns:
            List of PubMed IDs.
        """
        date_range = self._get_date_range(days_back)
        query = urllib.parse.quote(f"{PUBMED_SEARCH_TERMS} AND {date_range}[PDAT]")
        search_url = f"{PUBMED_BASE_URL}/esearch.fcgi?db=pubmed&term={query}&retmax=100&retmode=json&sort=relevance"
        
        print(f"Searching PubMed for papers...")
        
        with urllib.request.urlopen(search_url, timeout=10) as response:
            search_results = json.loads(response.read())
            return search_results.get('esearchresult', {}).get('idlist', [])
    
    def _search_papers_by_keywords(self, keywords, days_back, max_results):
        """Search for paper IDs matching specific keywords.
        
        Args:
            keywords: List of keyword strings to search for.
            days_back: Number of days to look back.
            max_results: Maximum number of results to return.
            
        Returns:
            List of PubMed IDs.
        """
        date_range = self._get_date_range(days_back)
        
        # Build query: OR between keywords for broader matching
        keyword_terms = ' OR '.join([f'"{kw}"[Title/Abstract]' for kw in keywords])
        full_query = f"({keyword_terms}) AND {date_range}[PDAT]"
        
        query_encoded = urllib.parse.quote(full_query)
        search_url = f"{PUBMED_BASE_URL}/esearch.fcgi?db=pubmed&term={query_encoded}&retmax={max_results * 2}&retmode=json&sort=pub_date"
        
        print(f"Searching PubMed for topic with keywords: {keywords}")
        
        with urllib.request.urlopen(search_url, timeout=10) as response:
            search_results = json.loads(response.read())
            pmids = search_results.get('esearchresult', {}).get('idlist', [])
            print(f"Found {len(pmids)} papers for keywords: {keywords}")
            return pmids
    
    def _fetch_paper_details(self, all_pmids, num_papers):
        """Fetch detailed paper information.
        
        Args:
            all_pmids: List of all PubMed IDs to fetch.
            num_papers: Target number of papers to return.
            
        Returns:
            List of paper dictionaries with full metadata.
        """
        print(f"Found {len(all_pmids)} papers, fetching up to {num_papers}")
        
        selected_pmids = random.sample(all_pmids, min(num_papers, len(all_pmids)))
        pmid_string = ",".join(selected_pmids)
        detail_url = f"{PUBMED_BASE_URL}/efetch.fcgi?db=pubmed&id={pmid_string}&retmode=xml"
        
        print(f"Fetching {len(selected_pmids)} papers in a single batch request...")
        
        with urllib.request.urlopen(detail_url, timeout=30) as response:
            xml_data = response.read().decode('utf-8')
        
        return self._parse_papers_xml(xml_data, num_papers)
    
    def _parse_papers_xml(self, xml_data, num_papers):
        """Parse XML response and extract paper information.
        
        Args:
            xml_data: XML string from PubMed API.
            num_papers: Maximum number of papers to parse.
            
        Returns:
            List of paper dictionaries.
        """
        root = ET.fromstring(xml_data)
        papers = []
        
        for article in root.findall('.//PubmedArticle'):
            try:
                paper = self._extract_paper_info(article)
                if paper and len(paper.get('abstract', '')) >= 100:
                    papers.append(paper)
                    print(f"✓ Parsed paper {len(papers)}: {paper['title'][:50]}...")
            except Exception as e:
                print(f"Error parsing paper: {e}")
                continue
        
        print(f"Successfully retrieved {len(papers)} papers!")
        return papers
    
    def _extract_paper_info(self, article):
        """Extract paper information from XML article element.
        
        Args:
            article: XML element representing a PubMed article.
            
        Returns:
            Dictionary containing paper metadata, or None if critical data is missing.
        """
        pmid_elem = article.find('.//PMID')
        pmid = pmid_elem.text if pmid_elem is not None and pmid_elem.text else "Unknown"
        
        title_elem = article.find('.//ArticleTitle')
        title = title_elem.text if title_elem is not None and title_elem.text else ""
        
        # Extract abstract
        abstract_parts = []
        for abstract_elem in article.findall('.//AbstractText'):
            text = abstract_elem.text or ""
            label = abstract_elem.get('Label', '')
            if label and text:
                abstract_parts.append(f"{label}: {text}")
            elif text:
                abstract_parts.append(text)
        
        abstract = " ".join(abstract_parts).strip() if abstract_parts else ""
        
        # Skip papers with no title AND no abstract
        if not title and not abstract:
            return None
        
        journal_elem = article.find('.//Journal/Title')
        journal = journal_elem.text if journal_elem is not None and journal_elem.text else "Unknown Journal"
        
        pub_date = article.find('.//PubDate')
        year = pub_date.find('Year').text if pub_date is not None and pub_date.find('Year') is not None else "2025"
        
        return {
            'pmid': pmid,
            'title': title or "Untitled",
            'abstract': abstract[:1500] if abstract else "",
            'journal': journal,
            'year': year,
            'url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        }