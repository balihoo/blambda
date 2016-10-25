# blambda
Balihoo Lambda deploy tools

## installation
```
pip install git+https://github.com/balihoo-gens/blambda.git
```

## configuration
First, make sure your AWS credentials are set up
Then configure at least these two variables:
```
blambda config region us-east-1
blambda config role 'arn:aws:iam::etcetera'
```
you can also set the variables 'application' and 'environment' which will automatically be prepended and appended to your function name. `my_function` would turn into `myapp_my_function_myenv` for example.

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
      }
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

For Python, you can choose to have them installed in/with whatever python environment you are in, or to set up an AWS Lambda equivalent 2.7 environment specifically for your function. The latter is convenient for local testing to avoid missing dependencies
```
blambda deps new_thing --ve
```


## deploying your function
Deploy sets up your lambda function as well as any IAM roles, CloudWatch Events schedules etc.
```
blambda deploy test_thing
```

## running your function
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


