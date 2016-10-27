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

def get_streams(log_group, from_ms, to_ms, quiet=False):
    def ts2date(ts):
        return datetime.utcfromtimestamp(ts / 1000).strftime("%Y/%m/%d")
    fds = ts2date(from_ms)
    tds = ts2date(to_ms)
    minlen = min(len(fds), len(tds))
    common = "".join([fds[i] for i in range(minlen) if fds[i] == tds[i]])
    if not quiet:
        print("getting streams with prefix {}".format(common))
    try:
        response = client.describe_log_streams(
            logGroupName=log_group,
            logStreamNamePrefix=common
        )
        return [stream['logStreamName'] for stream in response['logStreams']]
    except ClientError as ce:
        if "ResourceNotFound" in str(ce):
            print(pRed("{} not found in cloudwatch".format(log_group)))
            return []
        raise

def get_events(log_group, stream, from_ms, to_ms, quiet=False):
    events = client.get_log_events(
        logGroupName = log_group,
        logStreamName = stream,
        startTime = from_ms,
        endTime = to_ms
    )['events']

    if not quiet:
        print("{} events from stream {}".format(len(events), stream))

    #return a timestamp and msg tuple for each event
    return [(
        event['timestamp'],
        event['message'].strip()
    ) for event in events]

def histogram(data, buckets=10):
    lo = min(data)
    hi = max(data)
    step = max((hi-lo)/buckets,1)
    thresholds = range(lo, hi, step) + [hi+1]
    histogram = { th:[] for th in thresholds }
    for t in data:
        for i, th in enumerate(thresholds):
            if t < th:
                histogram[thresholds[i-1]].append(t)
                break
    return histogram

def parse_time(t):
    """ parse a date time string, or a negative number as
    the number of seconds ago.
    returns unix timestamp in MS
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
    #Get the millisec by subtracting epoch in the same tz, then x 1000
    return int((parsed - datetime.fromtimestamp(0, parsed.tzinfo)).total_seconds() * 1000)

def summarize(executions, parallelism_map):
    excount = len(executions)
    if excount > 0:
        exectimes = [e["END"] - e["START"] for i, e in executions.items() if "END" in e and "START" in e]
        if exectimes:
            hist = histogram(exectimes, 50)
            total = float(sum(exectimes))
            avg = int(total / excount) / 1000.0
            print("total executions: {}".format(excount))
            print("max parallelism: {}".format(max(parallelism_map.values())))
            print("execution time:")
            print("  minimum: {:.3f} sec".format(min(exectimes) / 1000.0))
            print("  maximum: {:.3f} sec".format(max(exectimes) / 1000.0))
            print("  average: {:.3f} sec".format(avg))
            print("  histogram:")
            keys = sorted(hist)
            for i,k in enumerate(keys[:-1]):
                l = len(hist[k])
                if l > 0:
                    print("{:8} -{:8}: {}".format(k, keys[i+1]-1, l))
        else:
            print("weird. {}".format(dict(executions)))
    else:
        print("zero executions")

def analyze(events, json_output, summary_only, no_headers, human_times):
    #optionally filter out headers and print result
    re_headers = re.compile("^(START|END|REPORT) RequestId: ([a-z0-9\-]{36})")
    executions = defaultdict(dict)
    parallelism_map = {}
    parallelism = 0

    if json_output and not summary_only:
        print("[")
    for event in sorted(events, key=lambda e: e[0]):
        t, data = (event[0], event[1])
        header_match = re_headers.match(data)
        if header_match:
            hdr_type = header_match.group(1)
            request_id = header_match.group(2)
            executions[request_id][hdr_type] = t
            if hdr_type == "START":
                parallelism += 1
            elif hdr_type == "END":
                parallelism -= 1
            parallelism_map[t] = parallelism

        elif not ((no_headers and header_match) or summary_only):
            if human_times:
                t = datetime.fromtimestamp(int(t) / 1000.0).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            if json_output:
                try:
                    data = json.loads(data)
                except ValueError:
                    pass
                print(json.dumps({
                    "datetime": t,
                    "message": data
                }) + ",")
            else:
                print("{}: {}".format(t, data))
    return (executions, parallelism_map)

def main(args=None):
    parser = argparse.ArgumentParser("get cloudwatch log events for a lambda function. Json output can be fed into tools like decider/dec_stats")
    parser.add_argument('function_name', type=str, help='the base name of the function')
    parser.add_argument('--prefix', type=str, help='the prefix for the function', default='fulfillment')
    parser.add_argument('--env', type=str, help='dev or stage or something', default="dev")
    parser.add_argument('-q', '--quiet', help='only output the log messages', action='store_true')
    parser.add_argument('-c', '--clean', help='suppress lambda START END and REPORT messages', action='store_true')
    parser.add_argument('-H', '--human', help='use human readable timestamps', action='store_true')
    parser.add_argument('-s', '--summary', help='output only the execution summary', action='store_true')
    parser.add_argument('-j', '--json', help='output valid json', action='store_true')
    parser.add_argument('-f', '--from', dest="fromdt", type=str, help='start time', default="-60")
    parser.add_argument('-t', '--to', type=str, help='end time', default="0")
    parser.add_argument('-i', '--infile', type=str, help='read events from file')
    parser.add_argument('-o', '--outfile', type=str, help='save events to file')
    args = parser.parse_args(args)

    log_group = "/aws/lambda/{}_{}_{}".format(args.prefix, args.function_name, args.env)

    from_ms = parse_time(args.fromdt)
    to_ms = parse_time(args.to)

    if not args.quiet:
        print("from: {} to: {}".format(from_ms, to_ms))

    if args.infile:
        with open(args.infile) as f:
            events = json.load(f)
    else:
        streams = get_streams(log_group, from_ms, to_ms, args.quiet)
        if not args.quiet:
            print("found {} streams".format(len(streams)))
        #accumulate events from streams asynchronously (50 thread max)
        with ThreadPoolExecutor(50) as tpx:
            def partial_get_events(stream):
                return get_events(log_group, stream, from_ms, to_ms, args.quiet)
            events = merge_lists(tpx.map(partial_get_events, streams))

        if args.outfile:
            with open(args.outfile, 'w') as f:
                json.dump(events, f)

    (executions, parallelism_map) = analyze(events, args.json, args.summary, args.clean, args.human)

    if not args.quiet:
        summarize(executions, parallelism_map)

    if args.json and not args.summary:
        print("{}]")
