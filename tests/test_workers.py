
import pytest
from unittest.mock import MagicMock, patch

# Mock PyQt5 classes and functions before they are imported by the workers module
qt_mocks = {
    'QObject': MagicMock(),
    'QThread': MagicMock(),
    'pyqtSignal': MagicMock(),
    'QMessageBox': MagicMock(),
    'QFileInfo': MagicMock(),
}
with patch.dict('sys.modules', {
    'PyQt5.QtCore': MagicMock(spec=['pyqtSignal', 'QObject', 'QThread', 'QFileInfo'], **qt_mocks),
    'PyQt5.QtWidgets': MagicMock(spec=['QMessageBox'], **qt_mocks),
}):
    from lib.workers import UploadWorker, SubfolderLoaderWorker, DownloadLogWorker

@pytest.fixture
def upload_worker(mocker):
    mocker.patch('lib.workers.QObject')
    mocker.patch('lib.workers.pyqtSignal', return_value=MagicMock())
    
    mock_ssh_client = MagicMock()
    mock_target_info = {'username': 'test_user', 'session_name': 'test_session', 'password': 'test_pass'}
    selected_folders = ['/path/to/folder1']
    mode = 'TRUE'
    var_folder_cr = 'CR_FOLDER'

    worker = UploadWorker(
        ssh_client=mock_ssh_client,
        target_info=mock_target_info,
        selected_folders=selected_folders,
        mode=mode,
        var_FOLDER_CR=var_folder_cr
    )
    return worker, mock_ssh_client, mock_target_info

def test_upload_worker_init(upload_worker):
    worker, mock_ssh_client, mock_target_info = upload_worker

    assert worker.ssh_client == mock_ssh_client
    assert worker.target_info == mock_target_info
    assert worker.selected_folders == ['/path/to/folder1']
    assert worker.mode == 'TRUE'
    assert worker.var_FOLDER_CR == 'CR_FOLDER'
    assert worker._should_stop is False
    worker.output.emit.assert_called()

def test_upload_worker_stop(upload_worker):
    worker, _, _ = upload_worker
    worker.stop()
    assert worker._should_stop is True


def test_upload_worker_run_happy_path(upload_worker, mocker):
    worker, mock_ssh_client, mock_target_info = upload_worker

    # Mock os and shutil functions
    mocker.patch('os.path.exists', side_effect=lambda x: x == '00_IPDB/ipdb_delim_ALLOSS_NEW.txt')
    mocker.patch('os.makedirs')
    mocker.patch('os.path.join', side_effect=lambda *args: '/'.join(args))
    mocker.patch('os.listdir', return_value=['log1.log'])
    mocker.patch('os.path.basename', return_value='folder1')
    mocker.patch('os.path.getsize', return_value=100)
    mocker.patch('os.remove')
    mocker.patch('shutil.rmtree')

    # Mock pandas
    mock_df_ipdb = MagicMock()
    mock_df_ipdb.__getitem__.side_effect = lambda key: {'Node': ['node1'], 'OSS': ['oss1']}[key]
    mocker.patch('pandas.read_csv', return_value=mock_df_ipdb)

    # Mock zipfile
    mock_zipfile = MagicMock()
    mocker.patch('zipfile.ZipFile', return_value=mock_zipfile)
    mock_zipfile.__enter__.return_value = mock_zipfile
    mock_zipfile.__exit__.return_value = None

    # Mock QFileInfo
    mocker.patch('lib.workers.QFileInfo', return_value=MagicMock(size=100))

    # Mock ssh_client methods
    mock_sftp = MagicMock()
    mock_ssh_client.open_sftp.return_value = mock_sftp
    mock_sftp.stat.return_value = MagicMock()
    mock_ssh_client.exec_command.return_value = (MagicMock(), MagicMock(read=lambda: b''), MagicMock(read=lambda: b''))

    # Mock open for file operations
    mock_open = mocker.mock_open()
    mocker.patch('builtins.open', mock_open)

    worker.run()

    # Assertions for file operations
    mock_open.assert_any_call('/path/to/folder1/sites_list.txt', encoding='utf-8')
    mock_open.assert_any_call('/path/to/folder1/sites_list_oss1.txt', 'w', encoding='utf-8', newline='\n')
    mock_open.assert_any_call('/Temp/tmp_upload_test_session/RUN_CR_test_session.txt', 'w', encoding='utf-8', newline='\n')
    mock_zipfile.write.assert_called()

    # Assertions for SSH/SFTP operations
    mock_ssh_client.open_sftp.assert_called_once()
    mock_sftp.stat.assert_called_once_with('/home/shared/test_user/CR_FOLDER')
    mock_ssh_client.exec_command.assert_any_call('rm -rf /home/shared/test_user/CR_FOLDER/*')
    mock_sftp.put.assert_called_once()
    mock_sftp.close.assert_called()
    mock_ssh_client.exec_command.assert_any_call('cd /home/shared/test_user/CR_FOLDER && unzip -o SFTP_CR_test_session.zip')
    mock_ssh_client.exec_command.assert_any_call('cd /home/shared/test_user/CR_FOLDER && ./RUN_CR_test_session.txt')

    # Assertions for signals
    worker.output.emit.assert_called()
    worker.completed.emit.assert_called_with("Upload completed successfully.")
    worker.progress.emit.assert_called()

