"""
Before/After Report Generator for Network Configuration Comparison
This module provides functionality to compare network configuration and performance data
between 'Before' and 'After' states, generating detailed Excel reports with summaries,
comparisons, and KPI analysis.
"""

import os
import re
import pandas as pd
import numpy as np
import xlsxwriter
import glob
import sys
import os
from datetime import datetime
from .report_before_after_KPI import process_kpi_logs, create_main_merge_df, transform_headers
from tqdm import tqdm


# Centralized patterns so it's easy to add/remove
PATTERN_LOOP = ("cellstatus", "Alarm", 
                "bandwidth", "SleepState", 
"BAND_NR_SECTOR", "SSBFREQ_NR_CELL",
"INTERMELINK_status","FEATURE_status","RSRPSCELLCOVERAGE","WAITFORBETTERSCELLREP",
"ADDITIONALPUCCHFORCAENABLED","INTRAFREQMCCELLPROFILEREF", "NRCELLRELATION_STATUS",
"GNBCUCPFunction_xnIpAddrViaNgActive",
"AMF_status","SCTP_XN","LocalSctpEndpoint","AnrFunctionNR","TermPointToGNodeB"
)

# Map a pattern (as it appears in filename) to a key used in dataframes dict
PATTERN_KEY_MAP = {
    'Alarm': 'Alarm',
    'bandwidth': 'bandwidth',
    'cellstatus': 'Cell Status',
    'SleepState': 'SleepState',
    'BAND_NR_SECTOR': 'BAND_NR_SECTOR',
    'SSBFREQ_NR_CELL': 'SSBFREQ_NR_CELL',
    'AMF_status': 'TermPointToAmf',
    'SCTP_XN' : 'Xn_SctpEndpoint',
    'LocalSctpEndpoint' : 'Xn_LocalSctpEndpoint',
    'AnrFunctionNR' : 'Xn_Parameter',
    'TermPointToGNodeB' : 'TermPointToGNodeB',
    'INTERMELINK_status': 'intermelink',
    'FEATURE_status': 'Feature',
    'RSRPSCELLCOVERAGE': 'rsrpSCellCoverage',
    'WAITFORBETTERSCELLREP': 'waitForBetterSCellRep',
    'ADDITIONALPUCCHFORCAENABLED': 'additionalPucchForCaEnabled',
    'INTRAFREQMCCELLPROFILEREF': 'intraFreqMcCellProfileRef',
    'GNBCUCPFunction_xnIpAddrViaNgActive': 'xnIpAddrViaNgActive_status',
    'NRCELLRELATION_STATUS': 'NRCellRelation'
}


def reorder_columns(df):
    """
    Reorders the columns of a DataFrame to start with 'NODENAME' and 'MO' (if they exist), 
    followed by all other columns in their original relative order.
    """
    
    # Define the desired starting columns
    start_cols_target = ['NODENAME', 'MO']
    
    # 1. Identify which of the target columns exist in the DataFrame
    existing_start_cols = [col for col in start_cols_target if col in df.columns]
    
    # 2. Get all other columns, excluding the ones we already placed in the start list
    other_cols = [col for col in df.columns if col not in existing_start_cols]
    
    # 3. Create the final new column order
    new_column_order = existing_start_cols + other_cols
    
    # 4. Reindex the DataFrame using the new column order
    df_reordered = df[new_column_order]
    
    return df_reordered


# Function to extract NODENAME using regex
def extract_nodename(filename):
    # Build the alternation part from PATTERN_LOOP to make this extensible
    # Also keep any legacy/static patterns if needed (e.g., freqPrioListEUTRA)
    extra_patterns = ['freqPrioListEUTRA']
    patterns = list(PATTERN_LOOP) + extra_patterns
    alternation = '|'.join(re.escape(p) for p in patterns)
    regex = rf'(.+?)_({alternation})\.LOGS_FILE'
    match = re.match(regex, filename)
    if match:
        return match.group(1)
    return None


def remark_log_as_unremote(logfile_path):
    # Define the regex pattern to match lines that start with "Bye"
    pattern = re.compile(r'^Bye')

    # Read the log file
    with open(logfile_path, 'r', encoding='utf-8', errors='ignore') as file:
        lines = file.readlines()

    # Check if any line matches the pattern
    contains_bye = any(pattern.match(line) for line in lines)
    
    # If no line matches, remark the log as "Unremote"
    if not contains_bye:
        remark_status = "Unremote"
    else:
        remark_status = "OK"
        
    return remark_status


def extract_log_patterns(logfile, patterns, log_folder):
    log_folder = log_folder
    input_path = os.path.join(log_folder, logfile)
    base_name = os.path.splitext(logfile)[0]
    
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as infile:
        lines = infile.readlines()
    
    for pattern in patterns:
        output_file = os.path.join(log_folder, f"{base_name}_{pattern}.LOGS_FILE")
        extracting = False
        
        with open(output_file, 'w', encoding='utf-8') as outfile:
            for line in lines:
                if f'####LOG_{pattern}' in line:
                    extracting = True
                    continue  # Skip writing the start marker
                elif f'####END_LOG_{pattern}' in line:
                    extracting = False
                    break  # Stop reading once end marker is found
                
                if extracting and ";" in line:
                    cleaned_line = re.sub(r'\s{2,}', ' ', line.strip())  # Replace multiple spaces with a single space
                    cleaned_line = re.sub(r' ;', ';', cleaned_line.strip())  # Replace multiple spaces with a single space
                    outfile.write(cleaned_line + "\n")
        
        # print(f"Extracted content saved to: {output_file}")


