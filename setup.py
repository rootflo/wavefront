import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="flo-ai",                          # This is the name of the package
    version="0.0.3",                        # The initial release version
    author="Vishnu Satis",                  # Full name of the author
    description="Create composable AI agents",
    long_description=long_description,      # Long description read from the the readme file
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),    # List of all python modules to be installed
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],                                      # Information to filter the project on PyPi website
    python_requires='>=3.10',               # Minimum version requirement of the package
    py_modules=["flo"],                     # Name of the python package
    package_dir={'':'flo'},                 # Directory of the source code of the package
    install_requires=[]                     # Install other dependencies if any
)