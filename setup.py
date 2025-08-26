from setuptools import setup, find_packages

setup(
    name='ifixit-api-client',
    version='0.1.0',
    description='A Python client for the iFixit API v2.0',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Julian Brünn',
    author_email='julianbruenncontact@gmail.com',
    url='https://github.com/NoJokeFNA/ifixit-api-client',
    py_modules=['ifixit_api_client'],
    install_requires=[
        'requests',
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
