"""End-to-end tests for Lambda function."""

import pytest
from unittest.mock import Mock, patch
import json
import os


@pytest.mark.e2e
class TestLambdaHandler:
    """Test full Lambda execution flow."""
    
    @patch('boto3.client')
    @patch('urllib.request.urlopen')
    def test_lambda_handler_complete_success(self, mock_urlopen, mock_boto3, 
                                            mock_pubmed_search, mock_pubmed_fetch,
                                            comprehensive_pubmed_xml):
        """Test successful end-to-end Lambda execution."""
        from iridia_daily.lambda_function import lambda_handler
        
        # Mock PubMed
        pmids = ['12345678', '87654321', '11223344', '44556677', '99887766']
        mock_urlopen.side_effect = [
            mock_pubmed_search(pmids),
            mock_pubmed_fetch(comprehensive_pubmed_xml)
        ]
        
        # Mock Bedrock
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.return_value = {
            'body': Mock(read=lambda: json.dumps({
                'content': [{'text': '''Paper 1:
Summary 1

Paper 2:
Summary 2

Paper 3:
Summary 3

Paper 4:
Summary 4

Paper 5:
Summary 5'''}]
            }).encode())
        }
        
        # Mock SES
        mock_ses = Mock()
        mock_ses.send_email.return_value = {'MessageId': 'test-msg-123'}
        
        # Configure boto3
        def boto3_factory(service, **kwargs):
            return mock_bedrock if service == 'bedrock-runtime' else mock_ses
        mock_boto3.side_effect = boto3_factory
        
        # Execute
        result = lambda_handler({}, {})
        
        # Verify
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['message'] == 'Iridia sent successfully'
        assert body['papers_count'] == 5
        assert 'messageId' in body
        
        # Verify SES called with correct params
        mock_ses.send_email.assert_called_once()
        call_kwargs = mock_ses.send_email.call_args[1]
        assert call_kwargs['Source'] == 'Iridia Daily <research@iridia-daily.com>'
        assert 'test@example.com' in call_kwargs['Destination']['ToAddresses']
    
    @patch('boto3.client')
    @patch('urllib.request.urlopen')
    def test_lambda_handler_no_papers_found(self, mock_urlopen, mock_boto3, 
                                           mock_pubmed_search):
        """Test Lambda when PubMed returns no papers."""
        from iridia_daily.lambda_function import lambda_handler
        
        mock_urlopen.return_value = mock_pubmed_search([])
        mock_boto3.return_value = Mock()
        
        result = lambda_handler({}, {})
        
        assert result['statusCode'] == 500
        assert 'No papers found' in result['body']
    
    @patch('boto3.client')
    @patch('urllib.request.urlopen')
    def test_lambda_handler_ses_error(self, mock_urlopen, mock_boto3,
                                     mock_pubmed_search, mock_pubmed_fetch,
                                     comprehensive_pubmed_xml):
        """Test Lambda handling of SES send error."""
        from iridia_daily.lambda_function import lambda_handler
        
        # Mock PubMed success
        pmids = ['12345678']
        mock_urlopen.side_effect = [
            mock_pubmed_search(pmids),
            mock_pubmed_fetch(comprehensive_pubmed_xml)
        ]
        
        # Mock Bedrock success
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.return_value = {
            'body': Mock(read=lambda: json.dumps({
                'content': [{'text': 'Paper 1:\nSummary'}]
            }).encode())
        }
        
        # Mock SES error
        mock_ses = Mock()
        mock_ses.send_email.side_effect = Exception("SES Send Failed")
        
        def boto3_factory(service, **kwargs):
            return mock_bedrock if service == 'bedrock-runtime' else mock_ses
        mock_boto3.side_effect = boto3_factory
        
        result = lambda_handler({}, {})
        
        assert result['statusCode'] == 500
        assert 'Error sending Iridia' in result['body']
    
    def test_lambda_handler_missing_env_vars(self, monkeypatch):
        """Test Lambda when environment variables are missing."""
        from iridia_daily.lambda_function import lambda_handler
        
        # Remove required env vars
        monkeypatch.delenv('SENDER_EMAIL', raising=False)
        monkeypatch.delenv('RECIPIENT_EMAIL', raising=False)
        
        # Mock PubMed to return papers so we get past that check
        with patch('urllib.request.urlopen') as mock_urlopen:
            # Mock search response
            search_response = Mock()
            search_response.read.return_value = json.dumps({
                'esearchresult': {'idlist': ['12345678']}
            }).encode()
            search_response.__enter__ = Mock(return_value=search_response)
            search_response.__exit__ = Mock(return_value=False)
            
            # Mock fetch response with valid paper
            fetch_response = Mock()
            fetch_response.read.return_value = b'''<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345678</PMID>
      <Article>
        <ArticleTitle>Test Paper</ArticleTitle>
        <Abstract>
          <AbstractText>This is a test abstract with enough text to meet the minimum length requirement for paper selection in the test suite.</AbstractText>
        </Abstract>
        <Journal><Title>Test Journal</Title></Journal>
      </Article>
      <PubDate><Year>2024</Year></PubDate>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>'''
            fetch_response.__enter__ = Mock(return_value=fetch_response)
            fetch_response.__exit__ = Mock(return_value=False)
            
            mock_urlopen.side_effect = [search_response, fetch_response]
            
            # Mock Bedrock
            with patch('boto3.client') as mock_boto3:
                mock_bedrock = Mock()
                mock_bedrock.invoke_model.return_value = {
                    'body': Mock(read=lambda: json.dumps({
                        'content': [{'text': 'Paper 1:\nSummary'}]
                    }).encode())
                }
                mock_boto3.return_value = mock_bedrock
                
                result = lambda_handler({}, {})
                
                assert result['statusCode'] == 500
                assert 'Configuration error' in result['body']