
import pytest
from unittest.mock import Mock, patch, MagicMock

# Mock PyQt5 classes and functions before they are imported by the widgets module
qt_mocks = {
    'QWidget': MagicMock(),
    'QVBoxLayout': MagicMock(),
    'QHBoxLayout': MagicMock(),
    'QLineEdit': MagicMock(),
    'QPushButton': MagicMock(),
    'QTextEdit': MagicMock(),
    'QMessageBox': MagicMock(),
    'QFileDialog': MagicMock(),
    'QTabWidget': MagicMock(),
    'QMainWindow': MagicMock(),
    'QLabel': MagicMock(),
    'QProgressBar': MagicMock(),
    'QStackedWidget': MagicMock(),
    'QListWidget': MagicMock(),
    'QAbstractItemView': MagicMock(),
    'QCheckBox': MagicMock(),
    'QGroupBox': MagicMock(),
    'QFormLayout': MagicMock(),
    'QDialog': MagicMock(),
    'QDialogButtonBox': MagicMock(),
}
with patch.dict('sys.modules', {
    'PyQt5.QtWidgets': MagicMock(spec=list(qt_mocks.keys()), **qt_mocks),
    'PyQt5.QtCore': MagicMock(),
    'PyQt5.QtGui': MagicMock(),
}):
    from lib.widgets import ConcheckToolsWidget

@pytest.fixture
def mock_q_objects(mocker):
    """Mocks all Qt related objects used in the widget."""
    mocker.patch('lib.widgets.QWidget')
    mocker.patch('lib.widgets.QVBoxLayout')
    mocker.patch('lib.widgets.QHBoxLayout')
    mocker.patch('lib.widgets.QLineEdit')
    mocker.patch('lib.widgets.QPushButton')
    mocker.patch('lib.widgets.QTextEdit')
    mocker.patch('lib.widgets.QMessageBox')
    mocker.patch('lib.widgets.QFileDialog')


def test_concheck_tools_widget_init(mock_q_objects):
    """
    Test the initialization of ConcheckToolsWidget.
    """
    # Act
    widget = ConcheckToolsWidget()

    # Assert
    assert isinstance(widget, qt_mocks['QWidget'])
    widget.browse_button.clicked.connect.assert_called_once_with(widget.browse_file)
    widget.run_concheck_button.clicked.connect.assert_called_once_with(widget.run_concheck_process)
    assert widget.selected_file_path is None

def test_concheck_browse_file_happy_path(mocker, mock_q_objects):
    """
    Test the browse_file method - Happy Path.
    A file is selected and the UI is updated.
    """
    # Arrange
    mocker.patch('lib.widgets.QFileDialog.getOpenFileName', return_value=('path/to/file.txt', 'All Files (*)'))
    widget = ConcheckToolsWidget()
    widget.results_text_edit = MagicMock()
    widget.file_path_label = MagicMock()

    # Act
    widget.browse_file()

    # Assert
    assert widget.selected_file_path == 'path/to/file.txt'
    widget.file_path_label.setText.assert_called_once_with('Selected File: path/to/file.txt')
    widget.results_text_edit.clear.assert_called_once()

def test_concheck_browse_file_edge_case_no_file_selected(mocker, mock_q_objects):
    """
    Test the browse_file method - Edge Case.
    No file is selected (dialog is cancelled).
    """
    # Arrange
    mocker.patch('lib.widgets.QFileDialog.getOpenFileName', return_value=(None, None))
    widget = ConcheckToolsWidget()
    widget.results_text_edit = MagicMock()
    widget.file_path_label = MagicMock()
    initial_file_path = widget.selected_file_path

    # Act
    widget.browse_file()

    # Assert
    assert widget.selected_file_path == initial_file_path
    widget.file_path_label.setText.assert_not_called()
    widget.results_text_edit.clear.assert_not_called()

def test_concheck_run_concheck_process_happy_path(mocker, mock_q_objects):
    """
    Test the run_concheck_process method - Happy Path.
    A file is selected and the concheck process runs successfully.
    """
    # Arrange
    mock_run_concheck = mocker.patch('lib.widgets.run_concheck', return_value=['result1', 'result2'])
    widget = ConcheckToolsWidget()
    widget.selected_file_path = 'path/to/file.txt'
    widget.results_text_edit = MagicMock()

    # Act
    widget.run_concheck_process()

    # Assert
    widget.results_text_edit.clear.assert_called_once()
    widget.results_text_edit.append.assert_any_call('Running concheck...')
    mock_run_concheck.assert_called_once_with('path/to/file.txt')
    widget.results_text_edit.append.assert_any_call('Concheck Results:')
    widget.results_text_edit.append.assert_any_call('result1')
    widget.results_text_edit.append.assert_any_call('result2')
    widget.results_text_edit.append.assert_any_call('Concheck finished.')

