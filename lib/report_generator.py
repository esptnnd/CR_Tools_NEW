import sys
import os
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QFileDialog,
    QListWidget,
    QVBoxLayout,
    QPushButton,
    QWidget,
    QMessageBox,
    QLabel,
    QLineEdit,
    QProgressBar,
    QAbstractItemView
)
import openpyxl
from openpyxl.styles import Font, PatternFill , Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows


from PyQt5.QtCore import Qt, QThread, pyqtSignal,QObject
import re
import time as today
from datetime import datetime
import time
import zipfile
from collections import Counter
from queue import Queue
from PyQt5.QtWidgets import QLineEdit  # Add this import statement


from PyQt5.QtCore import QThread, pyqtSignal
import os
import re
import time
import mmap
from concurrent.futures import ProcessPoolExecutor, as_completed

# Move this function to top-level so it can be pickled by multiprocessing
def process_single_log(args):
    filename, folder_path, selected_file = args
    start_time = time.time()
    filepath = os.path.join(folder_path, filename)
    node_log = re.search(r"^(.*?).log$", filename, re.IGNORECASE).group(1) if re.search(r"^(.*?).log$", filename, re.IGNORECASE) else filename
    local_log_data = []

    # Compile regex patterns once
    pattern_cmd = re.compile(r"^[A-Z0-9\_\-]{4,180}\>(.*?)$", re.IGNORECASE)
    pattern_run_script = re.compile(r".*?run\s+.*?\$nodename\_(.*?).mos$", re.IGNORECASE)
    pattern_truni = re.compile(r"^(trun|truni)\s+(.*?)$", re.IGNORECASE)
    pattern_tag = re.compile(r'^!!!!.*?TAG\s+:"(.*?)".*?$', re.IGNORECASE)
    pattern_alt_tag = re.compile(r"^>>>\s+(\[.*?\]).*?$", re.IGNORECASE)
    pattern_set = re.compile(r"^(SET\s+.*?)$", re.IGNORECASE)
    pattern_create = re.compile(r"^(CREATE.*?)$", re.IGNORECASE)
    pattern_delete = re.compile(r"^(DELETE.*?)$", re.IGNORECASE)
    tag_errs = [
        re.compile(r"^(ERROR:.*?:.*?)$", re.IGNORECASE),
        re.compile(r"(!!!!\s+(ERROR|Processing):.*?)$", re.IGNORECASE),
        re.compile(r"(!!!!\s+Processing.*?)$", re.IGNORECASE),
        re.compile(r"^(>>>.*?:.*?)$", re.IGNORECASE),
        re.compile(r"^(Total.*?MOs\s+attempted.*?)$", re.IGNORECASE)
    ]

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as file:
            mm = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
            type_script = "NULL"
            type_script_rnc = "NULL"
            line_execute = "NULL"
            TAG_RESULT = "NULL"
            truni_script = "NULL"
            TAG_RESULT_FULL = "NULL"
            print_tag = "NULL"
            number_tag = 0
            cmd_get = "NULL"
            att_list = []

            for line in iter(mm.readline, b''):
                line = line.decode(errors='ignore')
                cmd_match = pattern_cmd.search(line)
                cmd_get_1 = cmd_match.group(1).strip() if cmd_match else line_execute

                run_match = pattern_run_script.search(line)
                if run_match:
                    type_script = run_match.group(1)

                truni_match = pattern_truni.search(cmd_get_1)
                if truni_match:
                    truni_script = truni_match.group(1)

                if truni_script != "NULL":
                    for key in ["trun", "truni"]:
                        tsr_match = re.search(fr".*?{key}\s+(.*?).mo$", line, re.IGNORECASE)
                        if tsr_match:
                            type_script_rnc = tsr_match.group(1)

                    for pattern in [pattern_create, pattern_delete, pattern_set]:
                        cmd = pattern.search(line)
                        if cmd:
                            line_execute = cmd.group(1)

                    tag = pattern_tag.search(line)
                    if tag:
                        TAG_RESULT = tag.group(1)
                        TAG_RESULT_FULL = line.rstrip()

                    tag_alt = pattern_alt_tag.search(line)
                    if tag_alt:
                        TAG_RESULT = tag_alt.group(1)
                        TAG_RESULT_FULL = line.rstrip()

                    if len(line.rstrip()) == 0 and line_execute != "NULL":
                        if len(TAG_RESULT_FULL.rstrip()) == 0:
                            TAG_RESULT = "Executed"
                        local_log_data.append((selected_file, node_log, type_script_rnc, line_execute.strip(), TAG_RESULT, TAG_RESULT_FULL, []))
                        line_execute = "NULL"
                        TAG_RESULT = "NULL"
                        TAG_RESULT_FULL = ""

                if truni_script == "NULL":
                    if pattern_cmd.match(line):
                        if number_tag == 1:
                            if re.search(r"^(del|rdel|crn|set)", cmd_get.strip(), re.IGNORECASE):
                                TAG_REPORT, TAG_COLOR = CATEGORY_CHECKING1(TAG_RESULT)
                                local_log_data.append((selected_file, node_log, type_script, line_execute.strip(), TAG_REPORT.strip(), TAG_RESULT.strip(), att_list))                                
                                
                                ###local_log_data.append((selected_file ,node_log,type_script, line_execute.strip(),TAG_REPORT.strip() ,TAG_RESULT.strip() , att_list    ))  # Store filename and line
                                TAG_RESULT = "NULL"
                                print_tag = "NULL"
                                number_tag = 0
                            else:
                                number_tag = 0
                        number_tag += 1
                        cmd_get = cmd_get_1

                    for pattern in tag_errs:
                        match = pattern.search(line)
                        if match:
                            TAG_RESULT = match.group(1)

                    if pattern_cmd.match(line):
                        att_list = ["", line.strip()]
                    else:
                        att_list.append(line.strip())

                if "Checking ip contact...Not OK" in line:
                    local_log_data.append((selected_file, node_log, "", "", "UNREMOTE", line.strip(), ""))
                if re.search(r"(?i)tbac\s*control\s*-\s*unauthori[sz]ed\s*network\s*element", line):
                    local_log_data.append((selected_file, node_log, "", "", "UNREMOTE", line.strip(), ""))

    except Exception as e:
        print(f"Error processing {filename}: {e}")
    end_time = time.time()
    print(f"Processed {filename} in {end_time - start_time:.2f}s")
    return local_log_data


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



