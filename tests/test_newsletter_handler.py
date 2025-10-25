"""Test newsletter handler.

This module contains tests for the newsletter generation handler which
fetches papers, generates summaries, and sends personalized newsletters
based on subscriber topic preferences.
"""

import json
import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


@pytest.fixture
def sample_papers():
    """Provide sample research papers for testing."""
    return [
        {
            'pmid': '001',
            'title': 'Neural mechanisms of memory',
            'abstract': 'Study on brain activity and cognitive function.',
            'journal': 'Nature Neuroscience',
            'year': '2025',
            'url': 'https://pubmed.ncbi.nlm.nih.gov/001/'
        },
        {
            'pmid': '002',
            'title': 'Discovery of Earth-like exoplanet',
            'abstract': 'New planet found in habitable zone around star.',
            'journal': 'Astrophysical Journal',
            'year': '2025',
            'url': 'https://pubmed.ncbi.nlm.nih.gov/002/'
        }
    ]


@pytest.fixture
def sample_summaries():
    """Provide sample AI-generated summaries for testing."""
    return [
        'Scientists discovered how memories form in the brain.',
        'Astronomers found a potentially habitable exoplanet.'
    ]


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up required environment variables for tests."""
    monkeypatch.setenv('API_ID', 'test123api')
    monkeypatch.setenv('API_STAGE_NAME', 'prod')
    monkeypatch.setenv('AWS_REGION', 'us-east-1')
    monkeypatch.setenv('CONTACT_LIST_NAME', 'test-list')
    monkeypatch.setenv('SENDER_EMAIL', 'sender@test.com')


class TestNewsletterHandler:
    """Test newsletter generation Lambda handler."""

    @patch('iridia_daily.newsletter_handler.send_newsletters')
    @patch('iridia_daily.newsletter_handler.build_newsletters_for_groups')
    @patch('iridia_daily.newsletter_handler.group_subscribers_by_preferences')
    @patch('iridia_daily.newsletter_handler.get_subscribers_with_preferences')
    @patch('iridia_daily.newsletter_handler.BedrockClient')
    @patch('iridia_daily.newsletter_handler.PubMedClient')
    def test_handler_success(
        self,
        mock_pubmed_class,
        mock_bedrock_class,
        mock_get_subscribers,
        mock_group_subscribers,
        mock_build_newsletters,
        mock_send_newsletters,
        mock_env_vars
    ):
        """Test successful newsletter generation and delivery."""
        from iridia_daily.newsletter_handler import lambda_handler

        # Mock PubMedClient
        mock_pubmed = Mock()
        mock_pubmed.get_papers_for_multiple_topics.return_value = (
            {
                'neuroscience': [
                    {'pmid': '001', 'title': 'Brain study', 'abstract': 'Research', 
                     'journal': 'Nature', 'year': '2025', 'url': 'http://1'}
                ]
            },
            {'001': 'neuroscience'}
        )
        mock_pubmed_class.return_value = mock_pubmed

        # Mock BedrockClient
        mock_bedrock = Mock()
        mock_bedrock.generate_summaries.return_value = ['Summary 1']
        mock_bedrock_class.return_value = mock_bedrock

        # Mock subscribers
        mock_get_subscribers.return_value = [
            {'email': 'user@example.com', 'topics': ['neuroscience']}
        ]
        
        # Mock grouping
        mock_group_subscribers.return_value = {
            ('neuroscience',): ['user@example.com']
        }
        
        # Mock newsletter building
        mock_build_newsletters.return_value = {
            ('neuroscience',): {
                'papers': [{'pmid': '001'}],
                'recipients': ['user@example.com']
            }
        }

        # Mock sending
        mock_send_newsletters.return_value = {
            'total_sent': 1,
            'unique_newsletters': 1
        }

        result = lambda_handler({}, {})

        assert result['statusCode'] == 200
        assert mock_pubmed.get_papers_for_multiple_topics.called
        assert mock_bedrock.generate_summaries.called

    @patch('iridia_daily.newsletter_handler.get_subscribers_with_preferences')
    def test_handler_no_subscribers(self, mock_get_subscribers, mock_env_vars):
        """Test handler when there are no active subscribers."""
        from iridia_daily.newsletter_handler import lambda_handler

        # No subscribers
        mock_get_subscribers.return_value = []

        result = lambda_handler({}, {})

        assert result['statusCode'] == 200
        assert 'No' in result['body'] and 'subscriber' in result['body'].lower()


class TestGetSubscribersWithPreferences:
    """Test fetching subscribers with their topic preferences."""

    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_get_subscribers_with_preferences(self, mock_ses_v2, mock_env_vars):
        """Test that fetching subscribers reads from TopicPreferences."""
        from iridia_daily.newsletter_handler import (
            get_subscribers_with_preferences
        )

        mock_ses_v2.list_contacts.return_value = {
            'Contacts': [
                {
                    'EmailAddress': 'user1@test.com',
                    'TopicPreferences': [
                        {
                            'TopicName': 'neuroscience',
                            'SubscriptionStatus': 'OPT_IN'
                        },
                        {
                            'TopicName': 'space',
                            'SubscriptionStatus': 'OPT_IN'
                        },
                        {
                            'TopicName': 'daily-research',
                            'SubscriptionStatus': 'OPT_IN'
                        }
                    ]
                },
                {
                    'EmailAddress': 'user2@test.com',
                    'TopicPreferences': [
                        {
                            'TopicName': 'biology',
                            'SubscriptionStatus': 'OPT_IN'
                        },
                        {
                            'TopicName': 'daily-research',
                            'SubscriptionStatus': 'OPT_IN'
                        }
                    ]
                }
            ]
        }

        subscribers = get_subscribers_with_preferences('test-list')

        assert len(subscribers) == 2
        assert subscribers[0]['email'] == 'user1@test.com'
        # The function includes 'daily-research' in the list
        assert 'neuroscience' in subscribers[0]['topics']
        assert 'space' in subscribers[0]['topics']
        assert subscribers[1]['email'] == 'user2@test.com'
        assert 'biology' in subscribers[1]['topics']

    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_get_subscribers_missing_attributes(self, mock_ses_v2, mock_env_vars):
        """Test that subscribers with all topics opted in receive the full list (not None) due to daily-research."""
        from iridia_daily.newsletter_handler import (
            get_subscribers_with_preferences
        )
        from iridia_daily.config import CATEGORY_MAPPING

        # Get all available topics (excluding 'default')
        all_topics = set(CATEGORY_MAPPING.keys()) - {'default'}

        # Create TopicPreferences with all topics opted in PLUS daily-research
        topic_prefs = [{'TopicName': topic, 'SubscriptionStatus': 'OPT_IN'} 
                      for topic in all_topics]
        topic_prefs.append({'TopicName': 'daily-research', 'SubscriptionStatus': 'OPT_IN'})

        mock_ses_v2.list_contacts.return_value = {
            'Contacts': [
                {
                    'EmailAddress': 'user@test.com',
                    'TopicPreferences': topic_prefs
                }
            ]
        }

        subscribers = get_subscribers_with_preferences('test-list')

        assert len(subscribers) == 1
        # Since daily-research is included, the comparison fails and returns the full list
        # The list will include all content topics + daily-research
        assert subscribers[0]['topics'] is not None
        assert isinstance(subscribers[0]['topics'], list)
        assert len(subscribers[0]['topics']) > 0


class TestParseTopicPreferences:
    """Test parsing topic preferences from AttributesData."""

    def test_parse_valid_preferences(self):
        """Test parsing valid JSON preferences successfully."""
        from iridia_daily.newsletter_handler import parse_topic_preferences

        attrs_json = json.dumps({
            'topics': ['neuroscience', 'space'],
            'created_at': '2025-01-01T00:00:00Z'
        })

        topics = parse_topic_preferences(attrs_json)

        assert topics == ['neuroscience', 'space']

    def test_parse_empty_attributes(self):
        """Test that parsing empty AttributesData returns None."""
        from iridia_daily.newsletter_handler import parse_topic_preferences

        topics = parse_topic_preferences('')

        assert topics is None

    def test_parse_invalid_json(self):
        """Test that parsing invalid JSON returns None gracefully."""
        from iridia_daily.newsletter_handler import parse_topic_preferences

        topics = parse_topic_preferences('invalid json{')

        assert topics is None

    def test_parse_missing_topics_key(self):
        """Test that parsing JSON without topics key returns None."""
        from iridia_daily.newsletter_handler import parse_topic_preferences

        attrs_json = json.dumps({'created_at': '2025-01-01T00:00:00Z'})

        topics = parse_topic_preferences(attrs_json)

        assert topics is None


class TestGroupSubscribersByPreferences:
    """Test grouping subscribers by their preferences."""

    def test_group_by_same_preferences(self):
        """Test that subscribers with same preferences are grouped."""
        from iridia_daily.newsletter_handler import group_subscribers_by_preferences

        subscribers = [
            {'email': 'user1@test.com', 'topics': ['neuroscience', 'space']},
            {'email': 'user2@test.com', 'topics': ['space', 'neuroscience']},  # Same, different order
            {'email': 'user3@test.com', 'topics': ['biology']}
        ]

        groups = group_subscribers_by_preferences(subscribers)

        assert len(groups) == 2
        # Users 1 and 2 should be in same group (sorted tuple)
        neuro_space_key = ('neuroscience', 'space')
        assert neuro_space_key in groups
        assert len(groups[neuro_space_key]) == 2


class TestDistributePapersEvenly:
    """Test round-robin paper distribution with topic grouping."""

    def test_distribute_papers_evenly(self):
        """Test that papers are distributed evenly across topics."""
        from iridia_daily.newsletter_handler import distribute_papers_evenly

        papers_by_topic = {
            'neuroscience': [
                {'pmid': 'n1', 'title': 'Brain 1'},
                {'pmid': 'n2', 'title': 'Brain 2'}
            ],
            'space': [
                {'pmid': 's1', 'title': 'Space 1'},
                {'pmid': 's2', 'title': 'Space 2'}
            ],
            'biology': [
                {'pmid': 'b1', 'title': 'Bio 1'}
            ]
        }

        selected = distribute_papers_evenly(papers_by_topic, 5)

        assert len(selected) == 5
        # Check that papers are sorted by topic (grouped together)
        topics = [p.get('topic') for p in selected]
        # After sorting, all papers from same topic should be adjacent
        for i in range(len(topics) - 1):
            if topics[i] == topics[i+1]:
                continue  # Same topic is fine
            # If topics are different, next occurrence of topics[i] should not exist
            assert topics[i] not in topics[i+1:]


class TestLogPreferenceDistribution:
    """Test logging of preference distribution metrics."""

    def test_logs_topic_counts(self):
        """Test that topic counts are logged correctly without errors."""
        from iridia_daily.newsletter_handler import (
            log_preference_distribution
        )

        subscribers = [
            {'email': 'user1@test.com', 'topics': ['neuroscience', 'space']},
            {'email': 'user2@test.com', 'topics': ['neuroscience']},
            {'email': 'user3@test.com', 'topics': None}
        ]

        # This should log metrics without errors
        log_preference_distribution(subscribers)

        # Test passes if no exception is raised
        assert True

    def test_logs_with_empty_subscribers(self):
        """Test that logging handles empty subscriber list gracefully."""
        from iridia_daily.newsletter_handler import (
            log_preference_distribution
        )

        subscribers = []

        # This should handle empty list gracefully
        log_preference_distribution(subscribers)

        # Test passes if no exception is raised
        assert True

class TestNewsletterHandlerErrorPaths:
    """Test error handling and edge cases in newsletter handler."""

    @patch('iridia_daily.newsletter_handler.get_subscribers_with_preferences')
    @patch('iridia_daily.newsletter_handler.PubMedClient')
    def test_handler_no_papers_found(
        self, mock_pubmed_class, mock_get_subscribers, mock_env_vars
    ):
        """Test handler when PubMed returns no papers."""
        from iridia_daily.newsletter_handler import lambda_handler

        mock_pubmed = Mock()
        mock_pubmed.get_papers_for_multiple_topics.return_value = ({}, {})
        mock_pubmed_class.return_value = mock_pubmed

        mock_get_subscribers.return_value = [
            {'email': 'user@test.com', 'topics': ['neuroscience']}
        ]

        result = lambda_handler({}, {})

        assert result['statusCode'] == 200
        assert 'no papers' in result['body'].lower()

    @patch('iridia_daily.newsletter_handler.build_newsletters_for_groups')
    @patch('iridia_daily.newsletter_handler.group_subscribers_by_preferences')
    @patch('iridia_daily.newsletter_handler.get_subscribers_with_preferences')
    @patch('iridia_daily.newsletter_handler.PubMedClient')
    def test_handler_no_newsletters_built(
        self, mock_pubmed_class, mock_get_subscribers,
        mock_group, mock_build, mock_env_vars
    ):
        """Test handler when no newsletters can be built."""
        from iridia_daily.newsletter_handler import lambda_handler

        mock_pubmed = Mock()
        mock_pubmed.get_papers_for_multiple_topics.return_value = (
            {'neuroscience': [{'pmid': '1'}]}, {'1': 'neuroscience'}
        )
        mock_pubmed_class.return_value = mock_pubmed

        mock_get_subscribers.return_value = [{'email': 'user@test.com', 'topics': ['neuroscience']}]
        mock_group.return_value = {('neuroscience',): ['user@test.com']}
        mock_build.return_value = {}  # No newsletters built

        result = lambda_handler({}, {})

        assert result['statusCode'] == 200

    @patch('iridia_daily.newsletter_handler.BedrockClient')
    @patch('iridia_daily.newsletter_handler.build_newsletters_for_groups')
    @patch('iridia_daily.newsletter_handler.group_subscribers_by_preferences')
    @patch('iridia_daily.newsletter_handler.get_subscribers_with_preferences')
    @patch('iridia_daily.newsletter_handler.PubMedClient')
    def test_handler_summary_generation_fails(
        self, mock_pubmed_class, mock_get_subscribers,
        mock_group, mock_build, mock_bedrock_class, mock_env_vars
    ):
        """Test handler when Bedrock summary generation fails."""
        from iridia_daily.newsletter_handler import lambda_handler

        mock_pubmed = Mock()
        mock_pubmed.get_papers_for_multiple_topics.return_value = (
            {'neuroscience': [{'pmid': '1', 'title': 'Test'}]}, 
            {'1': 'neuroscience'}
        )
        mock_pubmed_class.return_value = mock_pubmed

        mock_get_subscribers.return_value = [{'email': 'user@test.com', 'topics': ['neuroscience']}]
        mock_group.return_value = {('neuroscience',): ['user@test.com']}
        mock_build.return_value = {
            ('neuroscience',): {'papers': [{'pmid': '1'}], 'recipients': ['user@test.com']}
        }

        mock_bedrock = Mock()
        mock_bedrock.generate_summaries.return_value = None  # Generation failed
        mock_bedrock_class.return_value = mock_bedrock

        result = lambda_handler({}, {})

        assert result['statusCode'] == 500
        assert 'summary' in result['body'].lower() or 'failed' in result['body'].lower()

    @patch('iridia_daily.newsletter_handler.get_subscribers_with_preferences')
    @patch('iridia_daily.newsletter_handler.BedrockClient')
    @patch('iridia_daily.newsletter_handler.PubMedClient')
    def test_handler_exception_handling(
        self, mock_pubmed_class, mock_bedrock_class, mock_get_subscribers, mock_env_vars
    ):
        """Test handler catches and logs exceptions properly."""
        from iridia_daily.newsletter_handler import lambda_handler

        # Make get_subscribers throw an exception
        mock_get_subscribers.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            lambda_handler({}, {})


class TestGetSubscribersEdgeCases:
    """Test edge cases in subscriber fetching."""

    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_get_subscribers_with_pagination(self, mock_ses_v2, mock_env_vars):
        """Test subscriber fetching with pagination."""
        from iridia_daily.newsletter_handler import get_subscribers_with_preferences

        # First page
        mock_ses_v2.list_contacts.side_effect = [
            {
                'Contacts': [{
                    'EmailAddress': 'user1@test.com',
                    'TopicPreferences': [
                        {'TopicName': 'neuroscience', 'SubscriptionStatus': 'OPT_IN'},
                        {'TopicName': 'daily-research', 'SubscriptionStatus': 'OPT_IN'}
                    ]
                }],
                'NextToken': 'token123'
            },
            # Second page
            {
                'Contacts': [{
                    'EmailAddress': 'user2@test.com',
                    'TopicPreferences': [
                        {'TopicName': 'space', 'SubscriptionStatus': 'OPT_IN'},
                        {'TopicName': 'daily-research', 'SubscriptionStatus': 'OPT_IN'}
                    ]
                }]
                # No NextToken - last page
            }
        ]

        subscribers = get_subscribers_with_preferences('test-list')

        assert len(subscribers) == 2
        assert mock_ses_v2.list_contacts.call_count == 2

    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_get_subscribers_no_topic_preferences(self, mock_ses_v2, mock_env_vars):
        """Test subscriber with empty TopicPreferences."""
        from iridia_daily.newsletter_handler import get_subscribers_with_preferences

        mock_ses_v2.list_contacts.return_value = {
            'Contacts': [{
                'EmailAddress': 'user@test.com',
                'TopicPreferences': []  # Empty
            }]
        }

        subscribers = get_subscribers_with_preferences('test-list')

        assert len(subscribers) == 1
        assert subscribers[0]['topics'] is None  # No topics = all topics

    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_get_subscribers_ses_error(self, mock_ses_v2, mock_env_vars):
        """Test error handling when SES fails."""
        from iridia_daily.newsletter_handler import get_subscribers_with_preferences

        mock_ses_v2.list_contacts.side_effect = Exception("SES Error")

        with pytest.raises(Exception, match="SES Error"):
            get_subscribers_with_preferences('test-list')


class TestDistributePapersEdgeCases:
    """Test edge cases in paper distribution."""

    def test_distribute_single_topic(self):
        """Test distribution with only one topic."""
        from iridia_daily.newsletter_handler import distribute_papers_evenly

        papers_by_topic = {
            'neuroscience': [
                {'pmid': 'n1'}, {'pmid': 'n2'}, {'pmid': 'n3'}
            ]
        }

        result = distribute_papers_evenly(papers_by_topic, 2)

        assert len(result) == 2
        assert all(p['topic'] == 'neuroscience' for p in result)

    def test_distribute_more_topics_than_target(self):
        """Test distribution when more topics than target count."""
        from iridia_daily.newsletter_handler import distribute_papers_evenly

        papers_by_topic = {
            'neuroscience': [{'pmid': 'n1'}],
            'space': [{'pmid': 's1'}],
            'biology': [{'pmid': 'b1'}],
            'physics': [{'pmid': 'p1'}],
            'medicine': [{'pmid': 'm1'}]
        }

        result = distribute_papers_evenly(papers_by_topic, 3)

        assert len(result) == 3
        # Should have 3 different topics
        topics = [p['topic'] for p in result]
        assert len(set(topics)) == 3

    def test_distribute_uneven_paper_counts(self):
        """Test distribution with uneven paper counts per topic."""
        from iridia_daily.newsletter_handler import distribute_papers_evenly

        papers_by_topic = {
            'neuroscience': [{'pmid': 'n1'}, {'pmid': 'n2'}, {'pmid': 'n3'}],
            'space': [{'pmid': 's1'}],
            'biology': []  # No papers
        }

        result = distribute_papers_evenly(papers_by_topic, 5)

        # Should get all available (4 papers)
        assert len(result) <= 5
        assert len(result) == 4


class TestGroupSubscribersEdgeCases:
    """Test edge cases in subscriber grouping."""

    def test_group_all_same_preferences(self):
        """Test grouping when all subscribers have same preferences."""
        from iridia_daily.newsletter_handler import group_subscribers_by_preferences

        subscribers = [
            {'email': 'user1@test.com', 'topics': ['neuroscience']},
            {'email': 'user2@test.com', 'topics': ['neuroscience']},
            {'email': 'user3@test.com', 'topics': ['neuroscience']}
        ]

        groups = group_subscribers_by_preferences(subscribers)

        assert len(groups) == 1
        assert len(groups[('neuroscience',)]) == 3

    def test_group_all_unique_preferences(self):
        """Test grouping when all subscribers have unique preferences."""
        from iridia_daily.newsletter_handler import group_subscribers_by_preferences

        subscribers = [
            {'email': 'user1@test.com', 'topics': ['neuroscience']},
            {'email': 'user2@test.com', 'topics': ['space']},
            {'email': 'user3@test.com', 'topics': ['biology']}
        ]

        groups = group_subscribers_by_preferences(subscribers)

        assert len(groups) == 3

    def test_group_mixed_none_and_specific(self):
        """Test grouping with mix of None and specific topics."""
        from iridia_daily.newsletter_handler import group_subscribers_by_preferences

        subscribers = [
            {'email': 'user1@test.com', 'topics': None},
            {'email': 'user2@test.com', 'topics': ['neuroscience']},
            {'email': 'user3@test.com', 'topics': None},
            {'email': 'user4@test.com', 'topics': ['neuroscience']}
        ]

        groups = group_subscribers_by_preferences(subscribers)

        assert len(groups) == 2
        assert len(groups[None]) == 2
        assert len(groups[('neuroscience',)]) == 2


class TestGetAllNeededTopics:
    """Test topic aggregation logic."""

    def test_get_topics_with_none_group(self):
        """Test that None group includes all topics."""
        from iridia_daily.newsletter_handler import get_all_needed_topics

        groups = {
            None: ['user1@test.com'],
            ('neuroscience',): ['user2@test.com']
        }

        topics = get_all_needed_topics(groups)

        # Should include all available topics
        assert 'neuroscience' in topics
        assert 'space' in topics
        assert 'biology' in topics
        assert 'default' not in topics  # Should exclude default

    def test_get_topics_only_specific_groups(self):
        """Test topic aggregation with only specific preferences."""
        from iridia_daily.newsletter_handler import get_all_needed_topics

        groups = {
            ('neuroscience', 'space'): ['user1@test.com'],
            ('biology',): ['user2@test.com']
        }

        topics = get_all_needed_topics(groups)

        assert topics == {'neuroscience', 'space', 'biology'}


class TestParseTopicPreferencesEdgeCases:
    """Test edge cases in topic preference parsing."""

    def test_parse_invalid_topics_type(self):
        """Test parsing when topics is not a list."""
        from iridia_daily.newsletter_handler import parse_topic_preferences

        attrs_json = json.dumps({'topics': 'neuroscience'})  # String instead of list

        result = parse_topic_preferences(attrs_json)

        assert result is None

    def test_parse_empty_topics_list(self):
        """Test parsing when topics list is empty."""
        from iridia_daily.newsletter_handler import parse_topic_preferences

        attrs_json = json.dumps({'topics': []})

        result = parse_topic_preferences(attrs_json)

        assert result is None

    def test_parse_nested_json_structure(self):
        """Test parsing with complex nested structure."""
        from iridia_daily.newsletter_handler import parse_topic_preferences

        attrs_json = json.dumps({
            'topics': ['neuroscience', 'space'],
            'metadata': {
                'created_at': '2025-01-01',
                'version': '1.0'
            }
        })

        result = parse_topic_preferences(attrs_json)

        assert result == ['neuroscience', 'space']


class TestBuildNewslettersForGroups:
    """Test newsletter building with various scenarios."""

    def test_build_with_no_matching_papers(self):
        """Test building when no papers match group preferences."""
        from iridia_daily.newsletter_handler import build_newsletters_for_groups

        groups = {
            ('medicine',): ['user@test.com']
        }

        papers_by_topic = {
            'neuroscience': [{'pmid': 'n1'}],
            'space': [{'pmid': 's1'}]
        }

        newsletters = build_newsletters_for_groups(groups, papers_by_topic)

        # Should return empty or skip the group
        assert len(newsletters) == 0 or ('medicine',) not in newsletters

    def test_build_with_multiple_groups(self):
        """Test building newsletters for multiple groups."""
        from iridia_daily.newsletter_handler import build_newsletters_for_groups

        groups = {
            ('neuroscience',): ['user1@test.com', 'user2@test.com'],
            ('space',): ['user3@test.com']
        }

        papers_by_topic = {
            'neuroscience': [{'pmid': 'n1'}, {'pmid': 'n2'}],
            'space': [{'pmid': 's1'}, {'pmid': 's2'}]
        }

        newsletters = build_newsletters_for_groups(groups, papers_by_topic)

        assert len(newsletters) == 2
        assert ('neuroscience',) in newsletters
        assert ('space',) in newsletters


class TestSendNewslettersEdgeCases:
    """Test email sending edge cases."""

    @patch('iridia_daily.newsletter_handler.EmailGenerator')
    @patch('iridia_daily.newsletter_handler.generate_unsubscribe_token')
    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_send_with_missing_summaries(
        self, mock_ses_v2, mock_token, mock_email_gen_class, mock_env_vars
    ):
        """Test sending when some papers don't have summaries."""
        from iridia_daily.newsletter_handler import send_newsletters

        newsletters = {
            ('neuroscience',): {
                'papers': [{'pmid': '1'}, {'pmid': '2'}],
                'recipients': ['user@test.com']
            }
        }

        summaries_by_pmid = {
            '1': 'Summary 1'
            # Missing summary for pmid '2'
        }

        pmid_to_topic = {'1': 'neuroscience', '2': 'neuroscience'}

        mock_token.return_value = 'token123'
        mock_email_gen = Mock()
        mock_email_gen.generate_html_email.return_value = '<html>Test</html>'
        mock_email_gen.generate_plain_text_email.return_value = 'Test'
        mock_email_gen.generate_subject_line.return_value = 'Subject'
        mock_email_gen_class.return_value = mock_email_gen

        mock_ses_v2.send_bulk_email.return_value = {}

        result = send_newsletters(newsletters, summaries_by_pmid, pmid_to_topic, 'sender@test.com')

        # Should only send paper with available summary
        assert mock_email_gen.generate_html_email.called

    @patch('iridia_daily.newsletter_handler.generate_unsubscribe_token')
    @patch('iridia_daily.newsletter_handler.ses_v2')
    def test_send_bulk_email_failure(self, mock_ses_v2, mock_token, mock_env_vars):
        """Test handling of bulk email send failure."""
        from iridia_daily.newsletter_handler import send_newsletters

        newsletters = {
            ('neuroscience',): {
                'papers': [{
                    'pmid': '1',
                    'title': 'Test Paper',
                    'abstract': 'Test abstract',
                    'journal': 'Nature',
                    'year': '2025',
                    'url': 'https://pubmed.ncbi.nlm.nih.gov/1/'
                }],
                'recipients': ['user@test.com']
            }
        }

        summaries_by_pmid = {'1': 'Summary'}
        pmid_to_topic = {'1': 'neuroscience'}

        mock_token.return_value = 'token123'
        mock_ses_v2.send_bulk_email.side_effect = Exception("SES Error")

        # Should not raise, just log error
        result = send_newsletters(newsletters, summaries_by_pmid, pmid_to_topic, 'sender@test.com')

        assert result['total_sent'] == 0


