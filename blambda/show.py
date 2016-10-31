import argparse
import os
from .utils.findfunc import all_manifests

def main(args=None):
    parser = argparse.ArgumentParser("list local functions")
    parser.add_argument('-v', '--verbose', help='verbose output', action='count')
    manifests = all_manifests(".", verbose=False)
    for m in manifests:
        print(os.path.basename(m))