def test_upload_worker_run_ipdb_not_found(upload_worker, mocker):
    worker, _, _ = upload_worker
    mocker.patch('os.path.exists', return_value=False)
    mocker.patch('os.path.join', side_effect=lambda *args: '/'.join(args))

    worker.run()

    worker.output.emit.assert_any_call("[ERROR] IPDB file not found: 00_IPDB/ipdb_delim_ALLOSS_NEW.txt")
    worker.error.emit.assert_called_with("[ERROR] IPDB file not found: 00_IPDB/ipdb_delim_ALLOSS_NEW.txt")
    worker.completed.emit.assert_called_with("[ERROR] IPDB file not found: 00_IPDB/ipdb_delim_ALLOSS_NEW.txt")

def test_upload_worker_run_sftp_error(upload_worker, mocker):
    worker, mock_ssh_client, _ = upload_worker
    mocker.patch('os.path.exists', side_effect=lambda x: x == '00_IPDB/ipdb_delim_ALLOSS_NEW.txt')
    mocker.patch('os.makedirs')
    mocker.patch('os.path.join', side_effect=lambda *args: '/'.join(args))
    mocker.patch('os.listdir', return_value=['log1.log'])
    mocker.patch('os.path.basename', return_value='folder1')
    mocker.patch('os.path.getsize', return_value=100)
    mocker.patch('os.remove')
    mocker.patch('shutil.rmtree')
    mocker.patch('pandas.read_csv', return_value=MagicMock(fillna=lambda x: MagicMock()))
    mocker.patch('zipfile.ZipFile', MagicMock())
    mocker.patch('lib.workers.QFileInfo', return_value=MagicMock(size=100))
    mocker.patch('builtins.open', mocker.mock_open())

    mock_ssh_client.open_sftp.side_effect = Exception("SFTP connection error")

    worker.run()

    worker.output.emit.assert_any_call("Upload failed: SFTP connection error")
    worker.error.emit.assert_called_with("Upload failed: SFTP connection error")


@pytest.fixture
def subfolder_loader_worker(mocker):
    mocker.patch('lib.workers.QObject')
    mocker.patch('lib.workers.pyqtSignal', return_value=MagicMock())
    worker = SubfolderLoaderWorker('/test/path')
    return worker

def test_subfolder_loader_worker_run_happy_path(subfolder_loader_worker, mocker):
    worker = subfolder_loader_worker
    mocker.patch('os.listdir', return_value=['sub1', 'file.txt', 'sub2'])
    mocker.patch('os.path.join', side_effect=lambda *args: '/'.join(args))
    mocker.patch('os.path.isdir', side_effect=lambda x: x in ['/test/path/sub1', '/test/path/sub2'])

    worker.run()

    worker.finished.emit.assert_called_once_with(['sub1', 'sub2'])

def test_subfolder_loader_worker_run_empty_folder(subfolder_loader_worker, mocker):
    worker = subfolder_loader_worker
    mocker.patch('os.listdir', return_value=[])
    mocker.patch('os.path.join', side_effect=lambda *args: '/'.join(args))
    mocker.patch('os.path.isdir', return_value=False)

    worker.run()

    worker.finished.emit.assert_called_once_with([])

def test_subfolder_loader_worker_run_error(subfolder_loader_worker, mocker):
    worker = subfolder_loader_worker
    mocker.patch('os.listdir', side_effect=Exception("Permission denied"))

    worker.run()

    worker.finished.emit.assert_called_once_with([])


@pytest.fixture
def download_log_worker(mocker):
    mocker.patch('lib.workers.QObject')
    mocker.patch('lib.workers.pyqtSignal', return_value=MagicMock())
    mock_target = {'username': 'test_user', 'host': 'test_host', 'port': 22, 'password': 'test_pass', 'session_name': 'test_session'}
    worker = DownloadLogWorker(mock_target, '/remote/path', 'CR_FOLDER')
    return worker, mock_target

