#!/usr/bin/env python3

# This script is for updating this repository from Pernosco's internal
# repositories. It's not for use by customers.

import json
import os
import subprocess
import sys
import tempfile

# Step 1, update the metadata.json
pernosco_root = os.environ["PERNOSCO_ROOT"]
pernosco_main = os.path.join(pernosco_root, "main")
new_rev = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=pernosco_main, encoding='utf-8').rstrip()

old_metadata = None
old_rev = None

with open("metadata.json", 'r') as f:
    data = json.load(f)
    old_rev = data['db_builder_revision']

with open("metadata.json", 'w') as f:
    new_data = {
        'db_builder_revision': new_rev,
        'appserver_revision': new_rev,
    }
    json.dump(new_data, f, indent=2)
    # Ensure there's a trailing newline
    print("", file=f)

print("Replacing on-prem revision ", old_rev, " with ", new_rev, file=sys.stderr)

# Step 2, run the test
test_output = subprocess.check_call(["./tests/main.py", "--headless"], encoding="utf-8")

#assert "PASS" in test_output.output

# Step 3, look at commit logs and autogenerate a commit message.
log = subprocess.Popen(["git", "log", "%s..%s"%(old_rev, new_rev)],
                       stdout=subprocess.PIPE,
                       cwd=pernosco_main,
                       encoding='utf-8')
(log_output, _) = log.communicate()
changelog = []
accumulating = False

for line in log_output.splitlines():
    line = line.strip()
    if not line:
        accumulating = False
    elif accumulating:
        changelog.append(line)
    elif line.startswith("Changelog:"):
        accumulating = True
        changelog.append(line.replace("Changelog:", "-", 1))

commit_message = tempfile.NamedTemporaryFile(mode='w')
print("Update to new container version.\n", file=commit_message)
for line in changelog:
    print(line, file=commit_message)
commit_message.flush()

subprocess.check_call(["git", "commit", "--edit", "--file", commit_message.name, "--", "metadata.json"])
