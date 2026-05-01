"""AWS Bedrock integration for AI-powered content generation."""

import json
import os
import boto3

DEFAULT_MODEL_ID = 'us.anthropic.claude-sonnet-4-6'


class BedrockClient:
    """Client for generating content using AWS Bedrock and Claude."""

    def __init__(self, region='us-east-1'):
        """Initialize Bedrock client.

        Args:
            region: AWS region for Bedrock service.
        """
        self.client = boto3.client('bedrock-runtime', region_name=region)
        self.model_id = os.environ.get('BEDROCK_MODEL_ID', DEFAULT_MODEL_ID)
    
    def generate_summaries(self, papers):
        """Generate entertaining summaries for research papers.
        
        Args:
            papers: List of paper dictionaries with title, abstract, etc.
            
        Returns:
            List of summary strings, one per paper.
        """
        prompt = self._build_prompt(papers)
        
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 600,  # Reduced to encourage shorter summaries
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9
        })
        
        try:
            print("Calling Bedrock to generate entertaining summaries...")
            
            response = self.client.invoke_model(modelId=self.model_id, body=body)
            response_body = json.loads(response['body'].read())
            summaries_text = response_body['content'][0]['text']
            
            summaries = self._parse_summaries(summaries_text)
            print(f"Generated {len(summaries)} entertaining summaries")
            return summaries
            
        except Exception as e:
            print(f"Error calling Bedrock: {e}")
            return ["Cool science fact coming soon!" for _ in papers] if papers else []
    
    def _build_prompt(self, papers):
        """Build the prompt for Claude based on papers.
        
        Args:
            papers: List of paper dictionaries.
            
        Returns:
            Formatted prompt string for Claude.
        """
        if not papers:
            return """Generate 3 fascinating, verified scientific facts from recent research. 
Make each one punchy, entertaining, and memorable. Format as a numbered list."""
        
        papers_text = "\n".join([
            f"Paper {i}:\nTitle: {paper['title']}\nJournal: {paper['journal']} ({paper['year']})\nAbstract: {paper['abstract'][:1200]}\nURL: {paper['url']}\n"
            for i, paper in enumerate(papers, 1)
        ])
        
        return f"""You're writing for Iridia Daily - science communication that's smart, witty, and genuinely engaging.

Here are {len(papers)} recently published research papers:

{papers_text}

Create SHORT, WITTY summaries for EACH paper (2-3 sentences, MAX 280 characters each).

CRITICAL RULES:
- Assume the role of a slightly feminine but scientific tone
- Be 100% accurate to the research - don't exaggerate
- Use clever observations and witty turns of phrase
- Include smart metaphors or analogies that illuminate the science
- Make people smile while learning something real
- Be conversational but intelligent - coffee shop, not lecture hall
- Focus on the "aha" moment that makes the finding interesting
- KEEP IT CONCISE: 2-3 sentences maximum, under 280 characters per summary

Format EXACTLY like this:

Paper 1:
[Your smart, witty 2-3 sentence summary - MAX 280 characters]

Paper 2:
[Your smart, witty 2-3 sentence summary - MAX 280 characters]

[Continue for all papers...]

Wit should come from clever insights about the science itself, not from trying to be funny."""
    
    def _parse_summaries(self, summaries_text):
        """Parse Claude's response into individual summaries.
        
        Args:
            summaries_text: Raw text response from Claude.
            
        Returns:
            List of individual summary strings.
        """
        summaries = []
        lines = summaries_text.split('\n')
        current_summary = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith('Paper'):
                if current_summary:
                    summaries.append(current_summary.strip())
                current_summary = ""
            elif line and not line.startswith('Paper'):
                current_summary += line + " "
        
        if current_summary:
            summaries.append(current_summary.strip())
        
        return summaries