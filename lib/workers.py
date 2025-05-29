# Worker classes

from PyQt5.QtCore import pyqtSignal, QObject, QThread, QFileInfo
from PyQt5.QtWidgets import QMessageBox # Needed for UploadWorker and DownloadLogWorker
import os
import shutil # Needed for UploadWorker and DownloadLogWorker cleanup
import pandas as pd # Needed for UploadWorker and check_logs_and_export_to_excel
import random # Needed for logic in UploadWorker but worker itself doesn't use it directly. Keeping import for now.
import time # Needed for UploadWorker and DownloadLogWorker
import zipfile # Needed for UploadWorker and DownloadLogWorker

# Import utility functions if needed by the worker
from .utils import remove_ansi_escape_sequences # Although not directly used in these workers' run methods, it's used in classes that might interact with them or in related utility code.

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
                ipdb_path = os.path.join("00_IPDB", "ipdb_delim_ALLOSS_NEW.txt")
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
                # This part needs to be handled in the main GUI thread, perhaps by emitting a signal
                # from the worker back to the SSHTab that initiated it.
                # For now, I will leave this as is, but note that direct access to
                # self.ssh or self.ssh_client.shell might not be safe from a worker thread.
                pass # Removing this section as it's not safe in a worker
            except Exception as e:
                # Log the error, but don't stop the process
                self.output.emit(f"Failed to send 'cd' command after upload: {e}")


            self.output.emit("Upload and remote execution process finished.")
            self.completed.emit("Upload completed successfully.")



        except Exception as e:
            self.output.emit(f"Upload failed: {str(e)}")
            self.error.emit(f"Upload failed: {str(e)}")
        finally:
            # 10. Clean up local temporary files
            if os.path.exists(local_run_cr_path):
                ##os.remove(local_run_cr_path) # Keep temp files for retry
                self.output.emit(f"Kept local {local_run_cr_path} for retry.")
            if os.path.exists(local_zip_path):
                ##os.remove(local_zip_path) # Keep temp files for retry
                self.output.emit(f"Kept local {local_zip_path} for retry.")

    # The initiate_multi_session_upload method is not part of the worker,
    # it should remain in SSHManager.

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