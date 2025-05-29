# Widget classes

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QTextEdit, QMessageBox, QFileDialog,
    QTabWidget, QMainWindow, QLabel, QProgressBar, QStackedWidget
)
from PyQt5.QtCore import (
    QEventLoop, QTimer, QObject, pyqtSignal, QThread, Qt, QFileInfo, QDir, QEvent
)
from PyQt5.QtGui import QFont, QTextCursor
import re
import time # For profiling in SSHTab, maybe move later
import os

# Import the run_concheck function and SSH related classes/dialogs/workers
from .concheck import run_concheck
from .ssh import InteractiveSSH # Assuming InteractiveSSH is needed by SSHTab
from .dialogs import ScreenSelectionDialog, MultiConnectDialog, UploadCRDialog, DownloadLogDialog # Import dialogs used by these widgets
from .workers import UploadWorker, SubfolderLoaderWorker, DownloadLogWorker # Import workers used by these widgets
# Assuming check_logs_and_export_to_excel will be moved to lib/log_checker.py later
# from .log_checker import check_logs_and_export_to_excel


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
        # QApplication.processEvents() # Removed as it might be unsafe in some contexts

        try:
            # Call the run_concheck function from lib.concheck
            results = run_concheck(self.selected_file_path)
            self.results_text_edit.append("Concheck Results:")
            for line in results:
                self.results_text_edit.append(line)
            self.results_text_edit.append("Concheck finished.")
        except Exception as e:
            self.results_text_edit.append(f"Error running concheck: {e}")


class SSHTab(QWidget):
    def __init__(self, target, ssh_manager):
        super().__init__()
        self.target = target
        self.ssh_manager = ssh_manager # Keep reference to the manager

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

            self.ssh._write_log("Disconnected") # Use internal log method if available
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

class CRExecutorWidget(QWidget):
    def __init__(self, targets, ssh_manager, parent=None, session_type="TRUE"):
        super().__init__(parent)
        self.ssh_manager = ssh_manager # Keep reference to the manager
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
        # Connect the tab close requested signal - Handled by SSHManager

        for target in targets:
            # Pass self (the CRExecutorWidget instance) and the ssh_manager instance to the SSHTab
            tab = SSHTab(target, ssh_manager)
            self.ssh_tabs.append(tab)
            self.tabs.addTab(tab, target['session_name'])

        # Connect the new button's signal to the SSHManager's corresponding slots
        self.connect_selected_button.clicked.connect(lambda: self.ssh_manager.open_multi_connect_dialog(self.targets)) # Pass targets
        self.download_log_button.clicked.connect(lambda: self.ssh_manager.open_download_log_dialog(self.targets)) # Pass targets
        self.upload_cr_button.clicked.connect(lambda: self.ssh_manager.open_upload_cr_dialog(self.targets)) # Pass targets
