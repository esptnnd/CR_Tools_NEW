import sys
import threading
import paramiko
import os
import re
import shutil
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QVBoxLayout, QTextEdit, QLineEdit, QPushButton, QHBoxLayout,
    QDialog, QListWidget, QMessageBox, QFileDialog, QLabel, QTreeView, QFileSystemModel, QAbstractItemView, QDialogButtonBox, QProgressBar, QComboBox, QProgressDialog,
    QMenuBar, QAction, QStackedWidget, QButtonGroup, QRadioButton
)
from PyQt5.QtCore import pyqtSignal, QObject, QEventLoop, QTimer, QDir, QThread, QFileInfo
from PyQt5.QtGui import QFont, QTextCursor
import pandas as pd
import random
import time
import zipfile
import json

# Import the run_concheck function
from lib.concheck import run_concheck

# Configuration variables will be loaded from settings.json
####TEST

def remove_ansi_escape_sequences(text):
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text)

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


class ScreenSelectionDialog(QDialog):
    def __init__(self, ssh_instance, parent=None):
        super().__init__(parent)
        self.ssh = ssh_instance
        self.setWindowTitle("Select Screen Session")
        self.setMinimumSize(400, 300)
        layout = QVBoxLayout()

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.connect_btn = QPushButton("Connect")
        self.detach_btn = QPushButton("Detach")
        self.close_btn = QPushButton("Close")

        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.connect_btn)
        btn_layout.addWidget(self.detach_btn)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.refresh_btn.clicked.connect(self.refresh_screens)
        self.connect_btn.clicked.connect(self.connect_to_screen)
        self.detach_btn.clicked.connect(self.detach_screen)
        self.close_btn.clicked.connect(self.close)

        self._output_buffer = []
        self._collecting = False

        self.refresh_screens()

    def refresh_screens(self):
        self.list_widget.clear()
        self._output_buffer.clear()
        self._collecting = True

        self.ssh.output_received.connect(self._buffer_output)
        self.ssh.send_command("screen -ls")

        loop = QEventLoop()
        QTimer.singleShot(1500, loop.quit)
        loop.exec_()

        self._collecting = False
        try:
            self.ssh.output_received.disconnect(self._buffer_output)
        except Exception:
            pass

        sessions = []
        pattern = re.compile(r'^\s*(\d+\.\S+)\s+\(([^)]+)\)')

        for line in self._output_buffer:
            if '$ ' in line:
                line_to_match = line.split('$ ', 1)[1]
            else:
                line_to_match = line
            match = pattern.match(line_to_match)
            if match:
                session_name = match.group(1)
                state = match.group(2)
                sessions.append((session_name, state))
                self.list_widget.addItem(f"{session_name} [{state}]")

        if not sessions:
            self.list_widget.addItem("No screen sessions found.")

    def _buffer_output(self, text):
        if self._collecting:
            clean_text = remove_ansi_escape_sequences(text)
            for line in clean_text.splitlines():
                if line.strip():
                    self._output_buffer.append(line.strip())

    def get_selected_session(self):
        item = self.list_widget.currentItem()
        if item:
            return item.text().split()[0]
        return None

    def connect_to_screen(self):
        session = self.get_selected_session()
        if session and session != "No":
            self.ssh.send_command(f"screen -r {session}")
            self.accept()
        else:
            QMessageBox.warning(self, "No Selection", "Please select a valid screen session to connect.")

    def detach_screen(self):
        self.ssh.detach_screen()


