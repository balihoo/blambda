#!/usr/bin/env python

import sys
import boto3
from botocore.exceptions import ClientError
import time
import argparse
import re
import json
from collections import defaultdict
from datetime import (
    date,
    datetime
)
from dateutil.parser import parse as dtparse
from dateutil.tz import tzlocal
from botocore.exceptions import ClientError
from botocore.client import Config as BotoConfig
from concurrent.futures import ThreadPoolExecutor
import itertools
from pprint import pprint
from .utils.base import pGreen, pRed, pBlue, pMagenta, spawn, timed

client = boto3.client(
    'logs',
    region_name='us-east-1',
    config=BotoConfig(
        connect_timeout=10,
        read_timeout=300)
)

def merge_lists(lists):
    return list(itertools.chain.from_iterable(lists))

def nowms():
    return int(time.time() * 1000)

def parse_time(t):
    """ parse a date time string, or a negative number as
    the number of seconds ago. returns unix timestamp in MS
    """
    try:
        tint = int(t)
        if tint <= 0:
            return int(nowms() + (tint * 1000))
    except ValueError:
        pass
    #the parsed date may or may not have a tz; if it does not, localize it.
    parsed = dtparse(t)
    if not parsed.tzinfo:
        parsed = parsed.replace(tzinfo=tzlocal())
    print('t {}'.format(parsed))
    #Get the millisec by subtracting epoch in the same tz, then x 1000
    return int((parsed - datetime.fromtimestamp(0, parsed.tzinfo)).total_seconds() * 1000)

def msts2str(ts):
    return datetime.fromtimestamp(int(ts) / 1000.0).strftime('%Y-%m-%d %H:%M:%S.%f %z')

def get_events(log_group, from_ms, to_ms, max_events=None, regex=None, verbose=False):
    kwargs = {
        'logGroupName': log_group,
        'startTime': from_ms,
        'endTime': to_ms,
        'interleaved': True,
    }
    token = True
    events = []
    while token:
        if max_events:
            if len(events) >= max_events:
               break
            limit = max_events - len(events)
            if limit < 10000: #max for aws api
                kwargs['limit'] = limit

        response = client.filter_log_events(**kwargs)
        token = response.get('nextToken')
        kwargs['nextToken'] = token
        evts = response['events']
        if verbose:
            print("call with {} limit returned {} events".format(kwargs.get('limit', 'no'), len(evts)))
        # filter if a regex was provided
        events += filtered(evts, regex) if regex else evts

    if verbose:
        print("{} events".format(len(events)))

    #return a timestamp and msg tuple for each event
    return events

def as_json(events, leave_ts=False):
    rhdr = re.compile("^(START|END|REPORT) RequestId: ([a-z0-9\-]{36})")
    json_events = []
    for evt in sorted(events, key=lambda e: e['timestamp']):
        t, data = (evt['timestamp'], evt['message'])
        if not rhdr.match(data):
            if not leave_ts:
                t = datetime.fromtimestamp(int(t) / 1000.0).strftime('%Y-%m-%d %H:%M:%S.%f %z')
            try:
                data = json.loads(data)
            except ValueError:
                pass
            json_events.append({
                "datetime": t,
                "message": data
            })
    return json_events

def filtered(raw_events, regex):
    rfilter = re.compile(regex)
    return [e for e in raw_events if rfilter.search(e['message'])]

def main(args=None):
    parser = argparse.ArgumentParser("get cloudwatch log events for a lambda function. Json output can be fed into tools like decider/dec_stats")
    parser.add_argument('function_name', type=str, help='the base name of the function')
    parser.add_argument('--prefix', type=str, help='the prefix for the function', default='fulfillment')
    parser.add_argument('--env', type=str, help='dev or stage or something', default="dev")
    parser.add_argument('-v', '--verbose', help='verbose information', action='store_true')
    parser.add_argument('-H', '--human', help='use human readable timestamps', action='store_true')
    parser.add_argument('-j', '--json', help='output valid json', action='store_true')
    parser.add_argument('-f', '--from', dest="fromdt", type=str, help='start time', default="-60")
    parser.add_argument('-t', '--to', type=str, help='end time', default="0")
    parser.add_argument('-r', '--filter', type=str, help='regex to filter by', default=None)
    parser.add_argument('--max', type=int, help='maximum number of records to fetch', default=None)
    args = parser.parse_args(args)

    log_group = "/aws/lambda/{}_{}_{}".format(args.prefix, args.function_name, args.env)

    from_ms = parse_time(args.fromdt)
    to_ms = parse_time(args.to)

    events = get_events(log_group, from_ms, to_ms, args.max, regex=args.filter, verbose=args.verbose)
    if args.json:
        parsed = as_json(events, leave_ts=(not args.human))
        print(json.dumps(parsed, indent=4))
    else:
        for e in events:
            t = e['timestamp']
            if args.human:
                t = msts2str(t)
            print('{}: {}'.format(t, e['message'].strip()))