def test_concheck_run_concheck_process_negative_case_no_file(mocker, mock_q_objects):
    """
    Test the run_concheck_process method - Negative Case.
    No file is selected.
    """
    # Arrange
    mock_run_concheck = mocker.patch('lib.widgets.run_concheck')
    mock_qmessagebox = mocker.patch('lib.widgets.QMessageBox.warning')
    widget = ConcheckToolsWidget()
    widget.selected_file_path = None

    # Act
    widget.run_concheck_process()

    # Assert
    mock_qmessagebox.assert_called_once_with(widget, "No File Selected", "Please select a file first.")
    mock_run_concheck.assert_not_called()

def test_concheck_run_concheck_process_error_handling(mocker, mock_q_objects):
    """
    Test the run_concheck_process method - Error Handling.
    The concheck process raises an exception.
    """
    # Arrange
    mocker.patch('lib.widgets.run_concheck', side_effect=Exception('Test Error'))
    widget = ConcheckToolsWidget()
    widget.selected_file_path = 'path/to/file.txt'
    widget.results_text_edit = MagicMock()

    # Act
    widget.run_concheck_process()

    # Assert
    widget.results_text_edit.append.assert_any_call('Running concheck...')
    widget.results_text_edit.append.assert_any_call('Error running concheck: Test Error')


with patch.dict('sys.modules', {
    'PyQt5.QtWidgets': MagicMock(spec=list(qt_mocks.keys()), **qt_mocks),
    'PyQt5.QtCore': MagicMock(),
    'PyQt5.QtGui': MagicMock(),
    'lib.ssh': MagicMock(),
    'lib.dialogs': MagicMock(),
    'lib.workers': MagicMock(),
    'lib.style': MagicMock(),
}):
    from lib.widgets import SSHTab

@pytest.fixture
def ssh_tab(mocker):
    """Fixture to create an SSHTab instance with mocked dependencies."""
    mock_ssh_manager = MagicMock()
    mock_target = {'session_name': 'test_session', 'username': 'test_user', 'password': 'test_password'}
    
    # Mock Qt classes used in SSHTab that are not in the global mock
    mocker.patch('lib.widgets.TransparentTextEdit', MagicMock())
    mocker.patch('lib.widgets.StyledPushButton', MagicMock())
    mocker.patch('lib.widgets.StyledLineEdit', MagicMock())
    mocker.patch('lib.widgets.StyledProgressBar', MagicMock())
    mocker.patch('lib.widgets.QFont', MagicMock())
    mocker.patch('lib.widgets.QTimer', MagicMock())

    tab = SSHTab(target=mock_target, ssh_manager=mock_ssh_manager)
    tab.ssh = MagicMock()
    tab.append_output = MagicMock() # Mock append_output to avoid dealing with buffer/timer
    return tab

def test_sshtab_init(ssh_tab):
    """Test SSHTab initialization."""
    assert ssh_tab.target == {'session_name': 'test_session', 'username': 'test_user', 'password': 'test_password'}
    assert ssh_tab.ssh_manager is not None
    assert ssh_tab.connected is False
    
    # Check if signals are connected
    ssh_tab.send_button.clicked.connect.assert_called_with(ssh_tab.send_command)
    ssh_tab.input_line.returnPressed.connect.assert_called_with(ssh_tab.send_command)
    ssh_tab.connect_button.clicked.connect.assert_called_with(ssh_tab.connect_session)
    ssh_tab.disconnect_button.clicked.connect.assert_called_with(ssh_tab.disconnect_session)
    ssh_tab.screen_button.clicked.connect.assert_called_with(ssh_tab.open_screen_dialog)
    ssh_tab.send_batch_button.clicked.connect.assert_called_with(ssh_tab.send_batch_commands)
    ssh_tab.retry_upload_button.clicked.connect.assert_called_with(ssh_tab.retry_upload)

def test_sshtab_connect_session_happy_path(ssh_tab, mocker):
    """Test connect_session method - Happy Path."""
    # Arrange
    mock_interactive_ssh = mocker.patch('lib.widgets.InteractiveSSH')
    ssh_tab.connected = False

    # Act
    ssh_tab.connect_session()

    # Assert
    ssh_tab.append_output.assert_any_call("Connecting to test_session...")
    mock_interactive_ssh.assert_called_once_with(session_name='test_session', username='test_user', password='test_password')
    ssh_tab.ssh.start.assert_called_once()
    assert ssh_tab.connected is True
    ssh_tab.connect_button.setEnabled.assert_called_with(False)
    ssh_tab.disconnect_button.setEnabled.assert_called_with(True)

