# -----------------------------------------------------------------------------
# Author      : esptnnd
# Company     : Ericsson Indonesia
# Created on  : 7 May 2025
# Description : CR TOOLS by esptnnd — built for the ECT Project to help the team
#               execute faster, smoother, and with way less hassle.
#               Making life easier, one script at a time!
# -----------------------------------------------------------------------------

import os
import pandas as pd
import zipfile
import re
import time
import subprocess
from PyQt5.QtWidgets import QApplication, QProgressDialog, QMessageBox # Needed for UI elements
from PyQt5.QtCore import QTimer
import openpyxl


def check_logs_and_export_to_excel(parent=None, compare_before=False):
    import os
    import pandas as pd
    import zipfile

    download_dir = os.path.join(os.path.dirname(__file__), '..', '02_DOWNLOAD') # Adjust path to 02_DOWNLOAD
    zip_files = [fname for fname in os.listdir(download_dir) if fname.lower().endswith('.zip')]
    result_rows = []
    result_alarm_check = []  # New list for alarm data
    result_cellstatus_check = []  # New list for cell status data
    progress = None

    # Load BEFORE.xlsx if compare_before is True
    df_alarm_before = None
    if compare_before:
        before_path = os.path.join(os.path.dirname(__file__), '..', '00_IPDB', 'BEFORE.xlsx')
        if os.path.exists(before_path):
            try:
                if QApplication.instance() is not None:
                    progress = QProgressDialog("Loading BEFORE.xlsx...", None, 0, 1, parent)
                    progress.setWindowTitle("Loading Before Data")
                    progress.setMinimumDuration(0)
                    progress.setValue(0)
                    progress.setCancelButton(None)
                    progress.show()
                
                df_alarm_before = pd.read_excel(before_path, sheet_name='Alarm_Before')
                
                if progress is not None:
                    progress.setValue(1)
                    progress.close()
            except Exception as e:
                print(f"Error loading BEFORE.xlsx: {e}")
                if progress is not None:
                    progress.close()
                QMessageBox.warning(parent, "Warning", f"Could not load BEFORE.xlsx: {e}")

    # Identify non-empty zip files
    loop_zip_ok_file = []
    total_zips = len(zip_files)
    if QApplication.instance() is not None:
        progress = QProgressDialog("Checking zip files...", None, 0, total_zips, parent)
        progress.setWindowTitle("Checking Zips")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.setCancelButton(None)
        progress.show()

    for idx, fname in enumerate(zip_files):
        zip_path = os.path.join(download_dir, fname)
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Check if the zip file is empty
                if zf.namelist(): # Check if namelist is NOT empty
                    loop_zip_ok_file.append(zip_path)
                else:
                    print(f"[INFO] Skipping empty zip file: {fname}")
        except zipfile.BadZipFile:
            print(f"Skipping bad zip file: {fname}")
        except Exception as e:
            print(f"Error processing zip file {fname} during check: {e}")

        if progress is not None:
            progress.setValue(idx + 1)
            QApplication.processEvents()

    if progress is not None:
        progress.close()

    # Now process the non-empty zip files
    if QApplication.instance() is not None:
        progress = QProgressDialog("Checking logs and exporting...", None, 0, len(loop_zip_ok_file), parent)
        progress.setWindowTitle("Checking Logs")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.setCancelButton(None)
        progress.show() # This might block the UI update, consider using a timer or worker for heavy tasks


    result_rows = []

    for idx, zip_path in enumerate(loop_zip_ok_file):
        fname = os.path.basename(zip_path)
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for member in zf.namelist():
                    # Looking for LOG/<ANY_FOLDER>/<NODENAME>.log
                    parts = member.split('/')
                    if len(parts) == 3 and parts[0] == 'LOG' and parts[2].endswith('.log'):
                        folder = parts[1]
                        nodename = parts[2][:-4]  # remove .log
                        try:
                            with zf.open(member) as f:
                                # Read lines safely, handle potential errors
                                try:
                                    # Added 'rb' mode for reading binary, and decode
                                    lines = [line.decode(errors='ignore').strip() for line in f.readlines()]
                                except Exception as read_err:
                                     print(f"Error reading {member} in {fname}: {read_err}")
                                     lines = [] # Assign empty list on error

                            # Update: UNREMOTE if either condition is met
                            if any('Checking ip contact...Not OK' in line for line in lines) or any(line.startswith('Unable to connect to ') for line in lines):
                                remark = 'UNREMOTE'
                            else:
                                remark = 'OK'
                            result_rows.append({
                                'FILE': fname,
                                'FOLDER': folder,
                                'NODENAME': nodename,
                                'REMARK': remark,
                                'Count': len(lines)
                            })

                            # Check for alarm logs in 99_CONCEK2 folder
                            if len(parts) == 3 and parts[0] == 'LOG' and folder == '99_Hygiene_collect' and parts[2].endswith('.log'):
                                alarm_section = False
                                cellstatus_section = False
                                for line in lines:
                                    if '####LOG_Alarm' in line:
                                        alarm_section = True
                                        continue
                                    elif '####END_LOG_Alarm' in line:
                                        alarm_section = False
                                        continue
                                    elif '####LOG_cellstatus' in line:
                                        cellstatus_section = True
                                        continue
                                    elif '####END_LOG_cellstatus' in line:
                                        cellstatus_section = False
                                        continue
                                    
                                    if alarm_section and line.strip() and ';' in line:
                                        try:
                                            # Split line by semicolon and strip whitespace from each part
                                            parts = [part.strip() for part in line.split(';')]
                                            if len(parts) >= 7 and parts[0] != "Date" and parts[1] != "Time":  # Skip header row and ensure we have all required fields
                                                result_alarm_check.append({
                                                    'FILE': fname,
                                                    'FOLDER': folder,
                                                    'NODENAME': nodename,
                                                    'Date': parts[0],
                                                    'Time': parts[1],
                                                    'Severity': parts[2],
                                                    'Problem': parts[4],
                                                    'Object': parts[3],
                                                    'Cause': parts[5],
                                                    'AdditionalText': parts[6]
                                                })
                                        except Exception as alarm_err:
                                            print(f"Error processing alarm line in {member}: {alarm_err}")

                                    if cellstatus_section and line.strip() and ';' in line:
                                        try:
                                            # Split line by semicolon and strip whitespace from each part
                                            parts = [part.strip() for part in line.split(';')]
                                            if len(parts) >= 3 and parts[0].lower() != "mo":  # Skip header row and ensure we have all required fields
                                                result_cellstatus_check.append({
                                                    'FILE': fname,
                                                    'NODENAME': nodename,
                                                    'MO': parts[0],
                                                    'administrativeState': parts[1],
                                                    'operationalState': parts[2]
                                                })
                                        except Exception as cellstatus_err:
                                            print(f"Error processing cell status line in {member}: {cellstatus_err}")

                        except Exception as open_err:
                            print(f"Error opening {member} in {fname}: {open_err}")
        except zipfile.BadZipFile:
            # This should ideally not happen if we checked in the first loop,
            # but keeping for robustness.
            print(f"Skipping bad zip file during processing: {fname}")
        except Exception as e:
            print(f"Error processing zip file {fname}: {e}")

        if progress is not None:
            progress.setValue(idx + 1)
            QApplication.processEvents() # Allow UI updates

    if progress is not None:
        progress.close()

    # Create DataFrames
    df = pd.DataFrame(result_rows, columns=['FILE', 'FOLDER', 'NODENAME', 'REMARK', 'Count'])
    out_path = os.path.join(download_dir, 'MOBATCH_Check.xlsx')
    
    # Export to Excel with multiple sheets
    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Connection_Check', index=False)
        if result_alarm_check:
            df_alarm = pd.DataFrame(result_alarm_check)
            df_alarm.to_excel(writer, sheet_name='ALARM', index=False)
            
            # Compare with before data if available
            if df_alarm_before is not None:
                # Rename columns in df_alarm_before to add _BEFORE suffix
                df_alarm_before = df_alarm_before.add_suffix('_BEFORE')
                
                # Merge the dataframes on the specified keys
                df_compare_alarm = pd.merge(
                    df_alarm,
                    df_alarm_before,
                    left_on=['NODENAME', 'Severity', 'Problem', 'Object'],
                    right_on=['NODENAME_BEFORE', 'Severity_BEFORE', 'Problem_BEFORE', 'Object_BEFORE'],
                    how='left'
                )
                
                # Remove specific _BEFORE columns
                columns_to_drop = ['NODENAME_BEFORE', 'Severity_BEFORE', 
                'Object_BEFORE','Cause_BEFORE','AdditionalText_BEFORE']
                df_compare_alarm = df_compare_alarm.drop(columns=columns_to_drop)
                
                # Add REMARK column based on whether the row exists in before data
                df_compare_alarm['REMARK'] = df_compare_alarm['Problem_BEFORE'].apply(
                    lambda x: 'Alarm Existing' if pd.notna(x) else 'NEW Alarm'
                )
                
                # Export the comparison data
                df_compare_alarm.to_excel(writer, sheet_name='ALARM_COMPARE', index=False)
                
                # Highlight NEW Alarm rows in yellow
                worksheet = writer.sheets['ALARM_COMPARE']
                for idx, row in enumerate(df_compare_alarm['REMARK'], start=2):  # start=2 because Excel is 1-based and we have header
                    if row == 'NEW Alarm':
                        for cell in worksheet[idx]:
                            cell.fill = openpyxl.styles.PatternFill(start_color='FFFF00',
                                                                  end_color='FFFF00',
                                                                  fill_type='solid')
                
                # Export the before data
                df_alarm_before.to_excel(writer, sheet_name='ALARM_BEFORE', index=False)
        
        # Export cell status data if available
        if result_cellstatus_check:
            df_cellstatus = pd.DataFrame(result_cellstatus_check)
            df_cellstatus.to_excel(writer, sheet_name='Cell_Status', index=False)

        # Adjust column widths for all sheets
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                
                # Find the maximum length of content in the column
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                
                # Set column width (max 25 characters)
                adjusted_width = min(max_length + 2, 25)  # Add 2 for padding
                worksheet.column_dimensions[column_letter].width = adjusted_width

    print(f"Exported check results to {out_path}")
    # Display a success message box after export
    if QApplication.instance() is not None:
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("Export Complete")
        msg_box.setText(f"Log check completed and exported to {out_path}\n DONT FORGET TO SAVE THE LOG BEFORE DOWNLOAD NEW LOGS")
        
        # If compare_before is True, open the Excel file after message box is closed
        if compare_before:
            def open_excel_file():
                try:
                    # Use the appropriate command based on the operating system
                    if os.name == 'nt':  # Windows
                        os.startfile(out_path)
                    else:  # Linux/Mac
                        subprocess.run(['xdg-open', out_path])
                except Exception as e:
                    print(f"Error opening Excel file: {e}")
            
            # Connect the finished signal to open the Excel file
            msg_box.finished.connect(open_excel_file)
        
        msg_box.exec_()





        