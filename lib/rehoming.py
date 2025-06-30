import os
import pandas as pd
from openpyxl import Workbook
from PyQt5.QtWidgets import QFileDialog




def merge_lacrac_files(files, output_dir, log_callback=None):
    """
    Gabungkan file *_DATA_CELL_LACRAC.txt menjadi DATA_CELL.xlsx di output_dir.
    files: list of file paths
    output_dir: directory to save DATA_CELL.xlsx
    log_callback: function for logging (optional)
    """
    def log(msg):
        if log_callback:
            log_callback(msg)

    if not files:
        log("Tidak ada file yang dipilih.")
        return False

    all_data = []
    header = None
    total_files = len(files)
    for idx, file in enumerate(files, 1):
        log(f"Membaca: {os.path.basename(file)}")
        with open(file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
            if not lines:
                continue
            if header is None:
                header = lines[0].split(';')
                data_lines = lines[1:]
            else:
                data_lines = lines[1:]
            all_data.extend([line.split(';') for line in data_lines])
        percent = int((idx / (total_files + 1)) * 100)  # +1 to leave room for export progress
        log(f"Progress: {percent}%")

    if not header or not all_data:
        log("Tidak ada data yang ditemukan di file.")
        return False

    # Export to Excel with progress, sheet name 'REF'
    output_path = os.path.join(output_dir, "DATA_CELL.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "REF"
    ws.append(header)
    total_rows = len(all_data)
    for i, row in enumerate(all_data, 1):
        ws.append(row)
        if i % max(1, total_rows // 20) == 0 or i == total_rows:
            percent = int(((idx + i / total_rows) / (total_files + 1)) * 100)
            log(f"Progress: {percent}%")
    wb.save(output_path)
    log(f"✅ File digabung dan disimpan: {output_path}")
    return True 



###### IMPORT DF FROM CMEXPORT
import pandas as pd
import os
import re
from tqdm import tqdm
from IPython.display import clear_output
import time
from PyQt5.QtCore import QThread, pyqtSignal

def parse_dump(folder_path, log_callback=None, progress_callback=None, df_ref_raw=None):
    # === KONFIGURASI ===
    output_folder = f"{folder_path}/00_output_df/"
    ignore_types = ['SubNetwork', 'MeContext', 'ManagedElement', 'RncFunction']

    os.makedirs(output_folder, exist_ok=True)
    data_groups = {}

    # Ambil semua file .txt di folder
    txt_files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]

    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    # === PARSING FILE ===
    log("=== Parsing log files ===")
    total_files = len(txt_files)
    for idx, filename in enumerate(txt_files, 1):
        percent = int((idx / total_files) * 100)
        if progress_callback:
            progress_callback(percent)
        log(f"Parsing files: {idx}/{total_files} - {filename}")
        file_path = os.path.join(folder_path, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            current_row = {}
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('FDN :'):
                    if current_row:
                        fdn = current_row.get('FDN', '')
                        m = re.findall(r',([A-Za-z0-9]+)=.*?', fdn)
                        type_str = next((x for x in reversed(m) if x not in ignore_types), 'SubNetwork')
                        data_groups.setdefault(type_str, []).append(current_row)
                        current_row = {}
                    key, value = line.split(':', 1)
                    current_row[key.strip()] = value.strip().strip('"')
                else:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        current_row[key.strip()] = value.strip().strip('"')
            if current_row:
                fdn = current_row.get('FDN', '')
                m = re.findall(r',([A-Za-z0-9]+)=.*?', fdn)
                type_str = next((x for x in reversed(m) if x not in ignore_types), 'SubNetwork')
                data_groups.setdefault(type_str, []).append(current_row)

    # === PROSES TIAP TYPE_STR DENGAN LOG ===
    total_types = len(data_groups)

    # Log info about df_ref if provided
    df_ref = df_ref_raw.copy()
    if df_ref is not None:
        log(f"[INFO] DATA_CELL.xlsx (df_ref) loaded: {df_ref.shape[0]} rows, {df_ref.shape[1]} columns.")

    for idx, (type_str, rows) in enumerate(data_groups.items(), start=1):
        log(f"📄 [{idx}/{total_types}] {type_str} - Total Rows: {len(rows)}")
        records = []
        total_rows = len(rows)
        for i, row in enumerate(rows, 1):
            records.append(row)
            if total_rows > 0 and i % max(1, total_rows // 20) == 0:
                percent = int((i / total_rows) * 100)
                if progress_callback:
                    progress_callback(percent)
        df = pd.DataFrame.from_records(records)
        output_file = os.path.join(output_folder, f'df_{type_str}.csv')
        log(f"💾 Menyimpan ke file: {output_file}")
        df.to_csv(output_file, index=False, sep=';')
        log(f"✅ Selesai: {type_str} ({len(df)} baris)")
        time.sleep(1)

    log("==========================================================")
    log("=== ✅ STEP 1 EXTRACT DATA DF DARI LOG CMEDIT EXPORT===")
    log("==========================================================")
    df_ref = df_ref_raw.copy()
    df_cell, df_IUB, df_IUB_ECDCH = manipulate_data_df_cell(df_ref=df_ref, data_groups=data_groups)
    df_ref = df_ref_raw.copy()
    ##print(df_ref.head)
    print(df_ref.columns)
    process_cmbulk_export(folder_path, data_groups, df_ref, df_cell, df_IUB, df_IUB_ECDCH, log_callback=log_callback, progress_callback=progress_callback)





def process_cmbulk_export(folder_path, data_groups, df_ref, df_cell, df_IUB, df_IUB_ECDCH, log_callback=None, progress_callback=None):
    import os, glob, re
    import pandas as pd
    from tqdm import tqdm
    from .rehoming_ref import (
        template_CELL, template_FACH, template_Hsdsch, template_Pch,
        template_IUBLINK, template_Rach, template_EUL, template_IUBLINK_EDCH,
        template_EutranFreqRelation, template_CELL_ANR
    )
    from .rehoming_ref import write_output    

    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    template_REFERENCE = """FDN : {FDN}\n"""
    template_DELETE = """delete\nFDN : {FDN}\n"""
    template_DELETE_CELL_SAC = """delete\nFDN : {FDN}\ndelete\nFDN : {serviceAreaRef_OLD}\n"""
    template_LOCK = """set\nFDN : {FDN}\nadministrativeState : {administrativeState}\n"""
    ##template_LOCK = """set\nFDN : {FDN}\nanrEutranUtranCellConfig : {{anrEnabled=FALSE}} \n"""
    ##anrEutranUtranCellConfig

    # === SETUP ===
    log("[STEP] Setup dan persiapan file referensi...")
    column_order = [
        'RNC_SOURCE', 'RNC_TARGET', 'IUBLINK', 'CELLNAME',
        'LAC_PLAN', 'RAC_PLAN', 'URA_PLAN', 'SAC_PLAN'
    ]    
    df_ref = df_ref[column_order]
    log(f"Loaded reference file with {len(df_ref)} rows")

    # Hapus semua file script lama
    log("[STEP] Menghapus file script lama di 01_output_script ...")
    os.makedirs(f"{folder_path}/01_output_script", exist_ok=True)
    for f in glob.glob(f'{folder_path}/01_output_script/0[0-9]_*.txt'):
        os.remove(f)
    os.chdir(folder_path)





    #================================================================
    ###### WRITE CMBULK SCRIPT FOR LAC RAC URA    
    #================================================================
    from .rehoming_ref import (
        template_URA_CREATE,template_LAC_CREATE,template_RAC_CREATE,
        write_output_lac_rac
    )



    ##print(df_list_rnc)



    def process_plan(df_ref, col_list, template, desc, progress_callback=None):
        df = df_ref[col_list].drop_duplicates()
        total_rows = len(df)
        for i, (_, row) in enumerate(df.iterrows(), 1):            
            ###00_SCRIPT_CELL_
            ###03_SCRIPT_URA_LAC_
            write_output_lac_rac(template, row , "00_SCRIPT_CELL" )
            if total_rows > 0 and (i % max(1, total_rows // 20) == 0 or i == total_rows):
                percent = int((i / total_rows) * 100)
                if progress_callback:
                    progress_callback(percent)
        return total_rows

    # Load once
    ##df_ref = pd.read_excel('REF/REF_CELL.xlsx')
    # URA_PLAN
    log(f"Processing template_URA_CREATE")
    n_ura = process_plan(df_ref, ['RNC_TARGET', 'URA_PLAN'], template_URA_CREATE, "Processing URA", progress_callback=progress_callback)
    log(f"✅ Completed: Processing URA ({n_ura} baris)")

    log(f"Processing template_LAC_CREATE")
    n_lac = process_plan(df_ref, ['RNC_TARGET', 'LAC_PLAN'], template_LAC_CREATE, "Processing LAC_PLAN", progress_callback=progress_callback)
    log(f"✅ Completed: Processing LAC_PLAN ({n_lac} baris)")

    log(f"Processing template_RAC_CREATE")
    n_rac = process_plan(df_ref, ['RNC_TARGET', 'LAC_PLAN', 'RAC_PLAN'], template_RAC_CREATE, "Processing RAC_PLAN", progress_callback=progress_callback)
    log(f"✅ Completed: Processing RAC_PLAN ({n_rac} baris)")

    ##log("=== ✅ SEMUA PROSES CMBULK COMPLETE ===")
    log("====================================================")
    log("=== ✅ [STEP 2] SCRIPT CREATE CMBULK LAC RAC URA ===")
    log("====================================================")


    #================================================================
    ###### WRITE CMBULK SCRIPT FOR CELL IUBLINK SAC ETC    
    #================================================================

    # Template mapping
    template_map = {
        'Fach': template_FACH,
        'Hsdsch': template_Hsdsch,
        'Pch': template_Pch,
        'Rach': template_Rach,
        'Eul': template_EUL,
        'EutranFreqRelation': template_EutranFreqRelation
    }

    # Urutan prioritas
    priority = ['IubLink', 'IubEdch', 'UtranCell', 'Fach', 'Hsdsch', 'Pch', 'Rach', 'Eul']
    all_keys = priority + [k for k in data_groups if k not in priority]

    # === PROSES DATA CMBULK CREATE ===
    log("[STEP] Mulai proses CREATE CMBULK...")
    for idx, type_str in enumerate(all_keys, 1):
        log_msg = f"Processing {type_str} ({idx}/{len(all_keys)})"
        log(log_msg)
        percent = int((idx / len(all_keys)) * 100)
        if progress_callback:
            progress_callback(percent)
        print(f"Processing {type_str}")
        df = pd.DataFrame(data_groups[type_str])

        # --- UtranCell ---
        if type_str == "UtranCell":
            total_rows = len(df_cell)
            for i, (_, row) in enumerate(df_cell.iterrows(), 1):
                row['administrativeState'] = 'LOCKED'
                write_output(template_CELL, row, filename_prefix="00_SCRIPT_CELL", filename_by='target')
                write_output(template_CELL, row, filename_prefix="05_FALLBACK_CREATE_CELL", filename_by='source', replace_fdn=False)
                write_output(template_CELL_ANR, row, filename_prefix="06_SCRIPT_CELL_ANR", filename_by='target', replace_fdn=True)
                write_output(template_REFERENCE, row, filename_prefix="09_FILE_REFERENCE", filename_by='all', replace_fdn=False)
                ##template_LOCK  01_LOCK_TARGET
                write_output(template_LOCK, row, filename_prefix="01_LOCK_TARGET", filename_by='target', replace_fdn=True)
                write_output(template_LOCK, row, filename_prefix="02_LOCK_SOURCE", filename_by='source', replace_fdn=False)
                row['administrativeState'] = 'UNLOCKED'
                write_output(template_LOCK, row, filename_prefix="01_UNLOCK_TARGET", filename_by='target', replace_fdn=True)
                write_output(template_LOCK, row, filename_prefix="02_UNLOCK_SOURCE", filename_by='source', replace_fdn=False)

                
                if total_rows > 0 and (i % max(1, total_rows // 20) == 0 or i == total_rows):
                    percent = int((i / total_rows) * 100)
                    if progress_callback:
                        progress_callback(percent)

            log(f"✅ Completed: {type_str} ({total_rows} baris)")

        # --- IubLink & IubEdch ---
        elif type_str in ['IubLink', 'IubEdch']:
            df_data = df_IUB if type_str == 'IubLink' else df_IUB_ECDCH
            template = template_IUBLINK if type_str == 'IubLink' else template_IUBLINK_EDCH
            total_rows = len(df_data)
            for i, (_, row) in enumerate(df_data.iterrows(), 1):
                if 'administrativeState' in row:
                    ##template_LOCK
                    row['administrativeState'] = 'UNLOCKED'
                    write_output(template_LOCK, row, filename_prefix="01_UNLOCK_TARGET", filename_by='target', replace_fdn=True)
                    write_output(template_LOCK, row, filename_prefix="02_UNLOCK_SOURCE", filename_by='source', replace_fdn=False)                 
                    row['administrativeState'] = 'LOCKED'
                    write_output(template_LOCK, row, filename_prefix="01_LOCK_TARGET", filename_by='target', replace_fdn=True)
                    write_output(template_LOCK, row, filename_prefix="02_LOCK_SOURCE", filename_by='source', replace_fdn=False)

                write_output(template, row, filename_prefix="00_SCRIPT_CELL", filename_by='target')
                write_output(template, row, filename_prefix="05_FALLBACK_CREATE_CELL", filename_by='source', replace_fdn=False)  
                if total_rows > 0 and (i % max(1, total_rows // 20) == 0 or i == total_rows):
                    percent = int((i / total_rows) * 100)
                    if progress_callback:
                        progress_callback(percent)

            log(f"✅ Completed: {type_str} ({total_rows} baris)")

        # --- Template umum dengan mapping ---
        elif type_str in template_map:
            # Extract RNC_SOURCE & CELLNAME dari FDN
            df['RNC_SOURCE'] = df['FDN'].str.extract(r'MeContext=(.*?),')[0]
            df['CELLNAME'] = df['FDN'].str.extract(r'UtranCell=(.*?),')[0]

            # Merge dengan referensi
            df = df.merge(df_ref, on=['RNC_SOURCE', 'CELLNAME'], how='left')

            # Hapus baris tanpa plan sama sekali
            df = df.dropna(subset=['LAC_PLAN', 'RAC_PLAN', 'URA_PLAN', 'SAC_PLAN'], how='all')

            total_rows = len(df)
            for i, (_, row) in enumerate(df.iterrows(), 1):
                if 'administrativeState' in row:
                    row['administrativeState'] = 'LOCKED'
                if 'barredCnOperatorRef' in row:
                    row['barredCnOperatorRef'] = re.sub(r'^\[(.*)\]$', r"'\1'", row['barredCnOperatorRef'])

                write_output(template_map[type_str], row, filename_prefix="00_SCRIPT_CELL", filename_by='target')            
                write_output(template_map[type_str], row, filename_prefix="05_FALLBACK_CREATE_CELL", filename_by='source', replace_fdn=False)
                if 'administrativeState' in row:
                    write_output(template_LOCK, row, filename_prefix="01_LOCK_TARGET", filename_by='target', replace_fdn=True)
                    write_output(template_LOCK, row, filename_prefix="02_LOCK_SOURCE", filename_by='source', replace_fdn=False)
                    row['administrativeState'] = 'UNLOCKED'
                    write_output(template_LOCK, row, filename_prefix="01_UNLOCK_TARGET", filename_by='target', replace_fdn=True)
                    write_output(template_LOCK, row, filename_prefix="02_UNLOCK_SOURCE", filename_by='source', replace_fdn=False)
                if total_rows > 0 and (i % max(1, total_rows // 20) == 0 or i == total_rows):
                    percent = int((i / total_rows) * 100)
                    if progress_callback:
                        progress_callback(percent)

            log(f"✅ Completed: {type_str} ({total_rows} baris)")

    log("===============================================================")
    log("=== ✅ [STEP 3] SCRIPT CREATE CMBULK CELL,IUBLINK & ETC ===")
    log("===============================================================")

    # Urutan prioritas DELETE
    log("[STEP] Mulai proses DELETE CMBULK...")
    if progress_callback:
        progress_callback(0)
    priority = ['IubEdch', 'IubLink', 'Eul', 'Hsdsch', 'Fach', 'Pch', 'Rach', 'EutranFreqRelation', 'UtranCell']
    all_keys = priority + [k for k in data_groups if k not in priority]

    # Proses DELETE CMBULK
    for idx, type_str in enumerate(all_keys, 1):
        log_msg = f"Processing DELETE {type_str} ({idx}/{len(all_keys)})"
        log(log_msg)

        if type_str == "UtranCell":
            df = df_cell

        elif type_str in ['IubLink', 'IubEdch']:
            df = df_IUB if type_str == 'IubLink' else df_IUB_ECDCH

        elif type_str in template_map:
            df = pd.DataFrame(data_groups[type_str])
            df = df.merge(
                df_ref,
                left_on=[df['FDN'].str.extract(r'MeContext=(.*?),')[0], df['FDN'].str.extract(r'UtranCell=(.*?),')[0]],
                right_on=['RNC_SOURCE', 'CELLNAME'],
                how='left'
            ).dropna(subset=['LAC_PLAN', 'RAC_PLAN', 'URA_PLAN', 'SAC_PLAN'], how='all')

        else:
            continue

        for _, row in tqdm(df.iterrows(), total=len(df), desc=type_str):
            if type_str == "UtranCell":
                write_output(template_DELETE_CELL_SAC, row, "04_DELETE_CELL", filename_by='source', replace_fdn=False)
            else:    
                write_output(template_DELETE, row, "04_DELETE_CELL", filename_by='source', replace_fdn=False)
        total_rows = len(df)
        log(f"✅ Completed: {type_str} ({total_rows} baris)")

    log("=== ✅ [STEP 4] SCRIPT DELETE CMBULK CELL,IUBLINK & ETC ===")


    










###### MANIPULATE DF DATA CELL RNC
import re

def manipulate_data_df_cell(df_ref, data_groups):
    # Read the reference Excel file
    # df_ref = pd.read_excel('REF/REF_CELL.xlsx')
    # print(f"Loaded reference file with {len(df_ref)} rows")
    column_order = [
        'RNC_SOURCE', 'RNC_TARGET', 'IUBLINK', 'CELLNAME',
        'LAC_PLAN', 'RAC_PLAN', 'URA_PLAN', 'SAC_PLAN' , 'SAC'
    ]
    df_ref = df_ref[column_order]
    cols = ['LAC_PLAN', 'RAC_PLAN', 'URA_PLAN', 'SAC_PLAN', 'SAC']
    df_ref[cols] = df_ref[cols].fillna(0).astype(int).astype(str)

    df_cell = pd.DataFrame(data_groups['UtranCell']).copy()
    df_cell['RNC_SOURCE'] = df_cell['FDN'].str.extract(r'MeContext=(.*?),ManagedElement=1')
    df_cell = df_cell.merge(df_ref, left_on=['RNC_SOURCE','UtranCellId'], right_on=['RNC_SOURCE','CELLNAME'], how='left')

    df_cell = df_cell.rename(columns={
        'routingAreaRef': 'routingAreaRef_OLD',
        'uraRef': 'uraRef_OLD',
        'serviceAreaRef': 'serviceAreaRef_OLD',    
    })
    # modify data routingAreaRef
    df_cell['routingAreaRef'] = (
        df_cell['routingAreaRef_OLD'].str.extract(r'^(.*?,RoutingArea=)', flags=re.IGNORECASE)[0].fillna('') +
        df_cell['RAC_PLAN'].fillna(0).astype(int).astype(str)
    )
    # modify data routingAreaRef
    df_cell['routingAreaRef'] = (
        df_cell['routingAreaRef_OLD'].str.extract(r'^(.*?,LocationArea=)', flags=re.IGNORECASE)[0].fillna('') +
        df_cell['LAC_PLAN'].fillna(0).astype(int).astype(str) +
        ',' + df_cell['routingAreaRef_OLD'].str.extract(r',(RoutingArea)=', flags=re.IGNORECASE)[0].fillna('RoutingArea') + '=' +
        df_cell['RAC_PLAN'].fillna(0).astype(int).astype(str)
    )

    # modify data uraRef
    df_cell['uraRef'] = (
        "'" +
        df_cell['uraRef_OLD'].str.extract(r'(SubNetwork.*?,Ura=)', flags=re.IGNORECASE)[0].fillna('') +
        df_cell['URA_PLAN'].fillna(0).astype(int).astype(str) + "'"
    )

    # modify data serviceAreaRef
    df_cell['serviceAreaRef'] = (
        df_cell['serviceAreaRef_OLD'].str.extract(r'^(.*?,LocationArea=)', flags=re.IGNORECASE)[0].fillna('') +
        df_cell['LAC_PLAN'].fillna(0).astype(int).astype(str) +
        ',' + df_cell['serviceAreaRef_OLD'].str.extract(r',(ServiceArea)=', flags=re.IGNORECASE)[0].fillna('ServiceArea') + '=' +
        df_cell['SAC_PLAN'].fillna(0).astype(int).astype(str)
    )
    # modify data locationAreaRef
    df_cell['locationAreaRef'] = (
        df_cell['serviceAreaRef'].str.extract(r'^(.*?,LocationArea=)', flags=re.IGNORECASE)[0].fillna('') +
        df_cell['LAC_PLAN'].fillna(0).astype(int).astype(str) 
    )

    df_cell = df_cell.dropna(subset=['LAC_PLAN', 'RAC_PLAN', 'URA_PLAN', 'SAC_PLAN'], how='all')
    # update params
    df_cell.loc[df_cell['localCellId'] == df_cell['SAC'], 'localCellId'] = df_cell['SAC_PLAN']
    df_cell['cId'] = df_cell['SAC_PLAN']

    # ref IUB
    df_ref_IUB =df_ref.copy()
    column_order = [
        'RNC_SOURCE', 'RNC_TARGET', 'IUBLINK',
        'LAC_PLAN', 'RAC_PLAN', 'URA_PLAN', 'SAC_PLAN'
    ]
    df_ref_IUB = df_ref_IUB[column_order]
    df_ref_IUB = df_ref_IUB.drop_duplicates(subset=['RNC_SOURCE', 'RNC_TARGET', 'IUBLINK'], keep='first')

    # IubLink
    df_IUB = pd.DataFrame(data_groups['IubLink']).copy()
    df_IUB['RNC_SOURCE'] = df_IUB['FDN'].str.extract(r'MeContext=(.*?),ManagedElement=1')
    df_IUB = df_IUB.merge(df_ref_IUB, left_on=['RNC_SOURCE','IubLinkId'], right_on=['RNC_SOURCE','IUBLINK'], how='left')
    df_IUB = df_IUB.dropna(subset=['LAC_PLAN', 'RAC_PLAN', 'URA_PLAN', 'SAC_PLAN'], how='all')

    df_IUB_ECDCH = pd.DataFrame(data_groups['IubEdch']).copy()
    df_IUB_ECDCH['RNC_SOURCE'] = df_IUB_ECDCH['FDN'].str.extract(r'(?i)MeContext=(.*?),ManagedElement=1')
    df_IUB_ECDCH['IubLinkId'] = df_IUB_ECDCH['FDN'].str.extract(r'(?i)IubLink=(.*?),IubEdch')
    df_IUB_ECDCH = df_IUB_ECDCH.merge(df_ref_IUB, left_on=['RNC_SOURCE','IubLinkId'], right_on=['RNC_SOURCE','IUBLINK'], how='left')
    df_IUB_ECDCH = df_IUB_ECDCH.dropna(subset=['LAC_PLAN', 'RAC_PLAN', 'URA_PLAN', 'SAC_PLAN'], how='all')

    return df_cell, df_IUB, df_IUB_ECDCH












class ParseDumpWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, folder_path, df_ref=None):
        super().__init__()
        self.folder_path = folder_path
        self.df_ref = df_ref

    def run(self):
        try:
            def log_callback(msg):
                self.log.emit(msg)
            def progress_callback(val):
                self.progress.emit(val)
            parse_dump(self.folder_path, log_callback=log_callback, progress_callback=progress_callback, df_ref_raw=self.df_ref)
            script_path = os.path.join(self.folder_path, "01_output_script")
            self.finished.emit(f"✅ SCRIPT REHOMING COMPLETE GENERATED\n{script_path}")
        except Exception as e:
            self.error.emit(f"❌ Error saat parse_dump: {e}")

def select_dump_and_excel(parent, log_callback=None):
    if log_callback:
        log_callback("=== Mulai proses SELECT DUMP and DATA_CELL.xlsx ===")
    folder_path = QFileDialog.getExistingDirectory(parent, "Pilih Folder Dump")
    if not folder_path:
        if log_callback:
            log_callback("❌ Folder dump tidak dipilih.")
        return None, None
    if log_callback:
        log_callback(f"📁 Folder dump: {folder_path}")
    file_path, _ = QFileDialog.getOpenFileName(parent, "Pilih DATA_CELL.xlsx", folder_path, "Excel Files (*.xlsx)")
    if not file_path:
        if log_callback:
            log_callback("❌ DATA_CELL.xlsx tidak dipilih.")
        return None, None
    if log_callback:
        log_callback(f"📄 DATA_CELL.xlsx: {file_path}")
    try:
        df_ref = pd.read_excel(file_path, sheet_name="REF")
        if log_callback:
            log_callback(f"✅ DATA_CELL.xlsx berhasil dibaca. Jumlah baris: {len(df_ref)}")
    except Exception as e:
        if log_callback:
            log_callback(f"❌ Gagal membaca DATA_CELL.xlsx: {e}")
        return None, None
    if log_callback:
        log_callback("🚀 Menjalankan parse_dump di background...")
    return folder_path, df_ref






