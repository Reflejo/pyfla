from setuptools import setup, find_packages
import sys, os

version = '0.1a'
setup(name='pyfla', version=version, packages=find_packages(),
      zip_safe=False, description="pyFLA", include_package_data=True,
      keywords='flash')