def read_files_from_folder(folder_path, progress_callback=None):
    # Initialize dataframes with 'Summary' first so Summary sheet is the first worksheet
    dataframes = {'Summary': []}
    for v in PATTERN_KEY_MAP.values():
        dataframes[v] = []

    log_files = [f for f in os.listdir(folder_path) if f.endswith('.log')]
    
    total_steps = len(log_files) + len(os.listdir(folder_path)) + 100 + 10  # Extraction + Summary + Processing + Cleanup
    current_step = 0
    
    # Extract logs with progress reporting
    total = len(log_files) or 1
    for idx, filename in enumerate(log_files):
        # use centralized PATTERN_LOOP
        extract_log_patterns(filename, PATTERN_LOOP, folder_path)
        current_step += 1
        # report progress as 0-40% for extraction phase
        if progress_callback:
            progress_callback(int(40 * current_step / total_steps), f"Extracting {filename}")
    
    # First, create summaries from .log files
    all_files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    for idx, filename in enumerate(all_files):
        if filename.endswith('.log'):
            file_path = os.path.join(folder_path, filename)
            check_log = remark_log_as_unremote(file_path)
            df = pd.DataFrame({'NODENAME': [filename.replace(".log", "")],
                               'MO': [filename.replace(".log", "")],
                               'Status': [check_log]})
            dataframes['Summary'].append(df)
        current_step += 1
        if progress_callback:
            # report progress up to ~60% for summary creation
            progress_callback(min(60, int(60 * current_step / total_steps)), f"Summarizing {filename}")

    # Process the .LOGS_FILE files
    logs_files = [f for f in os.listdir(folder_path) if f.endswith('.LOGS_FILE')]
    for idx, filename in enumerate(logs_files):
        if not filename.endswith('.LOGS_FILE'):
            continue

        file_path = os.path.join(folder_path, filename)
        if os.stat(file_path).st_size == 0:
            continue

        nodename = extract_nodename(filename)
        if nodename is None:
            print(f"Skipping file with unexpected format: {filename}")
            continue

        try:
            # Special-case Alarm layout
            if '_Alarm.LOGS_FILE' in filename:
                df = pd.read_csv(file_path, delimiter=';', skiprows=0,
                                 names=['Date', 'Time', 'Severity', 'Object', 'Problem', 'Cause'] + 
                                        [f'AdditionalText{i}' for i in range(1, 9)], dtype=str, keep_default_na=False)
                df['AdditionalText'] = df[[f'AdditionalText{i}' for i in range(1, 9)]].apply(
                    lambda x: ';'.join(x), axis=1)
                df = df[df['Date'] != 'Date']
                df = df[['Date', 'Time', 'Severity', 'Object', 'Problem', 'Cause', 'AdditionalText']]
            else:
                df = pd.read_csv(file_path, delimiter=';', dtype=str, keep_default_na=False)

            df['NODENAME'] = nodename

            # Determine which key to append to by checking which pattern appears in filename
            appended = False
            for pat, key in PATTERN_KEY_MAP.items():
                if f'_{pat}.LOGS_FILE' in filename:
                    dataframes[key].append(df)
                    appended = True
                    break

            if not appended:
                # If no pattern matched, print a debug message and skip
                print(f"No matching pattern for file: {filename}")

        except Exception as e:
            print(f"Error processing file {filename}: {e}")
            # Find the summary for the current node and update its status
            for summary_df in dataframes['Summary']:
                if summary_df['NODENAME'].iloc[0] == nodename:
                    summary_df.loc[summary_df['NODENAME'] == nodename, 'Status'] = 'ERROR'
                    break
            continue
        
        current_step += 1
        if progress_callback:
            # report progress up to ~90% for processing files
            progress_callback(min(90, int(60 + 30 * current_step / total_steps)), f"Processing {filename}")
    
    # Concatenate DataFrames
    for key in dataframes:
        if dataframes[key]:
            try:
                dataframes[key] = pd.concat(dataframes[key], ignore_index=True)
            except Exception as e:
                print(f"Warning: Failed to concatenate dataframes for key '{key}': {e}")
                # Create empty DataFrame with basic structure if concatenation fails
                dataframes[key] = pd.DataFrame(columns=['NODENAME', 'MO'])
        else:
            # Ensure empty keys have DataFrame structure instead of empty list
            dataframes[key] = pd.DataFrame(columns=['NODENAME', 'MO'])
    
    # Clean up temporary files
    files = glob.glob(os.path.join(folder_path, "*.LOGS_FILE"))
    for idx, file in enumerate(files):
        os.remove(file)
        current_step += 1
        if progress_callback:
            # report 90-99% for cleanup
            progress_callback(min(99, int(90 + 9 * current_step / total_steps)), f"Deleting {os.path.basename(file)}")
    
    return dataframes


# Function to compare two dataframes and format the difference
def compare_dataframes(df_before, df_after):
    df_merged = pd.merge(df_before, df_after, on=['NODENAME', 'MO'], how='outer', suffixes=('_Before', '_After'))

    # Remove rows where the MO column equals "MO"
    df_merged = df_merged[df_merged['MO'] != 'MO']

    # Ensure the columns are in the order: NODENAME, MO, and the rest
    ordered_columns = ['NODENAME', 'MO'] + [col for col in df_merged.columns if col not in ['NODENAME', 'MO']]
    df_merged = df_merged[ordered_columns]

    return df_merged


# Function to clean administrativeState and operationalState columns
def clean_cell_status(df):
    # Regex to extract values within brackets
    def extract_bracket_content(text):
        match = re.search(r'\((.*?)\)', text)
        return f"({match.group(1)})" if match else text

    if 'administrativeState' in df.columns:
        df['administrativeState'] = df['administrativeState'].apply(extract_bracket_content)
    if 'operationalState' in df.columns:
        df['operationalState'] = df['operationalState'].apply(extract_bracket_content)

    return df


