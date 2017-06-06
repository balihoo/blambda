from setuptools import setup, find_packages

setup(name='blambda',
      version='0.2.1',
      description='Balihoo Command Line Tools for AWS Lambda function management',
      author='Gerry Ens',
      author_email='gens@balihoo.com',
      license='MIT',
      url='git@github.com:balihoo/fulfillment-lambda-functions.git',
      install_requires=['boto3', 'python-dateutil', 'requests', 'termcolor'],
      packages=find_packages(exclude=['tests']),
      include_package_data=True,
      entry_points={
          'console_scripts': [
              'blambda = blambda.__main__:main',
          ]
      },
)
