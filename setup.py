import sys
import os
from setuptools import setup

setup(
    name='bciserver',
    version='0.1',
    description='Generic server for creating brain-computer interfaces.',
    author='Marijn van Vliet',
    author_email='marijn.vanvliet@med.kuleuven.be',
    license='closed',
    packages=['bciserver', 'bciserver.classifiers', 'bciserver.eegdevices'],
    entry_points=dict(console_scripts=['bciserver=bciserver:main']),
    data_files = [('', ['inpout32.dll'])],
    install_requires=[
        'cvxopt',
        'numpy',
        'scipy',
        'matplotlib',
        'argparse',
        'pywin32',
        'pyserial',
        'ctypes',
        'wmi',
    ]
)