# Function to write Alarm DataFrame with count and headers formatting
def write_alarm_dataframe_with_format(df, sheet_name, writer):
    # Create a writer object for xlsxwriter
    workbook  = writer.book
    worksheet = workbook.add_worksheet(sheet_name)

    # Add the count row
    alarm_count = len(df)
    worksheet.write('A1', alarm_count)
    
    # Add the header row
    headers = ['NODENAME', 'Date', 'Time', 'Severity', 'Problem', 'Object', 'Cause', 'AdditionalText']
    df = df[headers]

    for col_num, header in enumerate(headers):
        worksheet.write(1, col_num, header)
    
    # Write the DataFrame data starting from the third row
    for row_num, row_data in enumerate(df.values.tolist(), start=2):
        for col_num, cell_data in enumerate(row_data):
            # Handle NaN values
            if pd.isna(cell_data):
                worksheet.write(row_num, col_num, '')  # Write an empty string for NaN values
            else:
                worksheet.write(row_num, col_num, cell_data)


### for summary Sheet
def write_summary(df, sheet_name, writer, cell_bef, cell_after):
    # Compare cell cek
    df_check_cell = count_df_by_nodename(cell_bef, cell_after, "Cell_COUNT")
    df_result = pd.merge(df, df_check_cell, on='NODENAME', how='left')
    
    df_result.to_excel(writer, sheet_name=sheet_name, index=False)
    
    workbook  = writer.book
    worksheet = writer.sheets[sheet_name]
    
    # Define formats
    header_format1 = workbook.add_format({'bold': True, 'bg_color': '#FFFF00', 'border': 1})
    header_format = workbook.add_format({'bold': True, 'bg_color': '#ffa383', 'border': 1})
    cell_format = workbook.add_format({'border': 1})
    
    # Apply formats
    for col_num, value in enumerate(df.columns.values):
        worksheet.write(0, col_num, value, header_format1)
    
    # Apply cell format to the entire table
    for row in range(1, len(df) + 1):
        print(f"write NODENAME [{df.iloc[row - 1, 0]}] [{row} of {len(df) + 1}]")
        for col in range(len(df.columns)):
            worksheet.write(row, col, df.iloc[row - 1, col], cell_format)    
    
    # Set column widths
    worksheet.set_column('A:A', 20)  # Column A width 35
    worksheet.set_column('B:B', 14)  # Column B width 25
    worksheet.set_column('C:C', 14)  # Column C width 25
    worksheet.set_column('D:D', 14)  # Column C width 25
    worksheet.set_column('E:E', 14)  # Column C width 25
          
    ########################################################
    ########################################################
    ########################################################
    ########################################################
    ########################################################
    
    # Data for summary table
    summary_data = {
        'State': [
            ('Total Cell Enable', '=COUNTIF(\'Cell Status\'!D:D,"(ENABLED)")', '=COUNTIF(\'Cell Status\'!F:F,"(ENABLED)")'),
            ('Total Cell Unlock', '=COUNTIF(\'Cell Status\'!C:C,"(UNLOCKED)")', '=COUNTIF(\'Cell Status\'!E:E,"(UNLOCKED)")'),
            ('Total Cell Lock', '=COUNTIF(\'Cell Status\'!C:C,"(LOCKED)")', '=COUNTIF(\'Cell Status\'!E:E,"(LOCKED)")'),
            ('Total Cell Disable', '=COUNTIF(\'Cell Status\'!D:D,"(DISABLED)")', '=COUNTIF(\'Cell Status\'!F:F,"(DISABLED)")'),
        ],
        'Alarm': [
            ('Alarm', '=Alarm_Before!A1', '=Alarm_After!A1')
        ],
        
        'OTHERS': [
            ('Can connect', '=COUNTIF(B:B,"OK")', '=COUNTIF(C:C,"OK")'),
            ('Can\'t Connect', '=COUNTIF(B:B,"Unremote")', '=COUNTIF(C:C,"Unremote")'),
            ('Successful', '=COUNTIF(B:B,"OK")', '=COUNTIF(C:C,"OK")'),
            ('Rollback', '=COUNTIF(B:B,"OK")', '=COUNTIF(C:C,"OK")'),
            ('Skip', '=COUNTIF(B:B,"OK")', '=COUNTIF(C:C,"OK")'),
        ]
    }

    # Write summary table
    row_num = 1
    start_column = 6+3
    
    ##format
    header_format = workbook.add_format({'bold': True, 'bg_color': '#ffa383', 'border': 1})
    header_format_1 = workbook.add_format({'bold': True, 'font_color': 'black', 'bg_color': '#fea419', 'align': 'center', 'border': 1})
    header_format_2 = workbook.add_format({'bold': True, 'font_color': 'black', 'bg_color': '#b1b1b1', 'align': 'center', 'border': 1})
    
    # Write State section
    worksheet.write(0, start_column+0, 'Summary Cell Status',header_format_1 )
    worksheet.write(0, start_column+1, '',header_format_1 )
    worksheet.write(0, start_column+2, '',header_format_1 )
    worksheet.write(row_num, start_column+0, 'State', header_format)
    worksheet.write(row_num, start_column+1, 'Before', header_format)
    worksheet.write(row_num, start_column+2, 'After', header_format)
    row_num += 1
    for item, formula, formula2 in summary_data['State']:
        if re.search(r'(Unlock|Enable)', item, re.IGNORECASE):
            cell_format = workbook.add_format({'bold': False, 'font_color': '#030b6b', 'bg_color': '#fefd96', 'border': 1})
        else:
            cell_format = workbook.add_format({'bold': False, 'font_color': '#e72919', 'bg_color': '#fefd96', 'border': 1})
        worksheet.write(row_num, start_column+0, item, cell_format)
        worksheet.write_formula(row_num, start_column+1, formula, cell_format)
        worksheet.write_formula(row_num, start_column+2, formula2, cell_format)
        row_num += 1

    # Write Alarm section
    worksheet.write(row_num, start_column+0, 'Alarm Status', header_format_2)
    worksheet.write(row_num, start_column+1, '',header_format_2 )
    worksheet.write(row_num, start_column+2, '',header_format_2 )    
    row_num += 1
    worksheet.write(row_num, start_column+0, 'State', header_format)
    worksheet.write(row_num, start_column+1, 'Before', header_format)
    worksheet.write(row_num, start_column+2, 'After', header_format)
    row_num += 1
    for item, formula, formula2 in summary_data['Alarm']:
        cell_format = workbook.add_format({'bold': False, 'font_color': '#e72919', 'bg_color': '#fefd96', 'border': 1})
        worksheet.write(row_num, start_column+0, item, cell_format)
        worksheet.write_formula(row_num, start_column+1, formula, cell_format)
        worksheet.write_formula(row_num, start_column+2, formula2, cell_format)
        row_num += 1
    
    # Others section
    worksheet.write(row_num, start_column+0, '??? Sites', header_format)
    worksheet.write(row_num, start_column+1, 'Before', header_format)
    worksheet.write(row_num, start_column+2, 'After', header_format)
    
    row_num += 1
    for item, formula, formula2 in summary_data['OTHERS']:
        cell_format = workbook.add_format({'bold': True, 'border': 1})
        worksheet.write(row_num, start_column+0, item, cell_format)
        worksheet.write_formula(row_num, start_column+1, formula, cell_format)
        worksheet.write_formula(row_num, start_column+2, formula2, cell_format)
        row_num += 1
    
    # Set column widths
    worksheet.set_column(0,0, 20)  # Column A width 35
    worksheet.set_column(1,4, 14)  # Column B width 25
    
    worksheet.set_column(3+3,5+3, 3)  # Column C width 25    
    worksheet.set_column(6+3,6+3, 68)  # Column C width 25        
    worksheet.set_column(7+3,8+3, 14)  # Column C width 25   

    # Set zoom level
    worksheet.set_zoom(85)  # Adjust the zoom level as needed (e.g., 75% zoom)    
          
          
