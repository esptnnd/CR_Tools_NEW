import builtins
import importlib
import sys
from types import ModuleType
import io
import os
import pytest


# --- Prepare fake external modules before importing the target module ---
def _make_fake_pyqt5():
    PyQt5 = ModuleType("PyQt5")
    QtWidgets = ModuleType("PyQt5.QtWidgets")
    QtCore = ModuleType("PyQt5.QtCore")

    # Minimal signal implementation
    class FakeSignal:
        def __init__(self, *args, **kwargs):
            self._callbacks = []

        def connect(self, cb):
            self._callbacks.append(cb)

        def emit(self, *args, **kwargs):
            for cb in list(self._callbacks):
                try:
                    cb(*args, **kwargs)
                except Exception:
                    pass

    class FakeQThread:
        def __init__(self):
            pass

    # Widget stubs
    class FakeWidget:
        def __init__(self, *args, **kwargs):
            self._children = []

        def setWindowTitle(self, *args, **kwargs):
            pass

        def setGeometry(self, *args, **kwargs):
            pass

        def setCentralWidget(self, *args, **kwargs):
            pass

        def show(self, *args, **kwargs):
            pass

        def close(self, *args, **kwargs):
            pass

    class FakeQApplication:
        def __init__(self, args):
            pass

        def exec_(self):
            return 0

    class FakeQFileDialog:
        @staticmethod
        def getExistingDirectory(parent, title, start):
            return ""  # default empty

    class FakeClicked:
        def connect(self, cb):
            # store but do not call
            self._cb = cb

    class FakePushButton(FakeWidget):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.clicked = FakeClicked()

    class FakeListWidget(FakeWidget):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self._items = []

        def setSelectionMode(self, *args, **kwargs):
            pass

        def setStyleSheet(self, *args, **kwargs):
            pass

        def clear(self):
            self._items = []

        def addItems(self, items):
            self._items.extend(items)

        def selectedItems(self):
            # Return objects that have text() method
            return [type("It", (), {"text": lambda self=item: self})() for item in self._items]

    class FakeVBoxLayout:
        def __init__(self, *args, **kwargs):
            pass

    class FakeWidgetSimple(FakeWidget):
        pass

    class FakeMessageBox:
        Information = 1
        Critical = 2

        def __init__(self):
            self._icon = None
            self._title = None
            self._text = None

        def setIcon(self, icon):
            self._icon = icon

        def setWindowTitle(self, title):
            self._title = title

        def setText(self, text):
            self._text = text

        def exec_(self):
            return 0

    class FakeLabel:
        def __init__(self, *args, **kwargs):
            pass

        def setStyleSheet(self, *args, **kwargs):
            pass

    class FakeLineEdit:
        def __init__(self, *args, **kwargs):
            self._text = ""

        def setPlaceholderText(self, *args, **kwargs):
            pass

        def text(self):
            return self._text

        def setText(self, t):
            self._text = t

    class FakeProgressBar:
        def __init__(self):
            self.value = 0

        def setValue(self, v):
            self.value = v

    class FakeAbstractItemView:
        MultiSelection = 1

    # Assign to QtWidgets
    QtWidgets.QApplication = FakeQApplication
    QtWidgets.QMainWindow = FakeWidget
    QtWidgets.QFileDialog = FakeQFileDialog
    QtWidgets.QListWidget = FakeListWidget
    QtWidgets.QVBoxLayout = FakeVBoxLayout
    QtWidgets.QPushButton = FakePushButton
    QtWidgets.QWidget = FakeWidgetSimple
    QtWidgets.QMessageBox = FakeMessageBox
    QtWidgets.QLabel = FakeLabel
    QtWidgets.QLineEdit = FakeLineEdit
    QtWidgets.QProgressBar = FakeProgressBar
    QtWidgets.QAbstractItemView = FakeAbstractItemView

    # QtCore
    QtCore.QThread = FakeQThread
    QtCore.pyqtSignal = lambda *args, **kwargs: FakeSignal()
    QtCore.QObject = type("QObject", (), {})
    QtCore.Qt = type("X", (), {"AlignCenter": 0})

    PyQt5.QtWidgets = QtWidgets
    PyQt5.QtCore = QtCore
    return PyQt5