def CATEGORY_CHECKING1(TAG_RESULT):
    # Check if the string contains certain substrings
    if "Proxy ID" in TAG_RESULT:
        TAG_REMARK = "1 MOs created"
        TAG_COLOR="42FF00"
    elif TAG_RESULT == "Executed" or re.search(r"([0-9]{1,90}\s+.*?\-\-\>.*?set\.)$", TAG_RESULT, re.IGNORECASE):
        TAG_REMARK = "1 MOs set"
        TAG_COLOR="42FF00" 
    elif TAG_RESULT == "Mo deleted":
        TAG_REMARK = "Mo deleted"
        TAG_COLOR="42FF00"             
    elif "MO already exists" in TAG_RESULT or TAG_RESULT == "MoNameAlreadyTaken":
        TAG_REMARK = "1 MOs already exists"
        TAG_COLOR="FF7575"
    elif "Parent MO not found" in TAG_RESULT:
        TAG_REMARK = "Parent MO not found"
        TAG_COLOR="FF7575"
    elif TAG_RESULT == "MoNotFound":
        TAG_REMARK = "MO not found"
        TAG_COLOR="FF7575"  
    elif re.search(r"operation\-failed", TAG_RESULT, re.IGNORECASE) or re.search(r"unknown\-attribute", TAG_RESULT, re.IGNORECASE) or "failure" in TAG_RESULT:
        TAG_REMARK = "ERROR operation-failed"
        TAG_COLOR="FF7575"             
    else:
        TAG_REMARK = TAG_RESULT 
        TAG_COLOR="FF7575"
            
    return  TAG_REMARK, TAG_COLOR 
    
    
    