def compare_dataframes_with_check(df_before, df_after, col_lookup):
    # Make a copy to avoid modifying the original col_lookup
    ordered_columns = col_lookup.copy()
    before_columns = []  # Untuk menyimpan kolom _Before
    after_columns = []   # Untuk menyimpan kolom _After
    compare_columns = [] # Untuk menyimpan kolom _Compare

    # Ensure all col_lookup columns exist in both DataFrames
    missing_cols_before = [col for col in col_lookup if col not in df_before.columns]
    missing_cols_after = [col for col in col_lookup if col not in df_after.columns]

    # Tambahkan kolom yang hilang ke DataFrame
    if missing_cols_before:
        print(f"Menambahkan kolom yang hilang di BEFORE: {missing_cols_before}")
        for col in missing_cols_before:
            df_before[col] = None
            
    if missing_cols_after:
        print(f"Menambahkan kolom yang hilang di AFTER: {missing_cols_after}")
        for col in missing_cols_after:
            df_after[col] = None

    df_merged = pd.merge(df_before, df_after, on=col_lookup, how='outer', suffixes=('_Before', '_After'))

    # Remove unwanted rows
    if 'MO' in df_merged.columns:
        df_merged = df_merged[df_merged['MO'] != 'MO']

    # Proses kolom-kolom untuk membuat kolom _Before, _After, dan _Compare
    for column in df_before.columns:
        if column not in col_lookup:
            col_before = f'{column}_Before'
            col_after = f'{column}_After'
            col_compare = f'{column}_Compare'

            if col_before not in df_merged.columns:
                df_merged[col_before] = None
            if col_after not in df_merged.columns:
                df_merged[col_after] = None

            df_merged[col_compare] = df_merged[col_before] == df_merged[col_after]

            # Simpan kolom _Before, _After, dan _Compare dalam array terpisah
            before_columns.append(col_before)
            after_columns.append(col_after)
            compare_columns.append(col_compare)

    # Tambahkan kolom ke ordered_columns dengan urutan: kolom lookup, semua _Before, semua _After, semua _Compare
    ordered_columns.extend(before_columns)
    ordered_columns.extend(after_columns)
    ordered_columns.extend(compare_columns)

    # Reorder the columns
    df_merged = df_merged[ordered_columns]

    return df_merged


def clean_dataframe(df):
    # Replace NaN and infinite values with None
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.fillna('NULL')  # Or use another placeholder
    return df


def write_count_false(df, sheet_name, writer):
    # Get the xlsxwriter workbook and worksheet objects
    workbook  = writer.book
    #worksheet = writer.sheets[sheet_name]
    worksheet = workbook.add_worksheet(sheet_name)
    
    # Insert an empty row at the top (effectively shifting data down)
    worksheet.write_blank(0, 0, '', workbook.add_format())
    
    # Add the formula in the first row for each column
    for col_num, col in enumerate(df.columns, 0):
        if "Compare" in col:
            formula = f'=COUNTIF({chr(65+col_num)}3:{chr(65+col_num)}{len(df)+2}, FALSE)&"/"&COUNTIF({chr(65+col_num)}3:{chr(65+col_num)}{len(df)+2}, TRUE)'
            worksheet.write(0, col_num, formula)

    
    df.to_excel(writer, sheet_name=sheet_name, startrow=1, index=False)
    # Optionally set a column width for better visibility
    worksheet.set_column(0, len(df.columns), 18)


def count_df_by_nodename(df_before,df_after, col_name):
    col_before = f'{col_name}_Before'
    df_comp1 = df_before.groupby('NODENAME').size().reset_index(name=col_before)
    df_comp1[col_before] = 1

    col_after = f'{col_name}_After'
    df_comp2 = df_after.groupby('NODENAME').size().reset_index(name=col_after)
    df_comp2[col_after] = 1
    
    df_joined = pd.merge(df_comp1, df_comp2, on='NODENAME', how='outer')
    
    return df_joined