# New Worker class for handling upload in a separate thread
class UploadWorker(QObject):
    progress = pyqtSignal(int) # Signal for progress updates (0-100)
    completed = pyqtSignal(str) # Signal when upload is completed successfully
    error = pyqtSignal(str) # Signal when an error occurs
    output = pyqtSignal(str) # Signal to send output messages to GUI

    def __init__(self, ssh_client, target_info, selected_folders, mode, selected_sessions=None, mobatch_paralel=70, mobatch_timeout=30, assigned_nodes=None, mobatch_execution_mode="REGULAR_MOBATCH", var_FOLDER_CR=None):
        super().__init__()
        self.ssh_client = ssh_client
        self.target_info = target_info
        self.selected_folders = selected_folders
        self.mode = mode
        self.selected_sessions = selected_sessions or []
        self.mobatch_paralel = mobatch_paralel
        self.mobatch_timeout = mobatch_timeout
        self._should_stop = False
        self.assigned_nodes = assigned_nodes
        self.mobatch_execution_mode = mobatch_execution_mode # Store the selected mode
        self.var_FOLDER_CR = var_FOLDER_CR

    def stop(self):
        self._should_stop = True

    def run(self):
        username = self.target_info['username']
        # Use self.var_FOLDER_CR
        remote_base_dir = f"/home/shared/{username}/{self.var_FOLDER_CR}"
        ENM_SERVER = self.target_info['session_name']
        tmp_dir = os.path.join("Temp", f"tmp_upload_{ENM_SERVER}")
        if not os.path.exists("Temp"):
            os.makedirs("Temp", exist_ok=True)
        if os.path.exists(tmp_dir):
            import shutil
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir, exist_ok=True)



        local_run_cr_path = os.path.join(tmp_dir, f"RUN_CR_{ENM_SERVER}.txt")
        local_zip_path = os.path.join(tmp_dir, f"SFTP_CR_{ENM_SERVER}.zip")
        remote_zip_path = f"{remote_base_dir}/SFTP_CR_{ENM_SERVER}.zip"
        remote_run_cr_path = f"{remote_base_dir}/RUN_CR_{ENM_SERVER}.txt"

        try:
            self.output.emit("Starting upload process...")

            # 0. Read IPDB mapping
            node_to_oss = None
            if self.mode == "TRUE":
                ipdb_path = os.path.join("00_IPDB", "ipdb_delim_ALLOSS.txt")
                if not os.path.exists(ipdb_path):
                    self.output.emit(f"[ERROR] IPDB file not found: {ipdb_path}")
                    self.error.emit(f"IPDB file not found: {ipdb_path}")
                    return
                df_ipdb = pd.read_csv(ipdb_path, sep=';', dtype=str)
                df_ipdb = df_ipdb.fillna("")
                node_to_oss = dict(zip(df_ipdb['Node'], df_ipdb['OSS']))
            elif self.mode == "DTAC":
                ipdb_path = os.path.join("00_IPDB", "ALL_IPDB.txt")
                if not os.path.exists(ipdb_path):
                    self.output.emit(f"[ERROR] IPDB file not found: {ipdb_path}")
                    self.error.emit(f"IPDB file not found: {ipdb_path}")
                    return
                df_ipdb = pd.read_csv(ipdb_path, sep=';', dtype=str)
                df_ipdb = df_ipdb.fillna("")
                node_to_oss = dict(zip(df_ipdb['Node'], df_ipdb['OSS']))
            # else SPLIT_RANDOMLY: node_to_oss stays None

            # 1. Generate RUN_CR.txt content
            run_cr_content = ""
            files_to_zip = set()
            for folder_path in self.selected_folders:
                if self._should_stop:
                    self.output.emit("Upload cancelled by user.")
                    self.error.emit("Upload cancelled.")
                    return
                folder_name = os.path.basename(folder_path).rstrip()



                # --- Split sites_list.txt by OSS ---
                sites_list_path = os.path.join(folder_path, "sites_list.txt")
                

                with open(sites_list_path, encoding="utf-8") as f:
                    nodes = [line.strip() for line in f if line.strip()]
                oss_to_nodes = {}
                if self.mode == "SPLIT_RANDOMLY":
                    # Use only assigned_nodes for this session
                    session_names = self.selected_sessions if self.selected_sessions else [self.target_info['session_name']]
                    oss_to_nodes[self.target_info['session_name']] = self.assigned_nodes[self.target_info['session_name']]
                    cek_list = self.assigned_nodes[self.target_info['session_name']] 
                    
                    self.output.emit(f"[INFO] COBA {self.target_info['session_name']}")
                    self.output.emit(f"[INFO] COBA {', '.join(cek_list)}")
                    
                else:
                    for node in nodes:
                        if self.mode == "DTAC":
                            oss = node_to_oss.get(node, "ENM_DTAC_FDD1")
                            if not oss:
                                oss = "ENM_DTAC_FDD1"
                        else:
                            oss = node_to_oss.get(node, "ENM-RAN5A")
                            if oss == "ENM-RAN4" or not oss:
                                oss = "ENM-RAN5A"
                        oss_to_nodes.setdefault(oss, []).append(node)
                # Write out sites_list_OSSNAME files
                for oss, oss_nodes in oss_to_nodes.items():
                    oss_file = os.path.join(folder_path, f"sites_list_{oss}.txt")
                    with open(oss_file, "w", encoding="utf-8", newline='\n') as f:
                        f.write("\n".join(oss_nodes) + "\n")
                    self.output.emit(f"Generated {oss_file} with {len(oss_nodes)} nodes.")
                    if os.path.getsize(oss_file) > 0:
  
                        files_to_zip.add(oss_file)
                        files_to_zip.add(os.path.join(folder_path, "command_mos.txt"))
                    else:
                        self.output.emit(f"[INFO] Skipping mobatch for {oss_file} (file empty)")

            # 2. Create local RUN_CR_{ENM_SERVER}.txt
            if self.mobatch_execution_mode == "PYTHON_MOBATCH":
                # Use self.var_FOLDER_CR
                run_cr_content += f"python  ~/{self.var_FOLDER_CR}/mobatch_v2.py  ~/{self.var_FOLDER_CR}/{folder_name}/sites_list_{ENM_SERVER}.txt    ~/{self.var_FOLDER_CR}/{folder_name}/command_mos.txt   ~/{self.var_FOLDER_CR}/LOG/{folder_name}/  ~/{self.var_FOLDER_CR}/{folder_name}/  \n\n"
            else: # REGULAR_MOBATCH
                # Use self.var_FOLDER_CR
                run_cr_content += f"cd ~/{self.var_FOLDER_CR}/{folder_name}/ && " # Keep this line as it was in your provided code
                run_cr_content += f"mobatch -p {self.mobatch_paralel} -t {self.mobatch_timeout} ~/{self.var_FOLDER_CR}/{folder_name}/sites_list_{ENM_SERVER}.txt  ~/{self.var_FOLDER_CR}/{folder_name}/command_mos.txt  ~/{self.var_FOLDER_CR}/LOG/{folder_name}/\n"                        
            
            with open(local_run_cr_path, "w", encoding="utf-8", newline='\n') as f:
                f.write(run_cr_content)
            self.output.emit(f"Generated local {local_run_cr_path}")

            # 3. Create SFTP_CR_{ENM_SERVER}.zip with all files from each folder_path (recursively)
            with zipfile.ZipFile(local_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(local_run_cr_path, os.path.basename(local_run_cr_path)) # Add RUN_CR to zip
                # Add all files from each folder_path
                base_dir = os.path.dirname(self.selected_folders[0]) if self.selected_folders else '.'
                for folder_path in self.selected_folders:
                    for root, dirs, files in os.walk(folder_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, base_dir)
                            zipf.write(file_path, arcname)

                # Add 01_SCRIPT/mobatch_v2.py to the zip
                mobatch_script_path = os.path.join('01_SCRIPT', 'mobatch_v2.py')
                if os.path.exists(mobatch_script_path):
                     zipf.write(mobatch_script_path, 'mobatch_v2.py') # Add to the root of the zip
                     self.output.emit(f"Added {mobatch_script_path} to zip.")
                else:
                     self.output.emit(f"[WARNING] {mobatch_script_path} not found, skipping addition to zip.")

            self.output.emit(f"Created local {local_zip_path}")

            if self._should_stop:
                self.output.emit("Upload cancelled by user.")
                self.error.emit("Upload cancelled.")
                return

            # 4. Establish SFTP connection
            sftp = self.ssh_client.open_sftp()
            self.output.emit("SFTP connection established.")

            # 6. Check/Create remote directory
            try:
                sftp.stat(remote_base_dir)
                self.output.emit(f"Remote directory {remote_base_dir} already exists.")
            except FileNotFoundError:
                self.output.emit(f"Remote directory {remote_base_dir} not found, creating...")
                stdin, stdout, stderr = self.ssh_client.exec_command(f"mkdir -p {remote_base_dir}")
                error_output = stderr.read().decode()
                if error_output:
                    raise Exception(f"Error creating remote directory: {error_output}")
                self.output.emit(f"Remote directory {remote_base_dir} created.")

            if self._should_stop:
                self.output.emit("Upload cancelled by user.")
                self.error.emit("Upload cancelled.")
                sftp.close()
                return

            # Add step to clean up remote directory before uploading
            self.output.emit(f"Cleaning up remote directory {remote_base_dir}/*...")
            cleanup_command = f"rm -rf {remote_base_dir}/*"
            stdin, stdout, stderr = self.ssh_client.exec_command(cleanup_command)
            stdout.read()
            stderr_output = stderr.read().decode()
            if stderr_output:
                 self.output.emit(f"Warning during remote cleanup: {stderr_output}")
            else:
                self.output.emit(f"Remote directory {remote_base_dir}/* cleaned up.")

            if self._should_stop:
                self.output.emit("Upload cancelled by user.")
                self.error.emit("Upload cancelled.")
                sftp.close()
                return

            # 7. Upload files
            local_zip_size = QFileInfo(local_zip_path).size()

            def zip_upload_progress(bytes_transferred, bytes_total):
                 if bytes_total > 0:
                     percent = int(bytes_transferred / bytes_total * 90) # Reserve 10% for other steps
                     self.progress.emit(percent)

            self.output.emit(f"Uploading {local_zip_path} to {remote_zip_path}")
            sftp.put(local_zip_path, remote_zip_path, callback=zip_upload_progress)
            self.output.emit(f"Uploaded {local_zip_path}.")

            if self._should_stop:
                self.output.emit("Upload cancelled by user.")
                self.error.emit("Upload cancelled.")
                sftp.close()
                return

            self.progress.emit(95) # Indicate progress between zip and RUN_CR.txt upload
            self.output.emit(f"Uploading {local_run_cr_path} to {remote_run_cr_path}")
            sftp.put(local_run_cr_path, remote_run_cr_path)
            self.progress.emit(100) # Indicate file uploads are complete

            # Close SFTP connection
            sftp.close()
            self.output.emit("SFTP connection closed.")

            if self._should_stop:
                self.output.emit("Upload cancelled by user.")
                self.error.emit("Upload cancelled.")
                return

            # 8. Remote Unzip
            self.output.emit(f"Unzipping {os.path.basename(local_zip_path)} on remote server...")
            unzip_command = f"cd {remote_base_dir} && unzip -o {os.path.basename(local_zip_path)}"
            stdin, stdout, stderr = self.ssh_client.exec_command(unzip_command)
            self.output.emit("Remote unzip output:")
            self.output.emit(stdout.read().decode())
            error_output = stderr.read().decode()
            if error_output:
                 self.output.emit(f"Remote unzip error: {error_output}")

            if self._should_stop:
                self.output.emit("Upload cancelled by user.")
                self.error.emit("Upload cancelled.")
                return

            # 9. Remote Execution
            self.output.emit(f"Executing remote command: ./{os.path.basename(local_run_cr_path)}")
            execute_command = f"cd {remote_base_dir} && ./{os.path.basename(local_run_cr_path)}"
            stdin, stdout, stderr = self.ssh_client.exec_command(execute_command)
            self.output.emit("Remote execution output:")
            self.output.emit(stdout.read().decode())
            error_output = stderr.read().decode()
            if error_output:
                 self.output.emit(f"Remote execution error: {error_output}")

            # After upload, cd to 00_CR_FOLDER in the interactive shell if possible
            try:
                # Always use self.ssh.shell if available for a true interactive experience
                if hasattr(self, 'ssh') and self.ssh and hasattr(self.ssh, 'shell') and self.ssh.shell:
                    self.ssh.shell.send(f"cd {remote_base_dir}; ls -ltrh\n")
                elif hasattr(self.ssh_client, 'shell') and self.ssh_client.shell:
                    self.ssh_client.shell.send(f"cd {remote_base_dir}; ls -ltrh\n")
            except Exception as e:
                self.output.emit(f"Failed to send 'cd' command after upload: {e}")

            self.output.emit("Upload and remote execution process finished.")
            self.completed.emit("Upload completed successfully.")



        except Exception as e:
            self.output.emit(f"Upload failed: {str(e)}")
            self.error.emit(f"Upload failed: {str(e)}")
        finally:
            # 10. Clean up local temporary files
            if os.path.exists(local_run_cr_path):
                ##os.remove(local_run_cr_path)
                self.output.emit(f"Cleaned up local {local_run_cr_path}")
            if os.path.exists(local_zip_path):
                ##os.remove(local_zip_path)
                self.output.emit(f"Cleaned up local {local_zip_path}")

    def initiate_multi_session_upload(self, selected_folders, selected_sessions, selected_mode, mobatch_paralel, mobatch_timeout):
        print(f"Manager received upload request for folders: {selected_folders} to sessions: {selected_sessions}")
        print(f"Upload mode: {selected_mode}")
        print(f"mobatch_paralel: {mobatch_paralel}, mobatch_timeout: {mobatch_timeout}")

        unconnected_sessions = []
        # Check connection status for all selected sessions
        for session_name in selected_sessions:
            # Find the correct SSHTab within the CRExecutorWidget
            tab = self.find_ssh_tab(session_name)
            # Check if tab was found and if it's connected
            if not tab or not tab.connected:
                unconnected_sessions.append(session_name)

        if unconnected_sessions:
            QMessageBox.warning(self, "Connection Error",
                                f"The following selected sessions are not connected:\n" +
                                "\n".join(unconnected_sessions) +
                                "\nPlease connect them before uploading.")
            print(f"Upload cancelled due to unconnected sessions: {unconnected_sessions}")
            return # Stop the upload process

        # SPLIT_RANDOMLY: Pre-split nodes among sessions before starting threads
        session_to_nodes = None
        if selected_mode == "SPLIT_RANDOMLY":
            # Gather all nodes from all selected folders
            all_nodes = []
            for folder in selected_folders:
                sites_list_path = os.path.join(folder, "sites_list.txt")
                if os.path.exists(sites_list_path):
                    with open(sites_list_path, encoding="utf-8") as f:
                        all_nodes.extend([line.strip() for line in f if line.strip()])
            random.shuffle(all_nodes)
            n_sessions = len(selected_sessions)
            split_nodes = [[] for _ in range(n_sessions)]
            for idx, node in enumerate(all_nodes):
                split_nodes[idx % n_sessions].append(node)
            session_to_nodes = {session: split_nodes[i] for i, session in enumerate(selected_sessions)}

        # If all selected sessions are connected, proceed with upload for each relevant tab
        print("All selected sessions are connected. Proceeding with upload...")
        for tab in self.cr_executor_widget.ssh_tabs: # Iterate through tabs in CRExecutorWidget
            if tab.target['session_name'] in selected_sessions:
                print(f"Triggering upload for session: {tab.target['session_name']}")
                assigned_nodes = None
                if selected_mode == "SPLIT_RANDOMLY" and session_to_nodes:
                    assigned_nodes = session_to_nodes.get(tab.target['session_name'], [])
                # Pass the mobatch execution mode to perform_sftp_and_remote_commands
                # Need to get the selected mode from the dialog. The signal should pass it.
                # Let's assume the signal now passes the mobatch_execution_mode as the 6th argument.
                # The signature of initiate_multi_session_upload should be updated accordingly.
                # It currently takes 5 arguments. Let's add mobatch_execution_mode.
                # The signal definition upload_requested in UploadCRDialog should be updated too.

                # For now, let's assume the mode is available (will fix signal/signature next)
                # We need the actual selected mobatch execution mode from the dialog here.
                # Since the signal is emitted from the dialog, the dialog has the selected mode.
                # The initiate_multi_session_upload method in SSHManager receives the signal.
                # The signal needs to carry the selected mobatch mode.

                # Let's go back and update the UploadCRDialog.initiate_upload to emit the mobatch mode.

                # This requires changes in multiple places. Let's start with the UploadCRDialog signal.

    # Note: The following code is commented out and serves as a guide for the next steps.
    # The actual changes will be made in subsequent tool calls.

    # Update UploadCRDialog.upload_requested signal:
    # upload_requested = pyqtSignal(list, list, str, int, int, str) # Add str for mobatch_execution_mode

    # Update UploadCRDialog.initiate_upload to get and emit mobatch_execution_mode:
    # def initiate_upload(self):
    #     # ... (get other values)
    #     if self.radio_python_mobatch.isChecked():
    #         mobatch_execution_mode = "PYTHON_MOBATCH"
    #     else:
    #         mobatch_execution_mode = "REGULAR_MOBATCH"
    #     # Emit the signal with the new argument
    #     self.upload_requested.emit(selected_folders_full_paths, selected_sessions, selected_mode, mobatch_paralel, mobatch_timeout, mobatch_execution_mode)
    #     # ... (rest of the method)

    # Update SSHManager.initiate_multi_session_upload signature:
    # def initiate_multi_session_upload(self, selected_folders, selected_sessions, selected_mode, mobatch_paralel, mobatch_timeout, mobatch_execution_mode):
    #     # ... (rest of the method)

    # Update SSHManager.initiate_multi_session_upload to pass the mode to tab.perform_sftp_and_remote_commands:
    #             tab.perform_sftp_and_remote_commands(selected_folders, selected_mode, selected_sessions, mobatch_paralel, mobatch_timeout, assigned_nodes=assigned_nodes, mobatch_execution_mode=mobatch_execution_mode)

    # Update SSHTab.perform_sftp_and_remote_commands signature:
    # def perform_sftp_and_remote_commands(self, selected_folders, selected_mode, selected_sessions=None, mobatch_paralel=70, mobatch_timeout=30, assigned_nodes=None, mobatch_execution_mode="REGULAR_MOBATCH"):
    #     # ... (rest of the method)

    # Update UploadWorker.__init__ signature:
    # def __init__(self, ssh_client, target_info, selected_folders, mode, selected_sessions=None, mobatch_paralel=70, mobatch_timeout=30, assigned_nodes=None, mobatch_execution_mode="REGULAR_MOBATCH"):
    #     # ... (rest of the method and store mobatch_execution_mode)

    # The logic in UploadWorker.run to use self.mobatch_execution_mode is already added in the current tool call.


    def open_download_log_dialog(self):
        dlg = DownloadLogDialog(ssh_targets, var_FOLDER_CR, self)
        dlg.download_requested.connect(self.handle_download_log_request)
        dlg.exec_()


class SSHTab(QWidget):
    def __init__(self, target, ssh_manager):
        super().__init__()
        self.target = target
        self.ssh_manager = ssh_manager
        self.layout = QVBoxLayout()

        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        font = QFont("Consolas", 10)
        self.output_box.setFont(font)
        self.output_box.setStyleSheet("background-color: black; color: #00FF00;")

        # Batch command area
        self.command_batch_RUN = QTextEdit()
        self.command_batch_RUN.setPlaceholderText("Enter batch commands here, one per line...")
        self.command_batch_RUN.setFixedHeight(80)
        self.send_batch_button = QPushButton("Send Batch")
        self.retry_upload_button = QPushButton("Retry Upload")

        self.input_line = QLineEdit()
        self.send_button = QPushButton("Send")
        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        self.screen_button = QPushButton("Screen Sessions")

        # Add a progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False) # Start hidden

        # Add batch area and button to layout
        self.layout.addWidget(self.command_batch_RUN)
        self.layout.addWidget(self.send_batch_button)
        self.layout.addWidget(self.retry_upload_button)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.input_line)
        button_layout.addWidget(self.send_button)
        button_layout.addWidget(self.connect_button)
        button_layout.addWidget(self.disconnect_button)
        button_layout.addWidget(self.screen_button)

        self.layout.addWidget(self.output_box)
        self.layout.addLayout(button_layout)
        self.layout.addWidget(self.progress_bar) # Add progress bar to layout
        self.setLayout(self.layout)

        self.ssh = None
        self.connected = False

        # Worker and thread instances
        self.upload_worker = None
        self.upload_thread = None

        self.send_button.clicked.connect(self.send_command)
        self.input_line.returnPressed.connect(self.send_command)
        self.connect_button.clicked.connect(self.connect_session)
        self.disconnect_button.clicked.connect(self.disconnect_session)
        self.screen_button.clicked.connect(self.open_screen_dialog)
        self.send_batch_button.clicked.connect(self.send_batch_commands)
        self.retry_upload_button.clicked.connect(self.retry_upload)

        self.update_button_states()

        self._output_buffer = []  # For batching output
        self._output_batch_size = 20
        self._output_timer = QTimer(self)
        self._output_timer.setInterval(100)  # ms
        self._output_timer.timeout.connect(self.flush_output)
        self._waiting_for_prompt = False

        # Command history
        self._command_history = []
        self._history_index = -1

        # Install event filter for auto-focus on all widgets after creation
        self._install_auto_focus_event_filter()

    def _install_auto_focus_event_filter(self):
        # Install event filter on self and all relevant widgets
        widgets = [
            self,
            self.output_box,
            self.command_batch_RUN,
            self.input_line,
            self.send_button,
            self.connect_button,
            self.disconnect_button,
            self.screen_button,
            self.send_batch_button,
            self.retry_upload_button,
        ]
        for w in widgets:
            w.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent, Qt
        # Command history navigation in input_line
        if obj == self.input_line and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Up:
                if self._command_history and self._history_index > 0:
                    self._history_index -= 1
                    self.input_line.setText(self._command_history[self._history_index])
                    self.input_line.setCursorPosition(len(self.input_line.text()))
                return True
            elif event.key() == Qt.Key_Down:
                if self._command_history and self._history_index < len(self._command_history) - 1:
                    self._history_index += 1
                    self.input_line.setText(self._command_history[self._history_index])
                    self.input_line.setCursorPosition(len(self.input_line.text()))
                elif self._history_index == len(self._command_history) - 1:
                    self._history_index += 1
                    self.input_line.clear()
                return True
            else:
                # Reset history index on normal typing
                self._history_index = len(self._command_history)
        # Auto-focus input_line on any key press in the tab or its widgets
        if event.type() == QEvent.KeyPress:
            # Check if the source of the event is the batch command text edit
            if obj == self.command_batch_RUN:
                return super().eventFilter(obj, event) # Let batch command handle its own key press

            if not self.input_line.hasFocus():
                self.input_line.setFocus()
        return super().eventFilter(obj, event)

    def connect_session(self):
        if not self.connected:
            self.output_box.append(f"Connecting to {self.target['session_name']}...")
            self.output_box.append("Waiting for prompt...")
            self._waiting_for_prompt = True
            self.ssh = InteractiveSSH(**self.target)
            self.ssh.output_received.connect(self.append_output)
            self.ssh.start()
            self.connected = True
            self.update_button_states()

    def disconnect_session(self):
        if self.connected and self.ssh:
            self.ssh._write_log("Disconnected")
            self.ssh.close()
            self.connected = False
            self.update_button_states()

    def update_button_states(self):
        self.connect_button.setEnabled(not self.connected)
        self.disconnect_button.setEnabled(self.connected)
        self.screen_button.setEnabled(self.connected)

    def append_output(self, text):
        # If waiting for prompt, clear the waiting message on first real output
        if self._waiting_for_prompt:
            # Remove 'Waiting for prompt...' from the end if present
            cursor = self.output_box.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.output_box.setTextCursor(cursor)
            content = self.output_box.toPlainText()
            if content.endswith("Waiting for prompt...\n") or content.endswith("Waiting for prompt..."):
                # Remove the last line
                lines = content.splitlines()
                if lines and lines[-1] == "Waiting for prompt...":
                    self.output_box.setPlainText("\n".join(lines[:-1]))
            self._waiting_for_prompt = False
        self._output_buffer.append(text)
        if len(self._output_buffer) >= self._output_batch_size:
            self.flush_output()
        else:
            if not self._output_timer.isActive():
                self._output_timer.start()

    def flush_output(self):
        if self._output_buffer:
            self.output_box.moveCursor(QTextCursor.End)
            self.output_box.insertPlainText('\n'.join(self._output_buffer) + '\n')
            self.output_box.moveCursor(QTextCursor.End)
            self._output_buffer.clear()
            QApplication.processEvents()
        self._output_timer.stop()

    def send_command(self):
        cmd = self.input_line.text()
        if self.ssh:
            # Always send, even if empty (just ENTER)
            self.ssh.send_command(cmd)
            # Only store non-empty commands in history
            if cmd.strip():
                if not self._command_history or self._command_history[-1] != cmd:
                    self._command_history.append(cmd)
            self._history_index = len(self._command_history)
            self.input_line.clear() # Clear the input line after sending
            self.flush_output() # Immediately flush output buffer after sending command

    def open_screen_dialog(self):
        if self.ssh:
            dlg = ScreenSelectionDialog(self.ssh, self)
            dlg.exec_()

    def handle_upload_request(self, selected_folders, selected_sessions):
        print("handle_upload_request called (delegating to manager)")

    def perform_sftp_and_remote_commands(self, selected_folders, selected_mode, selected_sessions=None, mobatch_paralel=70, mobatch_timeout=30, assigned_nodes=None, mobatch_execution_mode="REGULAR_MOBATCH"):
        print("WEWWW")
        print(selected_sessions)
        self.append_output("Preparing for SFTP upload and remote commands...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.upload_thread = QThread()
        # Pass var_FOLDER_CR from ssh_manager to UploadWorker
        self.upload_worker = UploadWorker(self.ssh.client, self.target, selected_folders, selected_mode, selected_sessions, mobatch_paralel, mobatch_timeout, assigned_nodes, mobatch_execution_mode, var_FOLDER_CR=self.ssh_manager.var_FOLDER_CR)
        self.upload_worker.moveToThread(self.upload_thread)
        self.upload_thread.started.connect(self.upload_worker.run)
        self.upload_worker.progress.connect(self.update_progress_bar)
        self.upload_worker.output.connect(self.append_output)
        self.upload_worker.completed.connect(self.upload_finished)
        self.upload_worker.error.connect(self.upload_finished)
        self.upload_worker.completed.connect(self.cleanup_upload_thread)
        self.upload_worker.error.connect(self.cleanup_upload_thread)
        self.upload_thread.finished.connect(self.upload_thread.deleteLater)
        self.upload_thread.finished.connect(self.upload_worker.deleteLater)
        self.upload_thread.start()

    def cleanup_upload_thread(self, _=None):
        if self.upload_thread:
            self.upload_thread.quit()
            self.upload_thread.wait()
        self.upload_worker = None
        self.upload_thread = None

    def update_progress_bar(self, value):
        self.progress_bar.setValue(value)

    def upload_finished(self, message):
        self.append_output(message)
        self.progress_bar.setVisible(False) # Hide progress bar when finished

        # Show error in a message box if upload failed
        if 'failed' in message.lower() or 'error' in message.lower():
            QMessageBox.critical(self, "Upload Error", message)
        else:
            # On success, populate the batch run textarea with cd and ls commands
            # Use var_FOLDER_CR and var_SCREEN_CR from ssh_manager
            remote_base_dir = f"/home/shared/{self.target['username']}/{self.ssh_manager.var_FOLDER_CR}"
            ENM_SERVER = self.target['session_name']
            # Use CMD_BATCH_SEND_FORMAT from ssh_manager
            self.command_batch_RUN.setPlainText(self.ssh_manager.CMD_BATCH_SEND_FORMAT.format(remote_base_dir=remote_base_dir, ENM_SERVER=ENM_SERVER, screen_session=self.ssh_manager.var_SCREEN_CR))
            # Automatically send the batch commands
            self.send_batch_commands()
        # No need to clean up worker/thread here; handled by cleanup_upload_thread

    def send_batch_commands(self):
        if not self.ssh:
            self.append_output("[ERROR] Not connected.")
            return
        commands = self.command_batch_RUN.toPlainText().splitlines()
        for line in commands:
            cmd = line.strip()
            if cmd:
                self.ssh.send_command(cmd)

    def retry_upload(self):
        ENM_SERVER = self.target['session_name']
        tmp_dir = os.path.join("Temp", f"tmp_upload_{ENM_SERVER}")
        local_run_cr_path = os.path.join(tmp_dir, f"RUN_CR_{ENM_SERVER}.txt")
        local_zip_path = os.path.join(tmp_dir, f"SFTP_CR_{ENM_SERVER}.zip")
        # Use var_FOLDER_CR from ssh_manager
        remote_base_dir = f"/home/shared/{self.target['username']}/{self.ssh_manager.var_FOLDER_CR}"
        remote_zip_path = f"{remote_base_dir}/SFTP_CR_{ENM_SERVER}.zip"
        remote_run_cr_path = f"{remote_base_dir}/RUN_CR_{ENM_SERVER}.txt"
        if not (os.path.exists(local_run_cr_path) and os.path.exists(local_zip_path)):
            self.append_output(f"[RETRY] No temp upload files found for {ENM_SERVER}.")
            return
        self.append_output(f"[RETRY] Retrying upload for {ENM_SERVER}...")
        try:
            sftp = self.ssh.client.open_sftp()
            self.append_output("[RETRY] SFTP connection established.")
            # Upload zip
            self.append_output(f"[RETRY] Uploading {local_zip_path} to {remote_zip_path}")
            sftp.put(local_zip_path, remote_zip_path)
            self.append_output(f"[RETRY] Uploaded {local_zip_path}.")
            # Upload RUN_CR
            self.append_output(f"[RETRY] Uploading {local_run_cr_path} to {remote_run_cr_path}")
            sftp.put(local_run_cr_path, remote_run_cr_path)
            self.append_output(f"[RETRY] Uploaded {local_run_cr_path}.")
            sftp.close()
            self.append_output("[RETRY] SFTP connection closed.")
            # Unzip and execute remotely
            self.append_output(f"[RETRY] Unzipping {os.path.basename(local_zip_path)} on remote server...")
            unzip_command = f"cd {remote_base_dir} && unzip -o {os.path.basename(local_zip_path)}"
            stdin, stdout, stderr = self.ssh.client.exec_command(unzip_command)
            self.append_output("[RETRY] Remote unzip output:")
            self.append_output(stdout.read().decode())
            error_output = stderr.read().decode()
            if error_output:
                self.append_output(f"[RETRY] Remote unzip error: {error_output}")
            self.append_output(f"[RETRY] Executing remote command: ./{os.path.basename(local_run_cr_path)}")
            execute_command = f"cd {remote_base_dir} && ./{os.path.basename(local_run_cr_path)}"
            stdin, stdout, stderr = self.ssh.client.exec_command(execute_command)
            self.append_output("[RETRY] Remote execution output:")
            self.append_output(stdout.read().decode())
            error_output = stderr.read().decode()
            if error_output:
                self.append_output(f"[RETRY] Remote execution error: {error_output}")
            self.append_output("[RETRY] Upload and remote execution process finished.")
            # Set and send batch commands after retry
            # Use CMD_BATCH_SEND_FORMAT and var_SCREEN_CR from ssh_manager
            self.command_batch_RUN.setPlainText(self.ssh_manager.CMD_BATCH_SEND_FORMAT.format(remote_base_dir=remote_base_dir, ENM_SERVER=ENM_SERVER, screen_session=self.ssh_manager.var_SCREEN_CR))
            self.send_batch_commands()
        except Exception as e:
            self.append_output(f"[RETRY] Upload failed: {str(e)}")


class SubfolderLoaderWorker(QObject):
    finished = pyqtSignal(list)
    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path
    def run(self):
        subfolders = []
        try:
            for item_name in os.listdir(self.folder_path):
                item_path = os.path.join(self.folder_path, item_name)
                if os.path.isdir(item_path):
                    subfolders.append(item_name)
        except Exception:
            pass
        self.finished.emit(subfolders)


class UploadCRDialog(QDialog):
    upload_requested = pyqtSignal(list, list, str, int, int, str, list)

    def __init__(self, ssh_targets, parent=None, ssh_manager=None):
        print('[PROFILE] UploadCRDialog __init__ start')
        t0 = time.time()
        super().__init__(parent)
        self.ssh_targets = ssh_targets
        self.ssh_manager = ssh_manager
        self.setWindowTitle("Upload CR")
        self.setMinimumSize(500, 400)
        layout = QVBoxLayout()

        # 1. Button browse folder and display selected parent folder
        folder_browse_layout = QHBoxLayout()
        self.parent_folder_label = QLineEdit("Selected Parent Folder: ")
        self.parent_folder_label.setReadOnly(True)
        self.browse_button = QPushButton("Browse Parent Folder")
        folder_browse_layout.addWidget(self.parent_folder_label)
        folder_browse_layout.addWidget(self.browse_button)
        layout.addLayout(folder_browse_layout)

        # New: List widget to display subfolders for multi-selection
        subfolder_label = QLabel("Select Subfolders to Upload:")
        layout.addWidget(subfolder_label)
        self.subfolder_list_widget = QListWidget()
        self.subfolder_list_widget.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.subfolder_list_widget)

        # 2. Multi selection from SSH session
        session_label = QLabel("Select SSH Sessions:")
        layout.addWidget(session_label)
        self.session_list_widget = QListWidget()
        self.session_list_widget.setSelectionMode(QListWidget.MultiSelection)
        for target in self.ssh_targets:
            self.session_list_widget.addItem(target['session_name'])
        layout.addWidget(self.session_list_widget)

        # 2.5. Add mode selection
        mode_label = QLabel("Select IPDB/Random Split Mode:")
        layout.addWidget(mode_label)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["TRUE", "DTAC", "SPLIT_RANDOMLY"])
        layout.addWidget(self.mode_combo)

        # New: Radio buttons for Mobatch Execution Mode
        mobatch_mode_label = QLabel("Select Mobatch Execution Mode:")
        layout.addWidget(mobatch_mode_label)

        self.mobatch_mode_group = QButtonGroup(self)
        self.radio_python_mobatch = QRadioButton("PYTHON_MOBATCH")
        self.radio_regular_mobatch = QRadioButton("REGULAR_MOBATCH")
        self.radio_regular_mobatch.setChecked(True) # Default to regular

        self.mobatch_mode_group.addButton(self.radio_python_mobatch)
        self.mobatch_mode_group.addButton(self.radio_regular_mobatch)

        mobatch_mode_layout = QHBoxLayout()
        mobatch_mode_layout.addWidget(self.radio_python_mobatch)
        mobatch_mode_layout.addWidget(self.radio_regular_mobatch)
        mobatch_mode_layout.addStretch()
        layout.addLayout(mobatch_mode_layout)

        # 2.6. Add mobatch parameters
        mobatch_layout = QHBoxLayout()
        self.mobatch_paralel_input = QLineEdit("70")
        self.mobatch_paralel_input.setPlaceholderText("mobatch_paralel")
        self.mobatch_paralel_input.setFixedWidth(80)
        self.mobatch_timeout_input = QLineEdit("30")
        self.mobatch_timeout_input.setPlaceholderText("mobatch_timeout")
        self.mobatch_timeout_input.setFixedWidth(80)
        mobatch_layout.addWidget(QLabel("mobatch_paralel:"))
        mobatch_layout.addWidget(self.mobatch_paralel_input)
        mobatch_layout.addWidget(QLabel("mobatch_timeout:"))
        mobatch_layout.addWidget(self.mobatch_timeout_input)
        mobatch_layout.addStretch()
        layout.addLayout(mobatch_layout)

        # 3. Button "UPLOAD"
        upload_button_layout = QHBoxLayout()
        self.upload_button = QPushButton("UPLOAD")
        upload_button_layout.addStretch() # Push button to the right
        upload_button_layout.addWidget(self.upload_button)
        layout.addLayout(upload_button_layout)

        self.setLayout(layout)

        # Store the selected parent folder path
        self.selected_parent_folder = None

        # Connect signals
        self.browse_button.clicked.connect(self.browse_parent_folder)
        self.upload_button.clicked.connect(self.initiate_upload)

        print(f'[PROFILE] UploadCRDialog __init__ end, elapsed: {time.time() - t0:.3f}s')

    def browse_parent_folder(self):
        # Use QFileDialog to select a single parent directory
        print('[PROFILE] QFileDialog.getExistingDirectory start')
        t0 = time.time()
        dlg = QFileDialog(self)
        dlg.setOption(QFileDialog.DontUseNativeDialog, True)
        folder_path = dlg.getExistingDirectory(self, "Select Parent Folder Containing CRs")
        print(f'[PROFILE] QFileDialog.getExistingDirectory end, elapsed: {time.time() - t0:.3f}s')

        if folder_path:
            self.selected_parent_folder = folder_path
            self.parent_folder_label.setText("Selected Parent Folder: " + folder_path)
            # Populate the subfolder list widget with directories inside the selected parent folder
            self.subfolder_list_widget.clear()
            self.subfolder_list_widget.addItem("Loading...")
            self.subfolder_list_widget.setEnabled(False)
            # Start background thread to load subfolders
            self.subfolder_loader_thread = QThread()
            self.subfolder_loader_worker = SubfolderLoaderWorker(folder_path)
            self.subfolder_loader_worker.moveToThread(self.subfolder_loader_thread)
            self.subfolder_loader_thread.started.connect(self.subfolder_loader_worker.run)
            self.subfolder_loader_worker.finished.connect(self.on_subfolders_loaded)
            self.subfolder_loader_worker.finished.connect(self.subfolder_loader_thread.quit)
            self.subfolder_loader_worker.finished.connect(self.subfolder_loader_worker.deleteLater)
            self.subfolder_loader_thread.finished.connect(self.subfolder_loader_thread.deleteLater)
            self.subfolder_loader_thread.start()
        else:
            self.selected_parent_folder = None
            self.parent_folder_label.setText("Selected Parent Folder: ")
            self.subfolder_list_widget.clear()

    def on_subfolders_loaded(self, subfolders):
        self.subfolder_list_widget.clear()
        if subfolders:
            for item_name in subfolders:
                self.subfolder_list_widget.addItem(item_name)
        self.subfolder_list_widget.setEnabled(True)

    def initiate_upload(self):
        selected_sessions = [item.text() for item in self.session_list_widget.selectedItems()]
        selected_subfolder_names = [item.text() for item in self.subfolder_list_widget.selectedItems()]

        if not self.selected_parent_folder:
            QMessageBox.warning(self, "No Parent Folder Selected", "Please select a parent folder first.")
            return

        if not selected_subfolder_names:
            QMessageBox.warning(self, "No Subfolders Selected", "Please select at least one subfolder to upload.")
            return

        if not selected_sessions:
            QMessageBox.warning(self, "No Sessions Selected", "Please select at least one SSH session.")
            return

        # Construct full paths of the selected subfolders
        selected_folders_full_paths = [os.path.join(self.selected_parent_folder, subfolder_name) for subfolder_name in selected_subfolder_names]

        # Get selected mode
        selected_mode = self.mode_combo.currentText()

        # Get mobatch params
        try:
            mobatch_paralel = int(self.mobatch_paralel_input.text())
        except Exception:
            mobatch_paralel = 70
        try:
            mobatch_timeout = int(self.mobatch_timeout_input.text())
        except Exception:
            mobatch_timeout = 30

        # Get mobatch execution mode
        if self.radio_python_mobatch.isChecked():
            mobatch_execution_mode = "PYTHON_MOBATCH"
        else:
            mobatch_execution_mode = "REGULAR_MOBATCH"

        # Connect the signal to the SSHManager's handler before emitting
        if self.ssh_manager:
             self.upload_requested.connect(self.ssh_manager.initiate_multi_session_upload)

        # Emit the signal with the full paths of selected subfolders and sessions
        self.upload_requested.emit(selected_folders_full_paths, selected_sessions, selected_mode, mobatch_paralel, mobatch_timeout, mobatch_execution_mode, self.ssh_targets)

        # Disconnect the signal after emitting to prevent multiple connections
        if self.ssh_manager:
             self.upload_requested.disconnect(self.ssh_manager.initiate_multi_session_upload)

        self.accept() # Close the dialog after emitting the signal


