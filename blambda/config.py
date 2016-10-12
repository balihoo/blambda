import os
import json
import argparse

configfile=os.path.abspath(os.path.join(os.path.expanduser('~'), '.config', 'blambda', 'config.json'))

def save(var, val):
    cfg = load()
    cfg[var] = val
    cfgdir = os.path.dirname(configfile)
    if not os.path.exists(cfgdir):
        os.makedirs(cfgdir)
    with open(configfile, 'w') as f:
        f.write(json.dumps(cfg, sort_keys=True, indent=2))

def load():
    if os.path.exists(configfile):
        with open(configfile) as f:
            return json.load(f)
    return {}

def main(args=None):
    parser = argparse.ArgumentParser("configure blambda")
    parser.add_argument('variable', choices=['region', 'environment', 'role', 'application'])
    parser.add_argument('value', type=str, help='the value to give to the variable')
    args = parser.parse_args(args)
    save(args.variable, args.value)

if __name__ == '__main__':
    main()
