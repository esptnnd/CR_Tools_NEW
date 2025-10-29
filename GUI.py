# -----------------------------------------------------------------------------
# Author      : esptnnd
# Company     : Ericsson Indonesia
# Created on  : 7 May 2025
# Improve on  : 29 May 2025
# Description : CR TOOLS by esptnnd — built for the ECT Project to help the team
#               execute faster, smoother, and with way less hassle.
#               Making life easier, one script at a time!
# -----------------------------------------------------------------------------

import sys
import os
import json
import random
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QVBoxLayout, QTextEdit, QLineEdit, QPushButton, QHBoxLayout,
    QMessageBox, QProgressBar, QDialog,
    QMenuBar, QAction, QStackedWidget, QLabel, QFileDialog,
    QListWidget, QAbstractItemView
)
from PyQt5.QtCore import QObject, QTimer, QThread, Qt, QEventLoop, QEvent, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor, QPalette, QBrush, QPixmap, QPainter, QIcon, QImage, QColor, QLinearGradient, QPen
import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
import re
import time
from datetime import datetime
import zipfile
from collections import Counter
from queue import Queue
import mmap
from concurrent.futures import ProcessPoolExecutor, as_completed

# Import modules from the lib directory
from lib.concheck import run_concheck
from lib.ssh import InteractiveSSH
from lib.dialogs import ScreenSelectionDialog, MultiConnectDialog, UploadCRDialog, DownloadLogDialog, DuplicateSessionDialog
from lib.utils import debug_print, duplicate_session
from lib.workers import UploadWorker, DownloadLogWorker
from lib.widgets import ConcheckToolsWidget, CRExecutorWidget, ExcelReaderApp, WorkerThread, CMBulkFileMergeWidget, RehomingScriptToolsWidget
from lib.log_checker import check_logs_and_export_to_excel
from lib.report_generator import process_single_log, CATEGORY_CHECKING, CATEGORY_CHECKING1, write_logs_to_excel
from lib.style import (
    TransparentTextEdit, setup_window_style, update_window_style,
    StyledPushButton, StyledLineEdit, StyledProgressBar, StyledLabel,
    StyledListWidget, StyledContainer
)
from lib.SSHTab import SSHTab
from lib.utils import debug_print