def write_to_excel(df, df2, data_after, data_before, file_name):
    # Guard against None inputs from KPI.create_main_merge_df
    if df is None:
        df = pd.DataFrame()
    if df2 is None:
        df2 = pd.DataFrame()
    header_data = transform_headers(df)
    header_data_5G = transform_headers(df2)

    df = df.replace([np.inf, -np.inf], np.nan).fillna("")
    df2 = df2.replace([np.inf, -np.inf], np.nan).fillna("")                                                         
    
    with pd.ExcelWriter(file_name, engine='xlsxwriter') as writer:
        workbook = writer.book
        

        # For each key in data_after, ensure it's also in data_before and vice versa
        for key in data_after.keys():
            # If key doesn't exist in data_before, create an empty DataFrame with the same columns
            if key not in data_before:
                print(f"Membuat DataFrame kosong untuk {key} di data_before")
                if isinstance(data_after[key], pd.DataFrame):
                    data_before[key] = pd.DataFrame(columns=data_after[key].columns)
                else:
                    data_before[key] = pd.DataFrame(columns=['NODENAME', 'MO'])
            
            # If key exists in data_before but is not a DataFrame, convert it
            elif not isinstance(data_before[key], pd.DataFrame):
                print(f"Mengkonversi {key} dari {type(data_before[key]).__name__} ke DataFrame")
                if hasattr(data_before[key], '__len__') and len(data_before[key]) == 0:
                    if isinstance(data_after[key], pd.DataFrame):
                        data_before[key] = pd.DataFrame(columns=data_after[key].columns)
                    else:
                        data_before[key] = pd.DataFrame(columns=['NODENAME', 'MO'])
                else:
                    try:
                        data_before[key] = pd.DataFrame(data_before[key])
                    except:
                        if isinstance(data_after[key], pd.DataFrame):
                            data_before[key] = pd.DataFrame(columns=data_after[key].columns)
                        else:
                            data_before[key] = pd.DataFrame(columns=['NODENAME', 'MO'])
            
        # Debug for all keys
        print("DEBUG - Keys in data_before:", list(data_before.keys()))
        print("DEBUG - Keys in data_after:", list(data_after.keys()))
        
        for key in data_after:
            # Skip SSBFREQ_NR_CELL if it's empty (no data to process)
            if key == 'SSBFREQ_NR_CELL':
                if len(data_after[key]) == 0 or (len(data_before.get(key, pd.DataFrame())) == 0):
                    print(f"Skipping {key} - no data to process")
                    continue
            
            print(f"Processing [{key}]")
            # Use get to avoid KeyError if key doesn't exist in data_before
            before_data = data_before.get(key, pd.DataFrame())
            print(len(before_data))
            
            # Skip creating Excel sheet if both before and after DataFrames are empty
            before_empty = not isinstance(before_data, pd.DataFrame) or len(before_data) == 0
            after_empty = not isinstance(data_after[key], pd.DataFrame) or len(data_after[key]) == 0
            
            if before_empty and after_empty:
                print(f"Skipping Excel sheet for {key} - no data in both before and after")
                continue
            print(len(data_after[key]))
            
            # Debug for all sheets
            print(f"DEBUG - {key} in data_before: {key in data_before}")
            print(f"DEBUG - {key} in data_after: {key in data_after}")
            print(f"DEBUG - {key} data_before type: {type(data_before.get(key, 'Not Found'))}")
            print(f"DEBUG - {key} data_after type: {type(data_after.get(key, 'Not Found'))}")
            if key in data_before and isinstance(data_before[key], pd.DataFrame):
                print(f"DEBUG - {key} data_before columns: {data_before[key].columns.tolist()}")
            if key in data_after and isinstance(data_after[key], pd.DataFrame):
                print(f"DEBUG - {key} data_after columns: {data_after[key].columns.tolist()}")
            
            if key == 'Alarm':
                if isinstance(data_before[key], pd.DataFrame):
                    write_alarm_dataframe_with_format(data_before[key].reset_index(drop=True), 'Alarm_Before', writer)
                if isinstance(data_after[key], pd.DataFrame):
                    write_alarm_dataframe_with_format(data_after[key].reset_index(drop=True), 'Alarm_After', writer)
                # 2. Ambil semua nilai unik dari kolom 'NODENAME'
                unique_statuses = data_before['Cell Status']['NODENAME'].unique()
                df_bf1 = pd.DataFrame(unique_statuses, columns=['NODENAME'])

                # 4. Tambahkan kolom penanda (flag) baru yang bernilai 1
                df_bf1["MOBATCH_BEFORE"] = "OK"


                # --- Mulai Logika ---

                # Tentukan kolom kunci untuk merge pertama
                key_cols_1 = ['NODENAME', 'Severity', 'Problem', 'Object', 'Cause']

                # 2. Merge kiri pertama: data_after -> data_before
                # Kita hanya perlu kolom kunci dari data_before dan drop_duplicates
                # indicator=True akan membuat kolom '_merge'
                # ('both' = ada di data_before, 'left_only' = tidak ada di data_before)
                merged_df = pd.merge(
                    data_after[key],
                    data_before[key],
                    on=key_cols_1,
                    how='left',
                    indicator=True,
                    suffixes=('_After', '_Before')
                )

                # 3. Merge kiri kedua: merged_df -> df_bf1
                # Ini untuk menambahkan kolom FLAG_BEFORE berdasarkan NODENAME
                final_df = pd.merge(
                    merged_df,
                    df_bf1,
                    on='NODENAME',
                    how='left'
                )
                final_df['MOBATCH_BEFORE'] = final_df['MOBATCH_BEFORE'].fillna('NOK')


                # 4. Terapkan logika untuk kolom "REMARK"
                # Tentukan kondisi
                conditions = [
                    # Kondisi 1: if exist in data_before[key]
                    (final_df['_merge'] == 'both'),

                    # Kondisi 2: if not exist in data_before[key] and MOBATCH_BEFORE == "OK"
                    (final_df['_merge'] == 'left_only') & (final_df['MOBATCH_BEFORE'] == "OK")
                ]

                # Tentukan pilihan yang sesuai dengan kondisi
                choices = ['EXISTING', 'NEW ALARM']

                # Buat kolom REMARK menggunakan np.select
                # default=np.nan berarti jika tidak ada kondisi yang terpenuhi, akan diisi NaN
                final_df['REMARK'] = np.select(conditions, choices, default='DATA BEFORE NOT FOUND')

                # 5. Bersihkan DataFrame
                # Hapus kolom bantu yang tidak diperlukan di hasil akhir
                ##final_result = final_df.drop(columns=['_merge', 'FLAG_BEFORE'])
                
                # Define the required column order
                required_columns = [
                    'NODENAME', 'Object', 'Problem', 'Cause',
                    'Date_After', 'Time_After', 
                    'Date_Before', 'Time_Before', 
                    'REMARK','MOBATCH_BEFORE'
                ]
                
                # Create a new DataFrame with only the required columns
                # Fill missing columns with "NULL"
                filtered_df = pd.DataFrame()
                for col in required_columns:
                    if col in final_df.columns:
                        filtered_df[col] = final_df[col].fillna("NULL")
                    else:
                        filtered_df[col] = "NULL"
                
                # Print the filtered DataFrame
                print("Final DataFrame with specified columns:")
                ##print(filtered_df)
                
                
                def write_sheet(df, sheet_name, writer):
                    """Write DataFrame to Excel and auto-fit column widths (max 50), with yellow highlighting for NEW ALARM rows."""
                    df = reorder_columns(df)
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    ws = writer.sheets[sheet_name]
                    
                    # Auto-fit column widths
                    for i, col in enumerate(df.columns):
                        width = min(50, max(len(col), df[col].astype(str).str.len().max() or 0) + 2)
                        ws.set_column(i, i, width)
                    
                    # Add conditional formatting for NEW ALARM rows
                    if 'REMARK' in df.columns:
                        remark_col_idx = df.columns.get_loc('REMARK')
                        remark_col_letter = chr(65 + remark_col_idx)  # Convert to Excel column letter (A, B, C, etc.)
                        
                        # Create yellow background format
                        yellow_format = writer.book.add_format({'bg_color': '#FFFF00'})
                        
                        # Apply conditional formatting to highlight rows where REMARK = "NEW ALARM"
                        ws.conditional_format(f'A2:{chr(65 + len(df.columns) - 1)}{len(df) + 1}', {
                            'type': 'formula',
                            'criteria': f'=${remark_col_letter}2="NEW ALARM"',
                            'format': yellow_format
                        })

                write_sheet(filtered_df, f"NEW_Alarm", writer)                                     

            elif key == "Summary":
                df_diff = compare_dataframes(data_before[key], data_after[key]).drop(columns=['MO'])
                df_diff = clean_dataframe(df_diff)
                write_summary(df_diff, 'Summary', writer, data_before['Cell Status'],data_after['Cell Status'] )
            elif key == "TermPointToGNodeB" or key == "NRCellRelation":
                def write_sheet(df, sheet_name, writer):
                    """Write DataFrame to Excel and auto-fit column widths (max 50)."""
                    df = reorder_columns(df)
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    ws = writer.sheets[sheet_name]
                    for i, col in enumerate(df.columns):
                        width = min(50, max(len(col), df[col].astype(str).str.len().max() or 0) + 2)
                        ws.set_column(i, i, width)

                write_sheet(data_before[key], f"{key}_Before", writer)
                write_sheet(data_after[key], f"{key}_After", writer)


            else:

                if isinstance(data_before[key], pd.DataFrame) and isinstance(data_after[key], pd.DataFrame):
                    col_lookup = ['NODENAME', 'MO', 'arfcnValueEUtranDl'] if key == 'freqPrioListEUTRA' else ['NODENAME', 'MO']
                    if key == 'BAND_NR_SECTOR':
                        print(f"COBA OLAH [{key}]")
                        # Check if reservedBy column exists, if not skip this processing
                        if 'reservedBy' not in data_before[key].columns or 'reservedBy' not in data_after[key].columns:
                            print(f"Skipping {key} - reservedBy column not found")
                            continue
                        
                        pattern = r'(NRCellDU=.*?)(?:\s|$)'

                        data_before[key]['reservedBy'] = data_before[key]['reservedBy'].str.extract(pattern)
                        data_after[key]['reservedBy'] = data_after[key]['reservedBy'].str.extract(pattern)
                        merged_df = compare_dataframes_with_check(data_before[key], data_after[key], col_lookup) 
                        df_diff_ssbfreq = compare_dataframes_with_check(data_before["SSBFREQ_NR_CELL"], data_after["SSBFREQ_NR_CELL"], col_lookup)
                        df_diff_ssbfreq = df_diff_ssbfreq.rename(columns={'MO': 'CELLNAME'})
                        merged_df['MAIN_RESERVED_BY'] = merged_df['reservedBy_Before'].where(
                            merged_df['reservedBy_Before'].notna() & (merged_df['reservedBy_Before'] != ''), merged_df['reservedBy_After']
                        )
                        merged_df['MAIN_RESERVED_BY'] = merged_df['MAIN_RESERVED_BY'].fillna('NULL').replace('', 'NULL')
                                                
                        
                        merged_df = merged_df.merge(df_diff_ssbfreq, how='left', left_on=['NODENAME', 'MAIN_RESERVED_BY'], right_on=['NODENAME', 'CELLNAME'])
                        column_order = ['NODENAME', 'CELLNAME', 'MO', 'ssbFrequency_Before', 'arfcnDL_Before', 'arfcnUL_Before', 'bSChannelBwDL_Before', 'bSChannelBwUL_Before','ssbFrequency_After', 'arfcnDL_After', 'arfcnUL_After', 'bSChannelBwDL_After', 'bSChannelBwUL_After', 'MAIN_RESERVED_BY', 'ssbFrequency_Compare', 'arfcnDL_Compare', 'arfcnUL_Compare', 'bSChannelBwDL_Compare', 'bSChannelBwUL_Compare', 'reservedBy_Before' , 'reservedBy_After', 'reservedBy_Compare']

                        merged_df = merged_df.assign(**{col: pd.NA for col in column_order if col not in merged_df.columns})
                        merged_df = merged_df[column_order]   
                        
                        ###print(data_after[key])
                        write_count_false(merged_df, "Bandwidth 5G", writer)                                                
                        
                    elif key == 'bandwidth':
                        merged_df = compare_dataframes_with_check(data_before[key], data_after[key], col_lookup)
                        column_order = ['NODENAME', 'MO', 'dlChannelBandwidth_Before', 'ulChannelBandwidth_Before', 'earfcndl_Before', 'earfcnul_Before', 'dlChannelBandwidth_After', 'ulChannelBandwidth_After', 'earfcndl_After', 'earfcnul_After', 'dlChannelBandwidth_Compare', 'ulChannelBandwidth_Compare', 'earfcndl_Compare', 'earfcnul_Compare']
                        merged_df = merged_df.assign(**{col: pd.NA for col in column_order if col not in merged_df.columns})
                        merged_df = merged_df[column_order]   
                        
                                  
                        write_count_false(merged_df, key, writer)                          
                    
                    elif key == 'Cell Status':
                        data_before[key] = clean_cell_status(data_before[key])
                        data_after[key] = clean_cell_status(data_after[key])
                        #####
                        ##count_df_by_nodename(df_before,df_after, col_name):
                        ##df_check_cell = count_df_by_nodename(data_before[key], data_after[key] , "Cell_COUNT")
                        ##write_count_false(df_check_cell, "Cell_COUNT", writer)
                        
                        
                        table_SleepState = "SleepState"
                        print(data_after[table_SleepState])
                        df_diff_sleepstate = compare_dataframes_with_check(data_before[table_SleepState], data_after[table_SleepState], col_lookup)
                        # Clean the "MO" column
                        df_diff_sleepstate["MO"] = df_diff_sleepstate["MO"].str.replace(r",CellSleepFunction=1", "", flags=re.IGNORECASE, regex=True)
                                                
                        
                        cell_status_diff = compare_dataframes_with_check(data_before[key], data_after[key], col_lookup)
                        merged_df = pd.merge(cell_status_diff, df_diff_sleepstate, on=col_lookup, how='left')
                        # Reorder the columns
                        column_order = [
                            "NODENAME",
                            "MO",
                            "administrativeState_Before",
                            "operationalState_Before",
                            "administrativeState_After",
                            "operationalState_After",
                            "administrativeState_Compare",
                            "operationalState_Compare",
                            "sleepState_Before",
                            "sleepState_After",
                            "sleepState_Compare"
                        ]

                        merged_df = merged_df.assign(**{col: pd.NA for col in column_order if col not in merged_df.columns})
                        merged_df = merged_df[column_order]   
                        
                                  
                        write_count_false(merged_df, key, writer)                        
                    
                    else:
                        # Pastikan data_before[key] adalah DataFrame meskipun kosong
                        if not isinstance(data_before[key], pd.DataFrame) or len(data_before[key]) == 0:
                            data_before[key] = pd.DataFrame(columns=data_after[key].columns)
                            
                        # Pastikan data_after[key] adalah DataFrame meskipun kosong
                        if not isinstance(data_after[key], pd.DataFrame) or len(data_after[key]) == 0:
                            data_after[key] = pd.DataFrame(columns=data_before[key].columns)
                            
                        df_diff = compare_dataframes_with_check(data_before[key], data_after[key], col_lookup)
                        write_count_false(df_diff, key, writer)


        
        # Process KPI LTE
        worksheet = workbook.add_worksheet("KPI_LTE")
        writer.sheets["KPI_LTE"] = worksheet
        write_kpi_data(worksheet, header_data, df, workbook)
        
        # Process KPI 5G
        worksheet_5G = workbook.add_worksheet("KPI_5G")
        writer.sheets["KPI_5G"] = worksheet_5G
        write_kpi_data(worksheet_5G, header_data_5G, df2, workbook)        
    
    print(f"Excel file saved: {file_name}")


