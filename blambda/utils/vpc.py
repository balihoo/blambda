import boto3

from .base import is_string


class VpcInfo(object):
    """ gather information from the VPC """

    def __init__(self, region, env, vpcid=None):
        self._env = env
        self._region = region
        self._client = boto3.client('ec2', region_name=region)
        self._vpcid = vpcid or self._get_vpc_id()
        self._subnets = self.get_subnets()
        self._security_groups = self.get_security_groups()

    @property
    def vpcid(self):
        return self._vpcid

    @property
    def security_groups(self):
        return self._security_groups

    @property
    def security_group(self):
        return self._security_groups[0] if self._security_groups else None

    @property
    def external_subnets(self):
        return self._subnets["Public"]

    @property
    def dmz_subnets(self):
        return self._subnets["DMZ"]

    @property
    def private_subnets(self):
        return self._subnets["Private"]

    @property
    def subnets(self):
        return sum(self._subnets.values(), [])

    def _get_vpc_id(self):
        def envmatch(vpc):
            name = self.name_from_tags(vpc)
            return name == "{}-{}".format(self._env, self._region)

        vpcs = self._client.describe_vpcs()
        vpcids = [vpc['VpcId'] for vpc in vpcs['Vpcs'] if envmatch(vpc)]
        return vpcids[0] if vpcids else None

    def name_from_tags(self, obj):
        """ get the value of the 'Name' attribute in Tags """
        return self.keyval(obj['Tags'], 'Name')

    def keyval(self, l, key):
        """ get the 'Value' attribute from an item with a specific key """
        items = [item['Value'] for item in l if item['Key'] == key]
        return items[0] if items else None

    def vpcid_filter(self):
        return {'Name': 'vpc-id', 'Values': [self._vpcid]}

    def get_security_groups(self):
        sgroupname = "{}_{}_ssh_dmz_default".format(self._env, self._region)
        filters = [self.vpcid_filter(), {'Name': 'group-name', 'Values': [sgroupname]}]
        securitygroups = self._client.describe_security_groups(Filters=filters)
        grps = securitygroups['SecurityGroups']
        return [g['GroupId'] for g in grps]

    def get_subnets(self):
        def subnets_from_acl(acl):
            return [assoc['SubnetId'] for assoc in acl['Associations']]

        filt = [self.vpcid_filter()]
        acls = self._client.describe_network_acls(Filters=filt)['NetworkAcls']
        aclsubnets = {self.name_from_tags(acl): subnets_from_acl(acl) for acl in acls}
        subnets = {k.replace('cloud', ''): v for (k, v) in aclsubnets.items() if is_string(k)}
        return subnets


if __name__ == "__main__":
    vpcinfo = VpcInfo('us-east-1', 'dev')
    print("vpcid {}".format(vpcinfo.vpcid))
    print("secgrp {}".format(vpcinfo.security_group))
    print("external_subnets: {}".format(vpcinfo.external_subnets))
    print("dmz_subnets: {}".format(vpcinfo.dmz_subnets))
    print("private_subnets: {}".format(vpcinfo.private_subnets))
