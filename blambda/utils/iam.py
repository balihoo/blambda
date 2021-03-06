import json
import time
from copy import deepcopy
from difflib import unified_diff
from pprint import pprint

import boto3
from botocore.exceptions import ClientError
from termcolor import cprint


def make_assume_role_policy(services):
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": ["{}.amazonaws.com".format(s) for s in services]},
                "Action": "sts:AssumeRole"
            }
        ]
    }
    print("{} -> {}".format(services, policy))
    return policy


no_permission_policy = [
    {
        "Action": "s3:ListBucket",
        "Effect": "Deny",
        "Resource": "arn:aws:s3:::balihoo.dev.fulfillment"
    }
]


def expand_shorthand(action, arn):
    return {
        "Effect": "Allow",
        "Action": [action],
        "Resource": [arn]
    }


def expand_all_shorthands(original):
    """ allows specifying a statement like:
       { "logs:DescribeLogStreams": "arn:aws:logs:*:*:log-group:/aws/lambda:*" }
    """
    expanded = []
    for policy in original:
        if all(k in policy for k in ('Effect', 'Action', 'Resource')):
            expanded.append(policy)
        else:
            expanded += [expand_shorthand(k, v) for k, v in policy.items()]
    return expanded


def mk_policy(statement, fname, account):
    statement = statement if type(statement) == list else []
    if account:
        statement.append(mk_cloudlog_policy(fname, account))
    elif not statement:
        print("no account and no permissions; function may not be able to log")
        statement = no_permission_policy
    statement = expand_all_shorthands(statement)
    return {
        'Version': '2012-10-17',
        'Statement': statement
    }


def mk_cloudlog_policy(fname, account):
    return {
        "Effect": "Allow",
        "Action": [
            "logs:CreateLogGroup",
            "logs:CreateLogStream",
            "logs:PutLogEvents",
            "logs:DescribeLogStreams"
        ],
        "Resource": [
            "arn:aws:logs:*:{}:log-group:/aws/lambda/{}:*".format(account, fname)
        ]
    }


def mk_role_name(fname):
    name = fname.title().replace('_', '')
    return 'BalihooLambda{}'.format(name)


def mk_policy_name(fname):
    return mk_role_name(fname) + 'Policy'


def policy_diff(p_current, p_desired):
    def cleanstr(porg):
        p = deepcopy(porg)
        for statement in p['Statement']:
            if 'Sid' in statement:
                del statement['Sid']
        return json.dumps(p, sort_keys=True, indent=2)

    (s1, s2) = (cleanstr(p) for p in (p_current, p_desired))
    if s1 == s2:
        return None
    else:
        return unified_diff(
            s1.split('\n'),
            s2.split('\n'),
            fromfile='current',
            tofile='desired'
        )


def ensure_vpc_access(role):
    vpc_access_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
    for p in role.attached_policies.all():
        if p.arn == vpc_access_arn:
            print("vpn access policy was already attached. no change")
            return
    print("Attaching vpn access policy")
    role.attach_policy(PolicyArn=vpc_access_arn)
    time.sleep(5)


def ensure_events_access(role):
    pdoc = role.assume_role_policy_document
    if "events" in pdoc:
        print("events already in assume role policy document")
    else:
        assume_role_policy = make_assume_role_policy(["lambda", "events"])
        try:
            role.AssumeRolePolicy().update(PolicyDocument=json.dumps(assume_role_policy))
        except Exception as e:
            print("problem updating assume role policy: {}".format(e))
        time.sleep(5)


def role_policy_upsert(fname, policy_statement, account, vpc, events, dryrun):
    desired_policy = mk_policy(policy_statement, fname, account)
    role_name = mk_role_name(fname)
    policy_name = mk_policy_name(fname)
    print("applying {} permission(s) to {} as {}:".format(len(policy_statement), role_name, policy_name))
    pprint(desired_policy)

    iam = boto3.resource('iam', region_name='us-east-1')

    def get_role():
        for r in iam.roles.all():
            if r.name == role_name:
                return r

    def get_policy(role):
        for p in role.policies.all():
            if p.name == policy_name:
                return p

    try:
        role = get_role()
        if not role:
            print("role not found; creating {}".format(role_name))
            services = ["lambda"]
            if events:
                print("adding events to assume services")
                services.append("events")
            assume_role_policy = make_assume_role_policy(services)
            if not dryrun:
                role = iam.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(assume_role_policy)
                )
                # something does not happen right away
                time.sleep(5)
            else:
                print("dryrun: did not create role")
                return None
        else:
            print("role found")

        role_arn = role.meta.data['Arn']
        if vpc:
            ensure_vpc_access(role)

        if events:
            ensure_events_access(role)

        policy = get_policy(role)
        if not policy:
            print("no policy. creating")
            policy = iam.RolePolicy(role_name, policy_name)
            # something does not happen right away
            time.sleep(5)
        else:
            print("found policy. updating")
            diff = policy_diff(policy.policy_document, desired_policy)
            if not diff:
                print("policy matches: no update")
                return role_arn
            else:
                print("policy does not match")
                print('\n'.join(diff))

        if not dryrun:
            if desired_policy:
                print("updating policy")
                policy.put(PolicyDocument=json.dumps(desired_policy))
                # something does not happen right away
                time.sleep(5)
        else:
            print("DRYRUN: did not update role policy")
        return role_arn
    except ClientError as e:
        if 'AccessDenied' in str(e):
            cprint("ACCESS DENIED: unable to create roles/policies", 'red')
            return None
        raise