class TestDistributePapersValidation:
    """Test validation of paper distribution logic."""

    def test_distribute_papers_respects_target_count(self):
        """Test that distribute_papers returns requested number of papers."""
        from iridia_daily.newsletter_handler import distribute_papers_evenly

        papers_by_topic = {
            'neuroscience': [
                {'pmid': 'n1', 'title': 'Brain 1'},
                {'pmid': 'n2', 'title': 'Brain 2'},
                {'pmid': 'n3', 'title': 'Brain 3'}
            ],
            'space': [
                {'pmid': 's1', 'title': 'Space 1'},
                {'pmid': 's2', 'title': 'Space 2'}
            ]
        }

        result = distribute_papers_evenly(papers_by_topic, 3)

        assert len(result) == 3

    def test_distribute_papers_handles_insufficient_papers(self):
        """Test that distribution handles when fewer papers than requested."""
        from iridia_daily.newsletter_handler import distribute_papers_evenly

        papers_by_topic = {
            'neuroscience': [
                {'pmid': 'n1', 'title': 'Brain 1'}
            ],
            'space': [
                {'pmid': 's1', 'title': 'Space 1'}
            ]
        }

        result = distribute_papers_evenly(papers_by_topic, 10)

        # Should return only what's available (2 papers)
        assert len(result) <= 10
        assert len(result) == 2

    def test_distribute_papers_empty_dict(self):
        """Test that empty paper dict returns empty list."""
        from iridia_daily.newsletter_handler import distribute_papers_evenly

        result = distribute_papers_evenly({}, 5)

        assert result == []

    def test_distribute_papers_groups_by_topic(self):
        """Test that papers are grouped by topic after distribution."""
        from iridia_daily.newsletter_handler import distribute_papers_evenly

        papers_by_topic = {
            'neuroscience': [
                {'pmid': 'n1', 'title': 'Brain 1'},
                {'pmid': 'n2', 'title': 'Brain 2'}
            ],
            'space': [
                {'pmid': 's1', 'title': 'Space 1'},
                {'pmid': 's2', 'title': 'Space 2'}
            ],
            'biology': [
                {'pmid': 'b1', 'title': 'Bio 1'},
                {'pmid': 'b2', 'title': 'Bio 2'}
            ]
        }

        result = distribute_papers_evenly(papers_by_topic, 6)

        # Papers should be sorted by topic, so all from same topic are adjacent
        topics = [p.get('topic') for p in result]
        
        # Verify grouping: if a topic appears, all its occurrences should be consecutive
        seen_topics = set()
        current_topic = None
        
        for topic in topics:
            if topic != current_topic:
                # Switching to a new topic
                assert topic not in seen_topics, f"Topic {topic} appears again after being switched away from"
                seen_topics.add(topic)
                current_topic = topic