def _make_fake_openpyxl():
    openpyxl = ModuleType("openpyxl")

    class FakeCell:
        def __init__(self, value=None):
            self.value = value
            self.font = None
            self.fill = None
            self.border = None

    class FakeSheet:
        def __init__(self, title="Sheet"):
            self._cells = {}
            self.title = title

        def cell(self, row, column, value=None):
            c = FakeCell(value)
            self._cells[(row, column)] = c
            return c

        def append(self, row):
            pass

        @property
        def columns(self):
            return []

    class FakeWorkbook:
        def __init__(self):
            self._sheets = [FakeSheet()]
            self.active = self._sheets[0]

        def create_sheet(self, title=None):
            s = FakeSheet(title)
            self._sheets.append(s)
            return s

        def save(self, filename):
            # do not write to disk
            self._saved_to = filename

    # Minimal styles/utils
    styles = ModuleType("openpyxl.styles")
    styles.Font = lambda **kwargs: object()
    styles.PatternFill = lambda **kwargs: object()
    styles.Border = lambda **kwargs: object()
    styles.Side = lambda **kwargs: object()

    utils = ModuleType("openpyxl.utils")
    def get_column_letter(n):
        # very small implementation
        return chr(64 + n) if n > 0 and n < 27 else 'Z'

    utils.get_column_letter = get_column_letter

    dataf = ModuleType("openpyxl.utils.dataframe")
    def dataframe_to_rows(df, index=True, header=True):
        # return empty sequence for safety
        return []

    dataf.dataframe_to_rows = dataframe_to_rows

    openpyxl.Workbook = FakeWorkbook
    openpyxl.styles = styles
    openpyxl.utils = utils
    openpyxl.utils.dataframe = dataf
    return openpyxl


def _make_fake_tqdm():
    def fake_tqdm(iterable, **kwargs):
        return iterable

    return fake_tqdm


def _make_fake_pandas():
    pd = ModuleType("pandas")

    class FakeSeries:
        def __init__(self, data):
            self._data = data

        def apply(self, fn):
            return [fn(x) for x in self._data]

    class FakeDataFrame:
        def __init__(self, data=None, columns=None):
            # data: list of tuples
            self._columns = columns or []
            self._rows = [dict(zip(self._columns, row)) for row in data] if data else []

        @property
        def empty(self):
            return len(self._rows) == 0

        def __getitem__(self, key):
            if key in self._columns:
                return FakeSeries([r.get(key) for r in self._rows])
            # allow df['TAG'] assignment flow
            return FakeSeries([])

        def __setitem__(self, key, value):
            # assume value is list
            for i, r in enumerate(self._rows):
                r[key] = value[i] if i < len(value) else None
            if key not in self._columns:
                self._columns.append(key)

        def iterrows(self):
            # emulate pandas iterrows: yields (index, rowSeries)
            for r in self._rows:
                yield (None, r)

        def apply(self, fn):
            return [fn(r) for r in self._rows]

        def groupby(self, key):
            class G:
                def __init__(self, rows, key):
                    self.rows = rows
                    self.key = key

                def size(self):
                    counts = {}
                    for r in self.rows:
                        k = r.get(self.key)
                        counts[k] = counts.get(k, 0) + 1
                    # return DataFrame-like list of dicts
                    out = [ {self.key: k, 'Count': v} for k, v in counts.items() ]
                    class R:
                        def reset_index(self, name=None):
                            return out
                    return R()

            return G(self._rows, key)

    def fake_read_csv(buf_or_str, sep=';', engine=None):
        # parse simple CSV-like string
        if hasattr(buf_or_str, 'read'):
            txt = buf_or_str.read()
        else:
            txt = str(buf_or_str)
        lines = [l for l in txt.splitlines() if l.strip()]
        if not lines:
            return FakeDataFrame([])
        headers = [h.strip() for h in lines[0].split(sep)]
        rows = []
        for l in lines[1:]:
            parts = [p.strip() for p in l.split(sep)]
            rows.append(tuple(parts))
        return FakeDataFrame(rows, columns=headers)

    def fake_pivot_table(df, values=None, index=None, aggfunc=None, fill_value=0):
        # compute simple counts by index keys
        counts = {}
        for r in df._rows:
            key = tuple(r.get(k) for k in index)
            counts[key] = counts.get(key, 0) + 1
        class Pivot:
            def iterrows(self_inner):
                for k, v in counts.items():
                    yield (k, [v])

            def sum(self_inner):
                return list(counts.values())

            def iteritems(self_inner):
                return iter(counts.items())

        return Pivot()

    pd.DataFrame = FakeDataFrame
    pd.read_csv = fake_read_csv
    pd.pivot_table = fake_pivot_table
    pd.merge = lambda a, b, **kwargs: a
    pd.notna = lambda x: x is not None

    return pd


