import pytest
from unittest.mock import MagicMock, patch, mock_open
import os
import zipfile
import pandas as pd
from io import StringIO

# Since we are not using patch.dict, we need to handle the case where PyQt5 is not installed.
# We can do this by adding a try-except block around the import.
try:
    from PyQt5.QtCore import QObject, pyqtSignal
except ImportError:
    # If PyQt5 is not installed, create mock classes for the tests to run.
    class QObject:
        def __init__(self, parent=None):
            pass
    class pyqtSignal:
        def __init__(self, *args, **kwargs):
            pass
        def emit(self, *args, **kwargs):
            pass

# Now we can import the module to be tested.
from lib.workers import UploadWorker

class TestUploadWorker:
    @pytest.fixture
    def mock_ssh_client(self, mocker):
        """Fixture for a mock SSH client."""
        mock_client = MagicMock()
        mock_sftp = MagicMock()
        mock_client.open_sftp.return_value = mock_sftp
        return mock_client

    @pytest.fixture
    def mock_fs(self, mocker):
        """Fixture to create a fake file system."""
        initial_files = {
            '01_SCRIPT/99_Hygiene_collect/sites_list.txt': 'NODE1\nNODE2',
            '01_SCRIPT/99_Hygiene_collect/command_mos.txt': 'original content',
            '00_IPDB/ipdb_delim_ALLOSS_NEW.txt': 'Node;OSS\nNODE1;ENM-RAN1A\nNODE2;ENM-RAN1A',
        }

        def mock_os_path_exists(path):
            return path in initial_files or os.path.dirname(path) in initial_files

        mocker.patch('os.path.exists', side_effect=mock_os_path_exists)
        mocker.patch('os.makedirs')
        mocker.patch('shutil.rmtree')
        mocker.patch('pandas.read_csv', return_value=pd.DataFrame({'Node': ['NODE1', 'NODE2'], 'OSS': ['ENM-RAN1A', 'ENM-RAN1A']}))
        mocker.patch('os.walk', return_value=[('01_SCRIPT/99_Hygiene_collect', [], ['sites_list.txt', 'command_mos.txt'])])


    @pytest.fixture
    def upload_worker(self, mocker, mock_ssh_client, mock_fs):
        """Fixture for an UploadWorker instance."""
        target_info = {
            'session_name': 'ENM-RAN1A',
            'host': 'localhost',
            'port': 22,
            'username': 'testuser',
            'password': 'testpassword'
        }
        selected_folders = ['01_SCRIPT/99_Hygiene_collect']
        mode = 'TRUE'
        var_FOLDER_CR = 'CR_Tools_TEST'

        worker = UploadWorker(
            ssh_client=mock_ssh_client,
            target_info=target_info,
            selected_folders=selected_folders,
            mode=mode,
            var_FOLDER_CR=var_FOLDER_CR
        )

        # Replace pyqtSignal with MagicMock for testing
        worker.progress = MagicMock()
        worker.completed = MagicMock()
        worker.error = MagicMock()
        worker.output = MagicMock()

        return worker

    def test_upload_success(self, mocker, upload_worker):
        """Test the happy path of the UploadWorker.run method."""
        upload_worker.ssh_client.exec_command.return_value = (None, MagicMock(read=lambda: b''), MagicMock(read=lambda: b''))
        mocker.patch('zipfile.ZipFile')
        mocker.patch('lib.workers.QFileInfo')
        mocker.patch('builtins.open', mock_open(read_data='NODE1\nNODE2'))


        upload_worker.run()

        upload_worker.ssh_client.open_sftp().put.assert_called()
        upload_worker.completed.emit.assert_called_once_with('Upload completed successfully.')

    def test_prepost_check(self, mocker, upload_worker):
        """Test the UploadWorker with collect_prepost_checked set to True."""
        upload_worker.collect_prepost_checked = True
        mocker.patch('zipfile.ZipFile')
        mocker.patch('lib.workers.QFileInfo')
        m = mock_open()
        mocker.patch('builtins.open', m)

        upload_worker.run()

        # Check that the temporary command_mos.txt file was written with the pre-post check commands
        handle = m()
        handle.write.assert_any_call("uv com_username=rbs\nuv com_password=rbs\nlt cell|sectorcar|iublink\ny\n\n####LOG_Alarm_bf\naltc\n####LOG_status_bf\nhgetc ^(UtranCell|NRCellDU|EUtranCell.DD|NodeBLocalCell|trx|RbsLocalCell)= ^(operationalState|administrativeState)$\n\n\n")
        handle.write.assert_any_call("\n\n\nwait 5\nuv com_username=rbs\nuv com_password=rbs\nlt cell|sectorcar|iublink\ny\n\n####LOG_Alarm_af\naltc\n####LOG_status_af\nhgetc ^(UtranCell|NRCellDU|EUtranCell.DD|NodeBLocalCell|trx|RbsLocalCell)= ^(operationalState|administrativeState)$\n\n\n")