from setuptools import setup, find_packages

setup(name='blambda',
      version='0.1.0',
      description='Balihoo Command Line Tools for AWS Lambda function management',
      author='Gerry Ens',
      author_email='gens@balihoo.com',
      license='MIT',
      url='git@github.com:balihoo/fulfillment-lambda-functions.git',
      install_requires=['boto3', 'python-dateutil', 'futures', 'requests'],
      packages=find_packages(exclude=['tests']),
      package_data={'': ['mkve/*']},
      entry_points={
          'console_scripts': [
              'blambda = blambda.__main__:main',
          ]
      },
)
