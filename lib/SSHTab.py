# -----------------------------------------------------------------------------
# Author      : esptnnd
# Company     : Ericsson Indonesia
# Created on  : 7 May 2025
# Improve on  : 29 May 2025
# Description : CR TOOLS by esptnnd — built for the ECT Project to help the team
#               execute faster, smoother, and with way less hassle.
#               Making life easier, one script at a time!
# -----------------------------------------------------------------------------


from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QMessageBox
from PyQt5.QtCore import QThread, QTimer, Qt, QEvent, pyqtSlot
from PyQt5.QtGui import QTextCursor
from lib.style import TransparentTextEdit, StyledPushButton, StyledLineEdit, StyledProgressBar
from lib.ssh import InteractiveSSH
from lib.dialogs import ScreenSelectionDialog
from lib.workers import UploadWorker
from .utils import debug_print

class SSHTab(QWidget):
    def __init__(self, target, ssh_manager):
        super().__init__()
        self.target = target
        self.ssh_manager = ssh_manager
        self.ssh = None
        self.connected = False
        self._setup_ui()
        self._setup_connections()
        self._setup_state()

    def _setup_ui(self):
        """Initialize and setup all UI components"""
        self.layout = QVBoxLayout()
        
        # Create widgets
        self.output_box = TransparentTextEdit()
        self.output_box.setReadOnly(True)
        
        self.command_batch_RUN = TransparentTextEdit()
        self.command_batch_RUN.setPlaceholderText("Enter batch commands here, one per line...")
        self.command_batch_RUN.setFixedHeight(80)
        
        self.input_line = StyledLineEdit()
        self.progress_bar = StyledProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        
        # Create buttons
        self.buttons = {
            'send_batch': StyledPushButton("Send Batch"),
            'retry_upload': StyledPushButton("Retry Upload"),
            'send': StyledPushButton("Send"),
            'connect': StyledPushButton("Connect"),
            'disconnect': StyledPushButton("Disconnect"),
            'screen': StyledPushButton("Screen Sessions")
        }
        
        # Setup layouts
        self.layout.addWidget(self.command_batch_RUN)
        self.layout.addWidget(self.buttons['send_batch'])
        self.layout.addWidget(self.buttons['retry_upload'])
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.input_line)
        for btn in ['send', 'connect', 'disconnect', 'screen']:
            button_layout.addWidget(self.buttons[btn])
        
        self.layout.addWidget(self.output_box)
        self.layout.addLayout(button_layout)
        self.layout.addWidget(self.progress_bar)
        self.setLayout(self.layout)

    def _setup_connections(self):
        """Setup all signal connections"""
        self.buttons['send'].clicked.connect(self.send_command)
        self.input_line.returnPressed.connect(self.send_command)
        self.buttons['connect'].clicked.connect(self.connect_session)
        self.buttons['disconnect'].clicked.connect(self.disconnect_session)
        self.buttons['screen'].clicked.connect(self.open_screen_dialog)
        self.buttons['send_batch'].clicked.connect(self.send_batch_commands)
        self.buttons['retry_upload'].clicked.connect(self.retry_upload)
        
        # Install event filters
        for widget in [self, self.output_box, self.command_batch_RUN, self.input_line] + list(self.buttons.values()):
            widget.installEventFilter(self)

    def _setup_state(self):
        """Initialize state variables"""
        self._output_buffer = []
        self._output_batch_size = 20
        self._output_timer = QTimer(self)
        self._output_timer.setInterval(100)
        self._output_timer.timeout.connect(self.flush_output)
        self._waiting_for_prompt = False
        self._command_history = []
        self._history_index = -1
        self.upload_worker = None
        self.upload_thread = None
        self.download_worker = None
        self.download_thread = None
        self.update_button_states()

    def eventFilter(self, obj, event):
        """Handle keyboard events and auto-focus"""
        if obj == self.input_line and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Up:
                self._navigate_history(-1)
                return True
            elif event.key() == Qt.Key_Down:
                self._navigate_history(1)
                return True
            else:
                self._history_index = len(self._command_history)
        
        if event.type() == QEvent.KeyPress and obj != self.command_batch_RUN and not self.input_line.hasFocus():
            self.input_line.setFocus()
        
        return super().eventFilter(obj, event)

    def _navigate_history(self, direction):
        """Navigate through command history"""
        if not self._command_history:
            return
            
        if direction == -1 and self._history_index > 0:
            self._history_index -= 1
        elif direction == 1 and self._history_index < len(self._command_history) - 1:
            self._history_index += 1
        elif direction == 1 and self._history_index == len(self._command_history) - 1:
            self._history_index += 1
            self.input_line.clear()
            return
            
        self.input_line.setText(self._command_history[self._history_index])
        self.input_line.setCursorPosition(len(self.input_line.text()))

    def connect_session(self):
        """Establish SSH connection"""
        if not self.connected:
            self.append_output(f"Connecting to {self.target['session_name']}...")
            self.append_output("Waiting for prompt...")
            self._waiting_for_prompt = True
            self.ssh = InteractiveSSH(**self.target)
            self.ssh.output_received.connect(self.append_output)
            self.ssh.start()
            self.connected = True
            self.update_button_states()

    def disconnect_session(self):
        """Close SSH connection"""
        if self.connected and self.ssh:
            try:
                self.ssh.output_received.disconnect(self.append_output)
            except TypeError:
                pass
                
            if hasattr(self.ssh, '_write_log'):
                self.ssh._write_log("Disconnected")
            else:
                print("Warning: _write_log not found on ssh instance.")
                
            self.ssh.close()
            self.connected = False
            self.update_button_states()
            self.append_output(f"Disconnected from {self.target['session_name']}.")

    def update_button_states(self):
        """Update button states based on connection status"""
        self.buttons['connect'].setEnabled(not self.connected)
        self.buttons['disconnect'].setEnabled(self.connected)
        self.buttons['screen'].setEnabled(self.connected)

    def append_output(self, text):
        """Append text to output box with buffering"""
        if self._waiting_for_prompt:
            self._clear_waiting_message()
            self._waiting_for_prompt = False

        self._output_buffer.append(text)
        if len(self._output_buffer) >= self._output_batch_size:
            self.flush_output()
        elif not self._output_timer.isActive():
            self._output_timer.start()

    def _clear_waiting_message(self):
        """Clear the waiting for prompt message"""
        cursor = self.output_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.output_box.setTextCursor(cursor)
        content = self.output_box.toPlainText()
        for suffix in ["Waiting for prompt...\n", "Waiting for prompt..."]:
            if content.endswith(suffix):
                self.output_box.setPlainText(content[:-len(suffix)])
                break

    def flush_output(self):
        """Flush buffered output to the output box"""
        if self._output_buffer:
            self.output_box.moveCursor(QTextCursor.End)
            self.output_box.insertPlainText('\n'.join(self._output_buffer) + '\n')
            self.output_box.moveCursor(QTextCursor.End)
            self._output_buffer.clear()
        self._output_timer.stop()

    def send_command(self):
        """Send command to SSH session"""
        if not self.ssh:
            return
            
        cmd = self.input_line.text()
        self.ssh.send_command(cmd)
        
        if cmd.strip():
            if not self._command_history or self._command_history[-1] != cmd:
                self._command_history.append(cmd)
        self._history_index = len(self._command_history)
        self.input_line.clear()
        self.flush_output()

    def open_screen_dialog(self):
        """Open screen session dialog"""
        if self.ssh:
            ScreenSelectionDialog(self.ssh, self).exec_()

    def perform_sftp_and_remote_commands(self, selected_folders, selected_mode, selected_sessions=None, 
                                       mobatch_paralel=70, mobatch_timeout=30, assigned_nodes=None, 
                                       mobatch_execution_mode="REGULAR_MOBATCH", collect_prepost_checked=False):
        """Handle SFTP upload and remote commands"""
        self.append_output(f"SSHTab {self.target['session_name']} performing SFTP and remote commands.")
        self.append_output("Preparing for SFTP upload and remote commands...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        self.cleanup_upload_thread()
        self._setup_upload_worker(selected_folders, selected_mode, selected_sessions,
                                mobatch_paralel, mobatch_timeout, assigned_nodes,
                                mobatch_execution_mode, collect_prepost_checked)

    def _setup_upload_worker(self, selected_folders, selected_mode, selected_sessions,
                           mobatch_paralel, mobatch_timeout, assigned_nodes,
                           mobatch_execution_mode, collect_prepost_checked=False):
        """Setup and start upload worker"""
        self.upload_thread = QThread()
        self.upload_worker = UploadWorker(
            target_info=self.target,
            selected_folders=selected_folders,
            mode=selected_mode,
            selected_sessions=selected_sessions,
            mobatch_paralel=mobatch_paralel,
            mobatch_timeout=mobatch_timeout,
            assigned_nodes=assigned_nodes,
            mobatch_execution_mode=mobatch_execution_mode,
            var_FOLDER_CR=self.ssh_manager.var_FOLDER_CR,
            collect_prepost_checked=collect_prepost_checked,
            password_sesion=self.target.get('password', '')
        )
        
        self.upload_worker.moveToThread(self.upload_thread)
        self._connect_upload_signals()
        self.upload_thread.start()

    def _connect_upload_signals(self):
        """Connect all upload worker signals"""
        self.upload_thread.started.connect(self.upload_worker.run)
        self.upload_worker.progress.connect(self.update_progress_bar)
        self.upload_worker.progress.connect(self._report_progress_to_manager)
        self.upload_worker.stage_update.connect(self._report_stage_to_manager)
        self.upload_worker.zip_uploaded.connect(self._handle_zip_uploaded)
        
        self.upload_worker.output.connect(self.append_output)
        self.upload_worker.completed.connect(self.upload_finished)
        self.upload_worker.error.connect(self.upload_error_handler)
        
        # Connect cleanup to make sure it happens after completion/error is processed
        # Use direct connections to ensure proper order
        self.upload_worker.completed.connect(self._delayed_cleanup_upload)
        self.upload_worker.error.connect(self._delayed_cleanup_upload)
        self.upload_worker.completed.connect(self.upload_worker.deleteLater)
        self.upload_worker.error.connect(self.upload_worker.deleteLater)
        
        self.upload_thread.finished.connect(self.upload_thread.deleteLater)
    
    def _report_progress_to_manager(self, progress):
        """Report upload progress to SSH Manager for global tracking"""
        if self.ssh_manager and hasattr(self.ssh_manager, 'update_upload_progress'):
            self.ssh_manager.update_upload_progress(self.target['session_name'], progress)
    
    def _report_stage_to_manager(self, stage):
        """Report upload stage to SSH Manager"""
        if self.ssh_manager and hasattr(self.ssh_manager, 'update_upload_progress'):
            # Get current progress
            progress = self.progress_bar.value()
            self.ssh_manager.update_upload_progress(self.target['session_name'], progress, stage)
    
    def _handle_zip_uploaded(self):
        """Handle successful ZIP upload - mark this specific milestone"""
        self.append_output("✓ ZIP file uploaded successfully!")
        if self.ssh_manager and hasattr(self.ssh_manager, 'register_upload_zip_complete'):
            self.ssh_manager.register_upload_zip_complete(self.target['session_name'])
    
    def upload_error_handler(self, message):
        """Handle upload errors without blocking GUI"""
        self.append_output(f"[ERROR] {message}")
        # Report error to manager
        if self.ssh_manager and hasattr(self.ssh_manager, 'register_upload_error'):
            self.ssh_manager.register_upload_error(self.target['session_name'])
        # Don't show QMessageBox during concurrent uploads - just log it
        debug_print(f"Upload error for {self.target['session_name']}: {message}")
    
    def _safe_cleanup_upload(self):
        """Safely cleanup upload thread without blocking"""
        try:
            self.cleanup_upload_thread()
        except Exception as e:
            debug_print(f"Error during upload cleanup: {e}")
    
    def _delayed_cleanup_upload(self):
        """Delay cleanup to allow queued signals to be processed"""
        # Schedule cleanup after a brief delay to ensure all signals are processed
        # Add a small delay to ensure completion is properly registered before cleanup
        from PyQt5.QtCore import QTimer
        debug_print(f"[DELAYED_CLEANUP] Scheduling cleanup for {self.target['session_name']} in 1000ms to ensure completion is processed")
        QTimer.singleShot(1000, self._safe_cleanup_upload)

    def cleanup_upload_thread(self):
        """Clean up upload worker and thread"""
        try:
            if self.upload_thread and self.upload_thread.isRunning():
                debug_print(f"Cleaning up upload thread for {self.target['session_name']}...")
                if self.upload_worker:
                    try:
                        self.upload_worker.stop()
                    except RuntimeError:
                        debug_print(f"Worker already deleted for {self.target['session_name']}")
                
                self.upload_thread.quit()
                if not self.upload_thread.wait(2000):
                    debug_print(f"Upload thread for {self.target['session_name']} did not stop in time. Terminating.")
                    self.upload_thread.terminate()
                    self.upload_thread.wait()
        except Exception as e:
            debug_print(f"Error cleaning up upload thread: {e}")
        finally:
            self.upload_worker = None
            self.upload_thread = None
            self.progress_bar.setVisible(False)

    def update_progress_bar(self, value):
        """Update progress bar value"""
        self.progress_bar.setValue(value)

    def upload_finished(self, message):
        """Handle upload completion"""
        self.append_output(message)
        
        if 'failed' in message.lower() or 'error' in message.lower():
            debug_print(f"Upload error for {self.target['session_name']}: {message}")
            if self.ssh_manager and hasattr(self.ssh_manager, 'register_upload_error'):
                self.ssh_manager.register_upload_error(self.target['session_name'])
            # Don't block GUI with QMessageBox during concurrent uploads
        else:
            debug_print(f"[WORKER] Emitted upload_done for {self.target['session_name']}")
            # Set individual progress bar to 100% to indicate completion
            self.progress_bar.setValue(100)
            # Also report to manager that this upload is complete
            if self.ssh_manager and hasattr(self.ssh_manager, 'register_upload_complete'):
                self.ssh_manager.register_upload_complete(self.target['session_name'])
            self._setup_batch_commands()

    def _setup_batch_commands(self):
        """Setup batch commands after successful upload"""
        remote_base_dir = f"/home/shared/{self.target['username']}/{self.ssh_manager.var_FOLDER_CR}"
        ENM_SERVER = self.target['session_name']
        
        # Use appropriate command format based on mobatch execution mode
        if hasattr(self, 'mobatch_execution_mode'):
            if self.mobatch_execution_mode == "CMBULK IMPORT":
                command_format = self.ssh_manager.CMD_BATCH_SEND_FORMAT_CMBULK
            elif self.mobatch_execution_mode == "SEND_BASH_COMMAND" and hasattr(self, 'custom_cmd_format') and self.custom_cmd_format:
                command_format = self.custom_cmd_format
            else:
                command_format = self.ssh_manager.CMD_BATCH_SEND_FORMAT
        else:
            command_format = self.ssh_manager.CMD_BATCH_SEND_FORMAT
            
        self.command_batch_RUN.setPlainText(
            command_format.format(
                remote_base_dir=remote_base_dir,
                ENM_SERVER=ENM_SERVER,
                screen_session=self.ssh_manager.var_SCREEN_CR,
                password_sesion=self.target.get('password', '')
            )
        )
        self.send_batch_commands()

    def send_batch_commands(self):
        """Send batch commands to SSH session"""
        if not self.ssh or not self.connected:
            self.append_output("[ERROR] Not connected.")
            return
            
        for cmd in (line.strip() for line in self.command_batch_RUN.toPlainText().splitlines() if line.strip()):
            self.ssh.send_command(cmd)

    def retry_upload(self):
        """Retry last upload operation"""
        self.append_output("[RETRY] Functionality not fully implemented yet. Requires storing last upload parameters.")
        return