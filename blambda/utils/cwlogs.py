import itertools
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import boto3
from botocore.client import Config as BotoConfig
import time

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
    response = client.describe_log_streams(
        logGroupName=log_group,
        logStreamNamePrefix=common
    )
    return [stream['logStreamName'] for stream in response['logStreams']]


def get_events(log_group, stream, from_ms, to_ms, quiet=False):
    events = client.get_log_events(
        logGroupName=log_group,
        logStreamName=stream,
        startTime=from_ms,
        endTime=to_ms
    )['events']

    if not quiet:
        print("{} events from stream {}".format(len(events), stream))

    # return a timestamp and msg tuple for each event
    return [(
        event['timestamp'],
        event['message'].strip()
    ) for event in events]


def get_events_from_streams(log_group, from_ms, to_ms, quiet):
    streams = get_streams(log_group, from_ms, to_ms, quiet)
    if not quiet:
        print("found {} streams".format(len(streams)))
    # accumulate events from streams asynchronously (50 thread max)
    with ThreadPoolExecutor(50) as tpx:
        def partial_get_events(stream):
            return get_events(log_group, stream, from_ms, to_ms, quiet)

        events = merge_lists(tpx.map(partial_get_events, streams))

    return events
