#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_OWNER="xiefenga"
REPO_NAME="selgetabel"
BRANCH="main"
TARGET_DIR="docker"
EXCLUDED_FILES=("scripts" "docker-compose.build.yml" "docker-compose.dev.yml")

# Print functions
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check dependencies
check_dependencies() {
    print_info "Checking dependencies..."

    if ! command_exists curl; then
        print_error "curl is not installed. Please install curl first."
        exit 1
    fi

    if ! command_exists tar; then
        print_error "tar is not installed. Please install tar first."
        exit 1
    fi

    print_success "All dependencies are installed."
}

# Download and extract docker directory
download_docker_dir() {
    print_info "Downloading Selgetabel deployment files from GitHub..."

    local temp_dir=$(mktemp -d)
    local tarball_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/${BRANCH}.tar.gz"

    # Download tarball
    if ! curl -fsSL "$tarball_url" -o "${temp_dir}/repo.tar.gz"; then
        print_error "Failed to download repository from ${tarball_url}"
        rm -rf "$temp_dir"
        exit 1
    fi

    print_info "Extracting files..."

    # Extract docker directory
    tar -xzf "${temp_dir}/repo.tar.gz" -C "$temp_dir"

    local extracted_dir="${temp_dir}/${REPO_NAME}-${BRANCH}"
    local source_docker_dir="${extracted_dir}/${TARGET_DIR}"

    if [ ! -d "$source_docker_dir" ]; then
        print_error "Docker directory not found in repository"
        rm -rf "$temp_dir"
        exit 1
    fi

    # Check if any files from docker directory already exist
    local has_conflicts=false
    # Enable dotglob to match hidden files
    shopt -s dotglob
    for item in "${source_docker_dir}"/*; do
        local basename=$(basename "$item")
        # Skip excluded files
        local is_excluded=false
        for excluded in "${EXCLUDED_FILES[@]}"; do
            if [ "$basename" = "$excluded" ]; then
                is_excluded=true
                break
            fi
        done

        if [ "$is_excluded" = true ]; then
            continue
        fi

        if [ -e "./${basename}" ]; then
            has_conflicts=true
            break
        fi
    done
    shopt -u dotglob

    if [ "$has_conflicts" = true ]; then
        print_warning "Some files from docker directory already exist in current directory."
        read -p "Do you want to overwrite them? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Installation cancelled."
            rm -rf "$temp_dir"
            exit 0
        fi
    fi

    # Copy docker directory contents to current directory
    print_info "Copying files to current directory..."
    # Enable dotglob to match hidden files
    shopt -s dotglob
    for item in "${source_docker_dir}"/*; do
        local basename=$(basename "$item")

        # Skip excluded files
        local is_excluded=false
        for excluded in "${EXCLUDED_FILES[@]}"; do
            if [ "$basename" = "$excluded" ]; then
                is_excluded=true
                print_info "Skipped: ${excluded}"
                break
            fi
        done

        if [ "$is_excluded" = false ]; then
            cp -r "$item" "./"
            print_info "Copied: ${basename}"
        fi
    done
    shopt -u dotglob

    # Cleanup
    rm -rf "$temp_dir"

    print_success "Deployment files downloaded successfully!"
}

# Setup environment file
setup_env() {
    if [ -f "./.env.example" ]; then
        if [ ! -f "./.env" ]; then
            print_info "Creating .env file from .env.example..."
            mv "./.env.example" "./.env"
            print_warning "Please edit .env to configure your environment variables."
        else
            print_info ".env file already exists, skipping..."
        fi
    fi
}

# Print next steps
print_next_steps() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Installation completed successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}Next steps:${NC}"
    echo ""
    echo "1. Configure environment variables:"
    echo -e "   ${YELLOW}vi .env${NC}"
    echo ""
    echo "2. update environment variables:"
    echo "   - OPENAI_BASE_URL"
    echo "   - OPENAI_MODEL"
    echo "   - OPENAI_API_KEY (if use ollama, do not edit this variable)"
    echo "   - JWT_SECRET_KEY (use openssl rand -hex 32 to generate)"
    echo ""
    echo "3. Start the application:"
    echo -e "   ${YELLOW}docker compose up -d${NC}"
    echo ""
    echo "4. Access the application:"
    echo "   - Web UI: http://localhost:8080"
    echo "   - API: http://localhost:8080/api"
    echo "   - MinIO Console: http://localhost:9001"
    echo ""
    echo "For more information, visit:"
    echo "https://github.com/${REPO_OWNER}/${REPO_NAME}"
    echo ""
}

# Main function
main() {
    echo ""
    echo -e "${BLUE}======================================${NC}"
    echo -e "${BLUE}  Selgetabel Quick Installation${NC}"
    echo -e "${BLUE}======================================${NC}"
    echo ""

    check_dependencies
    download_docker_dir
    setup_env
    print_next_steps
}

# Run main function
main
