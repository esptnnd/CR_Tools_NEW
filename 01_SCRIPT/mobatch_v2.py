import threading
import sys
import os
import re
import tempfile
import subprocess
import time

# Get VM SCP type from PS1
ps1 = os.environ.get("PS1", "")
matches = re.findall(r'\((.*?)\)', ps1)

vm_scp = "sff"
if matches:
    extracted_value = matches[0]
    if extracted_value == "ENM2A":
        vm_scp = "svc"
    elif extracted_value == "enmwst":
        vm_scp = "scp"
    else:
        vm_scp = "svc"

# Input arguments
ref_file = sys.argv[1]
command_path = sys.argv[2]
log_path = sys.argv[3]
cd_folder = sys.argv[4]

# SSH credentials
username = subprocess.check_output("whoami", shell=True).strip()
password = "Bismillah*2024"

# Global list of threads
threads = []

def check_missing_logs_run(nodenames, log_dir):
    missing = []
    for nodename in nodenames:
        expected_file = os.path.join(log_dir, nodename + ".log")
        if not os.path.isfile(expected_file):
            missing.append(nodename)
            continue

        try:
            proc1 = subprocess.Popen(
                ['egrep', '-L', '^Output has been logged', expected_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout1, stderr1 = proc1.communicate()

            proc2 = subprocess.Popen(
                ['egrep', '-rl', '^Unable to connect to ', expected_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout2, stderr2 = proc2.communicate()

            if stdout1.strip() or stdout2.strip():
                missing.append(nodename)

        except Exception as e:
            print("Error checking file {}: {}".format(expected_file, e))
            missing.append(nodename)

    return missing

# Read nodenames
with open(ref_file, 'r') as f:
    all_nodenames = [line.strip() for line in f if line.strip()]

# Process each part
def process_part(part, i):
    target_vm = "{}-{}-amos".format(vm_scp, i + 1)
    if len(part) == 0:
        remote_command = "echo NO_MOBATCH"
    else:    
        remote_command = "cd {} && /opt/ericsson/amos/bin/mobatch -p 45 {} {} {}".format(cd_folder, ",".join(part), command_path, log_path)

    print("Execute part {} on {} with total {} nodes\n".format(i + 1, target_vm, len(part)))

    expect_script = """#!/usr/bin/expect -f
set timeout -1
log_user 0
spawn ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PubkeyAuthentication=no {username}@{target_vm} "{remote_command}"
expect "password:"
send "{password}\\r"
log_user 1
expect {{
    eof {{
        catch wait result
    }}
}}
""".format(username=username, target_vm=target_vm, remote_command=remote_command, password=password)

    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".expect") as temp:
        temp.write(expect_script)
        temp.flush()
        script_path = temp.name

    try:
        proc = subprocess.Popen(["expect", script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True)

        print("\n--- Live output from {} ---".format(target_vm))
        for line in iter(proc.stdout.readline, ''):
            sys.stdout.write("[{}] {}".format(target_vm, line))
            sys.stdout.flush()
        proc.stdout.close()
        proc.wait()
        print("\n--- End of output from {} ---".format(target_vm))

        stderr = proc.stderr.read()
        if stderr:
            print("Errors from {}:\n{}".format(target_vm, stderr))
    except Exception as e:
        print("Error on {}: {}".format(target_vm, e))

# Split and launch threads
def split_file_and_process(nodenames, num_parts):
    total = len(nodenames)
    lines_per_part = total // num_parts

    for i in range(num_parts):
        start = i * lines_per_part
        end = (i + 1) * lines_per_part if i < num_parts - 1 else total
        part = nodenames[start:end]
        thread = threading.Thread(target=process_part, args=(part, i))
        threads.append(thread)
        thread.start()

# Check for missing files and create log file if missing
def check_missing_logs(nodenames, log_dir):
    missing = []
    for nodename in nodenames:
        expected_file = os.path.join(log_dir, nodename + ".log")
        if not os.path.isfile(expected_file):
            missing.append(nodename)

    if missing:
        print("\nMISSING FILES as below")
        for node in missing:
            print(node)
    else:
        print("\nAll expected log files are present.")

# === RUN ===
run_nodes = check_missing_logs_run(all_nodenames, log_path)
split_file_and_process(run_nodes, 3)

# Wait for all threads to finish
for thread in threads:
    thread.join()

# Final check
check_missing_logs(run_nodes, log_path)