# Set up fake modules in sys.modules so importing report_generator uses them
fake_pyqt5 = _make_fake_pyqt5()
sys.modules['PyQt5'] = fake_pyqt5
sys.modules['PyQt5.QtWidgets'] = fake_pyqt5.QtWidgets
sys.modules['PyQt5.QtCore'] = fake_pyqt5.QtCore
sys.modules['openpyxl'] = _make_fake_openpyxl()
sys.modules['openpyxl.styles'] = sys.modules['openpyxl'].styles
sys.modules['openpyxl.utils'] = sys.modules['openpyxl'].utils
sys.modules['openpyxl.utils.dataframe'] = sys.modules['openpyxl'].utils.dataframe
sys.modules['tqdm'] = ModuleType('tqdm')
sys.modules['tqdm'].tqdm = _make_fake_tqdm()

# Provide a placeholder pandas so import succeeds; we'll patch report_generator.pd with a richer fake after import if needed
sys.modules['pandas'] = ModuleType('pandas')


import importlib

# Now import the module under test
report_generator = importlib.import_module('lib.report_generator')

# After import, replace pandas with our fake implementation for test usage
report_generator.pd = _make_fake_pandas()
report_generator.openpyxl = sys.modules['openpyxl']
report_generator.tqdm = sys.modules['tqdm'].tqdm


def test_CATEGORY_CHECKING1_various():
    f = report_generator.CATEGORY_CHECKING1
    assert f("Proxy ID something")[0] == "1 MOs created"
    assert f("Executed")[0] == "1 MOs set"
    assert f("Mo deleted")[0] == "Mo deleted"
    assert f("MO already exists")[0].startswith("1 MOs")
    assert f("Parent MO not found")[0] == "Parent MO not found"
    assert f("MoNotFound")[0] == "MO not found"
    assert f("operation-failed due to X")[0].startswith("ERROR")


def test_CATEGORY_CHECKING_various():
    f = report_generator.CATEGORY_CHECKING
    # direct known strings
    ret, color = f("1 MOs created")
    assert "1 MOs created" in ret or ret == "1 MOs created"
    # total attempted with numeric >0
    sample = "Total something MOs attempted, 5 MOs Success"
    ret, color = f(sample)
    assert "Success" in ret or ret.startswith("Success")
    # TOTAL X
    ret, color = f("TOTAL X should show success")
    assert color == "42FF00"


def test_check_folder_creates_and_returns(tmp_path, monkeypatch):
    # Ensure os.path.exists returns False once so directory is created
    called = {}

    def fake_exists(p):
        return called.get('exists', False)

    def fake_makedirs(p):
        called['made'] = p

    monkeypatch.setattr(report_generator.os.path, 'exists', fake_exists)
    monkeypatch.setattr(report_generator.os, 'makedirs', fake_makedirs)

    app = report_generator.ExcelReaderApp(start_path=str(tmp_path))
    out = app.check_folder(str(tmp_path / 'out'))
    assert out == str(tmp_path / 'out')
    assert called.get('made') == str(tmp_path / 'out')


