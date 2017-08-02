"""
package and deploy lambda functions
"""
import json
import os
import shutil
import subprocess as sp
import sys
import tempfile
from pathlib import Path, PurePath

import boto3
from botocore.exceptions import ClientError
from termcolor import cprint

from . import config
from .utils.base import spawn, timed, die
from .utils.findfunc import (
    find_all_manifests,
    find_manifest
)
from .utils.iam import role_policy_upsert
from .utils.lambda_manifest import LambdaManifest
from .utils.vpc import VpcInfo


def split_path(path):
    (basedir, jsonfile) = os.path.split(path)
    (name, ext) = os.path.splitext(jsonfile)
    return basedir, name, ext


clients = None

# todo: remove this and namespace node_modules directories
NODE_MANIFEST_COUNT = 0


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


def coffee_compile(coffee_file, target_dir, npm_bin_dir):
    """ compile a coffee file and return the compiled file's name
    Args:
        coffee_file (PurePath|str): name of a coffeescript file to compile
        target_dir (PurePath|str): directory for the compiled .js file
        npm_bin_dir (PurePath|str): node_modules/.bin dir which should contain the coffee binary
    """
    command = f"{npm_bin_dir}/coffee -o {target_dir} -bc {coffee_file}"
    spawn(command, show=True, raise_on_fail=True)


def copy_dependencies(manifest, tmpdir, options):
    """ Copy dependencies to the temporary directory for packaging """
    global NODE_MANIFEST_COUNT
    basedir = manifest.basedir
    data = manifest.manifest
    fname = manifest.short_name

    if 'python' in manifest.runtime:
        if data.get('dependencies') and not manifest.lib_dir.is_dir():
            die("Dependencies defined but no dependency directory found.  Please run 'blambda deps'")

        sp.call(f"cp -r {manifest.lib_dir / '*'} {tmpdir}", shell=True)

    elif 'nodejs' in manifest.runtime:
        NODE_MANIFEST_COUNT += 1
        if NODE_MANIFEST_COUNT > 0:
            raise NotImplementedError("blambda can't currently deploy more than 1 nodejs lambda function at a time, sorry!")
        node_modules_dir = basedir / "node_modules"

        if data.get('dependencies') and not node_modules_dir.exists():
            die("Dependencies defined but no dependency directory found.  Please run 'blambda deps'")

        shutil.copytree(node_modules_dir, tmpdir / "node_modules")
        (tmpdir / fname).mkdir()
        options.update({
            "Handler": f"{fname}/{fname}.handler",
            "Runtime": "nodejs"
        })

    else:
        die("Unknown runtime " + manifest.runtime)

    return options


def exec_deploy_hook(data, tmpdir, basedir, before_or_after):
    """Run the before deploy / after deploy script hooks"""
    for command in data.get(f'{before_or_after} deploy', []):
        (ret, out, err) = spawn(f"{command} {tmpdir}", show=True, working_directory=basedir)
        print('\n'.join(out + err))


