#!/usr/bin/env bash

pyenv uninstall -f blambdev
pyenv virtualenv 3.6.1 blambdev
pyenv local blambdev
pip install -r requirements.txt