def CATEGORY_CHECKING(TAG_RESULT):
    # Check if the string contains certain substrings
    check_number_executed = int(re.search(r"^Total.*?MOs\s+attempted\,\s+([0-9]{1,5})\s+MOs.*?$", TAG_RESULT, re.IGNORECASE).group(1)) if re.search(r"^(Total.*?MOs\s+attempted.*?)$", TAG_RESULT, re.IGNORECASE) else "NULL"
    Action_GET = re.search(r"^Total.*?MOs\s+attempted\,\s+[0-9]{1,5}\s+MOs\s+(.*?)$", TAG_RESULT, re.IGNORECASE).group(1) if re.search(r"^(Total.*?MOs\s+attempted.*?)$", TAG_RESULT, re.IGNORECASE) else "NULL"
    
    if TAG_RESULT == "1 MOs created" or TAG_RESULT == "1 MOs set" or TAG_RESULT == "Mo deleted":
        TAG_COLOR="42FF00"
    elif re.search(r"^Total.*?MOs\s+attempted", TAG_RESULT, re.IGNORECASE) and check_number_executed > 0:
        TAG_COLOR="42FF00"
    else:
        TAG_COLOR="FF7575"
    
    ###TOTAL X 
    if "TOTAL X" in TAG_RESULT:
        TAG_COLOR="42FF00"

    if (re.search(r"^Total.*?MOs\s+attempted", TAG_RESULT, re.IGNORECASE) and check_number_executed > 0):
        MSG = "Success"
    else:
        MSG = "Failed"
    

        
        
    if re.search(r"^Total.*?MOs\s+attempted", TAG_RESULT, re.IGNORECASE):
        TAG_RETURN = f'''{MSG} to {Action_GET}'''
    else:
        TAG_RETURN = TAG_RESULT
            
    return  TAG_RETURN, TAG_COLOR      


        
