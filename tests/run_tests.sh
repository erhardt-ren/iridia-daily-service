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
    
    lambda)
        echo -e "${GREEN}Testing Lambda handler...${NC}\n"
        pytest tests/test_lambda_handler.py -v
        ;;
    
    fast)
        echo -e "${GREEN}Running fast tests (excluding e2e)...${NC}\n"
        pytest tests/ -v -m "not e2e" --tb=short
        ;;
    
    coverage)
        echo -e "${GREEN}Running with coverage report...${NC}\n"
        pytest tests/ --cov=src --cov-report=html --cov-report=term-missing
        echo -e "\n${GREEN}📊 Coverage report: htmlcov/index.html${NC}"
        ;;
    
    clean)
        echo -e "${YELLOW}Cleaning test artifacts...${NC}"
        rm -rf .pytest_cache htmlcov .coverage __pycache__
        find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
        find . -type f -name "*.pyc" -delete 2>/dev/null || true
        echo -e "${GREEN}✓ Clean complete${NC}"
        ;;
    
    all|*)
        echo -e "${GREEN}Running all tests...${NC}\n"
        pytest tests/ -v
        ;;
esac

echo -e "\n${BLUE}================================${NC}"
echo -e "${GREEN}  ✓ Tests complete${NC}"
echo -e "${BLUE}================================${NC}"