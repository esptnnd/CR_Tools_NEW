# -----------------------------------------------------------------------------
# Author      : esptnnd
# Company     : Ericsson Indonesia
# Created on  : 7 May 2025
# Description : CR TOOLS by esptnnd — built for the ECT Project to help the team
#               execute faster, smoother, and with way less hassle.
#               Making life easier, one script at a time!
# -----------------------------------------------------------------------------

# Dialog classes

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout, QMessageBox,
    QLineEdit, QLabel, QComboBox, QButtonGroup, QRadioButton, QFileDialog, QProgressDialog,
    QDialogButtonBox, QCheckBox
)
from PyQt5.QtCore import QEventLoop, QTimer, QObject, pyqtSignal, QThread, Qt
import re
import os
import time
import random

# Import utility functions and worker classes
from .utils import remove_ansi_escape_sequences # May not be directly used here, but good to keep relevant imports.
from .workers import SubfolderLoaderWorker, DownloadLogWorker # Import workers used by these dialogs


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

    def refresh_screens(self, text):
        self.list_widget.clear()
        self._output_buffer.clear()
        self._collecting = True

        # Temporarily connect to capture output for screen -ls
        # Note: This assumes ssh.output_received is available and safe to connect/disconnect
        # Consider making this more robust if ssh might be None or in a bad state.
        try:
            self.ssh.output_received.connect(self._buffer_output)
            self.ssh.send_command("screen -ls")

            # Wait a bit for output
            loop = QEventLoop()
            QTimer.singleShot(1500, loop.quit) # Wait for 1.5 seconds
            loop.exec_()

        finally:
            self._collecting = False
            # Disconnect after collecting to avoid multiple connections
            try:
                if self.ssh and self.ssh.output_received:
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
            # Ensure remove_ansi_escape_sequences is imported or defined
            # Assuming it's imported from .utils
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
            if self.ssh:
                self.ssh.send_command(f"screen -r {session}")
                self.accept()
            else:
                 QMessageBox.warning(self, "SSH Error", "SSH session is not active.")
        else:
            QMessageBox.warning(self, "No Selection", "Please select a valid screen session to connect.")

    def detach_screen(self):
        if self.ssh:
            self.ssh.detach_screen()
        else:
             QMessageBox.warning(self, "SSH Error", "SSH session is not active.")

    def close(self):
        super().close() # Use super().close() to properly close the dialog


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

        # New: ComboBox for Mobatch Execution Mode
        mobatch_mode_label = QLabel("Select Mobatch Execution Mode:")
        layout.addWidget(mobatch_mode_label)

        self.mobatch_mode_combo = QComboBox()
        self.mobatch_mode_combo.addItems([
            "PYTHON_MOBATCH",
            "REGULAR_MOBATCH",
            "REGULAR_MOBATCH_nodelete",
            "CMBULK IMPORT"
        ])
        self.mobatch_mode_combo.setCurrentText("REGULAR_MOBATCH")
        layout.addWidget(self.mobatch_mode_combo)

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
        mobatch_execution_mode = self.mobatch_mode_combo.currentText()

        # Connect the signal to the SSHManager's handler before emitting
        # The connection needs to be made by the parent (SSHManager) when creating the dialog, not here.
        # Removing the connect and disconnect calls from here.
        # if self.ssh_manager:
        #      self.upload_requested.connect(self.ssh_manager.initiate_multi_session_upload)

        # Emit the signal with the full paths of selected subfolders and sessions
        # Assuming ssh_manager is the parent and has the slot connected
        self.upload_requested.emit(selected_folders_full_paths, selected_sessions, selected_mode, mobatch_paralel, mobatch_timeout, mobatch_execution_mode, self.ssh_targets)

        # Disconnect the signal after emitting to prevent multiple connections
        # if self.ssh_manager:
        #      self.upload_requested.disconnect(self.ssh_manager.initiate_multi_session_upload)

        self.accept() # Close the dialog after emitting the signal


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
    download_requested = pyqtSignal(list, str, str)

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
        # Use self.var_FOLDER_CR for the default path
        self.download_path_input = QLineEdit(f"~/{self.var_FOLDER_CR}/LOG/")
        layout.addWidget(self.download_path_input)

        # Add Log Checking Mode ComboBox
        self.log_check_mode_combo = QComboBox()
        self.log_check_mode_combo.addItems([
            "Normal Log Checking",
            "Normal Compare Before Checking",
            "3G_MOCN_CELL_LTE Checking"
        ])
        self.log_check_mode_combo.setCurrentText("Normal Log Checking")
        layout.addWidget(self.log_check_mode_combo)

        # Download button
        button_layout = QHBoxLayout()
        self.download_button = QPushButton("DOWNLOAD")
        button_layout.addStretch()
        button_layout.addWidget(self.download_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        self.download_button.clicked.connect(self.emit_download_request)

    def emit_download_request(self):
        selected_sessions = [item.text() for item in self.session_list_widget.selectedItems()]
        download_path = self.download_path_input.text().strip()
        log_check_mode = self.log_check_mode_combo.currentText()
        
        if not selected_sessions:
            QMessageBox.warning(self, "No Sessions Selected", "Please select at least one SSH session.")
            return
        if not download_path:
            QMessageBox.warning(self, "No Download Path", "Please enter a remote path to download.")
            return
        # Emit the signal with log_check_mode parameter
        self.download_requested.emit(selected_sessions, download_path, log_check_mode)
        self.accept()