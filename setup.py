from setuptools import setup, find_packages

setup(name='blambda',
      version='0.1.0',
      description='Balihoo Command Line Tools for AWS Lambda function management',
      install_requires=['boto3'],
      packages=find_packages(exclude=['tests']),
      package_data={'': ['mkve/*']},
      entry_points={
          'console_scripts': [
              'blambda = blambda.__main__:main',
          ]
      },
)