# New Dialog for multi-session connection selection
class MultiConnectDialog(QDialog):
    def __init__(self, targets, parent=None):
        super().__init__(parent)
        self.targets = targets
        self.setWindowTitle("Select Sessions to Connect")
        self.setMinimumSize(300, 200)
        layout = QVBoxLayout()

        label = QLabel("Select SSH Sessions to Connect:")
        layout.addWidget(label)

        self.session_list_widget = QListWidget()
        self.session_list_widget.setSelectionMode(QListWidget.MultiSelection)
        for target in self.targets:
            self.session_list_widget.addItem(target['session_name'])
        layout.addWidget(self.session_list_widget)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.setLayout(layout)

    def getSelectedSessions(self):
        return [item.text() for item in self.session_list_widget.selectedItems()]


class DownloadLogDialog(QDialog):
    download_requested = pyqtSignal(list, str)

    def __init__(self, targets, var_FOLDER_CR_value, parent=None):
        super().__init__(parent)
        self.targets = targets
        # Store var_FOLDER_CR as an instance variable
        self.var_FOLDER_CR = var_FOLDER_CR_value
        self.setWindowTitle("Download LOG")
        self.setMinimumSize(500, 300)
        layout = QVBoxLayout()

        # Session selection
        session_label = QLabel("Select SSH Sessions:")
        layout.addWidget(session_label)
        self.session_list_widget = QListWidget()
        self.session_list_widget.setSelectionMode(QListWidget.MultiSelection)
        for target in self.targets:
            self.session_list_widget.addItem(target['session_name'])
        layout.addWidget(self.session_list_widget)

        # Download path input
        path_label = QLabel("Remote LOG Path to Download:")
        layout.addWidget(path_label)
        self.download_path_input = QLineEdit()
        self.download_path_input.setText(f"~/{self.var_FOLDER_CR}/LOG/")           
        layout.addWidget(self.download_path_input)

        # Download button
        button_layout = QHBoxLayout()
        self.download_button = QPushButton("DOWNLOAD")
        button_layout.addStretch()
        button_layout.addWidget(self.download_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        self.download_button.clicked.connect(self.emit_download_request)
        ##self.session_list_widget.itemSelectionChanged.connect(self.update_default_path)

    def update_default_path(self):
        selected_items = self.session_list_widget.selectedItems()
        if selected_items:
            session_name = selected_items[0].text()
            for target in self.targets:
                if target['session_name'] == session_name:
                    username = target['username']
                    self.download_path_input.setText(f"/home/shared/{username}/{self.var_FOLDER_CR}/LOG/")
                    break

    def emit_download_request(self):
        selected_sessions = [item.text() for item in self.session_list_widget.selectedItems()]
        download_path = self.download_path_input.text().strip()
        if not selected_sessions:
            QMessageBox.warning(self, "No Sessions Selected", "Please select at least one SSH session.")
            return
        if not download_path:
            QMessageBox.warning(self, "No Download Path", "Please enter a remote path to download.")
            return
        self.download_requested.emit(selected_sessions, download_path)
        self.accept()



class DownloadLogWorker(QObject):
    output = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, target, remote_path, var_FOLDER_CR):
        super().__init__()
        self.target = target
        self.remote_path = remote_path
        self.var_FOLDER_CR = var_FOLDER_CR

    def run(self):
        username = self.target['username']
        host = self.target['host']
        port = self.target['port']
        password = self.target['password']
        remote_zip = f"/home/shared/{username}/00_download.zip"
        local_dir = "02_DOWNLOAD"
        os.makedirs(local_dir, exist_ok=True)
        local_zip = os.path.join(local_dir, f"{self.target['session_name']}_download.zip")

        try:
            self.output.emit(f"Connecting to {host}...")
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(host, port, username, password)



            self.output.emit(f"Connected to {host}. Zipping remote log folder...")

            # Zip the remote folder
            # Use self.var_FOLDER_CR
            zip_cmd = f"cd {os.path.dirname(self.remote_path.rstrip('/'))} && zip -r {remote_zip} {os.path.basename(self.remote_path.rstrip('/'))}"
            stdin, stdout, stderr = client.exec_command(zip_cmd)
            out = stdout.read().decode()
            err = stderr.read().decode()

            if err:
                self.output.emit(f"[ZIP ERROR] {err}")
            if out:
                self.output.emit(f"[ZIP OUTPUT] {out}")

            if err and ("zip error" in err.lower() or "permission denied" in err.lower()):
                self.output.emit(f"Remote zipping failed with error. Skipping download.")
                self.error.emit(f"Download failed for {self.target['session_name']}: Remote zipping failed.")
                client.close()
                return


            # Wait for 5 seconds before checking the remote folder
            time.sleep(5)


            # Check if remote folder has files
            check_files_cmd = f"find {remote_zip} -type f | wc -l"
            stdin, stdout, stderr = client.exec_command(check_files_cmd)
            file_count_output = stdout.read().decode().strip()
            file_count_error = stderr.read().decode().strip()


            if not file_count_output.isdigit() or int(file_count_output) == 0:
                self.output.emit(f"[SKIP] No files found in {self.remote_path}. Skipping zip and download.")
                self.completed.emit(f"No files to download for {self.target['session_name']}")
                client.close()
                return


            # Download the zip
            self.output.emit(f"Downloading {remote_zip} to {local_zip} ...")
            sftp = client.open_sftp()
            try:
                remote_file_size = sftp.stat(remote_zip).st_size
            except Exception as e:
                self.output.emit(f"[SFTP STAT ERROR] {e}")
                remote_file_size = 0

            def progress_callback(transferred, total):
                if total > 0:
                    percent = int(transferred / total * 100)
                    self.progress.emit(percent)

            self.progress.emit(0)
            sftp.get(remote_zip, local_zip, callback=progress_callback)
            self.progress.emit(100)
            sftp.close()
            self.output.emit(f"Downloaded to {local_zip}")

            # Validate zip file
            try:
                with zipfile.ZipFile(local_zip, 'r') as zf:
                    pass
                self.output.emit(f"Successfully downloaded and validated {local_zip}")
            except zipfile.BadZipFile:
                self.output.emit(f"[WARNING] Downloaded file {local_zip} is a bad zip file. Deleting...")
                if os.path.exists(local_zip):
                    os.remove(local_zip)
                    self.output.emit(f"Deleted bad zip file: {local_zip}")

            # Remove remote zip file
            rm_cmd = f"rm -f {remote_zip}"
            client.exec_command(rm_cmd)
            client.close()

            self.completed.emit(f"Download completed for {self.target['session_name']}")

        except Exception as e:
            self.output.emit(f"Download failed for {self.target['session_name']}: {e}")
            self.error.emit(f"Download failed for {self.target['session_name']}: {e}")



class ConcheckToolsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()

        # File selection layout
        file_select_layout = QHBoxLayout()
        self.file_path_label = QLineEdit("No file selected")
        self.file_path_label.setReadOnly(True)
        self.browse_button = QPushButton("Browse File")
        file_select_layout.addWidget(self.file_path_label)
        file_select_layout.addWidget(self.browse_button)
        layout.addLayout(file_select_layout)

        # Concheck button
        self.run_concheck_button = QPushButton("Run Concheck")
        layout.addWidget(self.run_concheck_button)

        # Results text area
        self.results_text_edit = QTextEdit()
        self.results_text_edit.setReadOnly(True)
        layout.addWidget(self.results_text_edit)

        self.setLayout(layout)

        # Connect signals
        self.browse_button.clicked.connect(self.browse_file)
        self.run_concheck_button.clicked.connect(self.run_concheck_process)

        self.selected_file_path = None

    def browse_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File for Concheck", "", "All Files (*);;Text Files (*.txt)", options=options)
        if file_path:
            self.selected_file_path = file_path
            self.file_path_label.setText(f"Selected File: {file_path}")
            self.results_text_edit.clear() # Clear previous results

    def run_concheck_process(self):
        if not self.selected_file_path:
            QMessageBox.warning(self, "No File Selected", "Please select a file first.")
            return

        self.results_text_edit.clear()
        self.results_text_edit.append("Running concheck...")
        QApplication.processEvents() # Update UI

        try:
            # Call the run_concheck function from lib.concheck
            results = run_concheck(self.selected_file_path)
            self.results_text_edit.append("Concheck Results:")
            for line in results:
                self.results_text_edit.append(line)
            self.results_text_edit.append("Concheck finished.")
        except Exception as e:
            self.results_text_edit.append(f"Error running concheck: {e}")