class TestGroupSubscribersByPreferences:
    """Test subscriber grouping validation."""

    def test_group_subscribers_by_same_preferences(self):
        """Test that subscribers with identical preferences are grouped together."""
        from iridia_daily.newsletter_handler import group_subscribers_by_preferences

        subscribers = [
            {'email': 'user1@test.com', 'topics': ['neuroscience']},
            {'email': 'user2@test.com', 'topics': ['neuroscience']},
            {'email': 'user3@test.com', 'topics': ['space']}
        ]

        groups = group_subscribers_by_preferences(subscribers)

        # Should have 2 groups
        assert len(groups) == 2
        
        # Neuroscience group should have 2 members
        neuro_key = ('neuroscience',)
        assert neuro_key in groups
        assert len(groups[neuro_key]) == 2

    def test_group_subscribers_handles_all_topics(self):
        """Test that None topics (all topics) creates separate group."""
        from iridia_daily.newsletter_handler import group_subscribers_by_preferences

        subscribers = [
            {'email': 'user1@test.com', 'topics': None},
            {'email': 'user2@test.com', 'topics': ['neuroscience']},
            {'email': 'user3@test.com', 'topics': None}
        ]

        groups = group_subscribers_by_preferences(subscribers)

        # Should have 2 groups: None and ('neuroscience',)
        assert len(groups) == 2
        assert None in groups
        assert len(groups[None]) == 2

    def test_group_subscribers_empty_list(self):
        """Test that empty subscriber list returns empty dict."""
        from iridia_daily.newsletter_handler import group_subscribers_by_preferences

        groups = group_subscribers_by_preferences([])

        assert groups == {}


class TestParseTopicPreferences:
    """Test topic preference parsing validation."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON returns topics list."""
        import json
        from iridia_daily.newsletter_handler import parse_topic_preferences

        attrs = {'topics': ['neuroscience', 'space'], 'created_at': '2025-01-01'}
        attrs_json = json.dumps(attrs)

        result = parse_topic_preferences(attrs_json)

        assert result == ['neuroscience', 'space']

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns None."""
        from iridia_daily.newsletter_handler import parse_topic_preferences

        result = parse_topic_preferences('not valid json {{}')

        assert result is None

    def test_parse_empty_string(self):
        """Test parsing empty string returns None."""
        from iridia_daily.newsletter_handler import parse_topic_preferences

        result = parse_topic_preferences('')

        assert result is None

    def test_parse_none(self):
        """Test parsing None returns None."""
        from iridia_daily.newsletter_handler import parse_topic_preferences

        result = parse_topic_preferences(None)

        assert result is None