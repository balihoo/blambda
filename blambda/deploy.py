from __future__ import print_function

import argparse
import errno
import glob
import json
import shutil
import sys
import tempfile
from subprocess import (
    call,
    CalledProcessError
)

import boto3
import os
from botocore.exceptions import ClientError
from termcolor import cprint

from . import config
from .utils.base import spawn, timed
from .utils.findfunc import (
    all_manifests,
    find_manifest,
    split_path
)
from .utils.iam import role_policy_upsert
from .utils.lambda_manifest import LambdaManifest
from .utils.vpc import VpcInfo

clients = None


class Clients(object):
    def __init__(self):
        self.cfg = config.load()
        self.region = self.cfg.get('region', 'us-east-1')
        self.events_client = boto3.client('events', region_name=self.region)
        self.lambda_client = boto3.client('lambda', region_name=self.region)


def js_name(coffee_file):
    """ return the name of the provided file with the extension replaced by 'js'
    Args:
        coffee_file (str): name of a file to replace the extension of
    """
    return "{}.js".format(os.path.splitext(coffee_file)[0])


def coffee_compile(coffee_file, basedir):
    """ compile a coffee file and return the compiled file's name
    Args:
        coffee_file (str): name of a file to compile
    """
    compiler = os.path.join(basedir, "node_modules", "coffee-script", "bin", "coffee")
    command = "{} -bc {}".format(compiler, coffee_file)
    spawn(command, show=True)
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

    # todo: clean this up -- some shared logic was moved to LambdaManifest but this isn't complete
    lambda_manifest = LambdaManifest(manifest_filename)

    basedir = lambda_manifest.basedir
    fname = lambda_manifest.function_name
    manifest = lambda_manifest.manifest

    # default options
    options = {
        "Timeout": 30,
        "MemorySize": 128,
        "Description": "Fulfillment Function",
        "Runtime": "python2.7",
        "Handler": "{}.lambda_handler".format(fname),
    }

    tmpdir = tempfile.mkdtemp()
    for command in manifest.get('before deploy', []):
        (ret, out, err) = spawn("{} {}".format(command, tmpdir), show=True, working_directory=basedir)
        print('\n'.join(out + err))

    # default runtime is python2.7
    if 'python' in lambda_manifest.runtime:
        if not os.path.exists(lambda_manifest.lib_dir) and manifest.get('dependencies', {}):
            raise RuntimeError("Dependencies defined but no dependency directory found.  Please run 'blambda deps'")

        call(" ".join(("cp", "-r", os.path.join(lambda_manifest.lib_dir, "*"), tmpdir)), shell=True)

    elif 'nodejs' in lambda_manifest.runtime:
        moddir = os.path.join(basedir, "node_modules")

        if not os.path.exists(moddir) and manifest.get('dependencies', {}):
            raise RuntimeError("Dependencies defined but no dependency directory found.  Please run 'blambda deps'")

        shutil.copytree(moddir, os.path.join(tmpdir, "node_modules"))
        os.mkdir(os.path.join(tmpdir, fname))
        options.update({
            "Handler": "{0}/{0}.handler".format(fname),
            "Runtime": "nodejs"
        })

    else:
        raise RuntimeError("Unknown runtime " + lambda_manifest.runtime)

    def copy_source_file(source, destination_name):
        for src in glob.glob(source):
            if src.endswith(".coffee"):
                compiled = coffee_compile(src, basedir)
                dst = os.path.abspath(os.path.join(tmpdir, fname, js_name(destination_name)))
                copy_with_dir(compiled, dst)
                os.remove(compiled)
            else:
                dst = os.path.join(tmpdir, destination_name)
                copy_with_dir(src, dst)

    for filename in manifest.get('source files', []):
        srcname = dstname = filename
        if type(filename) == list:
            (srcname, dstname) = tuple(filename)

        src = os.path.abspath(os.path.join(basedir, srcname))
        files = glob.glob(src)
        if len(files) == 1:
            copy_source_file(files[0], dstname)
        elif len(files) > 1:
            for f in files:
                base_src = os.path.basename(f)
                (dest_dir, _) = os.path.split(dstname)
                destination = os.path.join(dest_dir, base_src)
                copy_source_file(f, destination)

    if 'options' in manifest:
        options.update(manifest['options'])

    manifest['options'] = options

    for command in manifest.get('after deploy', []):
        (ret, out, err) = spawn("{} {}".format(command, tmpdir), show=True, working_directory=basedir)
        print('\n'.join(out + err))

    archive = shutil.make_archive(fname, "zip", tmpdir)
    shutil.rmtree(tmpdir) if not dryrun else cprint("DRYRUN!! -- TEMPDIR: " + tmpdir, 'red')

    return archive, manifest


def git_sha():
    """ get the current sha """
    try:
        (ret, out, err) = spawn("git rev-parse --short HEAD", show=True)
        if ret == 0:
            return out[0]
        return ' '.join(err)
    except CalledProcessError:
        return "no git sha"