def write_kpi_data(worksheet, header_data, df, workbook):
    
    # --- 1. DEFINISI FORMAT SEL DASAR ---
    
    # Format Dasar Header (tanpa warna) - Digunakan untuk baris header yang tidak diwarnai (misal row_idx=0)
    merge_format_base = workbook.add_format({
        'bold': True,
        'align': 'center', 
        'valign': 'vcenter', 
        'border': 1,
    }) 
    
    rows_format_base = workbook.add_format({
        'bold': True,
        'border': 0,
    })     

    # --- 2. DEKLARASI MAPS ---
    color_map = {}
    
    # Akan menyimpan format untuk SELURUH KOLOM (Warna + Non-Bold)
    col_format_map = {} 
    # Akan menyimpan format untuk SEL HEADER (Warna + Bold)
    header_format_map = {} 

    # --- 3. MENULIS BARIS HEADER (Merge, Warna Acak, dan Format Kolom) ---
    for row_idx, row in enumerate(header_data):
        col_idx = 0
        
        if row_idx < 2:  # Only apply merging to the first two rows (KPI names and BEFORE/AFTER)
            while col_idx < len(row):
                start_col = col_idx
                
                # Look for consecutive identical values to group for merging
                while col_idx + 1 < len(row) and row[col_idx + 1] == row[start_col]:
                    col_idx += 1
                
                current_format = merge_format_base

                # --- Logika Pewarnaan Kolom (Hanya di baris indeks 1 - BEFORE/AFTER row) ---
                if row_idx == 1:  # BEFORE/AFTER row gets the colored background
                    if row[start_col] not in col_format_map:
                        # Create a random color function to get different colors for each unique header
                        def random_color():
                            import random
                            colors = [
                                "#33ffce", "#f0ff00", "#fbdb26", "#62c614",
                                "#ff1700", "#00ff46"
                            ]
                            return random.choice(colors)
                        
                        color_remark = random_color()
                        
                        # Properti Dasar (Alignment, Border)
                        base_properties = {
                            'align': 'center', 'valign': 'vcenter', 'border': 1
                        }
                        
                        # Menambahkan Warna jika ada
                        if color_remark:
                            base_properties['bg_color'] = color_remark
                        
                        # TAHAP 1: FORMAT KOLOM (Non-Bold, untuk Data)
                        col_properties = base_properties.copy()
                        col_properties['bold'] = False 
                        col_format_map[row[start_col]] = workbook.add_format(col_properties)
                        
                        # TAHAP 2: FORMAT HEADER (Bold, untuk Header Merge)
                        header_properties = base_properties.copy()
                        header_properties['bold'] = True
                        header_format_map[row[start_col]] = workbook.add_format(header_properties)
                    
                    # 1. Atur 'current_format' untuk Merge ke format BOLD
                    current_format = header_format_map[row[start_col]]
                    
                    # 2. Terapkan format NON-BOLD ke SELURUH KOLOM
                    for color_col in range(start_col, col_idx + 1):
                        # Format kolom disamakan dengan format berwarna NON-BOLD
                        worksheet.set_column(color_col, color_col, None, col_format_map[row[start_col]])

                # MENGGABUNGKAN SEL (HEADER)
                # Format BOLD (current_format) akan menimpa format kolom NON-BOLD 
                # HANYA untuk sel header ini.
                worksheet.merge_range(
                    row_idx, 
                    start_col, 
                    row_idx, 
                    col_idx, 
                    row[start_col], 
                    current_format
                )

                col_idx += 1
        else:
            # For the third row (timestamps) and data rows, write normally
            worksheet.write_row(row_idx, 0, row)
    
    # --- 4. MENULIS BARIS DATA ---
    
    start_data_row = len(header_data)

    for row_idx, row in enumerate(df.values, start=start_data_row):
        # Data ditulis TANPA format eksplisit (HANYA row)
        # Data akan mewarisi format dari set_column(), yaitu:
        # 1. Warna latar belakang
        # 2. Border
        # 3. bold: False (Non-bold)
        worksheet.write_row(row_idx, 0, row)