def test_sshtab_connect_session_negative_case_already_connected(ssh_tab, mocker):
    """Test connect_session method - Negative Case: already connected."""
    # Arrange
    mock_interactive_ssh = mocker.patch('lib.widgets.InteractiveSSH')
    ssh_tab.connected = True

    # Act
    ssh_tab.connect_session()

    # Assert
    mock_interactive_ssh.assert_not_called()
    ssh_tab.append_output.assert_not_called()

def test_sshtab_disconnect_session_happy_path(ssh_tab):
    """Test disconnect_session method - Happy Path."""
    # Arrange
    ssh_tab.connected = True
    ssh_tab.ssh = MagicMock()

    # Act
    ssh_tab.disconnect_session()

    # Assert
    ssh_tab.ssh.close.assert_called_once()
    assert ssh_tab.connected is False
    ssh_tab.append_output.assert_called_with("Disconnected from test_session.")
    ssh_tab.connect_button.setEnabled.assert_called_with(True)
    ssh_tab.disconnect_button.setEnabled.assert_called_with(False)

def test_sshtab_disconnect_session_negative_case_not_connected(ssh_tab):
    """Test disconnect_session method - Negative Case: not connected."""
    # Arrange
    ssh_tab.connected = False
    
    # Act
    ssh_tab.disconnect_session()

    # Assert
    ssh_tab.ssh.close.assert_not_called()
    ssh_tab.append_output.assert_not_called()

def test_sshtab_send_command_happy_path(ssh_tab):
    """Test send_command method - Happy Path."""
    # Arrange
    ssh_tab.input_line.text.return_value = "my_command"
    ssh_tab.ssh = MagicMock()
    
    # Act
    ssh_tab.send_command()

    # Assert
    ssh_tab.ssh.send_command.assert_called_once_with("my_command")
    ssh_tab.input_line.clear.assert_called_once()
    assert "my_command" in ssh_tab._command_history

def test_sshtab_send_command_edge_case_empty_command(ssh_tab):
    """Test send_command method - Edge Case: empty command."""
    # Arrange
    ssh_tab.input_line.text.return_value = "   " # Whitespace only
    ssh_tab.ssh = MagicMock()
    initial_history = list(ssh_tab._command_history)

    # Act
    ssh_tab.send_command()

    # Assert
    ssh_tab.ssh.send_command.assert_called_once_with("   ")
    ssh_tab.input_line.clear.assert_called_once()
    assert ssh_tab._command_history == initial_history # History should not change

def test_sshtab_send_command_negative_case_no_ssh(ssh_tab):
    """Test send_command method - Negative Case: no SSH session."""
    # Arrange
    ssh_tab.input_line.text.return_value = "my_command"
    ssh_tab.ssh = None
    
    # Act
    ssh_tab.send_command()

    # Assert
    ssh_tab.input_line.clear.assert_not_called()

def test_sshtab_open_screen_dialog_happy_path(ssh_tab, mocker):
    """Test open_screen_dialog method - Happy Path."""
    # Arrange
    mock_screen_dialog = mocker.patch('lib.widgets.ScreenSelectionDialog')
    ssh_tab.ssh = MagicMock()

    # Act
    ssh_tab.open_screen_dialog()

    # Assert
    mock_screen_dialog.assert_called_once_with(ssh_tab.ssh, ssh_tab)
    mock_screen_dialog.return_value.exec_.assert_called_once()

def test_sshtab_open_screen_dialog_negative_case_no_ssh(ssh_tab, mocker):
    """Test open_screen_dialog method - Negative Case: no SSH session."""
    # Arrange
    mock_screen_dialog = mocker.patch('lib.widgets.ScreenSelectionDialog')
    ssh_tab.ssh = None

    # Act
    ssh_tab.open_screen_dialog()

    # Assert
    mock_screen_dialog.assert_not_called()

def test_sshtab_perform_sftp_and_remote_commands(ssh_tab, mocker):
    """Test perform_sftp_and_remote_commands method."""
    # Arrange
    mock_setup_worker = mocker.patch.object(ssh_tab, '_setup_upload_worker')
    selected_folders = ['folder1']
    selected_mode = 'mode1'

    # Act
    ssh_tab.perform_sftp_and_remote_commands(selected_folders, selected_mode)

    # Assert
    ssh_tab.append_output.assert_any_call("SSHTab test_session performing SFTP and remote commands.")
    ssh_tab.progress_bar.setValue.assert_called_once_with(0)
    ssh_tab.progress_bar.setVisible.assert_called_once_with(True)
    mock_setup_worker.assert_called_once()

