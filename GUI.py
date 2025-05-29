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
from PyQt5.QtGui import QFont, QTextCursor
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
from lib.dialogs import ScreenSelectionDialog, MultiConnectDialog, UploadCRDialog, DownloadLogDialog
from lib.workers import UploadWorker, DownloadLogWorker
from lib.widgets import ConcheckToolsWidget, CRExecutorWidget
from lib.log_checker import check_logs_and_export_to_excel
from lib.report_generator import ExcelReaderApp, process_single_log, CATEGORY_CHECKING, CATEGORY_CHECKING1, write_logs_to_excel

class WorkerThread(QThread):
    finished = pyqtSignal(str, list, str, str)
    overall_progress = pyqtSignal(int)

    def __init__(self, file_path, selected_file, output_dir):
        super().__init__()
        self.file_path = file_path
        self.selected_file = selected_file
        self.output_dir = output_dir

    def run(self):
        folder_path = os.path.join(self.file_path, self.selected_file)
        log_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.log')]
        total_files = len(log_files)

        log_data = []
        args_list = [(f, folder_path, self.selected_file) for f in log_files]

        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(process_single_log, args): args[0] for args in args_list}
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                log_data.extend(result)
                self.overall_progress.emit(int((i / total_files) * 100))

        self.finished.emit(self.file_path, log_data, self.selected_file, self.output_dir)

