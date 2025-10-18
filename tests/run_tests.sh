#!/bin/bash
# Test runner for Iridia Daily
# Place in tests/ directory and run as: ./tests/run_tests.sh

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}  Iridia Daily Test Runner${NC}"
echo -e "${BLUE}================================${NC}\n"

# Check pytest installation
if ! command -v pytest &> /dev/null; then
    echo -e "${YELLOW}Installing test dependencies...${NC}"
    pip install -r "$PROJECT_ROOT/requirements-test.txt"
fi

# Change to project root for running tests
cd "$PROJECT_ROOT"

case ${1:-all} in
    pubmed)
        echo -e "${GREEN}Testing PubMed integration...${NC}\n"
        pytest tests/test_pubmed_client.py -v
        ;;
    
    bedrock)
        echo -e "${GREEN}Testing Bedrock/Claude...${NC}\n"
        pytest tests/test_bedrock_client.py -v
        ;;
    
    email)
        echo -e "${GREEN}Testing email generation...${NC}\n"
        pytest tests/test_email_generator.py -v
        ;;
    
    newsletter)
        echo -e "${GREEN}Testing newsletter handler...${NC}\n"
        pytest tests/test_newsletter_handler.py -v
        ;;
    
    subscribe)
        echo -e "${GREEN}Testing subscription handler...${NC}\n"
        pytest tests/test_subscribe_handler.py -v
        ;;
    
    unsubscribe)
        echo -e "${GREEN}Testing unsubscribe handler...${NC}\n"
        pytest tests/test_unsubscribe_handler.py -v
        ;;
    
    handlers)
        echo -e "${GREEN}Testing all Lambda handlers...${NC}\n"
        pytest tests/test_newsletter_handler.py tests/test_subscribe_handler.py tests/test_unsubscribe_handler.py -v
        ;;
    
    integration)
        echo -e "${GREEN}Running integration tests...${NC}\n"
        pytest tests/ -v -m "integration" --tb=short
        ;;
    
    fast)
        echo -e "${GREEN}Running fast tests (excluding integration)...${NC}\n"
        pytest tests/ -v -m "not integration and not e2e" --tb=short
        ;;
    
    coverage)
        echo -e "${GREEN}Running with coverage report...${NC}\n"
        pytest tests/ --cov=src/iridia_daily --cov-report=html --cov-report=term-missing
        echo -e "\n${GREEN}📊 Coverage report: htmlcov/index.html${NC}"
        ;;
    
    unit)
        echo -e "${GREEN}Running unit tests only...${NC}\n"
        pytest tests/test_pubmed_client.py tests/test_bedrock_client.py tests/test_email_generator.py tests/test_utils.py -v
        ;;
    
    watch)
        echo -e "${GREEN}Running tests in watch mode...${NC}\n"
        echo -e "${YELLOW}Tests will re-run on file changes. Press Ctrl+C to exit.${NC}\n"
        pytest-watch tests/ -- -v --tb=short
        ;;
    
    clean)
        echo -e "${YELLOW}Cleaning test artifacts...${NC}"
        rm -rf .pytest_cache htmlcov .coverage __pycache__
        find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
        find . -type f -name "*.pyc" -delete 2>/dev/null || true
        echo -e "${GREEN}✓ Clean complete${NC}"
        ;;
    
    help)
        echo -e "${BLUE}Available test commands:${NC}\n"
        echo "  all          - Run all tests (default)"
        echo "  pubmed       - Test PubMed integration"
        echo "  bedrock      - Test Bedrock/Claude AI"
        echo "  email        - Test email generation"
        echo "  newsletter   - Test newsletter handler"
        echo "  subscribe    - Test subscription handler"
        echo "  unsubscribe  - Test unsubscribe handler"
        echo "  handlers     - Test all Lambda handlers"
        echo "  integration  - Run integration tests only"
        echo "  unit         - Run unit tests only"
        echo "  fast         - Run fast tests (exclude slow/integration)"
        echo "  coverage     - Run with coverage report"
        echo "  watch        - Run tests in watch mode"
        echo "  clean        - Clean test artifacts"
        echo "  help         - Show this help message"
        echo ""
        echo -e "${YELLOW}Examples:${NC}"
        echo "  ./tests/run_tests.sh"
        echo "  ./tests/run_tests.sh subscribe"
        echo "  ./tests/run_tests.sh coverage"
        ;;
    
    all|*)
        echo -e "${GREEN}Running all tests...${NC}\n"
        pytest tests/ -v --tb=short
        ;;
esac

EXIT_CODE=$?

echo -e "\n${BLUE}================================${NC}"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}  ✓ Tests complete${NC}"
else
    echo -e "${RED}  ✗ Tests failed${NC}"
fi
echo -e "${BLUE}================================${NC}"

exit $EXIT_CODE