def test_sshtab_upload_finished_success(ssh_tab, mocker):
    """Test upload_finished method on success."""
    # Arrange
    ssh_tab.ssh_manager.var_FOLDER_CR = 'CR_FOLDER'
    ssh_tab.ssh_manager.var_SCREEN_CR = 'SCREEN_NAME'
    ssh_tab.ssh_manager.CMD_BATCH_SEND_FORMAT = "cd /home/shared/{username}/{var_FOLDER_CR}"
    ssh_tab.command_batch_RUN = MagicMock()
    mocker.patch.object(ssh_tab, 'send_batch_commands')

    # Act
    ssh_tab.upload_finished("Upload successful")

    # Assert
    ssh_tab.append_output.assert_called_with("Upload successful")
    ssh_tab.command_batch_RUN.setPlainText.assert_called_once()
    ssh_tab.send_batch_commands.assert_called_once()

def test_sshtab_upload_finished_failure(ssh_tab, mocker):
    """Test upload_finished method on failure."""
    # Arrange
    mock_qmessagebox = mocker.patch('lib.widgets.QMessageBox.critical')
    mocker.patch.object(ssh_tab, 'send_batch_commands')

    # Act
    ssh_tab.upload_finished("Upload failed")

    # Assert
    ssh_tab.append_output.assert_called_with("Upload failed")
    mock_qmessagebox.assert_called_once_with(ssh_tab, "Upload Error", "Upload failed")
    ssh_tab.send_batch_commands.assert_not_called()

def test_sshtab_send_batch_commands_happy_path(ssh_tab):
    """Test send_batch_commands method - Happy Path."""
    # Arrange
    ssh_tab.connected = True
    ssh_tab.ssh = MagicMock()
    ssh_tab.command_batch_RUN.toPlainText.return_value = "cmd1\ncmd2"

    # Act
    ssh_tab.send_batch_commands()

    # Assert
    ssh_tab.ssh.send_command.call_count == 2
    ssh_tab.ssh.send_command.assert_any_call("cmd1")
    ssh_tab.ssh.send_command.assert_any_call("cmd2")

def test_sshtab_send_batch_commands_not_connected(ssh_tab):
    """Test send_batch_commands method when not connected."""
    # Arrange
    ssh_tab.connected = False
    ssh_tab.ssh = None

    # Act
    ssh_tab.send_batch_commands()

    # Assert
    ssh_tab.append_output.assert_called_with("[ERROR] Not connected.")

def test_sshtab_retry_upload_happy_path(ssh_tab, mocker):
    """Test retry_upload method - Happy Path."""
    # Arrange
    mock_perform_sftp = mocker.patch.object(ssh_tab, 'perform_sftp_and_remote_commands')
    ssh_tab._last_upload_params = {'selected_folders': ['f1'], 'selected_mode': 'm1'}

    # Act
    ssh_tab.retry_upload()

    # Assert
    ssh_tab.append_output.assert_called_with("[RETRY] Retrying upload for test_session...")
    mock_perform_sftp.assert_called_once()

def test_sshtab_retry_upload_no_params(ssh_tab, mocker):
    """Test retry_upload method when no parameters are stored."""
    # Arrange
    mock_qmessagebox = mocker.patch('lib.widgets.QMessageBox.warning')
    ssh_tab._last_upload_params = {}

    # Act
    ssh_tab.retry_upload()

    # Assert
    ssh_tab.append_output.assert_called_with("[RETRY] No previous upload parameters found.")
    mock_qmessagebox.assert_called_once()

def test_sshtab_eventfilter_arrow_keys(ssh_tab, mocker):
    """Test eventFilter for up and down arrow key presses."""
    # Arrange
    ssh_tab._command_history = ["cmd1", "cmd2"]
    ssh_tab._history_index = 2
    mock_event_up = MagicMock()
    mock_event_up.type.return_value = 6 # KeyPress
    mock_event_up.key.return_value = 0x01000013 # Key_Up
    mock_event_down = MagicMock()
    mock_event_down.type.return_value = 6 # KeyPress
    mock_event_down.key.return_value = 0x01000015 # Key_Down

    # Act & Assert
    # Press Up
    ssh_tab.eventFilter(ssh_tab.input_line, mock_event_up)
    ssh_tab.input_line.setText.assert_called_with("cmd2")
    assert ssh_tab._history_index == 1

    # Press Up again
    ssh_tab.eventFilter(ssh_tab.input_line, mock_event_up)
    ssh_tab.input_line.setText.assert_called_with("cmd1")
    assert ssh_tab._history_index == 0

    # Press Down
    ssh_tab.eventFilter(ssh_tab.input_line, mock_event_down)
    ssh_tab.input_line.setText.assert_called_with("cmd2")
    assert ssh_tab._history_index == 1

    # Press Down again to clear
    ssh_tab.eventFilter(ssh_tab.input_line, mock_event_down)
    ssh_tab.input_line.clear.assert_called_once()
    assert ssh_tab._history_index == 2

