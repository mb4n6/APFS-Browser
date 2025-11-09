#!/bin/bash
# Setup Verification Script for APFS Cellebrite Browser Tool

echo "=========================================="
echo "APFS Browser Tool"
echo "Setup Verification"
echo "=========================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check function
check_tool() {
    if command -v $1 &> /dev/null; then
        echo -e "${GREEN}✓${NC} $1 found: $(which $1)"
        return 0
    else
        echo -e "${RED}✗${NC} $1 not found"
        return 1
    fi
}

# Python version check
echo "Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "${GREEN}✓${NC} Python found: $PYTHON_VERSION"
    
    # Check if version is >= 3.7
    MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    if [ $MAJOR -eq 3 ] && [ $MINOR -ge 7 ]; then
        echo -e "${GREEN}✓${NC} Python version is compatible (>= 3.7)"
    else
        echo -e "${YELLOW}⚠${NC} Python version might be too old (< 3.7)"
    fi
else
    echo -e "${RED}✗${NC} Python 3 not found"
    echo -e "${YELLOW}Install: brew install python3 (macOS) or apt-get install python3 (Linux)${NC}"
fi

echo ""
echo "Checking SleuthKit tools..."

TOOLS_MISSING=0

for tool in sigfind fsstat fls icat istat pstat; do
    check_tool $tool || TOOLS_MISSING=$((TOOLS_MISSING + 1))
done

echo ""
echo "Checking optional tools..."
check_tool xmount
check_tool xxd

echo ""
echo "=========================================="
if [ $TOOLS_MISSING -eq 0 ]; then
    echo -e "${GREEN}All required tools are installed!${NC}"
    echo "You're ready to use the APFS Cellebrite Browser Tool."
    echo ""
    echo "To start the tool, run:"
    echo "  python3 apfs_cellebrite_tool.py"
else
    echo -e "${RED}$TOOLS_MISSING required tool(s) missing!${NC}"
    echo ""
    echo "To install SleuthKit:"
    echo "  macOS:    brew install sleuthkit"
    echo "  Ubuntu:   sudo apt-get install sleuthkit"
    echo "  RHEL:     sudo yum install sleuthkit"
fi
echo "=========================================="