def generate_report(before_path, after_path, output_path, include_kpi=True, before_time="2025-04-10 09:00", after_time="2025-04-10 09:00", progress_callback=None):
    """
    Generate a comprehensive Excel report comparing Before and After data.
    
    Args:
        before_path (str): Path to the Before data directory
        after_path (str): Path to the After data directory
        output_path (str): Path to save the output Excel file
        include_kpi (bool): Whether to include KPI analysis in the report
        before_time (str): Start time for KPI processing
        after_time (str): Start time for KPI processing
        progress_callback (callable): Function to call with progress updates (progress, message)
    
    Returns:
        str: Path to the generated report
    """
    # Process KPI data if requested
    if include_kpi:
        if progress_callback:
            progress_callback(5, "Processing KPI 5G - Before")
        KPI_5G_BEFORE = process_kpi_logs(before_path, "GREP_KPI_5G", before_time)
        
        if progress_callback:
            progress_callback(15, "Processing KPI 5G - After")
        KPI_5G_AFTER = process_kpi_logs(after_path, "GREP_KPI_5G", after_time)
        
        if progress_callback:
            progress_callback(25, "Processing KPI LTE - Before")
        KPI_LTE_BEFORE = process_kpi_logs(before_path, "GREP_KPI_LTE", before_time)
        
        if progress_callback:
            progress_callback(35, "Processing KPI LTE - After")
        KPI_LTE_AFTER = process_kpi_logs(after_path, "GREP_KPI_LTE", after_time)

        if progress_callback:
            progress_callback(40, "Merging KPI 5G data")
        compare_5G = create_main_merge_df(KPI_5G_BEFORE, KPI_5G_AFTER)
        
        if progress_callback:
            progress_callback(45, "Merging KPI LTE data")
        compare_LTE = create_main_merge_df(KPI_LTE_BEFORE, KPI_LTE_AFTER)
    else:
        KPI_5G_BEFORE = pd.DataFrame()
        KPI_5G_AFTER = pd.DataFrame()
        KPI_LTE_BEFORE = pd.DataFrame()
        KPI_LTE_AFTER = pd.DataFrame()
        compare_5G = pd.DataFrame()
        compare_LTE = pd.DataFrame()

    print(KPI_LTE_BEFORE)
    print(KPI_LTE_AFTER)

    # Process log data
    if progress_callback:
        progress_callback(50, "Processing Before log files")
    data_before = read_files_from_folder(before_path, progress_callback)

    if progress_callback:
        progress_callback(75, "Processing After log files")
    data_after = read_files_from_folder(after_path, progress_callback)

    if progress_callback:
        progress_callback(90, "Writing Excel report")
    # Write to Excel
    write_to_excel(compare_LTE, compare_5G, data_after, data_before, output_path)

    if progress_callback:
        progress_callback(100, "Report generation complete")

    return output_path


def run_before_after_analysis(before_path, after_path, include_kpi=True, before_time="2025-04-10 09:00", after_time="2025-04-10 09:00", progress_callback=None):
    """
    Main function to run the Before/After analysis.
    
    Args:
        before_path (str): Path to the Before data directory
        after_path (str): Path to the After data directory
        include_kpi (bool): Whether to include KPI analysis
        before_time (str): Start time for KPI processing
        after_time (str): Start time for KPI processing
        progress_callback (callable): Function to call with progress updates (progress, message)
    """
    # Validate input paths
    if not os.path.exists(before_path):
        raise FileNotFoundError(f"Before path does not exist: {before_path}")
    if not os.path.exists(after_path):
        raise FileNotFoundError(f"After path does not exist: {after_path}")
    
    # Generate output path
    output_path = os.path.join(os.path.dirname(before_path), f"01_Report_CR_activity.xlsx")
    
    # Run the analysis and generate report
    report_path = generate_report(before_path, after_path, output_path, include_kpi, before_time, after_time, progress_callback)
    
    print(f"Analysis complete. Report saved to: {report_path}")
    return report_path