import pytest
from unittest.mock import MagicMock, patch, mock_open
import os
import pandas as pd

# Since we are not using patch.dict, we need to handle the case where PyQt5 is not installed.
# We can do this by adding a try-except block around the import.
try:
    from PyQt5.QtWidgets import QFileDialog, QWidget
    from PyQt5.QtCore import QThread, pyqtSignal
except ImportError:
    # If PyQt5 is not installed, create mock classes for the tests to run.
    class QWidget:
        pass
    class QFileDialog:
        @staticmethod
        def getExistingDirectory(parent=None, caption='', directory='', options=None):
            return ''
        @staticmethod
        def getOpenFileName(parent=None, caption='', directory='', filter=''):
            return ('', '')
    class QThread:
        def __init__(self, parent=None):
            pass
        def run(self):
            pass
        def start(self):
            pass
    class pyqtSignal:
        def __init__(self, *args, **kwargs):
            pass
        def emit(self, *args, **kwargs):
            pass

# Now we can import the module to be tested.
from lib.rehoming import merge_lacrac_files, parse_dump, ParseDumpWorker, select_dump_and_excel

@pytest.fixture
def mock_openpyxl(mocker):
    """Fixture to mock openpyxl."""
    mock_ws = MagicMock()
    mock_wb = MagicMock()
    mock_wb.active = mock_ws
    mocker.patch('lib.rehoming.Workbook', return_value=mock_wb)
    return mock_wb, mock_ws

def test_merge_lacrac_files_happy_path(mocker, mock_openpyxl):
    """Test merge_lacrac_files with valid input files."""
    mock_wb, mock_ws = mock_openpyxl
    mock_log_callback = MagicMock()
    files = ['file1.txt']
    output_dir = '/tmp'

    mocker.patch('os.path.basename', side_effect=lambda x: x)
    mocker.patch('os.path.join', return_value='/tmp/DATA_CELL.xlsx')

    file_content = "HEADER1;HEADER2\nDATA1A;DATA1B"
    mocker.patch('builtins.open', mock_open(read_data=file_content))

    result = merge_lacrac_files(files, output_dir, mock_log_callback)

    assert result is True
    mock_ws.append.assert_any_call(['HEADER1', 'HEADER2'])
    mock_ws.append.assert_any_call(['DATA1A', 'DATA1B'])
    mock_wb.save.assert_called_once_with('/tmp/DATA_CELL.xlsx')

def test_parse_dump_happy_path(mocker):
    """Test parse_dump with valid input and df_ref_raw."""
    mock_log_callback = MagicMock()
    mock_progress_callback = MagicMock()
    mock_df_ref_raw = pd.DataFrame({
        'RNC_SOURCE': ['RNC1'], 'RNC_TARGET': ['RNC2'], 'IUBLINK': ['IUB1'], 'CELLNAME': ['CELL1'],
        'LAC_PLAN': [100], 'RAC_PLAN': [200], 'URA_PLAN': [300], 'SAC_PLAN': [400], 'SAC': [500]
    })
    # Add IubLink to data_groups to avoid KeyError
    mocker.patch('lib.rehoming.manipulate_data_df_cell', return_value=(pd.DataFrame(), pd.DataFrame({'IubLink': ['IUB1']}), pd.DataFrame()))
    folder_path = '/test/dump_folder'

    mocker.patch('os.makedirs')
    mocker.patch('os.listdir', return_value=['dump1.txt'])
    mocker.patch('os.path.join', side_effect=lambda *args: '/'.join(args))
    mocker.patch('time.sleep')

    file_content = "FDN : SubNetwork=1,MeContext=RNC1,ManagedElement=1,UtranCell=CELL1,IubLink=IUB1\nUtranCellId:CELL1\nroutingAreaRef:OLD_RA\nuraRef:OLD_URA\nserviceAreaRef:OLD_SA\nlocalCellId:1\nkey1:value1"
    mocker.patch('builtins.open', mock_open(read_data=file_content))
    mocker.patch('pandas.DataFrame.to_csv')

    mocker.patch('lib.rehoming.process_cmbulk_export')

    parse_dump(folder_path, mock_log_callback, mock_progress_callback, mock_df_ref_raw)

    mock_log_callback.assert_any_call("=== Parsing log files ===")

def test_parsedumpworker_run_happy_path(mocker):
    """Test ParseDumpWorker.run on a happy path."""
    mocker.patch('lib.rehoming.QThread', QThread)
    mocker.patch('lib.rehoming.pyqtSignal', pyqtSignal)

    worker = ParseDumpWorker('/test/folder', df_ref=MagicMock(), exclude_types=['type1'])
    worker.log = MagicMock()
    worker.progress = MagicMock()
    worker.finished = MagicMock()
    worker.error = MagicMock()

    mock_parse_dump = mocker.patch('lib.rehoming.parse_dump')
    mocker.patch('os.path.join', return_value='/test/folder/01_output_script')

    worker.run()

    mock_parse_dump.assert_called_once()
    worker.finished.emit.assert_called_once()

def test_select_dump_and_excel_happy_path(mocker):
    """Test select_dump_and_excel on a happy path."""
    mock_log_callback = MagicMock()
    parent = None # Pass None as parent

    # Patch the static methods of QFileDialog
    mocker.patch('lib.rehoming.QFileDialog.getExistingDirectory', return_value='/selected/folder')
    mocker.patch('lib.rehoming.QFileDialog.getOpenFileName', return_value=('/selected/folder/DATA_CELL.xlsx', 'Excel Files (*.xlsx)'))

    mocker.patch('os.path.expanduser', return_value='/home/user')
    mocker.patch('pandas.read_excel', return_value=pd.DataFrame({'REF': [1, 2]}))

    folder_path, df_ref = select_dump_and_excel(parent, mock_log_callback)

    assert folder_path == '/selected/folder'
    assert isinstance(df_ref, pd.DataFrame)