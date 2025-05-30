# -----------------------------------------------------------------------------
# Author      : esptnnd
# Company     : Ericsson Indonesia
# Created on  : 7 May 2025
# Improve on  : 29 May 2025
# Description : CR TOOLS by esptnnd — built for the ECT Project to help the team
#               execute faster, smoother, and with way less hassle.
#               Making life easier, one script at a time!
# -----------------------------------------------------------------------------
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
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QTextCursor
import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
import re
import time as today
from datetime import datetime
import time
import zipfile
from collections import Counter
from queue import Queue
import mmap
from concurrent.futures import ProcessPoolExecutor, as_completed
from .style import (
    StyledPushButton, StyledLineEdit, 
    StyledProgressBar, StyledLabel, StyledListWidget,
    setup_window_style, update_window_style
)

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
    return TAG_REMARK, TAG_COLOR


        
    
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


        
def write_logs_to_excel(log_data, excel_filename, selected_file):
    # Create a new workbook and select the active sheet
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Log Analysis"

    # Define styles
    header_font = Font(name='Arial', size=11, bold=True)
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font_color = Font(color="FFFFFF")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # Write headers
    headers = ["Node", "Script", "Command", "Result", "Full Result"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
        cell.font = header_font_color
        cell.border = border

    # Write data
    for row, (_, node_log, type_script, line_execute, TAG_RESULT, TAG_RESULT_FULL, _) in enumerate(log_data, 2):
        ws.cell(row=row, column=1, value=node_log).border = border
        ws.cell(row=row, column=2, value=type_script).border = border
        ws.cell(row=row, column=3, value=line_execute).border = border
        ws.cell(row=row, column=4, value=TAG_RESULT).border = border
        ws.cell(row=row, column=5, value=TAG_RESULT_FULL).border = border

    # Adjust column widths
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column].width = adjusted_width

    # Save the workbook
    wb.save(excel_filename)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    sys.exit(app.exec_())
