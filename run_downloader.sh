#!/bin/bash
source .venv/bin/activate
export PYTHONPATH=$PYTHONPATH:$(pwd)/app
python3 app/subsplease_downloader.py