def git_local_mods():
    """ return the number of modified, added or deleted files beyond last commit """
    try:
        (ret, out, err) = spawn("git status -suno", show=True)
        if ret == 0:
            return len([c for c in out if len(c.strip()) > 0])
        cprint(' '.join(err), 'red')
        return 0
    except CalledProcessError:
        return 0


def setup_schedule(fname, farn, role, schedule, dryrun):
    events_client = clients.events_client
    lambda_client = clients.lambda_client

    # cleanup
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
    # (re)create
    rule_name = schedule['name'] if 'name' in schedule else "{}_trigger".format(fname)
    rate_or_cron = "rate" if "rate" in schedule else "cron"
    expression = schedule[rate_or_cron]
    # you cannot add this target to an existing rule with this (at this time)
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

    with open(zipfile, 'rb') as f:
        file_bytes = f.read()
        print("Function Package: {} bytes".format(len(file_bytes)))
    if not dryrun:
        try:
            cprint("Updating lambda function code", 'yellow')
            response = client.update_function_code(
                FunctionName=name,
                ZipFile=file_bytes
            )
            cprint("Updating lambda function configuration", 'yellow')
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
        return response['FunctionName'], response['FunctionArn']
    return name, "DRYRUN"


def deploy(function_names, env, prefix, override_role_arn, account, dryrun=False):
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

            # VPC setup
            vpcid = manifest.get('options', {}).get('VpcConfig', {}).get('VpcId')
            vpc = manifest.get('vpc', False)
            if vpcid:
                # this is not a valid option for boto, but it should be
                del manifest['options']['VpcConfig']['VpcId']
                with timed("get vpc by id"):
                    manifest['options']['VpcConfig'] = get_vpc_config(vpcid)
            elif vpc:
                with timed("get vpc without id"):
                    manifest['options']['VpcConfig'] = get_vpc_config()

            # Role setup
            role_arn = override_role_arn
            if not role_arn:
                if 'permissions' in manifest:
                    with timed("setup role"):
                        role_arn = role_policy_upsert(
                            function_name,
                            manifest['permissions'],
                            account,
                            bool(vpc or vpcid),
                            'schedule' in manifest,
                            dryrun
                        )
                    if not role_arn:
                        role_arn = clients.cfg.get('role')
                        cprint("Setting permissions failed. Defaulting to " + role_arn, 'red')
                    else:
                        cprint("Specific permissions set with role: " + role_arn, 'blue')
                else:
                    role_arn = clients.cfg.get('role')
                    cprint("no explicit role arn found, defaulting to " + role_arn, 'blue')
            else:
                cprint("Explicit role arn found: " + role_arn, 'blue')

            if role_arn:
                # Publishing
                with timed("publish"):
                    (fullname, arn) = publish(function_name, role_arn, zipfile, manifest['options'], dryrun)
                os.remove(zipfile)

                # Schedule setup
                if 'schedule' in manifest:
                    with timed("schedule setup"):
                        setup_schedule(fullname, arn, role_arn, manifest['schedule'], dryrun)

                deployed.append(fname)
                print("Success!\n")
            else:
                cprint("No role to default to, deploy cancelled. "
                       "Use blambda config role <some role> to set a default",
                       'red')
        else:
            cprint("*** WARNING: unable to find {} ***\n".format(fname), 'yellow')
    return set(deployed)


def main(args=None):
    """ main function for the deployment script.
        Parses args, calls deploy, outputs success or failure
    """
    global clients
    clients = Clients()
    parser = argparse.ArgumentParser("package and deploy lambda functions")
    parser.add_argument('function_names', nargs='*', type=str, help='the base name of the function')
    parser.add_argument('--prefix', type=str, help='the prefix for the function',
                        default=clients.cfg.get('application', ''))
    parser.add_argument('--account', type=str, help='the account to use for resource permissions',
                        default=clients.cfg.get('account'))
    parser.add_argument('--env', type=str, help='the environment this function will run in',
                        default=clients.cfg.get('environment', ''))
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
        cprint("NO PACKAGE PROVIDED", 'red')
        cprint("Choose one of the following:", 'blue')
        print("  " + "\n  ".join(all_manifests(".")))
        sys.exit(-1)

    deployed = deploy(fnames, args.env, args.prefix, args.role, args.account, args.dryrun)
    if deployed != fnames:
        not_deployed = fnames - deployed
        if len(deployed) > 0:
            cprint("deployed " + ", ".join(map(str, deployed)), 'blue')
        cprint("FAILED TO DEPLOY " + ", ".join(map(str, not_deployed)), 'red')
        sys.exit(len(not_deployed))
    cprint("Successfully deployed " + ", ".join(map(str, deployed)), 'blue')


if __name__ == '__main__':
    main()