class CRExecutorWidget(QWidget):
    def __init__(self, targets, ssh_manager, parent=None, session_type="TRUE"):
        super().__init__(parent)
        self.ssh_manager = ssh_manager
        self.targets = targets  # Store targets
        self.session_type = session_type # Store the type (TRUE or DTAC)

        main_layout = QVBoxLayout(self)

        # Create a layout for the top buttons (like Connect Selected)
        top_button_layout = QHBoxLayout() # Use QHBoxLayout for horizontal arrangement
        self.connect_selected_button = QPushButton("Connect Selected Sessions")
        self.download_log_button = QPushButton("Download LOG")
        self.upload_cr_button = QPushButton("UPLOAD CR")
        top_button_layout.addWidget(self.connect_selected_button)
        top_button_layout.addWidget(self.download_log_button)
        top_button_layout.addWidget(self.upload_cr_button)
        top_button_layout.addStretch() # Push buttons to the left

        # Add the top button layout to the main layout
        main_layout.addLayout(top_button_layout)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs) # Add tabs to the main layout

        self.ssh_tabs = []

        # Make tabs closable
        self.tabs.setTabsClosable(False) # Set to False to disable closing tabs
        # Connect the tab close requested signal
        # self.tabs.tabCloseRequested.connect(self.ssh_manager.close_ssh_tab) # Disconnect this signal

        for target in targets:
            # Pass self (the SSHManager instance) to the SSHTab
            # Pass ssh_manager to SSHTab as well
            tab = SSHTab(target, ssh_manager)
            self.ssh_tabs.append(tab)
            self.tabs.addTab(tab, target['session_name'])

        # Connect the new button's signal
        self.connect_selected_button.clicked.connect(lambda _: self.ssh_manager.open_multi_connect_dialog(self.targets)) # Connect to manager's method, pass current targets
        self.download_log_button.clicked.connect(lambda _: self.ssh_manager.open_download_log_dialog(self.targets)) # Connect to manager's method, pass current targets
        self.upload_cr_button.clicked.connect(lambda _: self.ssh_manager.open_upload_cr_dialog(self.targets)) # Connect to manager's method, pass current targets


class SSHManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CR TOOLS")

        # Load configuration from settings.json
        settings_path = os.path.join(os.path.dirname(__file__), 'settings.json')
        self.var_FOLDER_CR = "00_CR_FOLDER_DEFAULT" # Default value
        self.var_SCREEN_CR = "mob_tools_default" # Default value
        self.ssh_targets_true = [] # Default value
        self.ssh_targets_dtac = [] # Default value
        self.CMD_BATCH_SEND_FORMAT = "cd {remote_base_dir}\nls -ltrh\n pkill -f \"SCREEN.*{screen_session}\" \n screen -S {screen_session} \n bash -i  RUN_CR_{ENM_SERVER}.txt && exit\n" # Default

        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            self.var_FOLDER_CR = settings.get('var_FOLDER_CR', self.var_FOLDER_CR)
            self.var_SCREEN_CR = settings.get('var_SCREEN_CR', self.var_SCREEN_CR)
            self.ssh_targets_true = settings.get('ssh_targets_true', self.ssh_targets_true)
            self.ssh_targets_dtac = settings.get('ssh_targets_dtac', self.ssh_targets_dtac)
            self.CMD_BATCH_SEND_FORMAT = settings.get('CMD_BATCH_SEND_FORMAT', self.CMD_BATCH_SEND_FORMAT)

        except FileNotFoundError:
            QMessageBox.critical(self, "Configuration Error", f"settings.json not found at {settings_path}. Using default values.")
            print(f"Error: settings.json not found at {settings_path}. Using default values.")

        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Configuration Error", f"Error decoding settings.json at {settings_path}: {e}. Using default values.")
            print(f"Error: Could not decode settings.json at {settings_path}: {e}. Using default values.")
        except Exception as e:
            QMessageBox.critical(self, "Configuration Error", f"An unexpected error occurred loading settings.json: {e}. Using default values.")
            print(f"Unexpected error loading settings.json: {e}. Using default values.")

        # Create Menu Bar
        self.menu_bar = self.menuBar()
        self.tools_menu = self.menu_bar.addMenu("Tools")

        # Add Actions
        self.action_cr_executor_true = QAction("CR EXECUTOR TRUE", self)
        self.action_cr_executor_dtac = QAction("CR EXECUTOR DTAC", self)
        self.action_concheck_tools = QAction("CONCHECK TOOLS", self)

        self.tools_menu.addAction(self.action_cr_executor_true)
        self.tools_menu.addAction(self.action_cr_executor_dtac)
        self.tools_menu.addAction(self.action_concheck_tools)

        # Create Stacked Widget
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget) # Set stacked widget as central widget

        # Create Widgets for each form
        # The CR Executor widget will be created dynamically when a menu option is selected
        self.cr_executor_widget = None
        self.concheck_tools_widget = ConcheckToolsWidget() # Create the new widget

        # Add widgets to the stacked widget
        self.stacked_widget.addWidget(self.concheck_tools_widget)

        # Connect menu actions to switch widgets
        self.action_cr_executor_true.triggered.connect(lambda: self.show_cr_executor_form(self.ssh_targets_true, "TRUE"))
        self.action_cr_executor_dtac.triggered.connect(lambda: self.show_cr_executor_form(self.ssh_targets_dtac, "DTAC"))
        self.action_concheck_tools.triggered.connect(self.show_concheck_tools_form)

        # Show the CR EXECUTOR form initially (default to TRUE)
        self.show_cr_executor_form(self.ssh_targets_true, "TRUE")

        # Profile tab change event - Keep this in SSHManager as it relates to the overall window
        # Connect after the widget is created
        # self.cr_executor_widget.tabs.currentChanged.connect(self.profile_tab_change)
        self._last_tab_switch_time = None

        # Make tabs closable - This setup is now handled within CRExecutorWidget
        # self.tabs.setTabsClosable(True)
        # Connect the tab close requested signal - This is now connected in CRExecutorWidget
        # self.tabs.tabCloseRequested.connect(self.close_ssh_tab)

        # The initial tab creation is now handled in CRExecutorWidget.__init__
        # for target in targets:
        #     tab = SSHTab(target, self)
        #     self.ssh_tabs.append(tab)
        #     self.tabs.addTab(tab, target['session_name'])

        # Connect the new button's signal - This is now connected in CRExecutorWidget
        # self.connect_selected_button.clicked.connect(self.open_multi_connect_dialog)
        # self.download_log_button.clicked.connect(self.open_download_log_dialog)
        # self.upload_cr_button.clicked.connect(self.open_upload_cr_dialog)


    def show_cr_executor_form(self, targets, session_type):
        """Displays the CR Executor form with the specified targets."""
        # Clean up the old CR Executor widget if it exists
        if self.cr_executor_widget:
            # Perform cleanup actions before removing
            # Iterate over a copy of the list because close_ssh_tab modifies self.cr_executor_widget.ssh_tabs
            for index in range(self.cr_executor_widget.tabs.count()):
                tab = self.cr_executor_widget.tabs.widget(0) # Always close the first tab as indices shift
                self.close_ssh_tab(0) # Use index 0 because tabs are removed

            # Remove the old widget from the stacked widget and delete it
            self.stacked_widget.removeWidget(self.cr_executor_widget)
            self.cr_executor_widget.deleteLater() # Schedule for deletion
            self.cr_executor_widget = None

        # Create a new CR Executor widget with the new targets and session type
        self.cr_executor_widget = CRExecutorWidget(targets, self, session_type=session_type)
        self.stacked_widget.addWidget(self.cr_executor_widget)
        self.stacked_widget.setCurrentWidget(self.cr_executor_widget)

        # Connect the tab change signal for the new widget
        self.cr_executor_widget.tabs.currentChanged.connect(self.profile_tab_change)

    def show_concheck_tools_form(self):
        self.stacked_widget.setCurrentWidget(self.concheck_tools_widget)

    # The following methods are kept in SSHManager as they manage dialogs/processes
    # that interact with multiple tabs or the overall application.

    def open_multi_connect_dialog(self, targets):
        # Ensure targets is a list before proceeding
        if not isinstance(targets, list):
            QMessageBox.critical(self, "Internal Error", f"Received invalid data for sessions. Expected list, got {type(targets).__name__}")
            print(f"Error: open_multi_connect_dialog received unexpected targets type: {type(targets).__name__}")
            return

        # Open the dialog with the passed targets
        dlg = MultiConnectDialog(targets, self)
        if dlg.exec_() == QDialog.Accepted:
            selected_sessions = dlg.getSelectedSessions()
            # Pass the list of ALL targets for the current session type to connect_multiple_sessions
            self.connect_multiple_sessions(selected_sessions)

    def connect_multiple_sessions(self, selected_sessions):
        print(f"Attempting to connect to selected sessions: {selected_sessions}")
        for session_name in selected_sessions:
            # Find the correct SSHTab within the CRExecutorWidget
            tab = self.find_ssh_tab(session_name)
            if tab:
                 # Check if already connected to avoid reconnecting
                 if not tab.connected:
                     self.append_output_to_tab(session_name, f"Connecting to {session_name}...")
                     tab.connect_session()
                 else:
                     self.append_output_to_tab(session_name, f"{session_name} is already connected.")

    def find_ssh_tab(self, session_name):
        """Helper to find an SSHTab by session name."""
        for tab in self.cr_executor_widget.ssh_tabs:
            if tab.target['session_name'] == session_name:
                return tab
        return None

    def append_output_to_tab(self, session_name, text):
        # Helper to find the correct tab and append output
        tab = self.find_ssh_tab(session_name)
        if tab:
            tab.append_output(text)

    def close_ssh_tab(self, index):
        # Get the tab widget at the requested index from the CRExecutorWidget's tabs
        tab_to_close = self.cr_executor_widget.tabs.widget(index)

        # Instead of calling close_session, do the cleanup inline
        if isinstance(tab_to_close, SSHTab):
            # Disconnect SSH session
            tab_to_close.disconnect_session()
            # Stop the upload thread if it's running
            if tab_to_close.upload_thread and tab_to_close.upload_thread.isRunning():
                tab_to_close.append_output("Stopping upload thread...")
                if tab_to_close.upload_worker:
                    tab_to_close.upload_worker.stop()
                tab_to_close.upload_thread.quit()
                tab_to_close.upload_thread.wait()
                tab_to_close.append_output("Upload thread stopped.")
            tab_to_close.upload_worker = None
            tab_to_close.upload_thread = None
            # Remove the tab from the QTabWidget
            self.cr_executor_widget.tabs.removeTab(index)
            # Optionally remove the tab from our internal list as well
            if tab_to_close in self.cr_executor_widget.ssh_tabs: # Remove from CRExecutorWidget's list
                self.cr_executor_widget.ssh_tabs.remove(tab_to_close)

    def closeEvent(self, event):
        print("Closing SSH Manager...")
        # Iterate over a copy of the list because we modify cr_executor_widget.ssh_tabs
        if self.cr_executor_widget:
            for tab in self.cr_executor_widget.ssh_tabs[:]:
             # Inline cleanup (was close_session)
             tab.disconnect_session()
             if tab.upload_thread and tab.upload_thread.isRunning():
                tab.append_output("Stopping upload thread...")
                if tab.upload_worker:
                    tab.upload_worker.stop()
                tab.upload_thread.quit()
                tab.upload_thread.wait()
                tab.append_output("Upload thread stopped.")
             tab.upload_worker = None
             tab.upload_thread = None
        print("Accepting close event.")
        event.accept()

    def initiate_multi_session_upload(self, selected_folders, selected_sessions, selected_mode, mobatch_paralel, mobatch_timeout, mobatch_execution_mode, all_targets_for_session_type):
        print(f"Manager received upload request for folders: {selected_folders} to sessions: {selected_sessions}")
        print(f"Upload mode: {selected_mode}")
        print(f"mobatch_paralel: {mobatch_paralel}, mobatch_timeout: {mobatch_timeout}")

        # Use the targets passed from the dialog (which came from the active CRExecutorWidget)
        current_targets = all_targets_for_session_type

        unconnected_sessions = []
        # Check connection status for all selected sessions
        for session_name in selected_sessions:
            # Find the correct SSHTab within the CRExecutorWidget
            # Find the tab based on the *current* set of targets being managed by the active CRExecutorWidget
            tab = self.find_ssh_tab(session_name) # This method finds tabs in the current cr_executor_widget
            # Check if tab was found and if it's connected
            if not tab or not tab.connected:
                unconnected_sessions.append(session_name)

        if unconnected_sessions:
            QMessageBox.warning(self, "Connection Error",
                                f"The following selected sessions are not connected:\n" +
                                "\n".join(unconnected_sessions) +
                                "\nPlease connect them before uploading.")
            print(f"Upload cancelled due to unconnected sessions: {unconnected_sessions}")
            return # Stop the upload process

        #### cleanup list temporary
        for folder in selected_folders:
            # Clean up existing sites_list_*.txt files in the current folder
            for file_name in os.listdir(folder):
                 if file_name.startswith('sites_list_') and file_name.endswith('.txt'):
                     file_path = os.path.join(folder, file_name)
                     try:
                         os.remove(file_path)
                         print(f"Cleaned up old sites_list file in {folder}: {file_name}")
                     except Exception as e:
                         print(f"[WARNING] Failed to remove old sites_list file {file_name} in {folder}: {e}")  

        
        # SPLIT_RANDOMLY: Pre-split nodes among sessions before starting threads
        session_to_nodes = None
        if selected_mode == "SPLIT_RANDOMLY":
            # Gather all nodes from all selected folders
            all_nodes = []

          
         
            for folder in selected_folders:
                sites_list_path = os.path.join(folder, "sites_list.txt")
                if os.path.exists(sites_list_path):
                    with open(sites_list_path, encoding="utf-8") as f:
                        all_nodes.extend([line.strip() for line in f if line.strip()])
            random.shuffle(all_nodes)
            n_sessions = len(selected_sessions)
            split_nodes = [[] for _ in range(n_sessions)]
            for idx, node in enumerate(all_nodes):
                split_nodes[idx % n_sessions].append(node)
            session_to_nodes = {session: split_nodes[i] for i, session in enumerate(selected_sessions)}
            # Print the result
            print(selected_sessions)
            for i, group in enumerate(split_nodes):
                print("Session {} nodes: {}".format(i + 1, group))

        # If all selected sessions are connected, proceed with upload for each relevant tab
        print("All selected sessions are connected. Proceeding with upload...WWWW")
        print()
        for tab in self.cr_executor_widget.ssh_tabs: # Iterate through tabs in CRExecutorWidget
            if tab.target['session_name'] in selected_sessions:
                print(f"Triggering upload for session: {tab.target['session_name']}")
                assigned_nodes = None
                assigned_nodes = session_to_nodes
                ##if selected_mode == "SPLIT_RANDOMLY" and session_to_nodes:
                    ##assigned_nodes = session_to_nodes.get(tab.target['session_name'], [])
                # Pass the relevant subset of targets to the perform method if needed, or just the assigned nodes
                tab.perform_sftp_and_remote_commands(selected_folders, selected_mode, selected_sessions, mobatch_paralel, mobatch_timeout, assigned_nodes=assigned_nodes, mobatch_execution_mode=mobatch_execution_mode) # selected_sessions is list of names, assigned_nodes contains the mapping

    def open_download_log_dialog(self, targets):
        # Ensure targets is a list before proceeding
        if not isinstance(targets, list):
            QMessageBox.critical(self, "Internal Error", f"Received invalid data for sessions. Expected list, got {type(targets).__name__}")
            print(f"Error: open_download_log_dialog received unexpected targets type: {type(targets).__name__}")
            return

        if not self.cr_executor_widget:
            QMessageBox.warning(self, "No Sessions Available", "Cannot open download dialog without available sessions.")
            return

        # Open the dialog with the passed targets and var_FOLDER_CR from instance variable
        dlg = DownloadLogDialog(targets, self.var_FOLDER_CR, self)
        dlg.download_requested.connect(self.handle_download_log_request)
        dlg.exec_()

    def handle_download_log_request(self, selected_sessions, download_path):
        # Get the current targets from the active CR Executor widget
        current_targets = []
        if self.cr_executor_widget:
             current_targets = self.cr_executor_widget.targets

        # Clear the 02_DOWNLOAD directory before starting new downloads
        download_dir = os.path.join(os.path.dirname(__file__), '02_DOWNLOAD')
        if os.path.exists(download_dir):
            print(f"Clearing directory: {download_dir}")
            for item in os.listdir(download_dir):
                item_path = os.path.join(download_dir, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path) # remove file or link
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path) # remove directory
                except Exception as e:
                    print(f"Error removing {item_path}: {e}")

        # Defensive: Clean up any previous download threads before starting new ones
        for tab in self.cr_executor_widget.ssh_tabs:
            if hasattr(tab, 'download_thread') and tab.download_thread is not None:
                if tab.download_thread.isRunning():
                    tab.append_output("Cleaning up previous download thread...")
                    tab.download_thread.quit()
                    tab.download_thread.wait()
                    tab.append_output("Previous download thread stopped.")
                tab.download_thread = None
                tab.download_worker = None
                tab.progress_bar.setVisible(False)

        # Track how many downloads are pending
        self._pending_downloads = len(selected_sessions)
        self._download_tabs = [] # Keep track of tabs involved in download

        def on_download_finished():
            self._pending_downloads -= 1
            if self._pending_downloads == 0:
                # All downloads finished, run the check and export
                try:
                    check_logs_and_export_to_excel(self)
                    QMessageBox.information(self, "Check Exported", "Log check completed and exported to 02_DOWNLOAD/Check.xlsx")
                except Exception as e:
                    QMessageBox.critical(self, "Check Export Error", f"Failed to export check: {e}")

        # For each selected session, start a download worker
        for session_name in selected_sessions:
            # Find the correct SSHTab within the CRExecutorWidget
            tab = self.find_ssh_tab(session_name)
            if not tab:
                continue # Skip if tab not found (shouldn't happen if selected from dialog)
            # Pass self.var_FOLDER_CR to the DownloadLogWorker constructor
            worker = DownloadLogWorker(tab.target, download_path, self.var_FOLDER_CR)
            thread = QThread()
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.output.connect(tab.append_output)
            worker.completed.connect(tab.append_output)
            worker.error.connect(tab.append_output)
            worker.progress.connect(tab.update_progress_bar)
            # Show progress bar at start
            tab.progress_bar.setValue(0)
            tab.progress_bar.setVisible(True)

            # Store thread and worker on the tab for cleanup
            tab.download_thread = thread
            tab.download_worker = worker
            self._download_tabs.append(tab) # Add tab to tracking list

            def cleanup(tab=tab): # Use default argument to capture current tab
                if hasattr(tab, 'download_thread') and tab.download_thread is not None:
                    if tab.download_thread.isRunning():
                        tab.download_thread.quit()
                        tab.download_thread.wait() # Wait for thread to finish
                    tab.download_thread = None
                    tab.download_worker = None
                    tab.progress_bar.setVisible(False)

            # Connect signals using lambda to pass the specific tab instance
            worker.completed.connect(lambda: cleanup(tab))
            worker.error.connect(lambda: cleanup(tab))
            worker.completed.connect(on_download_finished)
            worker.error.connect(on_download_finished)
            worker.completed.connect(worker.deleteLater)
            worker.error.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.start()

    def profile_tab_change(self, index):
        import time
        t0 = time.time()
        print(f'[PROFILE] Tab change to index {index} started')
        # Optionally, you can do more here (e.g., check which tab, log tab name)
        QApplication.processEvents()  # Let the UI update
        t1 = time.time()
        print(f'[PROFILE] Tab change to index {index} finished, elapsed: {t1 - t0:.3f}s')

    def open_upload_cr_dialog(self, targets):
        # Ensure targets is a list before proceeding
        if not isinstance(targets, list):
            QMessageBox.critical(self, "Internal Error", f"Received invalid data for sessions. Expected list, got {type(targets).__name__}")
            print(f"Error: open_upload_cr_dialog received unexpected targets type: {type(targets).__name__}")
            return

        if not self.cr_executor_widget:
             QMessageBox.warning(self, "No Sessions Available", "Cannot open upload dialog without available sessions.")
             return

        # Open the upload CR dialog with the passed targets
        dlg = UploadCRDialog(targets, parent=self, ssh_manager=self)
        dlg.exec_()


