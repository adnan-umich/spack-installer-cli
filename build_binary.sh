#!/bin/bash
# build_binary.sh - Script to build the spack-installer binary

set -e  # Exit on error

# Make sure we're in the project root
cd "$(dirname "$0")"

echo "Building spack-installer binary..."
echo "-------------------------------------"

# Create the virtual environment if it doesn't exist
if [ ! -d "build_venv" ]; then
    echo "Creating virtual environment for build..."
    python3 -m venv build_venv
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source build_venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -e .
pip install pyinstaller

# Build the binary
echo "Building binary with PyInstaller..."
pyinstaller spack-installer.spec --clean

# Check the result
if [ -f "dist/spack-installer" ]; then
    echo "-------------------------------------"
    echo "Build successful! Binary created at:"
    echo "$(pwd)/dist/spack-installer"
    
    # Copy to a convenient location if specified
    if [ -n "$1" ]; then
        DEST="$1"
        echo "Copying binary to $DEST..."
        cp "dist/spack-installer" "$DEST"
        echo "Binary copied to $DEST"
    fi
    
    echo "You can now run it with:"
    echo "./dist/spack-installer --help"
else
    echo "Build failed. Check the error messages above."
    exit 1
fi

# Deactivate virtual environment
deactivate
