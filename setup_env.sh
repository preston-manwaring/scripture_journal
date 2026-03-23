#!/bin/bash
# Setup script for scripture_journal conda environment

echo "Setting up scripture_journal conda environment..."

# Remove existing environment if it exists
conda env remove -n scripture_journal -y 2>/dev/null || true

# Create new environment from environment.yml
conda env create -f environment.yml

echo ""
echo "Environment created successfully!"
echo ""
echo "To activate the environment, run:"
echo "  conda activate scripture_journal"
echo ""
echo "To run the application:"
echo "  conda activate scripture_journal"
echo "  python app.py"