def check_logs_and_export_to_excel(parent=None):
    import os
    import pandas as pd
    import zipfile

    download_dir = os.path.join(os.path.dirname(__file__), '02_DOWNLOAD')
    zip_files = [fname for fname in os.listdir(download_dir) if fname.lower().endswith('.zip')]
    result_rows = []
    progress = None

    # Identify non-empty zip files
    loop_zip_ok_file = []
    total_zips = len(zip_files)
    if QApplication.instance() is not None:
        progress = QProgressDialog("Checking zip files...", None, 0, total_zips, parent)
        progress.setWindowTitle("Checking Zips")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.setCancelButton(None)
        progress.show()

    for idx, fname in enumerate(zip_files):
        zip_path = os.path.join(download_dir, fname)
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Check if the zip file is empty
                if zf.namelist(): # Check if namelist is NOT empty
                    loop_zip_ok_file.append(zip_path)
                else:
                    print(f"[INFO] Skipping empty zip file: {fname}")
        except zipfile.BadZipFile:
            print(f"Skipping bad zip file: {fname}")
        except Exception as e:
            print(f"Error processing zip file {fname} during check: {e}")

        if progress is not None:
            progress.setValue(idx + 1)
            QApplication.processEvents()

    if progress is not None:
        progress.close()

    # Now process the non-empty zip files
    if QApplication.instance() is not None:
        progress = QProgressDialog("Checking logs and exporting...", None, 0, len(loop_zip_ok_file), parent)
        progress.setWindowTitle("Checking Logs")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.setCancelButton(None)
        progress.show() # This might block the UI update, consider using a timer or worker for heavy tasks


    result_rows = []

    for idx, zip_path in enumerate(loop_zip_ok_file):
        fname = os.path.basename(zip_path)
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for member in zf.namelist():
                    # Looking for LOG/<ANY_FOLDER>/<NODENAME>.log
                    parts = member.split('/')
                    if len(parts) == 3 and parts[0] == 'LOG' and parts[2].endswith('.log'):
                        folder = parts[1]
                        nodename = parts[2][:-4]  # remove .log
                        try:
                            with zf.open(member) as f:
                                # Read lines safely, handle potential errors
                                try:
                                    lines = [line.decode(errors='ignore').strip() for line in f.readlines()]
                                except Exception as read_err:
                                     print(f"Error reading {member} in {fname}: {read_err}")
                                     lines = [] # Assign empty list on error

                            # Update: UNREMOTE if either condition is met
                            if any('Checking ip contact...Not OK' in line for line in lines) or any(line.startswith('Unable to connect to ') for line in lines):
                                remark = 'UNREMOTE'
                            else:
                                remark = 'OK'
                            result_rows.append({
                                'FILE': fname,
                                'FOLDER': folder,
                                'NODENAME': nodename,
                                'REMARK': remark,
                                'Count': len(lines)
                            })
                        except Exception as open_err:
                            print(f"Error opening {member} in {fname}: {open_err}")
        except zipfile.BadZipFile:
            # This should ideally not happen if we checked in the first loop,
            # but keeping for robustness.
            print(f"Skipping bad zip file during processing: {fname}")
        except Exception as e:
            print(f"Error processing zip file {fname}: {e}")

        if progress is not None:
            progress.setValue(idx + 1)
            QApplication.processEvents() # Allow UI updates

    if progress is not None:
        progress.close()
    df = pd.DataFrame(result_rows, columns=['FILE', 'FOLDER', 'NODENAME', 'REMARK', 'Count'])
    out_path = os.path.join(download_dir, 'Check.xlsx')
    df.to_excel(out_path, index=False)
    print(f"Exported check results to {out_path}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SSHManager()
    window.resize(1000, 600)
    window.show()
    sys.exit(app.exec_())