class ExcelReaderApp(QMainWindow):
    processing_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.file_path = None
        self.selected_file = None
        self.output_dir = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Excel Reader')
        self.setGeometry(100, 100, 800, 600)

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Create folder selection button
        self.folder_button = QPushButton('Select Folder')
        self.folder_button.clicked.connect(self.open_folder_dialog)
        layout.addWidget(self.folder_button)

        # Create file list widget
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.file_list)

        # Create process button
        self.process_button = QPushButton('Process Selected File')
        self.process_button.clicked.connect(self.read_selected_excel)
        layout.addWidget(self.process_button)

        # Create progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

    def show_success_message(self, message):
        QMessageBox.information(self, 'Success', message)

    def show_error_message(self, message):
        QMessageBox.critical(self, 'Error', message)

    def update_overall_progress(self, value):
        self.progress_bar.setValue(value)

    def on_thread_finished(self, file_path, log_data, selected_file, output_dir):
        try:
            excel_filename = os.path.join(output_dir, f"{selected_file}_report.xlsx")
            write_logs_to_excel(log_data, excel_filename, selected_file)
            self.show_success_message(f"Processing completed. Report saved to {excel_filename}")
        except Exception as e:
            self.show_error_message(f"Error saving report: {str(e)}")
        finally:
            self.progress_bar.setValue(100)
            self.processing_finished.emit()

    def open_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.file_path = folder
            self.populate_file_list()

    def populate_file_list(self):
        if not self.file_path:
            return

        self.file_list.clear()
        try:
            for item in os.listdir(self.file_path):
                if os.path.isdir(os.path.join(self.file_path, item)):
                    self.file_list.addItem(item)
        except Exception as e:
            self.show_error_message(f"Error reading folder: {str(e)}")

    def read_selected_excel(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            self.show_error_message("Please select a file first")
            return

        self.selected_file = selected_items[0].text()
        self.output_dir = os.path.join(self.file_path, "reports")
        self.check_folder(self.output_dir)

        # Start processing in a separate thread
        self.worker = WorkerThread(self.file_path, self.selected_file, self.output_dir)
        self.worker.finished.connect(self.on_thread_finished)
        self.worker.overall_progress.connect(self.update_overall_progress)
        self.worker.start()

    def check_folder(self, output_dir):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

class SSHTab(QWidget):
    def __init__(self, target, ssh_manager):
        super().__init__()
        self.target = target
        self.ssh_manager = ssh_manager # Keep reference to the manager

        self.layout = QVBoxLayout()

        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        # Assuming QFont is imported in lib.widgets or keep here if only used here
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

        self.ssh = None # InteractiveSSH instance
        self.connected = False

        # Worker and thread instances
        self.upload_worker = None
        self.upload_thread = None
        self.download_worker = None
        self.download_thread = None


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
            self.append_output(f"Connecting to {self.target['session_name']}...")
            self.append_output("Waiting for prompt...")
            self._waiting_for_prompt = True
            # Use the InteractiveSSH class from lib.ssh
            self.ssh = InteractiveSSH(**self.target)
            self.ssh.output_received.connect(self.append_output)
            self.ssh.start()
            self.connected = True
            self.update_button_states()

    def disconnect_session(self):
        if self.connected and self.ssh:
            # Safely disconnect signals before closing SSH session
            try:
                self.ssh.output_received.disconnect(self.append_output)
            except TypeError:
                pass # Signal was not connected or already disconnected

            # Check if _write_log exists before calling it
            if hasattr(self.ssh, '_write_log'):
                 self.ssh._write_log("Disconnected") # Use internal log method if available
            else:
                 print("Warning: _write_log not found on ssh instance.") # For debugging

            self.ssh.close()
            self.connected = False
            self.update_button_states()
            self.append_output(f"Disconnected from {self.target['session_name']}.")


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
            # Check both with and without trailing newline
            if content.endswith("Waiting for prompt...\n"):
                 new_content = content[:-len("Waiting for prompt...\n")]
                 self.output_box.setPlainText(new_content)
            elif content.endswith("Waiting for prompt..."):
                 new_content = content[:-len("Waiting for prompt...")]
                 self.output_box.setPlainText(new_content)

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
            # QApplication.processEvents() # Removed to avoid potential re-entrancy issues
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
            # Use the ScreenSelectionDialog from lib.dialogs
            dlg = ScreenSelectionDialog(self.ssh, self)
            dlg.exec_()

    # This method seems to be a placeholder, actual handling is in SSHManager
    def handle_upload_request(self, selected_folders, selected_sessions):
        print("SSHTab received upload request (delegating to manager)")


    def perform_sftp_and_remote_commands(self, selected_folders, selected_mode, selected_sessions=None, mobatch_paralel=70, mobatch_timeout=30, assigned_nodes=None, mobatch_execution_mode="REGULAR_MOBATCH"):
        # This method is called by SSHManager to initiate upload on a specific tab
        print(f"SSHTab {self.target['session_name']} performing SFTP and remote commands.")
        self.append_output("Preparing for SFTP upload and remote commands...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        # Clean up existing upload worker/thread if they exist
        self.cleanup_upload_thread()

        self.upload_thread = QThread()
        # Pass necessary parameters to the UploadWorker, including var_FOLDER_CR from ssh_manager
        self.upload_worker = UploadWorker(
            self.ssh.client,
            self.target,
            selected_folders,
            selected_mode,
            selected_sessions,
            mobatch_paralel,
            mobatch_timeout,
            assigned_nodes,
            mobatch_execution_mode,
            var_FOLDER_CR=self.ssh_manager.var_FOLDER_CR # Get from manager
        )
        self.upload_worker.moveToThread(self.upload_thread)

        # Connect signals and slots
        self.upload_thread.started.connect(self.upload_worker.run)
        self.upload_worker.progress.connect(self.update_progress_bar)
        self.upload_worker.output.connect(self.append_output)
        self.upload_worker.completed.connect(self.upload_finished)
        self.upload_worker.error.connect(self.upload_finished)

        # Connect cleanup AFTER upload_finished to ensure messages are emitted first
        self.upload_worker.completed.connect(self.cleanup_upload_thread)
        self.upload_worker.error.connect(self.cleanup_upload_thread)

        # Connect worker and thread deletion
        self.upload_worker.completed.connect(self.upload_worker.deleteLater)
        self.upload_worker.error.connect(self.upload_worker.deleteLater)
        self.upload_thread.finished.connect(self.upload_thread.deleteLater)

        # Start the thread
        self.upload_thread.start()

    def cleanup_upload_thread(self):
        if self.upload_thread and self.upload_thread.isRunning():
            print(f"Cleaning up upload thread for {self.target['session_name']}...")
            if self.upload_worker:
                 self.upload_worker.stop() # Signal the worker to stop
            self.upload_thread.quit()
            self.upload_thread.wait(2000) # Wait up to 2 seconds
            if self.upload_thread.isRunning():
                 print(f"Upload thread for {self.target['session_name']} did not stop. Terminating.")
                 self.upload_thread.terminate()
                 self.upload_thread.wait() # Wait for termination

        self.upload_worker = None
        self.upload_thread = None
        self.progress_bar.setVisible(False) # Hide progress bar


    def update_progress_bar(self, value):
        self.progress_bar.setValue(value)

    def upload_finished(self, message):
        self.append_output(message)
        # Progress bar visibility is handled in cleanup_upload_thread

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
        if not self.ssh or not self.connected:
            self.append_output("[ERROR] Not connected.")
            return
        commands = self.command_batch_RUN.toPlainText().splitlines()
        for line in commands:
            cmd = line.strip()
            if cmd:
                self.ssh.send_command(cmd)

    def retry_upload(self):
        # This method needs to know the last successful upload parameters.
        # This requires storing the parameters when perform_sftp_and_remote_commands is called.
        # For simplicity now, I'll just show the structure assuming parameters are available.
        self.append_output("[RETRY] Functionality not fully implemented yet. Requires storing last upload parameters.")
        return # Prevent execution for now

        # Example structure if parameters were stored:
        # if not hasattr(self, '_last_upload_params') or not self._last_upload_params:
        #     self.append_output("[RETRY] No previous upload parameters found.")
        #     return
        #
        # # Retrieve stored parameters
        # selected_folders = self._last_upload_params['selected_folders']
        # selected_mode = self._last_upload_params['selected_mode']
        # selected_sessions = self._last_upload_params.get('selected_sessions')
        # mobatch_paralel = self._last_upload_params.get('mobatch_paralel', 70)
        # mobatch_timeout = self._last_upload_params.get('mobatch_timeout', 30)
        # assigned_nodes = self._last_upload_params.get('assigned_nodes')
        # mobatch_execution_mode = self._last_upload_params.get('mobatch_execution_mode', "REGULAR_MOBATCH")
        #
        # self.append_output(f"[RETRY] Retrying upload for {self.target['session_name']}...")
        # self.perform_sftp_and_remote_commands(
        #     selected_folders,
        #     selected_mode,
        #     selected_sessions=selected_sessions,
        #     mobatch_paralel=mobatch_paralel,
        #     mobatch_timeout=mobatch_timeout,
        #     assigned_nodes=assigned_nodes,
        #     mobatch_execution_mode=mobatch_execution_mode
        # )


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
        self.setCentralWidget(self.stacked_widget)

        # Create separate widgets for TRUE and DTAC modes
        self.cr_executor_widget_true = CRExecutorWidget(self.ssh_targets_true, self, session_type="TRUE")
        self.cr_executor_widget_dtac = CRExecutorWidget(self.ssh_targets_dtac, self, session_type="DTAC")
        self.excel_reader_app = ExcelReaderApp()

        # Add widgets to the stacked widget
        self.stacked_widget.addWidget(self.cr_executor_widget_true)
        self.stacked_widget.addWidget(self.cr_executor_widget_dtac)
        self.stacked_widget.addWidget(self.excel_reader_app)

        # Connect menu actions to switch widgets
        self.action_cr_executor_true.triggered.connect(self.show_cr_executor_true)
        self.action_cr_executor_dtac.triggered.connect(self.show_cr_executor_dtac)
        self.action_concheck_tools.triggered.connect(self.show_concheck_tools_form)

        # Connect tab change signals for both CR Executor widgets
        self.cr_executor_widget_true.tabs.currentChanged.connect(self.profile_tab_change)
        self.cr_executor_widget_dtac.tabs.currentChanged.connect(self.profile_tab_change)

        # Show the TRUE CR Executor form initially
        self.show_cr_executor_true()

    def show_cr_executor_true(self):
        """Shows the TRUE CR Executor form."""
        self.stacked_widget.setCurrentWidget(self.cr_executor_widget_true)

    def show_cr_executor_dtac(self):
        """Shows the DTAC CR Executor form."""
        self.stacked_widget.setCurrentWidget(self.cr_executor_widget_dtac)

    def show_concheck_tools_form(self):
        """Shows the Excel Reader form."""
        self.stacked_widget.setCurrentWidget(self.excel_reader_app)

    def get_current_cr_executor_widget(self):
        """Returns the currently active CR Executor widget."""
        current_widget = self.stacked_widget.currentWidget()
        if current_widget in [self.cr_executor_widget_true, self.cr_executor_widget_dtac]:
            return current_widget
        return None

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
            current_widget = self.get_current_cr_executor_widget()
            if current_widget:
                self.connect_multiple_sessions(selected_sessions)
            else:
                print("Error: No active CR Executor widget to connect sessions.")

    def connect_multiple_sessions(self, selected_sessions):
        print(f"Attempting to connect to selected sessions: {selected_sessions}")
        current_widget = self.get_current_cr_executor_widget()
        if not current_widget:
            print("Error: No active CR Executor widget to connect sessions.")
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
        print("Closing SSH Manager...")
        # Clean up all tabs in both CR Executor widgets before closing
        if self.cr_executor_widget_true:
            self.cleanup_cr_executor_tabs(self.cr_executor_widget_true)
        if self.cr_executor_widget_dtac:
            self.cleanup_cr_executor_tabs(self.cr_executor_widget_dtac)
        print("Accepting close event.")
        event.accept()

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
                            print(f"Download thread for {tab_to_close.target['session_name']} did not stop. Terminating.")
                            tab_to_close.download_thread.terminate()
                            tab_to_close.download_thread.wait()
                        tab_to_close.download_thread = None
                        tab_to_close.download_worker = None
                        tab_to_close.progress_bar.setVisible(False)

                widget.tabs.removeTab(index)
                if tab_to_close in widget.ssh_tabs:
                    widget.ssh_tabs.remove(tab_to_close)
        else:
            print(f"Warning: close_ssh_tab called with invalid index {index} or no active widget.")

    def profile_tab_change(self, index):
        import time
        t0 = time.time()
        print(f'[PROFILE] Tab change to index {index} started')
        # Optionally, you can do more here (e.g., check which tab, log tab name)
        # QApplication.processEvents()  # Removed to avoid potential re-entrancy issues
        t1 = time.time()
        print(f'[PROFILE] Tab change to index {index} finished, elapsed: {t1 - t0:.3f}s')

    def open_upload_cr_dialog(self, targets):
        # Ensure targets is a list before proceeding
        if not isinstance(targets, list):
            QMessageBox.critical(self, "Internal Error", f"Received invalid data for sessions. Expected list, got {type(targets).__name__}")
            print(f"Error: open_upload_cr_dialog received unexpected targets type: {type(targets).__name__}")
            return

        if not self.get_current_cr_executor_widget():
             QMessageBox.warning(self, "No Sessions Available", "Cannot open upload dialog without available sessions.")
             return

        # Open the upload CR dialog with the passed targets
        # Use UploadCRDialog from lib.dialogs
        dlg = UploadCRDialog(targets, parent=self, ssh_manager=self)

        # Connect the dialog's upload_requested signal to the SSHManager's handler
        dlg.upload_requested.connect(self.initiate_multi_session_upload)

        # The signal connection is handled inside the dialog when the button is clicked,
        # emitting to SSHManager.initiate_multi_session_upload.
        dlg.exec_()

    def initiate_multi_session_upload(self, selected_folders, selected_sessions, selected_mode, mobatch_paralel, mobatch_timeout, mobatch_execution_mode, all_targets_for_session_type):
        print("SSHManager: initiate_multi_session_upload called.") # Debug print
        print(f"Manager received upload request for folders: {selected_folders} to sessions: {selected_sessions}")
        print(f"Upload mode: {selected_mode}")
        print(f"mobatch_paralel: {mobatch_paralel}, mobatch_timeout: {mobatch_timeout}")

        # Use the targets passed from the dialog (which came from the active CRExecutorWidget)
        current_targets = all_targets_for_session_type

        unconnected_sessions = []
        # Check connection status for all selected sessions
        print("SSHManager: Checking connection status...") # Debug print
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
        print("SSHManager: Cleaning up local sites_list files...") # Debug print
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
        print(f"SSHManager: Processing mode: {selected_mode}") # Debug print
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
        print("SSHManager: All selected sessions are connected. Proceeding with upload...") # Debug print
        print()
        for tab in self.get_current_cr_executor_widget().ssh_tabs: # Iterate through tabs in CRExecutorWidget
            if tab.target['session_name'] in selected_sessions:
                print(f"SSHManager: Triggering upload for session: {tab.target['session_name']}") # Debug print
                assigned_nodes = None
                # Pass the node assignments if in SPLIT_RANDOMLY mode
                if selected_mode == "SPLIT_RANDOMLY" and session_to_nodes:
                     assigned_nodes = session_to_nodes


                # Pass the relevant subset of targets to the perform method if needed, or just the assigned nodes
                tab.perform_sftp_and_remote_commands(
                    selected_folders,
                    selected_mode,
                    selected_sessions, # This is the list of selected session names
                    mobatch_paralel,
                    mobatch_timeout,
                    assigned_nodes=assigned_nodes, # Pass the full mapping in SPLIT_RANDOMLY mode
                    mobatch_execution_mode=mobatch_execution_mode
                ) # selected_sessions is list of names, assigned_nodes contains the mapping

    def open_download_log_dialog(self, targets):
        # Ensure targets is a list before proceeding
        if not isinstance(targets, list):
            QMessageBox.critical(self, "Internal Error", f"Received invalid data for sessions. Expected list, got {type(targets).__name__}")
            print(f"Error: open_download_log_dialog received unexpected targets type: {type(targets).__name__}")
            return

        if not self.get_current_cr_executor_widget():
            QMessageBox.warning(self, "No Sessions Available", "Cannot open download dialog without available sessions.")
            return

        # Open the dialog with the passed targets and var_FOLDER_CR from instance variable
        # Use DownloadLogDialog from lib.dialogs
        dlg = DownloadLogDialog(targets, self.var_FOLDER_CR, self)
        # Connect the signal to the handler in SSHManager
        dlg.download_requested.connect(self.handle_download_log_request)
        dlg.exec_()

    def handle_download_log_request(self, selected_sessions, download_path):
        # Get the current targets from the active CR Executor widget
        current_targets = []
        if self.get_current_cr_executor_widget():
             current_targets = self.get_current_cr_executor_widget().targets

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
                        # Use shutil.rmtree for directories
                        import shutil
                        shutil.rmtree(item_path) # remove directory
                except Exception as e:
                    print(f"Error removing {item_path}: {e}")

        # Defensive: Clean up any previous download threads before starting new ones
        if self.get_current_cr_executor_widget():
            for tab in self.get_current_cr_executor_widget().ssh_tabs:
                if hasattr(tab, 'download_thread') and tab.download_thread is not None:
                    if tab.download_thread.isRunning():
                        tab.append_output("Cleaning up previous download thread...")
                        # Assuming download_worker has a stop method
                        if hasattr(tab.download_worker, 'stop'):
                             tab.download_worker.stop()
                        tab.download_thread.quit()
                        tab.download_thread.wait(2000) # Wait for thread to finish
                        if tab.download_thread.isRunning():
                            print(f"Download thread for {tab.target['session_name']} did not stop. Terminating.")
                            tab.download_thread.terminate()
                            tab.download_thread.wait()
                        tab.download_thread = None
                        tab.download_worker = None
                        tab.progress_bar.setVisible(False)

        # Track how many downloads are pending
        self._pending_downloads = len(selected_sessions)
        # _download_tabs was used for cleanup tracking, can be removed or kept if needed for other purposes.
        # self._download_tabs = [] # Keep track of tabs involved in download

        def on_download_finished():
            self._pending_downloads -= 1
            if self._pending_downloads == 0:
                # All downloads finished, run the check and export
                try:
                    # Use the check_logs_and_export_to_excel function from lib.log_checker
                    check_logs_and_export_to_excel(self) # Pass self as parent for QMessageBox
                    # Removed the QMessageBox here as it's now handled inside check_logs_and_export_to_excel
                except Exception as e:
                    QMessageBox.critical(self, "Check Export Error", f"Failed to export check: {e}")

        # For each selected session, start a download worker
        for session_name in selected_sessions:
            # Find the correct SSHTab within the CRExecutorWidget
            tab = self.find_ssh_tab(session_name)
            if not tab:
                continue # Skip if tab not found (shouldn't happen if selected from dialog)
            # Use DownloadLogWorker from lib.workers
            worker = DownloadLogWorker(tab.target, download_path, self.var_FOLDER_CR) # Pass self.var_FOLDER_CR
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
            # self._download_tabs.append(tab) # Add tab to tracking list

            def cleanup(tab=tab): # Use default argument to capture current tab
                if hasattr(tab, 'download_thread') and tab.download_thread is not None:
                    if tab.download_thread.isRunning():
                        tab.download_thread.quit()
                        tab.download_thread.wait() # Wait for thread to finish
                    tab.download_thread = None
                    tab.download_worker = None
                    tab.progress_bar.setVisible(False)

            # Connect signals using lambda to pass the specific tab instance
            # Connect cleanup and deletion
            worker.completed.connect(lambda: cleanup(tab))
            worker.error.connect(lambda: cleanup(tab))
            worker.completed.connect(worker.deleteLater)
            worker.error.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)

            # Connect the download finished signal to the overall handler
            worker.completed.connect(on_download_finished)
            worker.error.connect(on_download_finished)

            thread.start()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SSHManager()
    window.resize(1000, 600)
    window.show()
    sys.exit(app.exec_())
