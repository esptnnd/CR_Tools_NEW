# -----------------------------------------------------------------------------
# Author      : esptnnd
# Company     : Ericsson Indonesia
# Created on  : 7 May 2025
# Improve on  : 29 May 2025
# Description : CR TOOLS by esptnnd — built for the ECT Project to help the team
#               execute faster, smoother, and with way less hassle.
#               Making life easier, one script at a time!
# -----------------------------------------------------------------------------# SSH related classes

import threading
import paramiko
import os
from datetime import datetime
from PyQt5.QtCore import pyqtSignal, QObject, QTimer
import time
import re

# Import the utility function
from .utils import remove_ansi_escape_sequences

class InteractiveSSH(QObject):
    output_received = pyqtSignal(str)

    def __init__(self, session_name, host, port, username, password):
        super().__init__()
        self.session_name = session_name
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.shell = None
        self.keep_reading = False
        self.thread = None
        os.makedirs("LOG", exist_ok=True)
        self.log_path = os.path.join("LOG", f"{self.session_name}.log")
        # For combined real-time and batch output
        self._log_batch = []
        self._log_batch_timer = QTimer()
        self._log_batch_timer.setSingleShot(True)
        self._log_batch_timer.timeout.connect(self._flush_log_batch)
        self._log_batch_max = 5
        self._log_batch_interval = 30  # ms
        self._pre_prompt_batch_max = 30
        self._prompt_ready = False
        # Corrected regex pattern with proper escaping
        self._prompt_regex = re.compile(r"\[(\w+?)@\S+?\(([^)]+)\) ~\]\$")
        # 5-second auto-flush timer for pre-prompt
        self._log_auto_flush_timer = QTimer()
        self._log_auto_flush_timer.setInterval(5000)
        self._log_auto_flush_timer.timeout.connect(self._flush_log_batch)

    def start(self):
        self.keep_reading = True
        self.thread = threading.Thread(target=self._connect_and_read)
        self.thread.daemon = True
        self.thread.start()

    def _connect_and_read(self):
        try:
            self._prompt_ready = False  # Reset on connect
            self._log_auto_flush_timer.start()  # Start 5s auto-flush
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(self.host, self.port, self.username, self.password)
            self.shell = self.client.invoke_shell()
            self._write_log(f"Connected to {self.username}@{self.host} ({self.session_name})")

            # Robustly read and emit the initial prompt/welcome message (emit each line immediately)
            import time
            start = time.time()
            prompt_received = False
            while time.time() - start < 2.0:  # Wait up to 2 seconds
                if self.shell.recv_ready():
                    output = self.shell.recv(4096).decode(errors='ignore')
                    output = remove_ansi_escape_sequences(output)
                    for line in output.splitlines():
                        if line.strip():
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            full_line = f"[{timestamp}]{line}"
                            self.output_received.emit(full_line)
                            with open(self.log_path, "a", encoding="utf-8") as f:
                                f.write(full_line + "\n")
                            if self._prompt_regex.search(line):
                                self._prompt_ready = True
                                self._log_auto_flush_timer.stop()
                            prompt_received = True
                if prompt_received:
                    break
                time.sleep(0.1)
            # Optionally, force a newline if nothing received
            if not prompt_received:
                self.shell.send('\n')
                time.sleep(0.2)
                if self.shell.recv_ready():
                    output = self.shell.recv(4096).decode(errors='ignore')
                    output = remove_ansi_escape_sequences(output)
                    for line in output.splitlines():
                        if line.strip():
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            full_line = f"[{timestamp}]{line}"
                            self.output_received.emit(full_line)
                            with open(self.log_path, "a", encoding="utf-8") as f:
                                f.write(full_line + "\n")
                            if self._prompt_regex.search(line):
                                self._prompt_ready = True
                                self._log_auto_flush_timer.stop()

            # Main reading loop: always use _write_log for each line
            while self.keep_reading:
                if self.shell.recv_ready():
                    output = self.shell.recv(4096).decode(errors='ignore')
                    output = remove_ansi_escape_sequences(output)
                    for line in output.splitlines():
                        if line.strip():
                            self._write_log(line)
                else:
                    time.sleep(0.01)
            self._log_auto_flush_timer.stop()  # Stop timer on disconnect
        except Exception as e:
            self._write_log(f"Connection failed: {str(e)}")
            self._log_auto_flush_timer.stop()

    def _write_log(self, message):
        clean_message = remove_ansi_escape_sequences(message)
        lines = clean_message.splitlines()
        for line in lines:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            full_line = f"[{timestamp}]{line}"
            # Adaptive batching based on prompt detection
            if not self._prompt_ready:
                # If prompt detected, flush and output directly
                if self._prompt_regex.search(line):
                    self._log_batch.append(full_line)
                    self._flush_log_batch()
                    self._prompt_ready = True
                    self._log_auto_flush_timer.stop()
                    continue
                self._log_batch.append(full_line)
                if len(self._log_batch) >= self._pre_prompt_batch_max:
                    self._flush_log_batch()
                elif not self._log_batch_timer.isActive():
                    self._log_batch_timer.start(self._log_batch_interval)
            else:
                # If this is a prompt line, output directly
                if self._prompt_regex.search(line):
                    self.output_received.emit(full_line)
                    with open(self.log_path, "a", encoding="utf-8") as f:
                        f.write(full_line + "\n")
                else:
                    self._log_batch.append(full_line)
                    if len(self._log_batch) >= self._log_batch_max:
                        self._flush_log_batch()
                    elif not self._log_batch_timer.isActive():
                        self._log_batch_timer.start(self._log_batch_interval)

    def _flush_log_batch(self):
        if self._log_batch:
            batch_text = '\n'.join(self._log_batch)
            self.output_received.emit(batch_text)
            with open(self.log_path, "a", encoding="utf-8") as f:
                for bline in self._log_batch:
                    f.write(bline + "\n")
            self._log_batch.clear()

    def send_command(self, command):
        if self.shell:
            self.shell.send(command + '\n')

    def detach_screen(self):
        if self.shell:
            # Send Ctrl+a d to detach the screen
            self.shell.send('\x01d')
            self._write_log("[INFO] Sent Ctrl+a d to detach screen session.")

    def close(self):
        self.keep_reading = False
        try:
            if self.shell:
                self.shell.close()
            if self.client:
                self.client.close()
        except Exception:
            pass