def test_check_folder_when_exists(monkeypatch):
    monkeypatch.setattr(report_generator.os.path, 'exists', lambda p: True)
    made = []
    monkeypatch.setattr(report_generator.os, 'makedirs', lambda p: made.append(p))
    app = report_generator.ExcelReaderApp()
    out = app.check_folder('somewhere')
    assert out == 'somewhere'
    assert made == []


def test_process_single_log_empty_and_nonexistent(monkeypatch):
    # Simulate a non-existing file: open will raise for the mmap section but function should handle it
    def fake_open_fail(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(builtins, 'open', fake_open_fail)
    res = report_generator.process_single_log(("no.log", ".", "sel"))
    # Should return dictionary with keys even if file not found
    assert isinstance(res, dict)
    assert "log_data" in res


def test_process_single_log_with_sections(monkeypatch):
    # Create fake file content that contains LOG_Alarm_bf and a CSV header+row
    content_lines = [
        "####LOG_Alarm_bf\n",
        "MO;Severity;Object;Problem;Cause;AdditionalText\n",
        "MO1;High;Obj;Prob;Cause;More\n",
    ]

    class DummyFile:
        def __init__(self, lines):
            self._lines = lines

        def fileno(self):
            return 0

        def readlines(self):
            return self._lines

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyMmap:
        def __init__(self, lines):
            self._b = [l.encode() for l in lines]
            self._i = 0

        def readline(self):
            if self._i >= len(self._b):
                return b''
            r = self._b[self._i]
            self._i += 1
            return r

    # First with mmap and open used earlier in function: return DummyFile then DummyMmap
    def fake_open(path, *args, **kwargs):
        return DummyFile(content_lines)

    monkeypatch.setattr(builtins, 'open', fake_open)
    monkeypatch.setattr(report_generator.mmap, 'mmap', lambda fileno, length, access: DummyMmap(content_lines))

    res = report_generator.process_single_log(("f.log", ".", "SEL"))
    assert isinstance(res, dict)
    # The df_LOG_Alarm_bf should be a FakeDataFrame and not empty
    assert 'df_LOG_Alarm_bf' in res


def test_ExcelWriterThread_run_calls_write_and_emits(monkeypatch):
    called = {}

    def fake_write(log_data, excel_filename, selected_file, progress_callback=None, **kwargs):
        called['args'] = (log_data, excel_filename, selected_file)
        # call progress callback a few times if provided
        if progress_callback:
            progress_callback(50)
            progress_callback(100)

    monkeypatch.setattr(report_generator, 'write_logs_to_excel', fake_write)

    # Create thread and attach a listener to finished
    tw = report_generator.ExcelWriterThread([], 'out.xlsx', 'SEL')
    finished_called = {}

    def on_finished(path):
        finished_called['path'] = path

    tw.finished.connect(on_finished)
    # call run directly (no real threading)
    tw.run()
    assert called.get('args')[1] == 'out.xlsx'
    assert finished_called.get('path') == 'out.xlsx'


def test_write_logs_to_excel_minimal(monkeypatch):
    # Provide minimal log_data and ensure no real file writes happen
    saved = {}
    class FakeWB:
        def __init__(self):
            self.sheets = []

        def create_sheet(self, title=None):
            return None

        def save(self, filename):
            saved['file'] = filename

    # Patch openpyxl.Workbook used inside the module
    monkeypatch.setattr(report_generator, 'openpyxl', sys.modules['openpyxl'])

    # Provide a tiny log_data list
    log_data = [ ("F", "Site1", "Script1", "CMD", "Executed", "full", ["line"]) ]

    # Call the function; our fake pandas handles internal operations
    report_generator.write_logs_to_excel(log_data, "fake.xlsx", "SEL", progress_callback=lambda v: None)
    # If no exception, assume success (no disk writes performed because openpyxl.save is stubbed)
    assert True
