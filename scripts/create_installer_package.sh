#!/bin/bash
#
# create_installer_package.sh - Create downloadable AAC installer package
#
# This script creates a self-contained installer package that includes:
# - Installation guide
# - All scripts needed for installation
# - Environment configuration template
# - Quick start instructions
#
# Usage: ./create_installer_package.sh [output_directory]

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${1:-$HOME}"
PACKAGE_NAME="aac-installer"
VERSION="2.2"
DATE=$(date +%Y%m%d)

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Ansible Automated Compliance - Installer Package Creator  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Create temporary directory
TEMP_DIR=$(mktemp -d)
PACKAGE_DIR="${TEMP_DIR}/${PACKAGE_NAME}-${VERSION}"
mkdir -p "${PACKAGE_DIR}"

echo -e "${YELLOW}Creating installer package...${NC}"

# Create directory structure
mkdir -p "${PACKAGE_DIR}/scripts"
mkdir -p "${PACKAGE_DIR}/docs"
mkdir -p "${PACKAGE_DIR}/examples"

# Copy installation guide
echo "  Copying installation guide..."
cp "${REPO_ROOT}/docs/COMPLETE_INSTALLATION_GUIDE.md" "${PACKAGE_DIR}/" 2>/dev/null || \
    echo "  Note: COMPLETE_INSTALLATION_GUIDE.md not found"

# Copy scripts
echo "  Copying installation scripts..."
cp "${SCRIPT_DIR}/install.sh" "${PACKAGE_DIR}/scripts/" 2>/dev/null || true
cp "${SCRIPT_DIR}/verify_installation.sh" "${PACKAGE_DIR}/scripts/" 2>/dev/null || true
cp "${SCRIPT_DIR}/install_opa.sh" "${PACKAGE_DIR}/scripts/" 2>/dev/null || true
cp "${SCRIPT_DIR}/install_postgres.sh" "${PACKAGE_DIR}/scripts/" 2>/dev/null || true
cp "${SCRIPT_DIR}/init_database.sh" "${PACKAGE_DIR}/scripts/" 2>/dev/null || true
cp "${SCRIPT_DIR}/load_opa_policies.sh" "${PACKAGE_DIR}/scripts/" 2>/dev/null || true

# Copy environment template
echo "  Copying environment configuration..."
cp "${REPO_ROOT}/environment.conf.example" "${PACKAGE_DIR}/" 2>/dev/null || true

# Copy requirements
cp "${SCRIPT_DIR}/requirements.txt" "${PACKAGE_DIR}/scripts/" 2>/dev/null || true

# Create README
cat > "${PACKAGE_DIR}/README.md" << 'EOF'
# Ansible Automated Compliance (AAC) - Installer Package

## Quick Start

```bash
# 1. Extract the package
tar xzf aac-installer-*.tar.gz
cd aac-installer-*

# 2. Read the complete installation guide
less COMPLETE_INSTALLATION_GUIDE.md

# 3. Configure environment
cp environment.conf.example environment.conf
vim environment.conf

# 4. Clone the full repository
git clone https://github.com/ansible-automated-compliance/aac.git
cd compliance

# 5. Run installation
./scripts/install.sh

# 6. Verify installation
./scripts/verify_installation.sh
```

## What's Included

- `COMPLETE_INSTALLATION_GUIDE.md` - Step-by-step installation walkthrough
- `environment.conf.example` - Environment configuration template
- `scripts/install.sh` - Main installation script
- `scripts/verify_installation.sh` - Installation verification
- `scripts/requirements.txt` - Python dependencies

## Prerequisites

- RHEL 9+ with active Red Hat subscription
- Podman 5.x+
- Python 3.9+
- Git
- 16GB+ RAM, 100GB+ disk

## Support

- Repository: https://github.com/ansible-automated-compliance/aac
- Issues: https://github.com/ansible-automated-compliance/aac/issues

## Version

Package Version: 2.2
Created: $(date +%Y-%m-%d)
EOF

# Create quick install script
cat > "${PACKAGE_DIR}/quick-install.sh" << 'QUICKINSTALL'
#!/bin/bash
#
# AAC Quick Install Script
# This script performs a basic installation with prompts
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║     Ansible Automated Compliance - Quick Installer          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v podman &> /dev/null && ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: podman or docker is required${NC}"
    echo "Install with: sudo dnf install podman"
    exit 1
fi
echo "  ✓ Container runtime found"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is required${NC}"
    exit 1
fi
echo "  ✓ Python3 found"

if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is required${NC}"
    exit 1
fi
echo "  ✓ Git found"

echo ""

# Prompt for installation directory
read -p "Installation directory [$HOME/compliance]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-$HOME/compliance}

echo ""
echo -e "${YELLOW}Installing to: ${INSTALL_DIR}${NC}"
echo ""

# Clone repository
if [ -d "${INSTALL_DIR}" ]; then
    echo "Directory exists, updating..."
    cd "${INSTALL_DIR}"
    git pull
else
    echo "Cloning repository..."
    git clone https://github.com/ansible-automated-compliance/aac.git "${INSTALL_DIR}"
    cd "${INSTALL_DIR}"
fi

# Configure environment
if [ ! -f "environment.conf" ]; then
    cp environment.conf.example environment.conf
    echo -e "${YELLOW}Please edit environment.conf with your settings${NC}"
    echo "Press Enter to continue after editing, or Ctrl+C to exit"
    read
fi

source environment.conf

# Run installation
echo ""
echo -e "${YELLOW}Running installation script...${NC}"
./scripts/install.sh

# Verify
echo ""
echo -e "${YELLOW}Verifying installation...${NC}"
./scripts/verify_installation.sh

echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Configure your inventory: ${INSTALL_DIR}/ansible/inventory/hosts.yml"
echo "  2. Run a compliance assessment"
echo "  3. Access AAP at: https://$(hostname -f)"
echo ""
QUICKINSTALL

chmod +x "${PACKAGE_DIR}/quick-install.sh"

# Create the tarball
echo "  Creating archive..."
cd "${TEMP_DIR}"
tar czf "${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}-${DATE}.tar.gz" "${PACKAGE_NAME}-${VERSION}"

# Create checksum
cd "${OUTPUT_DIR}"
sha256sum "${PACKAGE_NAME}-${VERSION}-${DATE}.tar.gz" > "${PACKAGE_NAME}-${VERSION}-${DATE}.tar.gz.sha256"

# Cleanup
rm -rf "${TEMP_DIR}"

# Summary
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    Package Created!                         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Files created:"
echo "  ${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}-${DATE}.tar.gz"
echo "  ${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}-${DATE}.tar.gz.sha256"
echo ""
echo "Package contents:"
echo "  - COMPLETE_INSTALLATION_GUIDE.md (step-by-step walkthrough)"
echo "  - README.md (quick start)"
echo "  - quick-install.sh (automated installer)"
echo "  - environment.conf.example (configuration template)"
echo "  - scripts/ (installation scripts)"
echo ""
echo "To distribute:"
echo "  Upload both files to your distribution point"
echo ""
echo "To install:"
echo "  tar xzf ${PACKAGE_NAME}-${VERSION}-${DATE}.tar.gz"
echo "  cd ${PACKAGE_NAME}-${VERSION}"
echo "  ./quick-install.sh"
echo ""
