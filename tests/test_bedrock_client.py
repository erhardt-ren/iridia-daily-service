"""Tests for AWS Bedrock/Claude integration."""

import pytest
from unittest.mock import Mock, patch
import json


class TestBedrockClient:
    """Test Bedrock AI summary generation."""
    
    @patch('boto3.client')
    def test_generate_summaries_success(self, mock_boto3, sample_papers_diverse):
        """Test successful summary generation from Claude."""
        from iridia_daily.clients.bedrock_client import BedrockClient
        
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.return_value = {
            'body': Mock(read=lambda: json.dumps({
                'content': [{
                    'text': '''Paper 1:
Scientists found that your brain replays memories during sleep like a biological TiVo.

Paper 2:
Astronomers discovered an Earth-like planet hanging out in the Goldilocks zone.

Paper 3:
Gene therapy successfully fixed the genetic typo causing sickle cell disease.

Paper 4:
Quantum entanglement breakthrough enables room-temperature quantum computing.

Paper 5:
Ocean ecosystems show surprising resilience through novel symbiotic relationships.'''
                }]
            }).encode())
        }
        mock_boto3.return_value = mock_bedrock
        
        client = BedrockClient()
        summaries = client.generate_summaries(sample_papers_diverse)
        
        assert len(summaries) == 5
        assert all(len(s) > 20 for s in summaries)  # Meaningful summaries
        assert 'brain' in summaries[0].lower() or 'memory' in summaries[0].lower()
        mock_bedrock.invoke_model.assert_called_once()
    
    @patch('boto3.client')
    def test_generate_summaries_api_error(self, mock_boto3, sample_papers_diverse):
        """Test fallback when Bedrock API fails."""
        from iridia_daily.clients.bedrock_client import BedrockClient
        
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.side_effect = Exception("Bedrock API Error")
        mock_boto3.return_value = mock_bedrock
        
        client = BedrockClient()
        summaries = client.generate_summaries(sample_papers_diverse)
        
        # Should return fallback summaries
        assert len(summaries) == len(sample_papers_diverse)
        assert all("Cool science fact" in s for s in summaries)
    
    def test_build_prompt_includes_paper_details(self, sample_papers_diverse):
        """Test that prompt includes all paper details."""
        from iridia_daily.clients.bedrock_client import BedrockClient
        
        client = BedrockClient()
        prompt = client._build_prompt(sample_papers_diverse)
        
        assert 'Iridia Daily' in prompt
        assert sample_papers_diverse[0]['title'] in prompt
        assert sample_papers_diverse[0]['journal'] in prompt
        assert 'witty' in prompt.lower()
        assert str(len(sample_papers_diverse)) in prompt
    
    def test_parse_summaries_from_claude_response(self):
        """Test parsing Claude's response into individual summaries."""
        from iridia_daily.clients.bedrock_client import BedrockClient
        
        response_text = """Paper 1:
This is the first summary with interesting content.

Paper 2:
Second summary here with more science stuff.

Paper 3:
Third summary discussing breakthrough research."""
        
        client = BedrockClient()
        summaries = client._parse_summaries(response_text)
        
        assert len(summaries) == 3
        assert "first summary" in summaries[0].lower()
        assert "second summary" in summaries[1].lower()
        assert "third summary" in summaries[2].lower()