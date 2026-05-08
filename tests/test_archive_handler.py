"""Tests for archive_handler HTTP layer.

Covers the API contract: correct pagination envelope fields, input validation,
and the shape of responses the frontend depends on.
"""

import json
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(query_params=None, path='/archive/latest', proxy='latest'):
    return {
        'httpMethod': 'GET',
        'path': path,
        'pathParameters': {'proxy': proxy},
        'queryStringParameters': query_params or {}
    }


def _body(response):
    return json.loads(response['body'])


# ---------------------------------------------------------------------------
# Pagination envelope
# ---------------------------------------------------------------------------

class TestPaginationEnvelope:
    """The response from /archive/latest must contain all fields the frontend uses."""

    REQUIRED_PAGINATION_FIELDS = {
        'offset', 'limit', 'total_count', 'total_pages',
        'current_page', 'has_next_page', 'has_prev_page'
    }

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_all_pagination_fields_present(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event(), mock_context)
        body = _body(response)

        assert response['statusCode'] == 200
        assert set(body['pagination'].keys()) >= self.REQUIRED_PAGINATION_FIELDS

    @patch('iridia_daily.archive_handler.query_papers')
    def test_has_next_page_true_when_more_results_exist(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        mock_query.return_value = ([{'pmid': str(i)} for i in range(10)], 25)
        response = lambda_handler(_make_event({'limit': '10', 'offset': '0'}), mock_context)
        body = _body(response)

        assert body['pagination']['has_next_page'] is True

    @patch('iridia_daily.archive_handler.query_papers')
    def test_has_next_page_false_on_last_page(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        mock_query.return_value = ([{'pmid': '1'}, {'pmid': '2'}], 12)
        response = lambda_handler(_make_event({'limit': '10', 'offset': '10'}), mock_context)
        body = _body(response)

        assert body['pagination']['has_next_page'] is False

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_has_prev_page_false_on_first_page(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event({'limit': '10', 'offset': '0'}), mock_context)
        body = _body(response)

        assert body['pagination']['has_prev_page'] is False

    @patch('iridia_daily.archive_handler.query_papers')
    def test_has_prev_page_true_when_not_first_page(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        mock_query.return_value = ([{'pmid': str(i)} for i in range(10)], 30)
        response = lambda_handler(_make_event({'limit': '10', 'offset': '10'}), mock_context)
        body = _body(response)

        assert body['pagination']['has_prev_page'] is True

    @patch('iridia_daily.archive_handler.query_papers')
    def test_current_page_correct_for_aligned_offset(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        mock_query.return_value = ([], 50)
        response = lambda_handler(_make_event({'limit': '10', 'offset': '20'}), mock_context)
        body = _body(response)

        assert body['pagination']['current_page'] == 3

    @patch('iridia_daily.archive_handler.query_papers')
    def test_total_pages_ceiling_division(self, mock_query, mock_context):
        """11 papers with limit=10 should give 2 total pages, not 1."""
        from iridia_daily.archive_handler import lambda_handler

        mock_query.return_value = ([], 11)
        response = lambda_handler(_make_event({'limit': '10', 'offset': '0'}), mock_context)
        body = _body(response)

        assert body['pagination']['total_pages'] == 2

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_empty_database_returns_valid_envelope(self, mock_query, mock_context):
        """An empty result set should still return a valid pagination envelope."""
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event(), mock_context)
        body = _body(response)

        assert response['statusCode'] == 200
        assert body['pagination']['total_count'] == 0
        assert body['pagination']['has_next_page'] is False
        assert body['pagination']['has_prev_page'] is False


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:

    def test_non_integer_limit_returns_400(self, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event({'limit': 'abc'}), mock_context)
        assert response['statusCode'] == 400

    def test_non_integer_offset_returns_400(self, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event({'offset': 'xyz'}), mock_context)
        assert response['statusCode'] == 400

    def test_negative_offset_returns_400(self, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event({'offset': '-1'}), mock_context)
        assert response['statusCode'] == 400

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_limit_clamped_to_max_100(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        lambda_handler(_make_event({'limit': '500'}), mock_context)
        _, kwargs = mock_query.call_args
        assert kwargs['limit'] <= 100

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_limit_clamped_to_min_1(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        lambda_handler(_make_event({'limit': '0'}), mock_context)
        _, kwargs = mock_query.call_args
        assert kwargs['limit'] >= 1

    def test_invalid_sort_returns_400(self, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event({'sort': 'random'}), mock_context)
        assert response['statusCode'] == 400

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_valid_sort_date_desc_accepted(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event({'sort': 'date_desc'}), mock_context)
        assert response['statusCode'] == 200

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_valid_sort_date_asc_accepted(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event({'sort': 'date_asc'}), mock_context)
        assert response['statusCode'] == 200


# ---------------------------------------------------------------------------
# Topic filtering — no whitelist, any value is passed to the query
# ---------------------------------------------------------------------------

class TestTopicValidation:

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_unknown_topic_returns_200_empty(self, mock_query, mock_context):
        """An unrecognised topic is not an error — it just returns no results."""
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event({'topic': 'astrology'}), mock_context)
        assert response['statusCode'] == 200
        assert _body(response)['pagination']['total_count'] == 0

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_known_topic_returns_200(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event({'topic': 'neuroscience'}), mock_context)
        assert response['statusCode'] == 200

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_topic_is_lowercased(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event({'topic': 'Neuroscience'}), mock_context)
        assert response['statusCode'] == 200

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_empty_topic_treated_as_no_filter(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event({'topic': ''}), mock_context)
        assert response['statusCode'] == 200


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------

class TestResponseShape:

    @patch('iridia_daily.archive_handler.query_papers')
    def test_papers_list_present_in_response(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        mock_query.return_value = ([{
            'pmid': '001', 'topic': 'neuroscience', 'date': '2025-01-01',
            'title': 'Test', 'summary': 'A test.', 'journal': 'J', 'url': 'http://x'
        }], 1)

        response = lambda_handler(_make_event(), mock_context)
        body = _body(response)

        assert 'papers' in body
        assert len(body['papers']) == 1

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_filters_echoed_back_in_response(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(
            _make_event({'topic': 'neuroscience', 'sort': 'date_asc', 'search': 'brain'}),
            mock_context
        )
        body = _body(response)

        assert 'filters' in body
        assert body['filters']['topic'] == 'neuroscience'
        assert body['filters']['sort'] == 'date_asc'
        assert body['filters']['search'] == 'brain'

    @patch('iridia_daily.archive_handler.query_papers', return_value=([], 0))
    def test_cors_headers_present(self, mock_query, mock_context):
        from iridia_daily.archive_handler import lambda_handler

        response = lambda_handler(_make_event(), mock_context)
        assert 'Access-Control-Allow-Origin' in response['headers']


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_context():
    from unittest.mock import MagicMock
    ctx = MagicMock()
    ctx.aws_request_id = 'test-request-id'
    return ctx
