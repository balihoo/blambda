from __future__ import print_function
import boto3
from botocore.exceptions import ClientError
import json
import tempfile
import shutil
import argparse
import os
import errno
import sys

from subprocess import (
    call,
    check_output,
    Popen,
    PIPE,
    CalledProcessError
)

from . import config

from .utils.base import pGreen, pRed, pBlue, pMagenta, spawn, timed
from .utils.vpc import VpcInfo
from .utils.iam import role_policy_upsert

from .utils.findfunc import (
    all_manifests,
    find_manifest,
    split_path,
    all_remote_functions
)

clients = None
class Clients(object):
    def __init__(self):
        self.cfg = config.load()
        self.region = self.cfg.get('region', 'us-east-1')
        self.events_client = boto3.client('events', region_name=self.region)
        self.lambda_client = boto3.client('lambda', region_name=self.region)
        self.iam_client = boto3.client('iam', region_name=self.region)

def js_name(coffee_file):
    """ return the name of the provided file with the extension replaced by 'js'
    Args:
        coffee_file (str): name of a file to replace the extension of
    """
    return "{}.js".format(os.path.splitext(coffee_file)[0])

def coffee_compile(coffee_file):
    """ compile a coffee file and return the compiled file's name
    Args:
        coffee_file (str): name of a file to compile
    """
    command = "coffee -bc {}".format(coffee_file)
    (r,s,e) = spawn(command, show=True)
    return js_name(coffee_file)

def copy_with_dir(src, dst):
    """ copies a file to a destination path, creating the path if it does not exist
    Args:
        src (str): path to the file to copy
        dst (str): path to the file to copy to
    """
    try:
        (path, name) = os.path.split(dst)
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
    shutil.copyfile(src, dst)

def package(manifest_filename, dryrun=False):
    """ create an archive containing source files and deps for lambda
    Args:
        manifest_filename (str): path to the manifest file
        dryrun (bool): indicates that you're testing, and leaves the tmp dir for inspection
    """
    (basedir, fname, ext) = split_path(manifest_filename)
    options = {
        "Timeout": 30,
        "MemorySize": 128,
        "Description": "Fulfillment Function",
        "Runtime": "python2.7",
        "Handler": "{}.lambda_handler".format(fname),
    }
    manifest = {}
    with open(manifest_filename) as f:
        manifest = json.load(f)
    tmpdir = tempfile.mkdtemp()
    for command in manifest.get('before deploy', []):
        spawn("{} {}".format(command, tmpdir), show=True, workingDirectory=basedir)

    libdir = os.path.join(basedir, "lib")
    moddir = os.path.join(basedir, "node_modules")
    if os.path.isdir(libdir):
        call(" ".join(("cp", "-r", os.path.join(libdir, "*"), tmpdir)), shell=True)
    elif os.path.isdir(moddir):
        shutil.copytree(moddir, os.path.join(tmpdir, "node_modules"))
        os.mkdir(os.path.join(tmpdir, fname))
        options.update({
            "Handler": "{0}/{0}.handler".format(fname),
            "Runtime": "nodejs"
        })
    elif len(manifest.get('dependencies', {})) > 0:
        print(pRed("WARNING! dependencies defined, but no dependency directory found."))
        print("  --> Be sure to run setup_libs prior to deploying\n")

    for filename in manifest.get('source files', []):
        srcname = dstname = filename
        if type(filename) == list:
            (srcname, dstname) = tuple(filename)

        src = os.path.abspath(os.path.join(basedir, srcname))
        if src.endswith(".coffee"):
            compiled = coffee_compile(src)
            dst = os.path.abspath(os.path.join(tmpdir, fname, js_name(dstname)))
            copy_with_dir(compiled, dst)
            os.remove(compiled)
        else:
            dst = os.path.join(tmpdir, dstname)
            copy_with_dir(src,dst)
    if 'options' in manifest:
        options.update(manifest['options'])
    manifest['options'] = options
    for command in manifest.get('after deploy', []):
        spawn("{} {}".format(command, tmpdir), show=True, workingDirectory=basedir)
    archive = shutil.make_archive(fname, "zip", tmpdir)
    shutil.rmtree(tmpdir) if not dryrun else print(pRed("DRYRUN!! -- TEMPDIR: " + tmpdir))
    return archive, manifest

