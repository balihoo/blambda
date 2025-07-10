#!/usr/bin/env bash

pyenv install -s 3.10.18
pyenv uninstall -f blambdev
pyenv virtualenv 3.10.18 blambdev
pyenv local blambdev
pip install -r requirements.txt