with patch.dict('sys.modules', {
    'PyQt5.QtWidgets': MagicMock(spec=list(qt_mocks.keys()), **qt_mocks),
    'PyQt5.QtCore': MagicMock(),
    'PyQt5.QtGui': MagicMock(),
    'lib.widgets': MagicMock(),
    'lib.style': MagicMock(),
}):
    from lib.widgets import CRExecutorWidget

@pytest.fixture
def cr_executor_widget(mocker):
    """Fixture to create a CRExecutorWidget instance with mocked dependencies."""
    mock_ssh_manager = MagicMock()
    mock_targets = [
        {'session_name': 'session1'},
        {'session_name': 'session2'},
    ]
    mocker.patch('lib.widgets.StyledTabWidget', MagicMock())
    mocker.patch('lib.widgets.TopButton', MagicMock())
    mock_sshtab = mocker.patch('lib.widgets.SSHTab', MagicMock())

    widget = CRExecutorWidget(targets=mock_targets, ssh_manager=mock_ssh_manager)
    widget.ssh_manager = mock_ssh_manager
    widget.tabs.addTab = MagicMock()
    return widget, mock_sshtab, mock_ssh_manager, mock_targets

def test_crexecutorwidget_init(cr_executor_widget):
    """Test CRExecutorWidget initialization."""
    widget, mock_sshtab, mock_ssh_manager, mock_targets = cr_executor_widget

    assert widget.targets == mock_targets
    assert widget.ssh_manager == mock_ssh_manager
    assert mock_sshtab.call_count == 2
    widget.tabs.addTab.assert_any_call(mock_sshtab(), 'session1')
    widget.tabs.addTab.assert_any_call(mock_sshtab(), 'session2')

    # Check button connections
    widget.connect_selected_button.clicked.connect.assert_called_once()
    widget.download_log_button.clicked.connect.assert_called_once()
    widget.upload_cr_button.clicked.connect.assert_called_once()


with patch.dict('sys.modules', {
    'PyQt5.QtWidgets': MagicMock(spec=list(qt_mocks.keys()), **qt_mocks),
    'PyQt5.QtCore': MagicMock(),
    'PyQt5.QtGui': MagicMock(),
    'os': MagicMock(),
    'lib.style': MagicMock(),
    'lib.widgets': MagicMock(),
}):
    from lib.widgets import ExcelReaderApp

@pytest.fixture
def excel_reader_app(mocker):
    """Fixture to create an ExcelReaderApp instance with mocked dependencies."""
    mocker.patch('lib.widgets.setup_window_style')
    mocker.patch('lib.widgets.StyledContainer', MagicMock())
    mocker.patch('lib.widgets.StyledPushButton', MagicMock())
    mocker.patch('lib.widgets.StyledListWidget', MagicMock())
    mocker.patch('lib.widgets.QProgressBar', MagicMock())
    mocker.patch('lib.widgets.QLabel', MagicMock())
    mocker.patch('os.path.expanduser', return_value='/home/user')
    
    app = ExcelReaderApp()
    app.show_error_message = MagicMock()
    app.show_success_message = MagicMock()
    return app

def test_excelreaderapp_init(excel_reader_app):
    """Test ExcelReaderApp initialization."""
    assert excel_reader_app.start_path == '/home/user'
    excel_reader_app.folder_button.clicked.connect.assert_called_with(excel_reader_app.open_folder_dialog)
    excel_reader_app.process_button.clicked.connect.assert_called_with(excel_reader_app.read_selected_excel)

def test_excelreaderapp_open_folder_dialog_happy_path(excel_reader_app, mocker):
    """Test open_folder_dialog - Happy Path."""
    mocker.patch('lib.widgets.QFileDialog.getExistingDirectory', return_value='some/folder')
    mocker.patch.object(excel_reader_app, 'populate_file_list')

    excel_reader_app.open_folder_dialog()

    assert excel_reader_app.file_path == 'some/folder'
    excel_reader_app.populate_file_list.assert_called_once()

def test_excelreaderapp_open_folder_dialog_no_folder_selected(excel_reader_app, mocker):
    """Test open_folder_dialog - No folder selected."""
    mocker.patch('lib.widgets.QFileDialog.getExistingDirectory', return_value=None)
    mocker.patch.object(excel_reader_app, 'populate_file_list')

    excel_reader_app.open_folder_dialog()

    excel_reader_app.populate_file_list.assert_not_called()


