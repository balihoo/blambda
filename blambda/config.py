import os
import json
import argparse

configfile=os.path.abspath(os.path.join(os.path.expanduser('~'), '.config', 'blambda', 'config.json'))
configfile_local=os.path.abspath(os.path.join(os.getcwd(), '.blambda', 'config.json'))

def save(var, val, local):
    cfg = load()
    if val is None:
        #remove if setting existing value to None
        if var in cfg:
            del cfg[var]
    else:
        cfg[var] = val
    cfgfile = configfile_local if local else configfile
    cfgdir = os.path.dirname(cfgfile)
    if not os.path.exists(cfgdir):
        os.makedirs(cfgdir)
    with open(cfgfile, 'w') as f:
        f.write(json.dumps(cfg, sort_keys=True, indent=2))

def load():
    config = {}
    # load global config
    if os.path.exists(configfile):
        with open(configfile) as f:
            config = json.load(f)
    # override with local config
    if os.path.exists(configfile_local):
        with open(configfile_local) as f:
            config.update(json.load(f))
    return config

def main(args=None):
    parser = argparse.ArgumentParser("configure blambda")
    parser.add_argument('action', choices=['set_local', 'set_global', 'get'])
    parser.add_argument('variable', choices=['region', 'environment', 'role', 'application', 'account', 'all'])
    parser.add_argument('value', type=str, help='the value to give to the variable', nargs='?')
    args = parser.parse_args(args)
    if args.action == 'set_local':
        save(args.variable, args.value, local=True)
    elif args.action == 'set_global':
        save(args.variable, args.value, local=False)
    else:
        for k, v in sorted(load().items()):
            if args.variable in ('all', k):
                print("{}: {}".format(k, v))

if __name__ == '__main__':
    main()
