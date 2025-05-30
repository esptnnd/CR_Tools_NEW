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
        self._log_batch_max = 3  # Reduced from 5 to 3 for more frequent updates
        self._log_batch_interval = 10  # Reduced from 30ms to 10ms for faster updates
        self._pre_prompt_batch_max = 10  # Reduced from 30 to 10 for faster initial output
        self._prompt_ready = False
        
        # Corrected regex pattern with proper escaping
        self._prompt_regex = re.compile(r"\[(\w+?)@\S+?\(([^)]+)\) ~\]\$")
        
        # 2-second auto-flush timer for pre-prompt (reduced from 5s)
        self._log_auto_flush_timer = QTimer()
        self._log_auto_flush_timer.setInterval(2000)
        self._log_auto_flush_timer.timeout.connect(self._flush_log_batch)
        
        # Keepalive timer to prevent connection timeouts
        self._keepalive_timer = QTimer()
        self._keepalive_timer.setInterval(30000)  # 30 seconds
        self._keepalive_timer.timeout.connect(self._send_keepalive)
        
        # Track last command time for smart flushing
        self._last_command_time = 0
        self._command_timeout = 5  # seconds to wait before forcing flush after command

    def _send_keepalive(self):
        """Send a keepalive to prevent connection timeout"""
        if self.shell and self.keep_reading:
            try:
                self.shell.send('\n')
            except Exception as e:
                self._write_log(f"Keepalive failed: {str(e)}")

    def start(self):
        self.keep_reading = True
        self.thread = threading.Thread(target=self._connect_and_read)
        self.thread.daemon = True
        self.thread.start()
        self._keepalive_timer.start()

    def _connect_and_read(self):
        try:
            self._prompt_ready = False  # Reset on connect
            self._log_auto_flush_timer.start()  # Start auto-flush
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect first
            self.client.connect(self.host, self.port, self.username, self.password)
            
            # Set keepalive options after connection is established
            if self.client.get_transport():
                self.client.get_transport().set_keepalive(30)  # 30 second keepalive
            
            self.shell = self.client.invoke_shell()
            self._write_log(f"Connected to {self.username}@{self.host} ({self.session_name})")

            # Robustly read and emit the initial prompt/welcome message
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

            # Main reading loop with improved responsiveness
            while self.keep_reading:
                if self.shell.recv_ready():
                    output = self.shell.recv(4096).decode(errors='ignore')
                    output = remove_ansi_escape_sequences(output)
                    for line in output.splitlines():
                        if line.strip():
                            self._write_log(line)
                else:
                    # Check if we need to force flush after command timeout
                    if self._last_command_time > 0 and time.time() - self._last_command_time > self._command_timeout:
                        self._flush_log_batch()
                        self._last_command_time = 0
                    time.sleep(0.01)
                    
            self._log_auto_flush_timer.stop()
            self._keepalive_timer.stop()
            
        except Exception as e:
            self._write_log(f"Connection failed: {str(e)}")
            self._log_auto_flush_timer.stop()
            self._keepalive_timer.stop()

    def _write_log(self, message):
        clean_message = remove_ansi_escape_sequences(message)
        lines = clean_message.splitlines()
        for line in lines:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            full_line = f"[{timestamp}]{line}"
            
            # Check if this is a prompt line
            is_prompt = bool(self._prompt_regex.search(line))
            
            # If it's a prompt or we're not in prompt mode yet, output immediately
            if is_prompt or not self._prompt_ready:
                self.output_received.emit(full_line)
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(full_line + "\n")
                if is_prompt:
                    self._prompt_ready = True
                    self._log_auto_flush_timer.stop()
                continue
                
            # For regular output, use batching with smaller batches
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
            self._last_command_time = time.time()  # Track command time
            self.shell.send(command + '\n')
            # Force immediate flush for commands
            self._flush_log_batch()

    def detach_screen(self):
        if self.shell:
            self.shell.send('\x01d')
            self._write_log("[INFO] Sent Ctrl+a d to detach screen session.")

    def close(self):
        self.keep_reading = False
        self._keepalive_timer.stop()
        try:
            if self.shell:
                self.shell.close()
            if self.client:
                self.client.close()
        except Exception:
            pass