def test_excelreaderapp_populate_file_list_happy_path(excel_reader_app, mocker):
    """Test populate_file_list - Happy Path."""
    excel_reader_app.file_path = 'some/folder'
    mock_listdir = mocker.patch('os.listdir', return_value=['dir1', 'file1.txt'])
    mock_isdir = mocker.patch('os.path.isdir', side_effect=[True, False])
    excel_reader_app.file_list = MagicMock()

    excel_reader_app.populate_file_list()

    excel_reader_app.file_list.clear.assert_called_once()
    excel_reader_app.file_list.addItem.assert_called_once_with('dir1')

def test_excelreaderapp_populate_file_list_error(excel_reader_app, mocker):
    """Test populate_file_list - Error reading folder."""
    excel_reader_app.file_path = 'some/folder'
    mocker.patch('os.listdir', side_effect=OSError("Permission denied"))
    excel_reader_app.file_list = MagicMock()

    excel_reader_app.populate_file_list()

    excel_reader_app.file_list.clear.assert_called_once()
    excel_reader_app.show_error_message.assert_called_with('Error reading folder: Permission denied')

def test_excelreaderapp_read_selected_excel_happy_path(excel_reader_app, mocker):
    """Test read_selected_excel - Happy Path."""
    mock_item = MagicMock()
    mock_item.text.return_value = 'selected_dir'
    excel_reader_app.file_list.selectedItems.return_value = [mock_item]
    mocker.patch.object(excel_reader_app, 'process_next_file')

    excel_reader_app.read_selected_excel()

    assert not excel_reader_app.file_queue.empty()
    excel_reader_app.process_next_file.assert_called_once()

def test_excelreaderapp_read_selected_excel_no_selection(excel_reader_app, mocker):
    """Test read_selected_excel - No items selected."""
    excel_reader_app.file_list.selectedItems.return_value = []
    mocker.patch.object(excel_reader_app, 'process_next_file')

    excel_reader_app.read_selected_excel()

    excel_reader_app.show_error_message.assert_called_with("Please select a file first")
    excel_reader_app.process_next_file.assert_not_called()

def test_excelreaderapp_process_next_file_happy_path(excel_reader_app, mocker):
    """Test process_next_file - Happy Path."""
    mock_worker_thread = mocker.patch('lib.widgets.WorkerThread')
    excel_reader_app.file_queue.put('selected_dir')
    mocker.patch.object(excel_reader_app, 'check_folder')

    excel_reader_app.process_next_file()

    excel_reader_app.check_folder.assert_called_once()
    mock_worker_thread.assert_called_once()
    mock_worker_thread.return_value.start.assert_called_once()


def test_excelreaderapp_process_next_file_empty_queue(excel_reader_app, mocker):
    """Test process_next_file - Empty queue."""
    mock_worker_thread = mocker.patch('lib.widgets.WorkerThread')

    excel_reader_app.process_next_file()

    mock_worker_thread.assert_not_called()
    excel_reader_app.show_success_message.assert_called_with("All selected folders processed!")

def test_excelreaderapp_check_folder(excel_reader_app, mocker):
    """Test check_folder method."""
    mock_exists = mocker.patch('os.path.exists', return_value=False)
    mock_makedirs = mocker.patch('os.makedirs')

    excel_reader_app.check_folder('new/dir')

    mock_exists.assert_called_with('new/dir')
    mock_makedirs.assert_called_with('new/dir')

with patch.dict('sys.modules', {
    'PyQt5.QtCore': MagicMock(),
    'os': MagicMock(),
    'pandas': MagicMock(),
    'concurrent.futures': MagicMock(),
    'lib.report_generator': MagicMock(),
    'lib.widgets': MagicMock(),
}):
    from lib.widgets import WorkerThread

@pytest.fixture
def worker_thread(mocker):
    """Fixture to create a WorkerThread instance with mocked dependencies."""
    mocker.patch('lib.widgets.QThread')
    thread = WorkerThread('path/to', 'selected_file', 'output/dir')
    thread.finished = MagicMock()
    thread.overall_progress = MagicMock()
    thread.phase_changed = MagicMock()
    thread.details_changed = MagicMock()
    return thread

