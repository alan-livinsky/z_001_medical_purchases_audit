#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import find_packages, setup


setup(
    name='z_001_medical_purchases_audit',
    version='0.1',
    description='GNU Health Medical Purchases Audit Draft Workflow',
    author='Custom Health Team',
    author_email='health@example.com',
    url='https://www.gnuhealth.org',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'gnuhealth',
        'trytond',
    ],
    entry_points={
        'trytond.modules': [
            'z_001_medical_purchases_audit = z_001_medical_purchases_audit',
        ],
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Plugins',
        'Intended Audience :: Healthcare Industry',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Natural Language :: Spanish',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Topic :: Office/Business',
    ],
)
