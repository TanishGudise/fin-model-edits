#!/bin/bash
# Runs in the separate verifier container: the agent's /app/model.xlsx has been copied in.
mkdir -p /logs/verifier
python3 /tests/verify.py || echo 0 > /logs/verifier/reward.txt
