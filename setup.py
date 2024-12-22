import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='flo-ai',
    version='0.0.5-dev4',
    author='Rootflo',
    description='Create composable AI agents',
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=setuptools.find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.10',
    py_modules=['flo'],
    package_dir={'': 'flo'},
    install_requires=[],
)
