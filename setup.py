from setuptools import setup

setup(name='blambda',
      version='0.1.0',
      description='Balihoo Command Line Tools for AWS Lambda function management',
      install_requires=['boto3']
      packages=['blambda'],
      entry_points={
          'console_scripts': [
              'blambda = blambda.main:main',
          ]
      },
)