class ExcelReaderApp(QMainWindow):
    processing_finished = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.initUI()
        self.file_queue = Queue()  # Queue to store selected files
        self.append_log_data = []  # Initialize an empty list to store log data
        self.date_report = today.strftime('%Y%m%d_%H%M%S')

    
    def initUI(self):
        self.setWindowTitle("REPORT CR GENERATOR")
        self.setGeometry(100, 100, 400, 300)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        layout = QVBoxLayout(self.central_widget)

        placeholder_style = "font-style: italic;"
        # self.input_directory = QLineEdit(self)
        # # self.input_directory.setGeometry(X, Y, Length, Hight) 
        # self.input_directory.setPlaceholderText("Input Directory to save CR_FOLDER on ENM: e.g: /home/username/")
        
        self.browse_button = QPushButton("Browse", self)
        layout.addWidget(self.browse_button)
        self.browse_button.clicked.connect(self.open_folder_dialog)

        # self.file_list = QListWidget(self)
        # # self.file_list = QListWidgetItem(self)
        # layout.addWidget(self.file_list)

        self.file_list = QListWidget(self)
        self.file_list.setSelectionMode(QAbstractItemView.MultiSelection)  # Mengaktifkan modus seleksi multiple
        ##self.file_list.setSelectionMode(QAbstractItemView.SingleSelection) 
        layout.addWidget(self.file_list)
        
        # Add text box input
        self.input_directory = QLineEdit(self)
        self.input_directory.setPlaceholderText("Input Directory to upload script on ENM: e.g: /home/shared/username/sample_folder or ~/sample_folder")
        layout.addWidget(self.input_directory)        


        self.read_button = QPushButton("Generate Report", self)
        layout.addWidget(self.read_button)
        self.read_button.clicked.connect(self.read_selected_excel)

        self.quit_button = QPushButton("Quit", self)
        layout.addWidget(self.quit_button)
        self.quit_button.clicked.connect(self.close)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)


        self.show()


    def show_success_message(self, message):
        success_box = QMessageBox()
        success_box.setIcon(QMessageBox.Information)
        success_box.setWindowTitle("Success")
        success_box.setText(message)
        success_box.exec_()

    def show_error_message(self, message):
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Critical)
        error_box.setWindowTitle("Error")
        error_box.setText(message)
        error_box.exec_()


    def update_overall_progress(self, value):
        self.progress_bar.setValue(value)

    def on_thread_finished(self, file_path, log_data , selected_file , output_dir):
        ##append_data = []
        ##print(os.path.join(output_dir,selected_file ))
        report_file = f"{output_dir}\{selected_file}.xlsx"
        
        write_logs_to_excel(log_data, report_file, selected_file)
        
        ##self.show_success_message(f"Your Report Available On :\n{report_file}")
        print(f"Your Report Available On :\n{report_file}\n\n")
        ##print(log_data[0][0])
        ##print(cek)
        self.append_log_data.extend(log_data)
        
        # Check if all files are processed
        if self.file_queue.empty():
            self.processing_finished.emit()  # Signal that all files are processed
            work_dir = os.getcwd()
            self.summary_excel = os.path.join(work_dir, "output", "Summary_" + self.date_report +".xlsx")
            write_logs_to_excel(self.append_log_data, self.summary_excel, "NONAME")
            # 1. Create the DataFrame from log data with tqdm
            data_rows = [row for row in tqdm(self.append_log_data, desc="Creating DataFrame rows")]
            df = pd.DataFrame(data_rows, columns=["CR", "Site", "Script", "Command", "Report", "TAG", "Full_cmd"])
            column_names = list(df.columns)

            # Enable tqdm for pandas
            tqdm.pandas()

            pattern = r"^Total.*?MOs\s+attempted,\s+([0-9]{1,5})\s+MOs\s+(.*?)$"
            regex = re.compile(pattern)

            # Function to apply regex and format string
            def format_report(value):
                match = regex.match(str(value))
                if match:
                    attempted = int(match.group(1))
                    result = match.group(2)
                    if attempted == 0:
                        return value
                    else:    
                        return f"TOTAL X MOs {result}"
                return value  # This won't be used since we only apply to matching rows

            # Only apply to rows that match the regex
            mask = df['Report'].astype(str).str.match(pattern)
            df.loc[mask, 'Report'] = df.loc[mask, 'Report'].progress_apply(format_report)               

            # 2. Build pivot_df manually with tqdm
            grouped = df.groupby([column_names[0], column_names[4]])  # ['CR', 'Report']
            pivot_data = []

            for (cr, report), group in tqdm(grouped, desc="Building pivot_df", total=grouped.ngroups):
                pivot_data.append({
                    column_names[0]: cr,
                    column_names[4]: report,
                    'Count Result': len(group)
                })

            pivot_df = pd.DataFrame(pivot_data)

            # 3. Build pivot_df2 manually with tqdm
            grouped2 = df.groupby(column_names[0])  # ['CR']
            pivot_data2 = []

            for cr, group in tqdm(grouped2, desc="Building pivot_df2", total=grouped2.ngroups):
                pivot_data2.append({
                    column_names[0]: cr,
                    'Total': len(group)
                })

            pivot_df2 = pd.DataFrame(pivot_data2)

            # 4. Merge and calculate percentage with progress bar
            merged_df = pd.merge(pivot_df, pivot_df2, on='CR', how='left')

            # Add progress bar while calculating percentage
            merged_df['Percentage'] = [
                '{:.1f}%'.format((count / total) * 100)
                for count, total in tqdm(zip(merged_df['Count Result'], merged_df['Total']),
                                         total=len(merged_df), desc="Calculating percentage")
            ]

            # Now you can proceed with further logic like saving or parsing summary
            self.parse_summary(merged_df, self.summary_excel)
            self.show_success_message("ALL DONE")
        
            ##print(self.append_log_data)

     

    def parse_summary(self, pivot_df, excel_temp):
        workbook = openpyxl.load_workbook(excel_temp)
        pivot_sheet = workbook.create_sheet(title="Pivot Table")
        rows = list(dataframe_to_rows(pivot_df, index=True, header=True))

        # Set column widths
        column_widths = {2: 60, 3: 30, 4: 12, 5: 6, 6: 12}
        for col_idx, width in column_widths.items():
            pivot_sheet.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

        # Write rows to worksheet with progress bar
        for r_idx, row in enumerate(tqdm(rows, desc="Creating Pivot Table", unit="row"), 1):
            for c_idx, value in enumerate(row, 1):
                cell = pivot_sheet.cell(row=r_idx, column=c_idx, value=value)

                # Apply bold font to index column
                if c_idx == 2:
                    cell.font = Font(bold=True)

                # Apply color fill to specific category
                if c_idx == 3:
                    TAG_REMARK, TAG_COLOR = CATEGORY_CHECKING(value)
                    cell.fill = PatternFill(start_color=TAG_COLOR, end_color=TAG_COLOR, fill_type="solid")

                # Apply border to all cells
                cell.border = Border(
                    left=Side(style='thin'),
                    right=Side(style='thin'),
                    top=Side(style='thin'),
                    bottom=Side(style='thin')
                )

        # Highlight the header row (first row)
        for col_idx in range(1, 7):
            pivot_sheet.cell(row=1, column=col_idx).fill = PatternFill(start_color="0EA1DD", end_color="0EA1DD", fill_type="solid")

        # Optionally delete second row (as in original)
        pivot_sheet.delete_rows(2)

        # Save the workbook
        workbook.save(excel_temp)
   

    def open_folder_dialog(self):
        self.folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if self.folder_path:
            self.populate_file_list()
    
    def populate_file_list(self):
        self.file_list.clear()
        if self.folder_path:
            folders = [
                folder
                for folder in os.listdir(self.folder_path)
                if os.path.isdir(os.path.join(self.folder_path, folder))
            ]
            self.file_list.addItems(folders)
        


     


    def read_selected_excel(self):
        self.file_queue.queue.clear()  # Clear existing queue


        selected_items = self.file_list.selectedItems()
        
        if not selected_items:
            return

        for item in selected_items:
            self.file_queue.put(item.text())

        # Start processing files
        self.process_next_file()

    def process_next_file(self):
        if not self.file_queue.empty():
            selected_file = self.file_queue.get()
            file_path = os.path.join(self.folder_path)
            work_dir = os.getcwd()
            folder_enm = self.input_directory.text()
            # Check if the input_directory is empty
         
            ##self.output_dir = os.path.join(work_dir, "output")
            self.output_dir = os.path.join(work_dir, "output")
            self.result_dir = os.path.join(work_dir, "result")
            

            try:
                self.progress_bar.setValue(0)
                self.worker_thread = WorkerThread(file_path, selected_file, self.output_dir)
                self.worker_thread.overall_progress.connect(self.update_overall_progress)
                self.worker_thread.finished.connect(self.on_thread_finished)
                self.worker_thread.finished.connect(self.process_next_file)
                self.worker_thread.start()
                
                
            except Exception as e:
                print(f"Error reading Excel file: {e}")
                self.show_error_message(f"Error reading Excel file: {e}")
        #####else:
        #####    self.processing_finished.emit()  # Signal that all files are processed
        #####    work_dir = os.getcwd()
        #####    self.summary_excel = os.path.join(work_dir, "output", "SUM.xlsx")
        #####    write_logs_to_excel(self.append_log_data, self.summary_excel, "NONAME")
        #####    self.show_success_message(f"ALL DONE")
        #####    ##print(self.append_log_data)
            
            

    # Existing methods...

    
    def check_folder (self,output_dir):
        isExist_output_dir = os.path.exists(output_dir)
                            
        if not isExist_output_dir:
            os.makedirs(output_dir)
        return output_dir

    