def test_workerthread_run_happy_path(worker_thread, mocker):
    """Test WorkerThread.run() - Happy Path."""
    mocker.patch('os.listdir', return_value=['log1.log', 'log2.log'])
    mock_process_single_log = mocker.patch('lib.report_generator.process_single_log', return_value={
        "log_data": ["some data"],
        "df_LOG_Alarm_bf": MagicMock(empty=False),
        "df_LOG_Alarm_af": MagicMock(empty=True),
        "df_LOG_status_bf": MagicMock(empty=False),
        "df_LOG_status_af": MagicMock(empty=True),
    })
    mock_write_excel = mocker.patch('lib.report_generator.write_logs_to_excel')
    
    # Mock ProcessPoolExecutor
    mock_executor = MagicMock()
    mock_future = MagicMock()
    mock_future.result.return_value = mock_process_single_log.return_value
    mock_executor.submit.return_value = mock_future
    mocker.patch('concurrent.futures.ProcessPoolExecutor.__enter__', return_value=mock_executor)
    mocker.patch('concurrent.futures.as_completed', return_value=[mock_future, mock_future])

    worker_thread.run()

    assert worker_thread.phase_changed.call_count > 0
    assert worker_thread.overall_progress.call_count > 0
    mock_write_excel.assert_called_once()
    worker_thread.finished.assert_called_once()


def test_workerthread_run_no_logs(worker_thread, mocker):
    """Test WorkerThread.run() - Edge Case: No log files found."""
    mocker.patch('os.listdir', return_value=['file1.txt'])
    mock_write_excel = mocker.patch('lib.report_generator.write_logs_to_excel')

    worker_thread.run()

    mock_write_excel.assert_called_once()
    worker_thread.finished.assert_called_once()

def test_workerthread_run_error(worker_thread, mocker):
    """Test WorkerThread.run() - Error Handling."""
    mocker.patch('os.listdir', side_effect=Exception("Test error"))

    worker_thread.run()

    worker_thread.phase_changed.assert_called_with("Error!")
    worker_thread.details_changed.assert_called_with(mocker.ANY)
    worker_thread.finished.assert_called_once()


with patch.dict('sys.modules', {
    'PyQt5.QtWidgets': MagicMock(spec=list(qt_mocks.keys()), **qt_mocks),
    'os': MagicMock(),
    'lib.style': MagicMock(),
    'lib.merge_file_case': MagicMock(),
}):
    from lib.widgets import CMBulkFileMergeWidget

@pytest.fixture
def cmbulk_widget(mocker):
    mocker.patch('lib.widgets.setup_window_style')
    mocker.patch('lib.widgets.StyledContainer', MagicMock())
    mocker.patch('lib.widgets.StyledPushButton', MagicMock())
    mocker.patch('lib.widgets.TransparentTextEdit', MagicMock())
    mocker.patch('os.path.expanduser', return_value='/home/user')
    widget = CMBulkFileMergeWidget()
    widget.log = MagicMock()
    return widget

def test_cmbulkfilemergewidget_init(cmbulk_widget):
    """Test CMBulkFileMergeWidget initialization."""
    assert cmbulk_widget.start_path == '/home/user'
    cmbulk_widget.select_button.clicked.connect.assert_called_with(cmbulk_widget.select_files)

def test_cmbulkfilemergewidget_select_files_happy_path(cmbulk_widget, mocker):
    """Test select_files - Happy Path."""
    mock_get_open_files = mocker.patch('lib.widgets.QFileDialog.getOpenFileNames', return_value=(['file1.txt', 'file2.txt'], '*.txt'))
    mock_merge_files = mocker.patch('lib.widgets.merge_cmbulk_files')
    mock_qmessagebox = mocker.patch('lib.widgets.QMessageBox.information')

    cmbulk_widget.select_files()

    mock_get_open_files.assert_called_once()
    mock_merge_files.assert_called_once()
    mock_qmessagebox.assert_called_once()

def test_cmbulkfilemergewidget_select_files_no_files(cmbulk_widget, mocker):
    """Test select_files - No files selected."""
    mocker.patch('lib.widgets.QFileDialog.getOpenFileNames', return_value=([], '*.txt'))
    mock_merge_files = mocker.patch('lib.widgets.merge_cmbulk_files')

    cmbulk_widget.select_files()

    mock_merge_files.assert_not_called()

with patch.dict('sys.modules', {
    'PyQt5.QtCore': MagicMock(),
    'lib.rehoming': MagicMock(),
}):
    from lib.widgets import RehomingExportWorker

@pytest.fixture
def rehoming_export_worker(mocker):
    mocker.patch('lib.widgets.QThread')
    worker = RehomingExportWorker(['file1'], 'output/dir')
    worker.progress = MagicMock()
    worker.finished = MagicMock()
    worker.error = MagicMock()
    worker.log = MagicMock()
    return worker

def test_rehomingexportworker_run_happy_path(rehoming_export_worker, mocker):
    """Test RehomingExportWorker.run() - Happy Path."""
    mock_merge_files = mocker.patch('lib.rehoming.merge_lacrac_files')

    rehoming_export_worker.run()

    mock_merge_files.assert_called_once()
    rehoming_export_worker.finished.assert_called_with("Penggabungan file selesai.")