class SSHManager(QMainWindow):
    def __init__(self):
        start_time = time.time()
        debug_print(f"[TIMER] Start __init__ at {start_time}")
        super().__init__()
        debug_print(f"[TIMER] After super().__init__: {time.time() - start_time:.2f}s")
        self.setWindowTitle("CR TOOLS by esptnnd")
        
        # Setup window styling
        setup_window_style(self)
        debug_print(f"[TIMER] After setup_window_style: {time.time() - start_time:.2f}s")

        # Load configuration from settings.json
        settings_path = os.path.join(os.path.dirname(__file__), 'settings.json')
        var_FOLDER_CR = "00_CR_FOLDER_DEFAULT" # Default value
        var_SCREEN_CR = "mob_tools_default" # Default value
        self.ssh_targets_true = [] # Default value
        self.ssh_targets_dtac = [] # Default value
        self.CMD_BATCH_SEND_FORMAT = "cd {remote_base_dir}\nls -ltrh\n pkill -f \"SCREEN.*{screen_session}\" \n screen -S {screen_session} \n bash -i  RUN_CR_{ENM_SERVER}.txt && exit\n" # Default
        self.CMD_BATCH_SEND_FORMAT_CMBULK = (
            "cd {remote_base_dir}\n"
            "ls -ltrh\n"
            "grep -h -v NOT_EXIST_PATTERN */0*_{ENM_SERVER}*txt > CMBULK_{ENM_SERVER}.txt\n"
            "mkdir -p {remote_base_dir}/LOG/\n"
            "##python CMBULK_import.py upload CMBULK_{ENM_SERVER}.txt \n"
            "python CMBULK_import.py stat\n"
            "python CMBULK_import.py stat 9999 > {remote_base_dir}/LOG/CMBULK_{ENM_SERVER}.txt\n"
        )        
        self.START_PATH = os.path.expanduser('~')

        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            var_FOLDER_CR = settings.get('var_FOLDER_CR', var_FOLDER_CR)
            var_SCREEN_CR = settings.get('var_SCREEN_CR', var_SCREEN_CR)
            self.ssh_targets_true = settings.get('ssh_targets_true', self.ssh_targets_true)
            self.ssh_targets_dtac = settings.get('ssh_targets_dtac', self.ssh_targets_dtac)
            self.CMD_BATCH_SEND_FORMAT = settings.get('CMD_BATCH_SEND_FORMAT', self.CMD_BATCH_SEND_FORMAT)
            self.CMD_BATCH_SEND_FORMAT_CMBULK = settings.get('CMD_BATCH_SEND_FORMAT_CMBULK', self.CMD_BATCH_SEND_FORMAT_CMBULK)
            self.START_PATH = settings.get('START_PATH', self.START_PATH)
            self.DEBUG_MODE = settings.get('DEBUG_MODE', 'DEBUG')
            if self.DEBUG_MODE == 'DEBUG':
                debug_print(f"[TIMER] After loading settings.json: {time.time() - start_time:.2f}s")

        except FileNotFoundError:
            QMessageBox.critical(self, "Configuration Error", f"settings.json not found at {settings_path}. Using default values.")
            if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                debug_print(f"Error: settings.json not found at {settings_path}. Using default values.")

        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Configuration Error", f"Error decoding settings.json at {settings_path}: {e}. Using default values.")
            if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                debug_print(f"Error: Could not decode settings.json at {settings_path}: {e}. Using default values.")
        except Exception as e:
            QMessageBox.critical(self, "Configuration Error", f"An unexpected error occurred loading settings.json: {e}. Using default values.")
            if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                debug_print(f"Unexpected error loading settings.json: {e}. Using default values.")
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f"[TIMER] After config load: {time.time() - start_time:.2f}s")

        # Create Menu Bar
        self.menu_bar = self.menuBar()
        self.menu_cr_executor = self.menu_bar.addMenu("CR EXECUTOR")
        self.menu_tools = self.menu_bar.addMenu("Other Tools")

        # Add Actions
        self.action_cr_executor_true = QAction("CR EXECUTOR TRUE", self)
        self.action_cr_executor_dtac = QAction("CR EXECUTOR DTAC", self)
        self.action_concheck_tools = QAction("CR REPORT GENERATOR", self)
        self.action_cmbulk_file_merge = QAction("CMBULK FILE MERGE", self)
        self.action_rehoming_script_tools = QAction("Rehoming SCRIPT Tools", self)

        self.menu_cr_executor.addAction(self.action_cr_executor_true)
        self.menu_cr_executor.addAction(self.action_cr_executor_dtac)
        self.menu_tools.addAction(self.action_rehoming_script_tools)
        self.menu_tools.addAction(self.action_concheck_tools)
        self.menu_tools.addAction(self.action_cmbulk_file_merge)
        
        
        
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f"[TIMER] After menu setup: {time.time() - start_time:.2f}s")

        # Create Stacked Widget
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        # Create separate widgets for TRUE and DTAC modes
        widget_time = time.time()
        self.cr_executor_widget_true = CRExecutorWidget(self.ssh_targets_true, self, session_type="TRUE", var_FOLDER_CR=var_FOLDER_CR, var_SCREEN_CR=var_SCREEN_CR)
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f"[TIMER] After cr_executor_widget_true: {time.time() - widget_time:.2f}s")
        widget_time = time.time()
        self.cr_executor_widget_dtac = CRExecutorWidget(self.ssh_targets_dtac, self, session_type="DTAC", var_FOLDER_CR=var_FOLDER_CR, var_SCREEN_CR=var_SCREEN_CR)
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f"[TIMER] After cr_executor_widget_dtac: {time.time() - widget_time:.2f}s")
        widget_time = time.time()
        self.excel_reader_app = ExcelReaderApp(start_path=self.START_PATH)
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f"[TIMER] After excel_reader_app: {time.time() - widget_time:.2f}s")
        widget_time = time.time()
        self.cmbulk_file_merge_widget = CMBulkFileMergeWidget(start_path=self.START_PATH)
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f"[TIMER] After cmbulk_file_merge_widget: {time.time() - widget_time:.2f}s")
        widget_time = time.time()
        self.rehoming_script_tools_widget = RehomingScriptToolsWidget(start_path=self.START_PATH)
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f"[TIMER] After rehoming_script_tools_widget: {time.time() - widget_time:.2f}s")

        # Add widgets to the stacked widget
        self.stacked_widget.addWidget(self.cr_executor_widget_true)
        self.stacked_widget.addWidget(self.cr_executor_widget_dtac)
        self.stacked_widget.addWidget(self.excel_reader_app)
        self.stacked_widget.addWidget(self.cmbulk_file_merge_widget)
        self.stacked_widget.addWidget(self.rehoming_script_tools_widget)
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f"[TIMER] After adding widgets to stacked_widget: {time.time() - start_time:.2f}s")

        # Connect menu actions to switch widgets
        self.action_cr_executor_true.triggered.connect(self.show_cr_executor_true)
        self.action_cr_executor_dtac.triggered.connect(self.show_cr_executor_dtac)
        self.action_concheck_tools.triggered.connect(self.show_concheck_tools_form)
        self.action_cmbulk_file_merge.triggered.connect(self.show_cmbulk_file_merge_form)
        self.action_rehoming_script_tools.triggered.connect(self.show_rehoming_script_tools_form)

        # Connect tab change signals for both CR Executor widgets
        self.cr_executor_widget_true.tabs.currentChanged.connect(self.profile_tab_change)
        self.cr_executor_widget_dtac.tabs.currentChanged.connect(self.profile_tab_change)

        # Show the TRUE CR Executor form initially
        self.show_cr_executor_true()
        
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f"[TIMER] End of __init__: {time.time() - start_time:.2f}s")

    # ...existing code...

    def resizeEvent(self, event):
        # Update window styling when resized
        update_window_style(self)
        super().resizeEvent(event)

    def show_cr_executor_true(self):
        """Shows the TRUE CR Executor form."""
        self.stacked_widget.setCurrentWidget(self.cr_executor_widget_true)
        self.setWindowTitle(f"CR TOOLS by esptnnd - CR EXECUTOR TRUE")
        # Ensure background stays behind
        if hasattr(self, 'background_label'):
            self.background_label.lower()

    def show_cr_executor_dtac(self):
        """Shows the DTAC CR Executor form."""
        self.stacked_widget.setCurrentWidget(self.cr_executor_widget_dtac)
        self.setWindowTitle(f"CR TOOLS by esptnnd - CR EXECUTOR DTAC")
        # Ensure background stays behind
        if hasattr(self, 'background_label'):
            self.background_label.lower()

    def show_concheck_tools_form(self):
        """Shows the Excel Reader form."""
        self.stacked_widget.setCurrentWidget(self.excel_reader_app)
        self.setWindowTitle(f"CR TOOLS by esptnnd - CR REPORT GENERATOR")
        # Ensure background stays behind
        if hasattr(self, 'background_label'):
            self.background_label.lower()

    def show_cmbulk_file_merge_form(self):
        self.stacked_widget.setCurrentWidget(self.cmbulk_file_merge_widget)
        self.setWindowTitle(f"CR TOOLS by esptnnd - CMBULK FILE MERGE")
        if hasattr(self, 'background_label'):
            self.background_label.lower()

    def show_rehoming_script_tools_form(self):
        self.stacked_widget.setCurrentWidget(self.rehoming_script_tools_widget)
        self.setWindowTitle(f"CR TOOLS by esptnnd - Rehoming SCRIPT Tools")
        if hasattr(self, 'background_label'):
            self.background_label.lower()

    def get_current_cr_executor_widget(self):
        """Returns the currently active CR Executor widget."""
        current_widget = self.stacked_widget.currentWidget()
        if isinstance(current_widget, CRExecutorWidget):
            return current_widget
        return None

    def open_multi_connect_dialog(self, targets):
        # Ensure targets is a list before proceeding
        if not isinstance(targets, list):
            QMessageBox.critical(self, "Internal Error", f"Received invalid data for sessions. Expected list, got {type(targets).__name__}")
            if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                debug_print(f"Error: open_multi_connect_dialog received unexpected targets type: {type(targets).__name__}")
            return

        # Open the dialog with the passed targets
        dlg = MultiConnectDialog(targets, self)
        if dlg.exec_() == QDialog.Accepted:
            selected_sessions = dlg.getSelectedSessions()
            current_widget = self.get_current_cr_executor_widget()
            if current_widget:
                self.connect_multiple_sessions(selected_sessions)
            else:
                if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                    debug_print("Error: No active CR Executor widget to connect sessions.")

    def connect_multiple_sessions(self, selected_sessions):
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f"Attempting to connect to selected sessions: {selected_sessions}")
        current_widget = self.get_current_cr_executor_widget()
        if not current_widget:
            if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                debug_print("Error: No active CR Executor widget to connect sessions.")
            return

        for session_name in selected_sessions:
            tab = self.find_ssh_tab(session_name)
            if tab:
                if not tab.connected:
                    self.append_output_to_tab(session_name, f"Connecting to {session_name}...")
                    tab.connect_session()
                else:
                    self.append_output_to_tab(session_name, f"{session_name} is already connected.")

    def find_ssh_tab(self, session_name):
        """Helper to find an SSHTab by session name in the current CRExecutorWidget."""
        current_widget = self.get_current_cr_executor_widget()
        if current_widget:
            for tab in current_widget.ssh_tabs:
                if tab.target['session_name'] == session_name:
                    return tab
        return None

    def append_output_to_tab(self, session_name, text):
        # Helper to find the correct tab and append output
        tab = self.find_ssh_tab(session_name)
        if tab:
            tab.append_output(text)

    def closeEvent(self, event):
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print("Closing SSH Manager...")
        # Clean up all tabs in both CR Executor widgets before closing
        if self.cr_executor_widget_true:
            self.cleanup_cr_executor_tabs(self.cr_executor_widget_true)
        if self.cr_executor_widget_dtac:
            self.cleanup_cr_executor_tabs(self.cr_executor_widget_dtac)
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print("Accepting close event.")
        event.accept()

    def profile_tab_change(self, index):
        import time
        t0 = time.time()
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f'[PROFILE] Tab change to index {index} started')
        # Optionally, you can do more here (e.g., check which tab, log tab name)
        # QApplication.processEvents()  # Removed to avoid potential re-entrancy issues
        t1 = time.time()
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print(f'[PROFILE] Tab change to index {index} finished, elapsed: {t1 - t0:.3f}s')

    def open_upload_cr_dialog(self, targets):
        # Ensure targets is a list before proceeding
        if not isinstance(targets, list):
            QMessageBox.critical(self, "Internal Error", f"Received invalid data for sessions. Expected list, got {type(targets).__name__}")
            if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                debug_print(f"Error: open_upload_cr_dialog received unexpected targets type: {type(targets).__name__}")
            return

        if not self.get_current_cr_executor_widget():
             QMessageBox.warning(self, "No Sessions Available", "Cannot open upload dialog without available sessions.")
             return

        # Open the upload CR dialog with the passed targets
        # Use UploadCRDialog from lib.dialogs
        dlg = UploadCRDialog(targets, parent=self, ssh_manager=self, start_path=self.START_PATH)

        # Connect the dialog's upload_requested signal to the SSHManager's handler
        dlg.upload_requested.connect(self.initiate_multi_session_upload)

        dlg.exec_()

    def initiate_multi_session_upload(self, selected_folders, selected_sessions, selected_mode, mobatch_paralel, mobatch_timeout, mobatch_execution_mode, mobatch_extra_argument, all_targets_for_session_type, collect_prepost_checked, custom_cmd_format=None):
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print("[CR_DEBUG_SIGNAL] Arguments received in initiate_multi_session_upload:")
            debug_print(f"  selected_folders={selected_folders} type={type(selected_folders)}")
            debug_print(f"  selected_sessions={selected_sessions} type={type(selected_sessions)}")
            debug_print(f"  selected_mode={selected_mode} type={type(selected_mode)}")
            debug_print(f"  mobatch_paralel={mobatch_paralel} type={type(mobatch_paralel)}")
            debug_print(f"  mobatch_timeout={mobatch_timeout} type={type(mobatch_timeout)}")
            debug_print(f"  mobatch_execution_mode={mobatch_execution_mode} type={type(mobatch_execution_mode)}")
            debug_print(f"  mobatch_extra_argument={mobatch_extra_argument} type={type(mobatch_extra_argument)}")
            debug_print(f"  all_targets_for_session_type={all_targets_for_session_type} type={type(all_targets_for_session_type)}")
            debug_print(f"  collect_prepost_checked={collect_prepost_checked} type={type(collect_prepost_checked)}")
            debug_print(f"  custom_cmd_format={custom_cmd_format} type={type(custom_cmd_format)}")
        debug_print("SSHManager: initiate_multi_session_upload called.") # Debug print
        debug_print(f"Manager received upload request for folders: {selected_folders} to sessions: {selected_sessions}")
        debug_print(f"Upload mode: {selected_mode}")
        debug_print(f"mobatch_paralel: {mobatch_paralel}, mobatch_timeout: {mobatch_timeout}")

        # Use the targets passed from the dialog (which came from the active CRExecutorWidget)
        current_targets = all_targets_for_session_type

        unconnected_sessions = []
        # Check connection status for all selected sessions
        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
            debug_print("SSHManager: Checking connection status...") # Debug print
        for session_name in selected_sessions:
            tab = self.find_ssh_tab(session_name)
            if not tab or not tab.connected:
                unconnected_sessions.append(session_name)

        if unconnected_sessions:
            QMessageBox.warning(self, "Connection Error",
                                f"The following selected sessions are not connected:\n" +
                                "\n".join(unconnected_sessions) +
                                "\nPlease connect them before uploading.")
            if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                debug_print(f"Upload cancelled due to unconnected sessions: {unconnected_sessions}")
            return # Stop the upload process

        for folder in selected_folders:
            debug_print(f"SSHManager: Processing folder: {folder}")
            time.sleep(1) # Add a 1-second delay
            # Clean up local sites_list files for the current folder
            for file_name in os.listdir(folder):
                if file_name.startswith('sites_list_') and file_name.endswith('.txt'):
                    file_path = os.path.join(folder, file_name)
                    try:
                        os.remove(file_path)
                        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                            debug_print(f"Cleaned up old sites_list file in {folder}: {file_name}")
                    except Exception as e:
                        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                            debug_print(f"[WARNING] Failed to remove old sites_list file {file_name} in {folder}: {e}")

            session_to_nodes = None
            if selected_mode == "SPLIT_RANDOMLY":
                all_nodes = []
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
                if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                    debug_print(selected_sessions)
                    for i, group in enumerate(split_nodes):
                        debug_print("Session {} nodes: {}".format(i + 1, group))

            debug_print("SSHManager: All selected sessions are connected. Proceeding with upload...")
            debug_print()
            # Add small delay between concurrent uploads to prevent resource contention
            upload_delay = 0.5
            for idx, tab in enumerate(self.get_current_cr_executor_widget().ssh_tabs):
                if tab.target['session_name'] in selected_sessions:
                    if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                        debug_print(f"SSHManager: Triggering upload for session: {tab.target['session_name']}") # Debug print
                    assigned_nodes = None
                    if selected_mode == "SPLIT_RANDOMLY" and session_to_nodes:
                        assigned_nodes = session_to_nodes
                    
                    # If SEND_BASH_COMMAND is selected and custom_cmd_format is provided, set it on the tab
                    if mobatch_execution_mode == "SEND_BASH_COMMAND" and custom_cmd_format:
                        tab.custom_cmd_format = custom_cmd_format
                        if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                            debug_print(f"Setting custom command format for {tab.target['session_name']}: {custom_cmd_format}")

                    # Add staggered delay for concurrent uploads
                    if idx > 0:
                        time.sleep(upload_delay)

                    # Perform SFTP and remote commands with the custom command format
                    tab.perform_sftp_and_remote_commands(
                        [folder], # Pass the current folder as a list
                        selected_mode,
                        selected_sessions, # This is the list of selected session names
                        mobatch_paralel,
                        mobatch_timeout,
                        assigned_nodes=assigned_nodes, # Pass the full mapping in SPLIT_RANDOMLY mode
                        mobatch_execution_mode=mobatch_execution_mode,
                        collect_prepost_checked=collect_prepost_checked
                    ) # selected_sessions is list of names, assigned_nodes contains the mapping

    def open_download_log_dialog(self, targets):
        # Ensure targets is a list before proceeding
        if not isinstance(targets, list):
            QMessageBox.critical(self, "Internal Error", f"Received invalid data for sessions. Expected list, got {type(targets).__name__}")
            if getattr(self, 'DEBUG_MODE', 'DEBUG') == 'DEBUG':
                debug_print(f"Error: open_download_log_dialog received unexpected targets type: {type(targets).__name__}")
            return

        current_widget = self.get_current_cr_executor_widget()
        if not current_widget:
            QMessageBox.warning(self, "No Sessions Available", "Cannot open download dialog without available sessions.")
            return

        # Open the dialog with the passed targets and var_FOLDER_CR from instance variable
        # Use DownloadLogDialog from lib.dialogs
        dlg = DownloadLogDialog(targets, current_widget.var_FOLDER_CR, self)
        # Connect the signal to the handler in SSHManager
        dlg.download_requested.connect(self.handle_download_log_request)
        dlg.exec_()

    def handle_download_log_request(self, selected_sessions, download_path, compare_before):
        """Handle download log request with improved error handling and cleanup."""
        try:
            # Get the current targets from the active CR Executor widget
            current_widget = self.get_current_cr_executor_widget()
            if not current_widget:
                QMessageBox.warning(self, "No Active Widget", "No active CR Executor widget found.")
                return

            var_FOLDER_CR = current_widget.var_FOLDER_CR

            # Clear the 02_DOWNLOAD directory before starting new downloads
            download_dir = os.path.join(os.path.dirname(__file__), '02_DOWNLOAD')
            if os.path.exists(download_dir):
                debug_print(f"Clearing directory: {download_dir}")
                try:
                    for item in os.listdir(download_dir):
                        item_path = os.path.join(download_dir, item)
                        try:
                            if os.path.isfile(item_path) or os.path.islink(item_path):
                                os.unlink(item_path)
                            elif os.path.isdir(item_path):
                                import shutil
                                shutil.rmtree(item_path)
                        except Exception as e:
                            debug_print(f"Warning: Failed to remove {item_path}: {e}")
                except Exception as e:
                    debug_print(f"Warning: Error accessing download directory: {e}")

            # Clean up any existing download threads
            self._cleanup_existing_downloads(current_widget)

            # Track downloads and setup completion handler
            self._pending_downloads = len(selected_sessions)
            self._download_errors = []

            def on_download_finished():
                """Handle download completion and check results."""
                self._pending_downloads -= 1
                if self._pending_downloads == 0:
                    try:
                        if self._download_errors:
                            error_msg = "\n".join(self._download_errors)
                            QMessageBox.warning(self, "Download Warnings", 
                                f"Some downloads completed with warnings:\n{error_msg}")
                        
                        # Run the check and export with compare_before parameter
                        check_logs_and_export_to_excel(self, compare_before)
                    except Exception as e:
                        QMessageBox.critical(self, "Check Export Error", 
                            f"Failed to export check: {str(e)}")

            # Start downloads for each selected session
            for session_name in selected_sessions:
                self._start_download_for_session(session_name, download_path, on_download_finished, var_FOLDER_CR)

        except Exception as e:
            QMessageBox.critical(self, "Download Error", 
                f"An unexpected error occurred during download setup: {str(e)}")

    def _cleanup_existing_downloads(self, widget):
        """Clean up any existing download threads in the widget."""
        if not widget:
            return

        for tab in widget.ssh_tabs:
            try:
                if hasattr(tab, 'download_thread') and tab.download_thread is not None:
                    if tab.download_thread.isRunning():
                        tab.append_output("Cleaning up previous download thread...")
                        
                        # Safely stop the worker
                        if hasattr(tab, 'download_worker') and tab.download_worker is not None:
                            try:
                                if hasattr(tab.download_worker, 'stop'):
                                    tab.download_worker.stop()
                            except RuntimeError:
                                debug_print(f"Worker already deleted for {tab.target['session_name']}")
                            except Exception as e:
                                debug_print(f"Error stopping worker for {tab.target['session_name']}: {e}")
                        
                        # Quit and wait for thread
                        try:
                            tab.download_thread.quit()
                            if not tab.download_thread.wait(2000):  # Wait up to 2 seconds
                                debug_print(f"Download thread for {tab.target['session_name']} did not stop. Terminating.")
                                tab.download_thread.terminate()
                                tab.download_thread.wait()
                        except Exception as e:
                            debug_print(f"Error stopping thread for {tab.target['session_name']}: {e}")
            except Exception as e:
                debug_print(f"Error during cleanup for {tab.target['session_name']}: {e}")
            finally:
                # Always clear references
                tab.download_thread = None
                tab.download_worker = None
                tab.progress_bar.setVisible(False)

    def _start_download_for_session(self, session_name, download_path, on_download_finished, var_FOLDER_CR):
        """Start download for a specific session with error handling."""
        tab = self.find_ssh_tab(session_name)
        if not tab:
            self._download_errors.append(f"Session {session_name} not found")
            return

        try:
            # Create and setup worker
            worker = DownloadLogWorker(tab.target, download_path, var_FOLDER_CR)
            thread = QThread()
            worker.moveToThread(thread)

            # Connect signals
            thread.started.connect(worker.run)
            worker.output.connect(tab.append_output)
            worker.completed.connect(tab.append_output)
            worker.error.connect(lambda msg: self._handle_download_error(tab, msg))
            worker.progress.connect(tab.update_progress_bar)

            # Show progress bar
            tab.progress_bar.setValue(0)
            tab.progress_bar.setVisible(True)

            # Store references
            tab.download_thread = thread
            tab.download_worker = worker

            def cleanup():
                """Clean up worker and thread resources."""
                try:
                    if hasattr(tab, 'download_thread') and tab.download_thread is not None:
                        if tab.download_thread.isRunning():
                            tab.download_thread.quit()
                            tab.download_thread.wait()
                except Exception as e:
                    debug_print(f"Error during cleanup for {session_name}: {e}")
                finally:
                    tab.download_thread = None
                    tab.download_worker = None
                    tab.progress_bar.setVisible(False)

            # Connect cleanup and deletion signals
            worker.completed.connect(cleanup)
            worker.error.connect(cleanup)
            worker.completed.connect(worker.deleteLater)
            worker.error.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)

            # Connect completion handler
            worker.completed.connect(on_download_finished)
            worker.error.connect(on_download_finished)

            # Start the download
            thread.start()

        except Exception as e:
            error_msg = f"Failed to start download for {session_name}: {str(e)}"
            self._download_errors.append(error_msg)
            debug_print(error_msg)
            QMessageBox.warning(self, "Download Error", error_msg)

    def _handle_download_error(self, tab, error_msg):
        """Handle download error with proper logging and user feedback."""
        self._download_errors.append(f"Error in {tab.target['session_name']}: {error_msg}")
        tab.append_output(f"[ERROR] {error_msg}")
        debug_print(f"Download error for {tab.target['session_name']}: {error_msg}")

    def cleanup_cr_executor_tabs(self, widget):
        """Clean up tabs in the specified CR Executor widget."""
        if widget:
            tabs_to_close = widget.ssh_tabs[:]
            for tab in tabs_to_close:
                index = widget.tabs.indexOf(tab)
                if index != -1:
                    self.close_ssh_tab(index, widget)

    def close_ssh_tab(self, index, widget=None):
        """Close a tab at the specified index in the given widget."""
        if widget is None:
            widget = self.get_current_cr_executor_widget()
        
        if widget and index < widget.tabs.count():
            tab_to_close = widget.tabs.widget(index)
            if isinstance(tab_to_close, SSHTab):
                tab_to_close.disconnect_session()
                tab_to_close.cleanup_upload_thread()
                if hasattr(tab_to_close, 'download_thread') and tab_to_close.download_thread is not None:
                    if tab_to_close.download_thread.isRunning():
                        tab_to_close.append_output("Cleaning up download thread...")
                        if hasattr(tab_to_close.download_worker, 'stop'):
                            tab_to_close.download_worker.stop()
                        tab_to_close.download_thread.quit()
                        tab_to_close.download_thread.wait(2000)
                        if tab_to_close.download_thread.isRunning():
                            debug_print(f"Download thread for {tab_to_close.target['session_name']} did not stop. Terminating.")
                            tab_to_close.download_thread.terminate()
                            tab_to_close.download_thread.wait()
                        tab_to_close.download_thread = None
                        tab_to_close.download_worker = None
                        tab_to_close.progress_bar.setVisible(False)

                widget.tabs.removeTab(index)
                if tab_to_close in widget.ssh_tabs:
                    widget.ssh_tabs.remove(tab_to_close)
        else:
            debug_print(f"Warning: close_ssh_tab called with invalid index {index} or no active widget.")

    def duplicate_session_group(self):
        current_widget = self.get_current_cr_executor_widget()
        if not current_widget:
            return

        original_session_type = current_widget.session_type
        base_name = f"CR EXECUTOR {original_session_type}"

        existing_menu_actions = [action.text() for action in self.menu_cr_executor.actions()]
        new_session_group_name = duplicate_session(base_name, existing_menu_actions)

        dialog = DuplicateSessionDialog(
            parent=self,
            folder_cr=current_widget.var_FOLDER_CR,
            screen_cr=current_widget.var_SCREEN_CR
        )

        if dialog.exec_() == QDialog.Accepted:
            new_folder_cr, new_screen_cr = dialog.get_values()

            new_targets = []
            for tab in current_widget.ssh_tabs:
                new_target = tab.target.copy()
                new_targets.append(new_target)

            new_widget = CRExecutorWidget(new_targets, self, session_type=f"{original_session_type} CLONE {len(self.menu_cr_executor.actions()) - 1}", var_FOLDER_CR=new_folder_cr, var_SCREEN_CR=new_screen_cr)
            self.stacked_widget.addWidget(new_widget)

            new_action = QAction(new_session_group_name, self)
            self.menu_cr_executor.addAction(new_action)
            new_action.triggered.connect(lambda: self.show_cr_executor_clone(new_widget))

            QMessageBox.information(self, "Session Group Duplicated", f"Session group \"{base_name}\" has been duplicated as \"{new_session_group_name}\".")

    def show_cr_executor_clone(self, widget):
        self.stacked_widget.setCurrentWidget(widget)
        # Update window title with the clone's session type
        if hasattr(widget, 'session_type'):
            self.setWindowTitle(f"CR TOOLS by esptnnd - CR EXECUTOR {widget.session_type}")
        if hasattr(self, 'background_label'):
            self.background_label.lower()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SSHManager()
    window.resize(1000, 600)
    window.show()
    sys.exit(app.exec_())
