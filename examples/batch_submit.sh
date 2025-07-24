#!/bin/bash

# Example shell script for batch job submission

echo "=== Batch Job Submission Example ==="

# Submit a series of scientific packages with dependencies
echo "Submitting scientific computing stack..."

# Base packages
spack-installer submit gcc --priority high --estimated-time 900
spack-installer submit cmake --priority high --dependencies gcc --estimated-time 180
spack-installer submit python --priority high --estimated-time 300

# Scientific libraries
spack-installer submit openmpi --priority medium --dependencies gcc --estimated-time 600
spack-installer submit hdf5 --priority medium --dependencies gcc --estimated-time 240
spack-installer submit netcdf-c --priority medium --dependencies gcc,hdf5 --estimated-time 180

# Python packages
spack-installer submit py-numpy --priority medium --dependencies python --estimated-time 240
spack-installer submit py-scipy --priority medium --dependencies python,py-numpy --estimated-time 300
spack-installer submit py-matplotlib --priority low --dependencies python,py-numpy --estimated-time 360

# Specialized tools
spack-installer submit paraview --priority low --dependencies gcc,cmake,python,openmpi --estimated-time 1800
spack-installer submit visit --priority low --dependencies gcc,cmake,python,hdf5 --estimated-time 2400

echo ""
echo "Jobs submitted! Check status with:"
echo "  spack-installer status"
echo ""
echo "Start processing with:"
echo "  spack-installer worker start"
