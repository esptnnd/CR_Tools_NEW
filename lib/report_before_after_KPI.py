"""
KPI Processing Library for Before/After Network Configuration Comparison Tool
This module provides functions for processing and analyzing Key Performance Indicator (KPI) data
for both LTE and 5G technologies, extracting KPI metrics from logs, handling timestamps,
and preparing data for comparison between Before and After states.
"""

import os
import pandas as pd
import glob
import re
import numpy as np


def process_kpi_logs(folder, pattern, start_defined):
    """
    Process KPI log files in the specified folder with the given pattern.

    Args:
        folder (str): Path to the folder containing log files
        pattern (str): Pattern to look for in log files (e.g., "GREP_KPI_5G", "GREP_KPI_LTE")
        start_defined (str or datetime): Starting time for filtering data ("NO_START" or datetime string)

    Returns:
        pandas.DataFrame: DataFrame containing processed KPI data
    """
    all_data = []
    datetime_headers = set()
    
    # Read all log files in the directory
    log_files = sorted(glob.glob(os.path.join(folder, "*.log")), key=os.path.getsize)
    
    # Process each log file with progress tracking
    for idx, log_file in enumerate(log_files):
        nodename = os.path.splitext(os.path.basename(log_file))[0]
        temp_data = []
        temp_datetime_headers = set()
        
        with open(log_file, "r", encoding='utf-8', errors='ignore') as file:
            lines = file.readlines()
            
            for line in lines:
                if line.startswith(pattern):
                    parts = line.strip().rstrip(";").split("; ")
                    
                    if "Object" in parts and "Counter" in parts:
                        temp_datetime_headers.update(parts[3:])
                    else:
                        temp_data.append(parts[1:])
        
        if temp_data:
            datetime_headers.update(temp_datetime_headers)
            temp_datetime_headers = sorted(temp_datetime_headers)

            columns = ["NODENAME", "Object", "Counter"] + temp_datetime_headers
            formatted_data = []
            
            for row in temp_data:
                row_dict = {"NODENAME": nodename, "Object": row[0], "Counter": row[1]}
                for dt in temp_datetime_headers:
                    row_dict[dt] = "N/A"
                for i, dt in enumerate(row[2:]):
                    if i < len(temp_datetime_headers):
                        row_dict[temp_datetime_headers[i]] = dt
                formatted_data.append(row_dict)

            # Identify datetime columns based on format "YYYY-MM-DD HH:MM"
            datetime_mapping = {}
            temp_df = pd.DataFrame(formatted_data, columns=columns)
            for col in temp_df.columns:
                try:
                    datetime_format = "%Y-%m-%d %H:%M"
                    dt = pd.to_datetime(col, format=datetime_format, errors='raise')
                    datetime_mapping[col] = dt.strftime(datetime_format)  # Store as string
                except ValueError:
                    pass  # Ignore non-datetime columns        
            
            temp_df.columns = [datetime_mapping[col] if col in datetime_mapping else col for col in temp_df.columns]
            all_data.append(temp_df)
        
        
    max_rop = 20
    if start_defined == "NO_START":
        datetime_candidates = sorted(datetime_headers)
    else:
        # Convert string column names to datetime for filtering using collected headers
        datetime_candidates = sorted([
            col for col in datetime_headers
            if pd.to_datetime(col, format='%Y-%m-%d %H:%M', errors='coerce') >= pd.Timestamp(start_defined)
        ])
    datetime_headers = datetime_candidates[:max_rop]
        
    final_columns = ["NODENAME", "Object", "Counter"] + datetime_headers
    # If no data was collected, return an empty DataFrame with the expected columns
    if not all_data:
        df = pd.DataFrame(columns=final_columns)
        return df
    df = pd.concat(all_data, ignore_index=True).reindex(columns=final_columns)
    df.fillna("N/A", inplace=True)
    return df