from tqdm import tqdm

# Function to write log data to an Excel file
def write_logs_to_excel(log_data, excel_filename, selected_file):
    # Create a new Excel workbook
    wb = openpyxl.Workbook()
    ws = wb.active

    # Define a regular expression pattern to remove illegal characters
    illegal_char_pattern = re.compile(r'[\000-\010]|[\013-\014]|[\016-\037]')

    # Write headers
    headers = ["CR", "Site", "Command", "Parameter", "Report", "TAG", "Script", "Full command log"]
    column_widths = [20, 20, 45, 25, 25, 20, 40, 70]

    for col_num, (header, width) in enumerate(zip(headers, column_widths), start=1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = Font(size=12, bold=True)
        cell.fill = PatternFill(start_color="0EA1DD", end_color="0EA1DD", fill_type="solid")
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_num)].width = width

    # Write log data with tqdm progress bar
    for idx, (FILE_LOG, Site, type_script, line_execute, TAG_RESULT, line_full_log, att_list) in tqdm(
        enumerate(log_data, start=2),
        total=len(log_data),
        desc="Writing to Excel"
    ):
        log1 = illegal_char_pattern.sub('', line_full_log)
        TAG_REMARK, TAG_COLOR = CATEGORY_CHECKING(TAG_RESULT)
        line_execute = next((m.group(1) for line in att_list if (m := re.match(r"^[A-Z0-9_\-]{4,180}>(.*?)$", line))), "") if line_execute == "NULL" else line_execute

        parameter_match = re.search(r"^SET\s+.*?\s+(.*?)\s+\=", line_execute, re.IGNORECASE)
        parameter = parameter_match.group(1) if parameter_match else ""

        if not parameter:
            parameter_match = re.search(r">\s+set\s+.*?\s+(.*?)\s+", line_execute, re.IGNORECASE)
            parameter = parameter_match.group(1) if parameter_match else ""

        # Write data to cells
        ws.cell(row=idx, column=1, value=FILE_LOG).font = Font(size=9, bold=True)
        ws.cell(row=idx, column=2, value=Site).font = Font(size=9, bold=True)
        ws.cell(row=idx, column=3, value=line_execute).font = Font(size=9)
        ws.cell(row=idx, column=4, value=parameter).font = Font(size=9)
        ws.cell(row=idx, column=5, value=TAG_REMARK).font = Font(size=9)
        ws.cell(row=idx, column=6, value=log1).font = Font(size=9)
        ws.cell(row=idx, column=7, value=type_script).font = Font(size=9)
        ws.cell(row=idx, column=8, value='\n'.join(att_list)).font = Font(size=9)

        # Apply color fill to the "Report" column
        ws.cell(row=idx, column=5).fill = PatternFill(start_color=TAG_COLOR, end_color=TAG_COLOR, fill_type="solid")

    # Create a DataFrame from the log data for pivot tables
    df = pd.DataFrame(log_data, columns=["CR", "Site", "Script", "Command", "TAG", "Full Log", "Attachments"])
    df['Report'] = df['TAG'].apply(lambda x: CATEGORY_CHECKING(x)[0])

    # Create first pivot table (by Site)
    pivot_df = pd.pivot_table(
        df,
        values='Command',
        index=['Site'],
        columns=['Report'],
        aggfunc='count',
        fill_value=0
    )

    # Add total column
    pivot_df['Total'] = pivot_df.sum(axis=1)

    # Create pivot table sheet
    pivot_sheet = wb.create_sheet(title="Pivot Table")
    
    # Write pivot table headers
    headers = ['Site'] + list(pivot_df.columns)
    for col_num, header in enumerate(headers, start=1):
        cell = pivot_sheet.cell(row=1, column=col_num, value=header)
        cell.font = Font(size=12, bold=True)
        cell.fill = PatternFill(start_color="0EA1DD", end_color="0EA1DD", fill_type="solid")
        pivot_sheet.column_dimensions[openpyxl.utils.get_column_letter(col_num)].width = 15

    # Write pivot table data
    for row_idx, (site, row) in enumerate(pivot_df.iterrows(), start=2):
        pivot_sheet.cell(row=row_idx, column=1, value=site).font = Font(size=9, bold=True)
        for col_idx, value in enumerate(row, start=2):
            cell = pivot_sheet.cell(row=row_idx, column=col_idx, value=value)
            cell.font = Font(size=9)
            cell.border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )

    # Add total row
    total_row = len(pivot_df) + 2
    pivot_sheet.cell(row=total_row, column=1, value="Total").font = Font(size=9, bold=True)
    for col_idx, value in enumerate(pivot_df.sum(), start=2):
        cell = pivot_sheet.cell(row=total_row, column=col_idx, value=value)
        cell.font = Font(size=9, bold=True)
        cell.fill = PatternFill(start_color="0EA1DD", end_color="0EA1DD", fill_type="solid")
        cell.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

    # Create second pivot table (Report Summary)
    report_summary = df.groupby('Report').size().reset_index(name='Count')
    total_commands = report_summary['Count'].sum()
    report_summary['Percentage'] = (report_summary['Count'] / total_commands * 100).round(1).astype(str) + '%'

    # Create Report Summary sheet
    report_sheet = wb.create_sheet(title="Pivot DF Summary")
    
    # Write headers
    headers = ['Report', 'Count', 'Percentage']
    for col_num, header in enumerate(headers, start=1):
        cell = report_sheet.cell(row=1, column=col_num, value=header)
        cell.font = Font(size=12, bold=True)
        cell.fill = PatternFill(start_color="0EA1DD", end_color="0EA1DD", fill_type="solid")
        report_sheet.column_dimensions[openpyxl.utils.get_column_letter(col_num)].width = 30

    # Write data
    for row_idx, (_, row) in enumerate(report_summary.iterrows(), start=2):
        # Write Report
        cell = report_sheet.cell(row=row_idx, column=1, value=row['Report'])
        cell.font = Font(size=9)
        cell.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # Write Count
        cell = report_sheet.cell(row=row_idx, column=2, value=row['Count'])
        cell.font = Font(size=9)
        cell.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # Write Percentage
        cell = report_sheet.cell(row=row_idx, column=3, value=row['Percentage'])
        cell.font = Font(size=9)
        cell.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # Apply color fill based on Report category
        _, TAG_COLOR = CATEGORY_CHECKING(row['Report'])
        cell = report_sheet.cell(row=row_idx, column=1)
        cell.fill = PatternFill(start_color=TAG_COLOR, end_color=TAG_COLOR, fill_type="solid")

    # Add total row
    total_row = len(report_summary) + 2
    report_sheet.cell(row=total_row, column=1, value="Total").font = Font(size=9, bold=True)
    report_sheet.cell(row=total_row, column=2, value=total_commands).font = Font(size=9, bold=True)
    report_sheet.cell(row=total_row, column=3, value="100%").font = Font(size=9, bold=True)

    # Format total row
    for col in range(1, 4):
        cell = report_sheet.cell(row=total_row, column=col)
        cell.fill = PatternFill(start_color="0EA1DD", end_color="0EA1DD", fill_type="solid")
        cell.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

    # Save the Excel workbook
    wb.save(excel_filename)
     







if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = ExcelReaderApp()
    sys.exit(app.exec_())