def git_sha():
    """ get the current sha """
    try:
        return check_output(["git", "rev-parse", "--short", "HEAD"]).strip()
    except CalledProcessError:
        return "no git sha"

def git_local_mods():
    """ return the number of modified, added or deleted files beyond last commit """
    try:
        changes = check_output(["git", "status", "-suno"]).strip().split('\n')
        return len([c for c in changes if len(c.strip()) > 0])
    except CalledProcessError:
        return 0

def setup_schedule(fname, farn, role, schedule, dryrun):
    events_client = clients.events_client
    lambda_client = clients.lambda_client

    #cleanup
    rules = events_client.list_rule_names_by_target(TargetArn=farn)['RuleNames']
    for rule in rules:
        targets = events_client.list_targets_by_rule(Rule=rule)['Targets']
        if targets:
            print("removing target {} from {}".format(fname, rule))
            thisid = next(t['Id'] for t in targets if t['Arn'] == farn)
            if not dryrun:
                events_client.remove_targets(Rule=rule, Ids=[thisid])
        if len(targets) <= 1:
            print("removing {}".format(rule))
            if not dryrun:
                events_client.delete_rule(Name=rule)
    #(re)create
    rule_name = schedule['name'] if 'name' in schedule else "{}_trigger".format(fname)
    rate_or_cron = "rate" if "rate" in schedule else "cron"
    expression = schedule[rate_or_cron]
    #you cannot add this target to an existing rule with this (at this time)
    print("adding rule {}".format(rule_name))
    if not dryrun:
        rule_arn = events_client.put_rule(
            Name=rule_name,
            ScheduleExpression="{}({})".format(rate_or_cron, expression),
            State="ENABLED",
            Description="Trigger for Fulfillment Lambda function {}".format(fname),
            RoleArn=role
        )['RuleArn']

    target_name = "{}_target".format(rule_name)
    print("adding target {}".format(target_name))

    if not dryrun:
        events_client.put_targets(
            Rule=rule_name,
            Targets=[{
                'Id': target_name,
                'Arn': farn,
                'Input': json.dumps(schedule.get('input', {}))
            }]
        )

    print("adding permissions")
    if not dryrun:
        try:
            lambda_client.add_permission(
                FunctionName=fname,
                StatementId='Allow-scheduled-events',
                Action='lambda:InvokeFunction',
                Principal='events.amazonaws.com',
                SourceArn=rule_arn,
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceConflictException':
                print("permissions already existed")
            else:
                raise

def get_vpc_config(vpcid=None):
    """ retrieves VPC information for a given vpc id or the first one found
    for the configured region and environment. Returns it as a configuration
    that can be provided to Lambda.
    """
    vpc_info = VpcInfo(
        clients.region,
        clients.cfg.get('environment', 'dev'),
        vpcid
    )
    return {
        'SubnetIds': vpc_info.dmz_subnets,
        'SecurityGroupIds': vpc_info.security_groups
    }

def publish(name, role, zipfile, options, dryrun):
    """ publish a AWS Lambda function
    Args:
        name (str): name of the lambda function
        role (str): arn of the role to use
        zipfile (str): the archive containing function code
        options (dict): AWS Lambda configuration options
        returns the arn of the new or updated function
    """
    client = clients.lambda_client

    sha = git_sha()
    mods = "!" * git_local_mods()
    description = options.get("Description", "")
    options['Description'] = "{} [SHA {}{}]".format(description, sha, mods)
    if not 'Role' in options:
        options['Role'] = role

    file_bytes = None
    response = None
    with open(zipfile, 'rb') as f:
        file_bytes = f.read()
        print("Function Package: {} bytes".format(len(file_bytes)))
    if not dryrun:
        try:
            response = client.update_function_code(
                FunctionName=name,
                ZipFile=file_bytes
            )
            response = client.update_function_configuration(
                FunctionName=name,
                **options
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                response = client.create_function(
                    FunctionName=name,
                    Code={'ZipFile': file_bytes},
                    **options
                )
            else:
                raise e
        return (response['FunctionName'], response['FunctionArn'])
    return (name, "DRYRUN")

def deploy(function_names, env, prefix, role_arn, dryrun=False):
    """ deploys one or more functions to lambda
    Args:
        function_names (list(str)): list of function names
        env (str): the environment to deploy to
        prefix (srt): string to prefix the function name with
        role (str): the role to use for the function
        dryrun (bool): prevents AWS publish and retains tmpdir / zipfile
    """
    deployed = []

    for fname in function_names:
        with timed("find manifest"):
            name = find_manifest(fname)
        if name:
            print("Deploying function '{}'...".format(fname))
            group = os.path.basename(os.path.dirname(name))
            (zipfile, manifest) = package(name, dryrun)
            (basedir, basename, ext) = split_path(zipfile)
            # If the function name doesn't match it's parent folder, let's include the folder name
            # as part of the function name.. so timezone/timezone -> timezone and adwords/textad -> adwords_textad
            whole_name = basename
            if not basename.startswith(group):
                whole_name = "{}_{}".format(group, basename)
            function_name = "{}_{}_{}".format(prefix.lower(), whole_name, env.lower())

            #VPC setup
            vpcid = manifest.get('options', {}).get('VpcConfig', {}).get('VpcId')
            if  vpcid:
                #this is not a valid option for boto, but it should be
                del manifest['options']['VpcConfig']['VpcId']
                with timed("get vpc by id"):
                    manifest['options']['VpcConfig'] = get_vpc_config(vpcid)
            elif manifest.get('vpc', False):
                with timed("get vpc without id"):
                    manifest['options']['VpcConfig'] = get_vpc_config()

            #Role setup
            if not role_arn:
                if 'permissions' in manifest:
                    with timed("setup role"):
                        role_arn = role_policy_upsert(function_name, manifest['permissions'], dryrun)
                    if not role_arn:
                        role_arn = clients.cfg.get('role')
                        print(pRed("Setting permissions failed. Defaulting to {}".format(role_arn)))
                    else:
                        print(pGreen("Specific permissions set with role: {}".format(role_arn)))
                else:
                    role_arn = clients.cfg.get('role')
                    print(pMagenta("no explicit role arn found, defaulting to {}".format(role_arn)))
            else:
                print(pMagenta("Explicit role arn found: {}".format(role_arn)))

            if role_arn:
                #Publishing
                with timed("publish"):
                    (fullname, arn) = publish(function_name, role_arn, zipfile, manifest['options'], dryrun)
                os.remove(zipfile)

                #Schedule setup
                if 'schedule' in manifest:
                    with timed("schedule setup"):
                        setup_schedule(fullname, arn, role_arn, manifest['schedule'], dryrun)

                deployed.append(fname)
                print("Success!\n")
            else:
                print(pRed("No role to default to, deploy cancelled. Use blambda config role <some role> to set a default"))
        else:
            print(pYellow("*** WARNING: unable to find {} ***\n".format(fname)))
    return set(deployed)

def main(args=None):
    """ main function for the deployment script.
        Parses args, calls deploy, outputs success or failure
    """
    global clients
    clients = Clients()
    parser = argparse.ArgumentParser("package and deploy lambda functions")
    parser.add_argument('function_names', nargs='*', type=str, help='the base name of the function')
    parser.add_argument('--prefix', type=str, help='the prefix for the function', default=clients.cfg.get('application', ''))
    parser.add_argument('--env', type=str, help='the environment this function will run in', default=clients.cfg.get('environment', ''))
    parser.add_argument('--role', type=str, help='the arn of the IAM role to apply', default=None)
    parser.add_argument('--file', type=str, help='filename containing function names')
    parser.add_argument('--dryrun', help='do not actually send anything to lambda', action='store_true')

    args = parser.parse_args(args)

    fnames = args.function_names
    if args.file:
        with open(args.file) as f:
            fnames += [l.strip() for l in f.readlines()]
        print("read {} from {}".format(fnames, args.file))

    fnames = set(fnames)
    if len(fnames) < 1:
        print(pRed("NO PACKAGE PROVIDED"))
        print(pBlue("Choose one of the following:"))
        print("  " + "\n  ".join(all_manifests(".")))
        sys.exit(-1)

    deployed = deploy(fnames, args.env, args.prefix, args.role, args.dryrun)
    if deployed != fnames:
        not_deployed = fnames - deployed
        if len(deployed) > 0:
            print(pBlue("deployed " + ", ".join(map(str, deployed))))
        print(pRed("FAILED TO DEPLOY " + ", ".join(map(str, not_deployed))))
        sys.exit(len(not_deployed))
    print(pGreen("Successfully deployed " + ", ".join(map(str, deployed))))

if __name__ == '__main__':
    main()
