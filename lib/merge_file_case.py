# This file is now only for shared constants or utilities for CMBULK FILE MERGE

import os
import re
from collections import defaultdict

ENM_NAMES = [
    "ENM-RAN1A", "ENM-RAN2A", "ENM-RAN3A", "ENM-RAN4A", "ENM-RAN5A", "ENM-RAN7A",
    "ENM_DTAC_FDD1", "ENM_DTAC_FDD2", "ENM_DTAC_FDD3", "ENM_DTAC_FDD4"
]

def merge_cmbulk_files(files, enm_names, log_callback=None):
    """
    Gabungkan file CMBULK berdasarkan ENM-NAME dan prefix nomor.
    files: list of file paths
    enm_names: list of ENM-NAME
    log_callback: function for logging (optional)
    """
    def log(msg):
        if log_callback:
            log_callback(msg)

    if not files:
        return

    log("🔍 File dipilih:")
    for f in files:
        log(f)

    grouped_files = defaultdict(list)
    for file in files:
        filename = os.path.basename(file)
        folder = os.path.dirname(file)
        matched_enm = None
        for enm in enm_names:
            if enm in filename:
                matched_enm = enm
                break
        if matched_enm:
            key = (folder, matched_enm)
            grouped_files[key].append(file)
        else:
            log(f"❌ Tidak ditemukan ENM-NAME di list untuk file: {filename}")

    for (folder, enm_name), file_list in grouped_files.items():
        prefix = "98"
        for infile_path in file_list:
            match = re.match(r"(\d{2})_CMBULK_", os.path.basename(infile_path))
            if match:
                prefix = match.group(1)
                break
        output_filename = os.path.join(folder, f"{prefix}_CMBULK_{enm_name}_OUTPUT.txt")
        log(f"\n📝 Menggabungkan untuk ENM: {enm_name}")
        with open(output_filename, 'w', encoding='utf-8') as outfile:
            for infile_path in file_list:
                log(f"➕ Tambahkan: {os.path.basename(infile_path)}")
                with open(infile_path, 'r', encoding='utf-8') as infile:
                    outfile.write(infile.read())
                    outfile.write("\n")
        log(f"✅ Disimpan: {output_filename}")
    return True
