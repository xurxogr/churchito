#!/bin/bash
# Test runner script with coverage reporting

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default values
COVERAGE=true
HTML_REPORT=true
VERBOSE=false
SPECIFIC_TEST=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-coverage)
            COVERAGE=false
            shift
            ;;
        --no-html)
            HTML_REPORT=false
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --test)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-coverage    Run tests without coverage"
            echo "  --no-html        Don't generate HTML coverage report"
            echo "  -v, --verbose    Verbose test output"
            echo "  --test PATH      Run specific test file or directory"
            echo "  -h, --help       Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                              # Run all tests with coverage"
            echo "  $0 --no-coverage                # Run tests without coverage"
            echo "  $0 --test tests/core            # Run only core tests"
            echo "  $0 --test tests/core/test_settings.py  # Run specific test file"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Change to project root
cd "$(dirname "$0")/.."

echo -e "${BLUE}==================================${NC}"
echo -e "${BLUE}Discord Bot - Test Runner${NC}"
echo -e "${BLUE}==================================${NC}"
echo ""

# Check if virtual environment is activated
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo -e "${YELLOW}Warning: Virtual environment not activated${NC}"
    echo -e "${YELLOW}Run: source venv/bin/activate${NC}"
    echo ""
fi

# Build pytest command
PYTEST_CMD="pytest"

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=discord_bot --cov-report=term-missing"

    if [ "$HTML_REPORT" = true ]; then
        PYTEST_CMD="$PYTEST_CMD --cov-report=html"
    fi
fi

if [ -n "$SPECIFIC_TEST" ]; then
    PYTEST_CMD="$PYTEST_CMD $SPECIFIC_TEST"
fi

# Run tests
echo -e "${GREEN}Running tests...${NC}"
echo -e "${BLUE}Command: $PYTEST_CMD${NC}"
echo ""

if $PYTEST_CMD; then
    echo ""
    echo -e "${GREEN}==================================${NC}"
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo -e "${GREEN}==================================${NC}"

    if [ "$COVERAGE" = true ] && [ "$HTML_REPORT" = true ]; then
        echo ""
        echo -e "${BLUE}Coverage report generated: htmlcov/index.html${NC}"
        echo -e "${BLUE}Open with: open htmlcov/index.html (macOS) or xdg-open htmlcov/index.html (Linux)${NC}"
    fi

    exit 0
else
    echo ""
    echo -e "${RED}==================================${NC}"
    echo -e "${RED}✗ Tests failed!${NC}"
    echo -e "${RED}==================================${NC}"
    exit 1
fi