def test_download_log_worker_run_happy_path(download_log_worker, mocker):
    worker, mock_target = download_log_worker

    # Mock os functions
    mocker.patch('os.makedirs')
    mocker.patch('os.path.join', side_effect=lambda *args: '/'.join(args))
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('os.remove')

    # Mock paramiko
    mock_paramiko_client = MagicMock()
    mock_paramiko_client.exec_command.return_value = (MagicMock(), MagicMock(read=lambda: b'1\n'), MagicMock(read=lambda: b''))
    mock_paramiko_sftp = MagicMock()
    mock_paramiko_client.open_sftp.return_value = mock_paramiko_sftp
    mock_paramiko_sftp.stat.return_value = MagicMock(st_size=100)
    mocker.patch('paramiko.SSHClient', return_value=mock_paramiko_client)
    mocker.patch('paramiko.AutoAddPolicy')

    # Mock zipfile
    mock_zipfile = MagicMock()
    mocker.patch('zipfile.ZipFile', return_value=mock_zipfile)
    mock_zipfile.__enter__.return_value = mock_zipfile
    mock_zipfile.__exit__.return_value = None

    worker.run()

    worker.output.emit.assert_called()
    mock_paramiko_client.connect.assert_called_once_with('test_host', 22, 'test_user', 'test_pass')
    mock_paramiko_client.exec_command.assert_any_call('cd /remote && zip -r /home/shared/test_user/00_CR_FOLDER_download.zip path')
    mock_paramiko_sftp.get.assert_called_once()
    mock_paramiko_client.close.assert_called()
    worker.completed.emit.assert_called_with("Download completed for test_session")

def test_download_log_worker_run_zip_error(download_log_worker, mocker):
    worker, _ = download_log_worker
    mocker.patch('os.makedirs')
    mocker.patch('os.path.join', side_effect=lambda *args: '/'.join(args))

    mock_paramiko_client = MagicMock()
    mock_paramiko_client.exec_command.return_value = (MagicMock(), MagicMock(read=lambda: b''), MagicMock(read=lambda: b'zip error'))
    mocker.patch('paramiko.SSHClient', return_value=mock_paramiko_client)
    mocker.patch('paramiko.AutoAddPolicy')

    worker.run()

    worker.output.emit.assert_any_call("[ZIP ERROR] zip error")
    worker.error.emit.assert_called_with("Download failed for test_session: Remote zipping failed.")
    mock_paramiko_client.close.assert_called_once()

def test_download_log_worker_run_no_files_to_download(download_log_worker, mocker):
    worker, _ = download_log_worker
    mocker.patch('os.makedirs')
    mocker.patch('os.path.join', side_effect=lambda *args: '/'.join(args))

    mock_paramiko_client = MagicMock()
    mock_paramiko_client.exec_command.return_value = (MagicMock(), MagicMock(read=lambda: b'0\n'), MagicMock(read=lambda: b''))
    mocker.patch('paramiko.SSHClient', return_value=mock_paramiko_client)
    mocker.patch('paramiko.AutoAddPolicy')

    worker.run()

    worker.output.emit.assert_any_call("[SKIP] No files found in /remote/path. Skipping zip and download.")
    worker.completed.emit.assert_called_with("No files to download for test_session")
    mock_paramiko_client.close.assert_called_once()

def test_download_log_worker_run_bad_zip_file(download_log_worker, mocker):
    worker, _ = download_log_worker
    mocker.patch('os.makedirs')
    mocker.patch('os.path.join', side_effect=lambda *args: '/'.join(args))
    mocker.patch('os.path.exists', return_value=True)
    mocker.patch('os.remove')

    mock_paramiko_client = MagicMock()
    mock_paramiko_client.exec_command.return_value = (MagicMock(), MagicMock(read=lambda: b'1\n'), MagicMock(read=lambda: b''))
    mock_paramiko_sftp = MagicMock()
    mock_paramiko_client.open_sftp.return_value = mock_paramiko_sftp
    mock_paramiko_sftp.stat.return_value = MagicMock(st_size=100)
    mocker.patch('paramiko.SSHClient', return_value=mock_paramiko_client)
    mocker.patch('paramiko.AutoAddPolicy')

    mocker.patch('zipfile.ZipFile', side_effect=zipfile.BadZipFile("Bad zip"))

    worker.run()

    worker.output.emit.assert_any_call("[WARNING] Downloaded file 02_DOWNLOAD/test_session_download.zip is a bad zip file. Deleting...")
    mocker.patch('os.remove').assert_called_with('02_DOWNLOAD/test_session_download.zip')
    worker.completed.emit.assert_called_with("Download completed for test_session")

def test_download_log_worker_run_exception(download_log_worker, mocker):
    worker, _ = download_log_worker
    mocker.patch('os.makedirs', side_effect=Exception("Test error"))

    worker.run()

    worker.output.emit.assert_any_call("Download failed for test_session: Test error")
    worker.error.emit.assert_called_with("Download failed for test_session: Test error")