def create_main_merge_df(before_df, after_df):
    """
    Merge BEFORE and AFTER datasets for comparison.

    Args:
        before_df (pandas.DataFrame): DataFrame containing before data
        after_df (pandas.DataFrame): DataFrame containing after data

    Returns:
        pandas.DataFrame: Merged DataFrame comparing before and after data
    """
    columns_to_keep = {"NODENAME", "Object", "Counter"}
    
    # Rename columns for before_df
    before_df = before_df.rename(
        columns={col: f"{col}_BEFORE" for col in before_df.columns if col not in columns_to_keep}
    )
    
    # Rename columns for after_df
    after_df = after_df.rename(
        columns={col: f"{col}_AFTER" for col in after_df.columns if col not in columns_to_keep}
    ) 
    
    merged_df = before_df.merge(after_df, on=["NODENAME", "Object", "Counter"], suffixes=("_BEFORE", "_AFTER"), how="outer")
    
    # Get unique Counter values
    counter_values = merged_df["Counter"].unique()
    # If there are no counters, return None as requested
    if len(counter_values) == 0:
        return None
    main_merge_df = None
    
    for counter in counter_values:
        temp_df = merged_df[merged_df["Counter"] == counter].drop(columns=["Counter"]).copy()        
        
        if main_merge_df is None:  
            main_merge_df = temp_df
            
        else:
            formatted_suffix = f"_{counter}"
            main_merge_df = main_merge_df.merge(temp_df, on=["NODENAME", "Object"], how="outer", suffixes=("", formatted_suffix))

    # Safe-guard: if no merged data by counters, return None
    if main_merge_df is None:
        return None
    first_counter_value = counter_values[0]  # Get the first unique value
    formatted_suffix = f"_{first_counter_value}"  # Ensures the format _latest
    # Rename columns dynamically using regex
    main_merge_df.rename(columns={
        col: re.sub(r"_BEFORE$", f"_BEFORE{formatted_suffix}", col)
             if re.search(r"_BEFORE$", col) else
             re.sub(r"_AFTER$", f"_AFTER{formatted_suffix}", col)
             if re.search(r"_AFTER$", col) else col
        for col in main_merge_df.columns
    }, inplace=True)    
    return main_merge_df


def split_column_name(col_name):
    """
    Split column name into date/time, before/after, and KPI name components.

    Args:
        col_name (str): Column name to split

    Returns:
        tuple: (date_time, before_after, kpi_name) or (col_name, "", "") if no match
    """
    match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})_(BEFORE|AFTER)_(.+)", col_name)
    if match:
        return match.groups()
    return col_name, "", ""


def transform_headers(df):
    """
    Transform headers into a multi-level format for proper Excel presentation.

    Args:
        df (pandas.DataFrame): DataFrame to transform headers for

    Returns:
        list: List of header rows for multi-level Excel headers
    """
    if df.empty:
        return [[], [], []]
    
    original_headers = df.columns.tolist()
    first_row, second_row, third_row = [], [], []
    
    for col in original_headers:
        if col in ["NODENAME", "Object", "Counter"]:  # Include Counter as static column
            # For static columns like NODENAME, Object, Counter - put them in all rows but with different content
            first_row.append(col)
            second_row.append(col)
            third_row.append(col)
        else:
            # For time-based KPI columns like "2025-04-10 18:00_BEFORE_Acc_InitialErabSetupSuccRate"
            date_time, before_after, kpi_name = split_column_name(col)
            if kpi_name and date_time and before_after:  # If it's a properly formatted time-based column
                first_row.append(kpi_name)
                second_row.append(before_after)
                third_row.append(date_time)
            else:
                # For any other columns that don't match the pattern, just add as is
                first_row.append(col)
                second_row.append(col)
                third_row.append(col)
    
    # Return in the order expected for Excel multi-level headers: [row0, row1, row2] 
    # Looking at the expected format more carefully:
    # Row 1 (first_row): KPI names like Acc_InitialErabSetupSuccRate, Acc_RrcConnSetupSuccRate
    # Row 2 (second_row): BEFORE/AFTER indicators 
    # Row 3 (third_row): timestamps like 18:00, 18:15, 18:30, etc
    return [first_row, second_row, third_row]


def process_kpi_data(before_log_path, after_log_path, technology):
    """
    Main function to process KPI data from both before and after log paths.

    Args:
        before_log_path (str): Path to before log directory
        after_log_path (str): Path to after log directory
        technology (str): Technology type ('LTE' or '5G')

    Returns:
        pandas.DataFrame: Processed and merged KPI data
    """
    # Determine pattern based on technology
    if technology.upper() == 'LTE':
        pattern = "GREP_KPI_LTE"
    elif technology.upper() == '5G':
        pattern = "GREP_KPI_5G"
    else:
        raise ValueError("Technology must be either 'LTE' or '5G'")
    
    # Process KPI data for both folders
    kpi_before = process_kpi_logs(before_log_path, pattern, "NO_START")
    kpi_after = process_kpi_logs(after_log_path, pattern, "NO_START")
    
    # For now, return the before data; in a real implementation, this would merge before/after
    # For the new tool, we need to create a comparison DataFrame
    comparison_df = create_main_merge_df(kpi_before, kpi_after)
    
    return comparison_df