def copy_source_files(manifest, tmpdir: Path):
    """Copy the specified source files to the packaging temporary directory"""
    data = manifest.manifest
    npm_bin_dir = manifest.basedir / 'node_modules' / '.bin'

    for source_spec in data.get('source files', []):
        if type(source_spec) == list:
            # e.g. ["../shared/lambda_chain.py", "lambda_chain.py"]
            src_filename, dest_path = source_spec
        else:
            # .e.g. "config.py" or "../shared/util.coffee"
            src_filename = dest_path = source_spec

        target = (tmpdir / dest_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        src = manifest.basedir / src_filename

        if src.suffix == ".coffee":
            # FYI -- this matches the original implementation, if you mix .coffee and .js source files your directory
            # tree in the deployed package is going to be confusing, but if you don't mix and match it'll be fine.
            coffee_target = (tmpdir / manifest.short_name / dest_path).parent
            coffee_compile(coffee_file=src, target_dir=coffee_target, npm_bin_dir=npm_bin_dir)
        else:
            shutil.copyfile(src=src, dst=str(target))


def package(manifest, dryrun=False):
    """ create an archive containing source files and deps for lambda
    Args:
        manifest (LambdaManifest): the manifest object to package
        dryrun (bool): indicates that you're testing, and leaves the tmp dir for inspection
    """

    basedir = manifest.basedir
    fname = manifest.short_name
    data = manifest.manifest

    # default options
    options = {
        "Timeout": 30,
        "MemorySize": 128,
        "Description": "Fulfillment Function",
        "Runtime": "python2.7",
        "Handler": "{}.lambda_handler".format(fname),
    }

    tmpdir = Path(tempfile.mkdtemp())

    if dryrun:
        cprint(f"DRYRUN!! -- TEMPDIR: {tmpdir}", 'red')

    exec_deploy_hook(data, tmpdir, basedir, 'before')

    options = copy_dependencies(manifest, tmpdir, options)
    copy_source_files(manifest, tmpdir)

    if 'options' in data:
        options.update(data['options'])

    data['options'] = options

    exec_deploy_hook(data, tmpdir, basedir, 'after')

    archive = shutil.make_archive(fname, "zip", tmpdir)

    if not dryrun:
        shutil.rmtree(str(tmpdir))

    return archive


def git_sha():
    """ get the current sha """
    try:
        (ret, out, err) = spawn("git rev-parse --short HEAD", show=True)
        if ret == 0:
            return out[0]
        return ' '.join(err)
    except sp.CalledProcessError:
        return "no git sha"


def git_local_mods():
    """ return the number of modified, added or deleted files beyond last commit """
    try:
        (ret, out, err) = spawn("git status -suno", show=True)
        if ret == 0:
            return len([c for c in out if len(c.strip()) > 0])
        cprint(' '.join(err), 'red')
        return 0
    except sp.CalledProcessError:
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
        dryrun: (bool): Only publish if False

    Returns:
         str: the arn of the new or updated function
    """
    client = clients.lambda_client

    sha = git_sha()
    mods = "!" * git_local_mods()
    description = options.get("Description", "")
    options['Description'] = "{} [SHA {}{}]".format(description, sha, mods)
    if 'Role' not in options:
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
        override_role_arn (str): the role to use for the function
        account (str): the account to use for resource permissions
        dryrun (bool): prevents AWS publish and retains tmpdir / zipfile
    """
    deployed = []

    for fname in function_names:
        with timed("find manifest"):
            manifest = find_manifest(fname)
        if manifest:
            print("Deploying function '{}'...".format(fname))

            zipfile = package(manifest, dryrun)
            manifest_data = manifest.manifest
            function_name = f"{prefix.lower()}_{manifest.deployed_name}_{env.lower()}"

            # VPC setup
            vpcid = manifest_data.get('options', {}).get('VpcConfig', {}).get('VpcId')
            vpc = manifest_data.get('vpc', False)
            if vpcid:
                # this is not a valid option for boto, but it should be
                del manifest_data['options']['VpcConfig']['VpcId']
                with timed("get vpc by id"):
                    manifest_data['options']['VpcConfig'] = get_vpc_config(vpcid)
            elif vpc:
                with timed("get vpc without id"):
                    manifest_data['options']['VpcConfig'] = get_vpc_config()

            # Role setup
            role_arn = override_role_arn
            if not role_arn:
                if 'permissions' in manifest_data:
                    with timed("setup role"):
                        role_arn = role_policy_upsert(
                            function_name,
                            manifest_data['permissions'],
                            account,
                            bool(vpc or vpcid),
                            'schedule' in manifest_data,
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
                    (fullname, arn) = publish(function_name, role_arn, zipfile, manifest_data['options'], dryrun)
                os.remove(zipfile)

                # Schedule setup
                if 'schedule' in manifest_data:
                    with timed("schedule setup"):
                        setup_schedule(fullname, arn, role_arn, manifest_data['schedule'], dryrun)

                deployed.append(fname)
                print("Success!\n")
            else:
                cprint("No role to default to, deploy cancelled. "
                       "Use blambda config role <some role> to set a default",
                       'red')
        else:
            cprint("*** WARNING: unable to find {} ***\n".format(fname), 'yellow')
    return set(deployed)


def setup_parser(parser):
    """ main function for the deployment script.
        Parses args, calls deploy, outputs success or failure
    """
    global clients
    clients = Clients()
    env = clients.cfg.get('environment', '')
    account = clients.cfg.get('account')
    app = clients.cfg.get('application', '')

    parser.add_argument('function_names', nargs='*', type=str, help='the base name of the function')
    parser.add_argument('--prefix', type=str, help='the prefix for the function', default=app)
    parser.add_argument('--account', type=str, help='the account to use for resource permissions', default=account)
    parser.add_argument('--env', type=str, help='the environment this function will run in', default=env)
    parser.add_argument('--role', type=str, help='the arn of the IAM role to apply', default=None)
    parser.add_argument('--file', type=str, help='filename containing function names')
    parser.add_argument('--dryrun', '--dry-run', help='do not actually send anything to lambda', action='store_true')


def run(args):
    fnames = args.function_names
    if args.file:
        with open(args.file) as f:
            fnames += [l.strip() for l in f.readlines()]
        print("read {} from {}".format(fnames, args.file))

    fnames = set(fnames)
    if len(fnames) < 1:
        cprint("NO PACKAGE PROVIDED", 'red')
        cprint("Choose one of the following:", 'blue')
        for m in find_all_manifests("."):
            print("  " + m.full_name)
        sys.exit(-1)

    deployed = deploy(fnames, args.env, args.prefix, args.role, args.account, args.dryrun)
    if deployed != fnames:
        not_deployed = fnames - deployed
        if len(deployed) > 0:
            cprint("deployed " + ", ".join(map(str, deployed)), 'blue')
        cprint("FAILED TO DEPLOY " + ", ".join(map(str, not_deployed)), 'red')
        sys.exit(len(not_deployed))
    cprint("Successfully deployed " + ", ".join(map(str, deployed)), 'blue')
