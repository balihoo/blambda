import boto3
import json
from copy import deepcopy
from difflib import unified_diff
from botocore.exceptions import ClientError
from base import pRed
from pprint import pprint
import time

assume_role_policy = {
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}

no_permission_policy = [
    {
        "Action": "s3:ListBucket",
        "Effect": "Deny",
        "Resource": "arn:aws:s3:::balihoo.dev.fulfillment"
    }
]

def mk_policy(statement):
    return {
        'Version': '2012-10-17',
        'Statement': statement
    }

def mk_role_name(fname):
    name = fname.title().replace('_','')
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
    (s1,s2) = (cleanstr(p) for p in (p_current, p_desired))
    if s1 == s2:
        return None
    else:
        return unified_diff(
            s1.split('\n'),
            s2.split('\n'),
            fromfile='current',
            tofile='desired'
        )

def role_policy_upsert(fname, policy_statement, dryrun):
    desired_policy = mk_policy(policy_statement) if policy_statement else None
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
            if not dryrun:
                role = iam.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(assume_role_policy)
                )
                # something does not happen right away
                time.sleep(1)
            else:
                print("dryrun: did not create role")
                return None
        else:
            print("role found")

        role_arn = role.meta.data['Arn']
        policy = get_policy(role)
        if not policy:
            if desired_policy:
                print("no policy. creating")
                policy = iam.RolePolicy(role_name, policy_name)
                # something does not happen right away
                time.sleep(1)
            else:
                print("no permissions defined; not creating policy")
        else:
            print("found policy:")
            if not desired_policy:
                print("no permissions defined; implementing a no-permission policy")
                desired_policy = mk_policy(no_permission_policy)

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
                time.sleep(1)
        else:
            print("DRYRUN: did not update role policy")
        return role_arn
    except ClientError as e:
        if 'AccessDenied' in e.message:
            print(pRed("ACCESS DENIED: unable to create roles/policies"))
            return None
        raise