def test_rehomingexportworker_run_error(rehoming_export_worker, mocker):
    """Test RehomingExportWorker.run() - Error Handling."""
    mocker.patch('lib.rehoming.merge_lacrac_files', side_effect=Exception("Test error"))

    rehoming_export_worker.run()

    rehoming_export_worker.error.assert_called_with("Test error")


with patch.dict('sys.modules', {
    'PyQt5.QtWidgets': MagicMock(spec=list(qt_mocks.keys()), **qt_mocks),
}):
    from lib.widgets import ExcludeTypesDialog

@pytest.fixture
def exclude_dialog(mocker):
    mocker.patch('lib.widgets.QDialog')
    mocker.patch('lib.widgets.QCheckBox')
    mocker.patch('lib.widgets.QFormLayout')
    mocker.patch('lib.widgets.QDialogButtonBox')
    dialog = ExcludeTypesDialog(current_excluded=['UtranCell'])
    return dialog

def test_excludetypesdialog_init(exclude_dialog):
    """Test ExcludeTypesDialog initialization."""
    assert 'UtranCell' in exclude_dialog.type_checkboxes
    exclude_dialog.type_checkboxes['UtranCell'].setChecked.assert_called_with(True)
    exclude_dialog.type_checkboxes['IubLink'].setChecked.assert_not_called()

def test_excludetypesdialog_get_excluded_types(exclude_dialog):
    """Test get_excluded_types method."""
    exclude_dialog.type_checkboxes['UtranCell'].isChecked.return_value = True
    exclude_dialog.type_checkboxes['IubLink'].isChecked.return_value = False

    excluded = exclude_dialog.get_excluded_types()

    assert excluded == ['UtranCell']


with patch.dict('sys.modules', {
    'PyQt5.QtWidgets': MagicMock(spec=list(qt_mocks.keys()), **qt_mocks),
    'os': MagicMock(),
    'lib.style': MagicMock(),
    'lib.rehoming': MagicMock(),
    'lib.widgets': MagicMock(),
}):
    from lib.widgets import RehomingScriptToolsWidget

@pytest.fixture
def rehoming_widget(mocker):
    mocker.patch('lib.widgets.setup_window_style')
    mocker.patch('lib.widgets.StyledContainer', MagicMock())
    mocker.patch('lib.widgets.StyledPushButton', MagicMock())
    mocker.patch('lib.widgets.TransparentTextEdit', MagicMock())
    mocker.patch('lib.widgets.QProgressBar', MagicMock())
    mocker.patch('os.path.expanduser', return_value='/home/user')
    widget = RehomingScriptToolsWidget()
    widget.log = MagicMock()
    return widget

def test_rehomingscripttoolswidget_init(rehoming_widget):
    """Test RehomingScriptToolsWidget initialization."""
    assert rehoming_widget.start_path == '/home/user'
    rehoming_widget.select_dump_and_excel_button.clicked.connect.assert_called_with(rehoming_widget.select_dump_and_excel)
    rehoming_widget.select_files_button.clicked.connect.assert_called_with(rehoming_widget.select_files)
    rehoming_widget.filter_button.clicked.connect.assert_called_with(rehoming_widget.open_exclude_dialog)

def test_rehomingscripttoolswidget_open_exclude_dialog(rehoming_widget, mocker):
    """Test open_exclude_dialog method."""
    mock_dialog = mocker.patch('lib.widgets.ExcludeTypesDialog')
    mock_dialog.return_value.exec_.return_value = 1 # Accepted
    mock_dialog.return_value.get_excluded_types.return_value = ['UtranCell']

    rehoming_widget.open_exclude_dialog()

    assert rehoming_widget.exclude_types == ['UtranCell']

def test_rehomingscripttoolswidget_select_dump_and_excel(rehoming_widget, mocker):
    """Test select_dump_and_excel method."""
    mock_select = mocker.patch('lib.widgets.select_dump_and_excel', return_value=('some/path', MagicMock()))
    mock_worker = mocker.patch('lib.widgets.ParseDumpWorker')

    rehoming_widget.select_dump_and_excel()

    mock_select.assert_called_once()
    mock_worker.assert_called_once()
    mock_worker.return_value.start.assert_called_once()

def test_rehomingscripttoolswidget_select_files(rehoming_widget, mocker):
    """Test select_files method."""
    mock_get_files = mocker.patch('lib.widgets.QFileDialog.getOpenFileNames', return_value=(['file1'], '*.txt'))
    mock_worker = mocker.patch('lib.widgets.RehomingExportWorker')
    mocker.patch('os.path.dirname', return_value='some/dir')

    rehoming_widget.select_files()

    mock_get_files.assert_called_once()
    mock_worker.assert_called_once()
    mock_worker.return_value.start.assert_called_once()
