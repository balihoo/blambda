#!/usr/bin/env bash

pyenv install -s 3.12.0
pyenv uninstall -f blambdev
pyenv virtualenv 3.12.0 blambdev
pyenv local blambdev
pip install -r requirements.txt
