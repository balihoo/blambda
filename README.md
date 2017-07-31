# blambda
Balihoo Lambda deploy tools

## Requirements

1. Install pyenv

pyenv is used to manage multiple python versions, detailed instructions
are [here](https://github.com/pyenv/pyenv-installer#github-way-recommended)

```bash
curl -L https://raw.githubusercontent.com/pyenv/pyenv-installer/master/bin/pyenv-installer | bash
```

Then add the following to your `~/.bashrc`

```bash
export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
```

If you have build issues, see [pyenv help](https://github.com/pyenv/pyenv/wiki/Common-build-problems), 
e.g. I needed to install:

```bash
sudo apt-get install libbz2-dev
```

## installation
```
pyenv install -s 3.6.1 && pyenv shell 3.6.1   # install blambda to a 3.6.1 environment 
pip install git+https://github.com/balihoo/blambda.git
```

## configuration
First, make sure your AWS credentials are set up
Then configure at least these two variables:
```
blambda config set_global region us-east-1
blambda config set_global role 'arn:aws:iam::etcetera'
```
these will be set in `~/.config/blambda/config.json`
you can also set the variables 'application' and 'environment' which will automatically be prepended and appended to your function name. `my_function` would turn into `myapp_my_function_myenv` for example.

you can override these variables locally with
```
blambda config set_local region us-west-2
```
this will be set in `./.blambda/config.json`
when config values are loaded by blambda, it first loads the global file and then overrides any values with the config from the current directory.

you can see the value of variables with:
```
blambda config get <variable name>
blambda config get all
```

variables can be unset by omitting the value:
```
blambda config set_local application
```

## create a new AWS Lambda function:
`blambda new new_thing`
will get you a directory called 'new_thing' containing new_thing.py and new_thing.json
you can provide`--runtime coffee` to create a new coffee script function.

The json file is your manifest, which can look like:
```
{
    "blambda": "manifest",
    "dependencies": {
        "tldextract": "2.0.1"
    },
    "options": {
        "Description": "test_thing",
        "Runtime": "python2.7",
        "Timeout": 300
    },
    "permissions": [
      {
          "Effect": "Allow",
          "Action": "route53:ChangeResourceRecordSets",
          "Resource": "arn:aws:route53:::hostedzone/SAKJHAUHIS"
      },
      { "logs:DescribeLogStreams": "arn:aws:logs:*:*:log-group:/aws/lambda:*" }
    ],
    "schedule": {
        "input": { "things": "stuff" },
        "rate": "1 minute"
    },
    "source files": [
        "test_thing.py",
        "my_other_file.py"
    ]
}
```

you can add dependencies with an explicit version, and permissions as IAM statements
source files can be relative paths, and can be a tuple with (local, remote) name, so you can pull in shared files

## setting up your deps
before deploying, your dependencies need to be installed. This is a separate step because you do not need to do this as often.
```
blambda deps new_thing
```

## deploying your function
Deploy sets up your lambda function as well as any IAM roles, CloudWatch Events schedules etc.
```
blambda deploy test_thing
```

## running your function on AWS lambda
You can run your function right from the commandline
```
blambda exec test_thing
```
will take a json payload from stdin, so
```
cat payload.json | blambda exec test_thing
```
will send the contents of `payload.json` to the deployed test_thing lambda function
```
blambda exec test_thing --payload '{ "my": "payload"}'
```
will do the same as:
```
echo '{ "my": "payload"}' | blambda exec test_thing --payload
```

## running your function locally

You can run the local code with `blambda local`.

```bash
blambda local test_thing
cat payload.json | blambda local test_thing
blambda local test_thing --payload payload.json
echo '{ "my": "payload"}' | blambda local test_thing --payload
```

You can also run unittests using `blambda test`.  The following
will run the unittests for each function, including the proper
`lib_*` directory for the corresponding unittest.
 
```bash
blambda test appnexus/target appnexus/brand hash
```

Note that `blambda test` requires that your unittest file be named
`test_<function_name>.py`.

## intellij help

Running `blambda ide` will add a function's parent and lib_ 
directories as source folders by rewriting the iml file:

```bash
blambda ide <function_name>
```

This should fix any indexing/import issues intellij has for a 
given lambda function -- you'll need to run this every time
you switch functions and work on a different one.


## Seeing the logs
```
blambda logs new_thing
```
will get you the cloudwatch log messages (== function stdout) from your function for recent executions. logs has many options, that you can see with `blambda logs --help`. In short, you can specify different output formattings, summary and date/time range

## stale functions
Sometimes, you forget what is deployed in lambda and how far out of date it is with your current repo.
Blambda can help you with this by asking it to check for 'stale' functions:
```
blambda stale
```
will tell you which functions are out of date compared to the current repo HEAD.
Supplying the -v (verbose) option will also tell you which files are out of date.


## Developing blambda

To set up the development environment, install pyenv using the instructions above,
then run

```bash
./ve_setup.sh
```