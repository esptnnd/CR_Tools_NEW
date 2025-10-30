"""
Before/After Report GUI Widget
This widget provides a GUI interface for running Before/After analysis of network configuration data.
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QTextEdit, QMessageBox, QFileDialog,
    QCheckBox, QGroupBox, QFormLayout, QLabel, QProgressBar, QDateEdit, QTimeEdit, QSlider
)
from PyQt5.QtCore import QThread, pyqtSignal, QEventLoop, QTimer, QObject
from PyQt5.QtCore import QDate, QTime, Qt
from datetime import datetime
from .report_before_after import run_before_after_analysis
from .style import StyledPushButton, StyledLineEdit, StyledProgressBar, StyledContainer, TransparentTextEdit, StyledLabel, StyledDateEdit, StyledSlider


def slider_value_to_time_string(value):
    """Converts a slider value (0-95) to a HH:mm time string."""
    total_minutes = value * 15
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"


def normalize_path_for_display(path):
    """Normalize path separators for consistent display across platforms."""
    # Normalize all types of path separators to forward slashes for display
    return path.replace('\\', '/').replace('//', '/')  # Also cleanup double slashes


class BeforeAfterReportWidget(QWidget):
    def __init__(self, parent=None, start_path=None):
        super().__init__(parent)
        self.start_path = start_path or os.path.expanduser('~')
        self.initUI()
        
        # Thread for running analysis in background
        self.analysis_thread = None

    def initUI(self):
        main_layout = QVBoxLayout()
        
        # Create a styled container to provide proper background contrast
        container = StyledContainer()
        main_layout.addWidget(container)
        
        # Use the container's layout for all content
        layout = container.layout()
        
        # Create group box for folder selection
        folder_group = QGroupBox("Folder Selection")
        folder_group.setStyleSheet("""
            QGroupBox {
                color: white;
                font-weight: bold;
                font-size: 11pt;
                border: 1px solid rgba(128, 128, 128, 0.5);
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        folder_layout = QFormLayout()
        
        # Single parent folder selection
        parent_layout = QHBoxLayout()
        self.parent_path_edit = StyledLineEdit()
        self.parent_path_edit.setReadOnly(True)
        self.parent_browse_button = StyledPushButton("Browse Parent Folder")
        self.parent_browse_button.clicked.connect(self.browse_parent_folder)
        parent_layout.addWidget(self.parent_path_edit)
        parent_layout.addWidget(self.parent_browse_button)
        parent_label = StyledLabel("Parent Folder:")
        folder_layout.addRow(parent_label, parent_layout)
        
        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)
        
        # Time selection (for date/time of analysis)
        time_group = QGroupBox("Analysis Time")
        time_group.setStyleSheet("""
            QGroupBox {
                color: white;
                font-weight: bold;
                font-size: 11pt;
                border: 1px solid rgba(128, 128, 128, 0.5);
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        time_layout = QVBoxLayout()
        
        # Date/time pickers
        self.date_before = StyledDateEdit()
        self.date_before.setDate(QDate.currentDate())
        self.date_after = StyledDateEdit()
        self.date_after.setDate(QDate.currentDate())

        for date_edit in [self.date_before, self.date_after]:
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")

        # Time sliders
        self.time_before_slider = StyledSlider(Qt.Horizontal)
        self.time_before_slider.setRange(0, 95)
        self.time_before_slider.setValue(36) # Default to 09:00
        self.time_before_label = StyledLabel(slider_value_to_time_string(self.time_before_slider.value()))
        self.time_before_slider.valueChanged.connect(lambda val: self.time_before_label.setText(slider_value_to_time_string(val)))

        self.time_after_slider = StyledSlider(Qt.Horizontal)
        self.time_after_slider.setRange(0, 95)
        self.time_after_slider.setValue(36) # Default to 09:00
        self.time_after_label = StyledLabel(slider_value_to_time_string(self.time_after_slider.value()))
        self.time_after_slider.valueChanged.connect(lambda val: self.time_after_label.setText(slider_value_to_time_string(val)))

        dt_layout = QVBoxLayout()

        # Before section
        before_group_layout = QVBoxLayout()
        before_date_layout = QHBoxLayout()
        before_date_layout.addWidget(StyledLabel("Before START Date:"))
        before_date_layout.addWidget(self.date_before)
        before_group_layout.addLayout(before_date_layout)

        before_time_layout = QHBoxLayout()
        before_time_layout.addWidget(StyledLabel("Time:"))
        before_time_layout.addWidget(self.time_before_slider)
        before_time_layout.addWidget(self.time_before_label)
        before_group_layout.addLayout(before_time_layout)
        dt_layout.addLayout(before_group_layout)

        # After section
        after_group_layout = QVBoxLayout()
        after_date_layout = QHBoxLayout()
        after_date_layout.addWidget(StyledLabel("After START Date:"))
        after_date_layout.addWidget(self.date_after)
        after_group_layout.addLayout(after_date_layout)

        after_time_layout = QHBoxLayout()
        after_time_layout.addWidget(StyledLabel("Time:"))
        after_time_layout.addWidget(self.time_after_slider)
        after_time_layout.addWidget(self.time_after_label)
        after_group_layout.addLayout(after_time_layout)
        dt_layout.addLayout(after_group_layout)
        time_layout.addLayout(dt_layout)

        time_group.setLayout(time_layout)
        layout.addWidget(time_group)
        
        # Options group
        options_group = QGroupBox("Options")
        options_group.setStyleSheet("""
            QGroupBox {
                color: white;
                font-weight: bold;
                font-size: 11pt;
                border: 1px solid rgba(128, 128, 128, 0.5);
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        options_layout = QVBoxLayout()
        
        # KPI analysis checkbox
        self.kpi_checkbox = QCheckBox("Include KPI Analysis")
        self.kpi_checkbox.setChecked(True)  # Checked by default
        self.kpi_checkbox.setStyleSheet("""
            QCheckBox {
                color: white;
                font-weight: bold;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid rgba(128, 128, 128, 0.5);
                border-radius: 3px;
                background-color: rgba(26, 26, 26, 0.8);
            }
            QCheckBox::indicator:checked {
                background-color: #00FF00;
                border: 1px solid #00FF00;
            }
        """)
        options_layout.addWidget(self.kpi_checkbox)
        
        # Dark mode toggle (for future expansion if needed)
        self.dark_mode_checkbox = QCheckBox("Dark Mode")
        self.dark_mode_checkbox.setChecked(False)
        self.dark_mode_checkbox.setStyleSheet("""
            QCheckBox {
                color: white;
                font-weight: bold;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid rgba(128, 128, 128, 0.5);
                border-radius: 3px;
                background-color: rgba(26, 26, 26, 0.8);
            }
            QCheckBox::indicator:checked {
                background-color: #00FF00;
                border: 1px solid #00FF00;
            }
        """)
        options_layout.addWidget(self.dark_mode_checkbox)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Run button
        self.run_button = StyledPushButton("Run Analysis")
        self.run_button.clicked.connect(self.run_analysis)
        layout.addWidget(self.run_button)
        
        # Progress bar
        self.progress_bar = StyledProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Results text area
        self.results_text_edit = TransparentTextEdit()
        self.results_text_edit.setReadOnly(True)
        layout.addWidget(self.results_text_edit)
        
        self.setLayout(main_layout)

    def browse_parent_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Parent Folder", self.start_path)
        if folder_path:
            self.parent_path_edit.setText(folder_path)
            
            # Automatically set the Before and After folders
            before_folder = os.path.join(folder_path, "Before")
            after_folder = os.path.join(folder_path, "After")
            
            self.results_text_edit.clear()
            self.results_text_edit.append(f"Parent folder selected: {normalize_path_for_display(folder_path)}")
            self.results_text_edit.append(f"Before folder will be: {normalize_path_for_display(before_folder)}")
            self.results_text_edit.append(f"After folder will be: {normalize_path_for_display(after_folder)}")
            
            # Check if the Before and After folders exist
            if not os.path.exists(before_folder):
                self.results_text_edit.append("WARNING: Before folder does not exist")
            if not os.path.exists(after_folder):
                self.results_text_edit.append("WARNING: After folder does not exist")

    def run_analysis(self):
        # Get the parent folder and construct Before/After paths
        parent_path = self.parent_path_edit.text().strip()
        if not parent_path:
            QMessageBox.warning(self, "Missing Parent Folder", "Please select a Parent folder.")
            return

        before_path = os.path.join(parent_path, "Before")
        after_path = os.path.join(parent_path, "After")
        
        include_kpi = self.kpi_checkbox.isChecked()
        
        # Get the selected date and time
        before_date = self.date_before.date().toString('yyyy-MM-dd')
        before_time = self.time_before_label.text()
        after_date = self.date_after.date().toString('yyyy-MM-dd')
        after_time = self.time_after_label.text()
        
        before_datetime = f"{before_date} {before_time}"
        after_datetime = f"{after_date} {after_time}"
        
        if not os.path.exists(before_path):
            QMessageBox.warning(self, "Invalid Path", f"Before folder does not exist: {normalize_path_for_display(before_path)}")
            return
            
        if not os.path.exists(after_path):
            QMessageBox.warning(self, "Invalid Path", f"After folder does not exist: {normalize_path_for_display(after_path)}")
            return
        
        # Clear previous results
        self.results_text_edit.clear()
        
        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.run_button.setEnabled(False)
        
        # Run analysis in background thread
        self.analysis_worker = AnalysisWorker(before_path, after_path, include_kpi, before_datetime, after_datetime)
        self.analysis_thread = QThread()
        self.analysis_worker.moveToThread(self.analysis_thread)
        
        # Connect signals
        self.analysis_worker.analysis_started.connect(self.on_analysis_started)
        self.analysis_worker.analysis_finished.connect(self.on_analysis_finished)
        self.analysis_worker.analysis_error.connect(self.on_analysis_error)
        self.analysis_worker.log_message.connect(self.append_log)
        self.analysis_worker.progress_update.connect(self.update_progress)
        
        self.analysis_thread.started.connect(self.analysis_worker.run_analysis)
        
        # Start the thread
        self.analysis_thread.start()

    def on_analysis_started(self):
        self.append_log("Analysis started...")

    def on_analysis_finished(self, report_path):
        self.append_log(f"Analysis completed successfully!")
        self.append_log(f"Report saved to: {report_path}")
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.run_button.setEnabled(True)
        
        # Stop and delete the thread
        self.analysis_thread.quit()
        self.analysis_thread.wait()
        self.analysis_thread = None

    def on_analysis_error(self, error_msg):
        self.append_log(f"Error: {error_msg}")
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.run_button.setEnabled(True)
        
        # Stop and delete the thread
        if self.analysis_thread and self.analysis_thread.isRunning():
            self.analysis_thread.quit()
            self.analysis_thread.wait()
        self.analysis_thread = None

    def update_progress(self, value, message):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(value)
        self.append_log(message)

    def append_log(self, message):
        self.results_text_edit.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def closeEvent(self, event):
        # Clean up thread if still running
        if self.analysis_thread and self.analysis_thread.isRunning():
            self.analysis_worker.stop()
            self.analysis_thread.quit()
            self.analysis_thread.wait()
        event.accept()


class AnalysisWorker(QObject):
    analysis_started = pyqtSignal()
    analysis_finished = pyqtSignal(str)  # report path
    analysis_error = pyqtSignal(str)     # error message
    log_message = pyqtSignal(str)
    progress_update = pyqtSignal(int, str)  # progress value and message
    
    def __init__(self, before_path, after_path, include_kpi, before_time, after_time):
        super().__init__()
        self.before_path = before_path
        self.after_path = after_path
        self.include_kpi = include_kpi
        self.before_time = before_time
        self.after_time = after_time
        self._is_stopped = False

    def run_analysis(self):
        if self._is_stopped:
            return
            
        try:
            self.analysis_started.emit()
            
            # Define a wrapper function to emit progress updates
            def progress_callback(progress_val, message):
                if not self._is_stopped:
                    self.progress_update.emit(progress_val, f"[PROGRESS] {message}")

            # Import the report_before_after module to access its functions
            from . import report_before_after
            
            # Run the analysis with progress callback
            report_path = report_before_after.run_before_after_analysis(
                self.before_path, 
                self.after_path, 
                self.include_kpi,
                self.before_time,
                self.after_time,
                progress_callback
            )
            
            if not self._is_stopped:
                self.analysis_finished.emit(report_path)
        except Exception as e:
            if not self._is_stopped:
                self.analysis_error.emit(str(e))

    def stop(self):
        self._is_stopped = True