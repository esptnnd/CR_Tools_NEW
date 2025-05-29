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
from PyQt5.QtWidgets import QApplication, QProgressDialog, QMessageBox # Needed for UI elements


def check_logs_and_export_to_excel(parent=None):
    import os
    import pandas as pd
    import zipfile

    download_dir = os.path.join(os.path.dirname(__file__), '..', '02_DOWNLOAD') # Adjust path to 02_DOWNLOAD
    zip_files = [fname for fname in os.listdir(download_dir) if fname.lower().endswith('.zip')]
    result_rows = []
    progress = None

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
    df = pd.DataFrame(result_rows, columns=['FILE', 'FOLDER', 'NODENAME', 'REMARK', 'Count'])
    out_path = os.path.join(download_dir, 'Check.xlsx')
    df.to_excel(out_path, index=False)
    print(f"Exported check results to {out_path}")
    # Display a success message box after export
    if QApplication.instance() is not None:
        QMessageBox.information(parent, "Export Complete", f"Log check completed and exported to {out_path}")