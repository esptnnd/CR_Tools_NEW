
Here is the project history:

```text
# -----------------------------------------------------------------------------
# Author                : esptnnd
# Tools Name            : CR_Tools_NEW
# Company               : Ericsson Indonesia
# Created on            : 7 May 2025
# Description           : CR TOOLS by esptnnd — built for the ECT Project to help the team
#                         execute faster, smoother, and with way less hassle.
#                         Making life easier, one script at a time!
#
#
# === Late May 2025: Project Start & Core Features ===
#
# # 25 May 2025 :
# # - Project begins with "Initial commit." (Note: The log shows the first commit on May 25, 2025)
#
# # 28-29 May 2025 :
# # - Code is split into modules.
# # - Core tools "CR EXECUTOR" and "CR REPORT GENERATOR" are added and marked as stable.
#
# # 30 May 2025 :
# # - Work focuses on updating the application's GUI to a "Modern look."
#
# === June 2025: New Tools & Hygiene ===
#
# # 4 Jun 2025 :
# # - Bugs fixed in the "Report LOGS Generator."
# # - New "RNC Cell checking" feature added.
#
# # 8 Jun 2025 :
# # - A new "CMbulk feature (BETA)" is introduced.
#
# # 14-16 Jun 2025 :
# # - "Hygiene" checks are a major focus, with several updates to add more list checking.
#
# # 26 Jun 2025 :
# # - A significant new feature, "REHOMING TOOLS," is added.
#
# === July 2025: Stabilization & Rehoming ===
#
# # 2-3 Jul 2025 :
# # - This period is dedicated to refining and fixing the new "REHOMING TOOLS" (revisions REV3, REV4).
#
# # 4-9 Jul 2025 :
# # - Other fixes are implemented, including debug printouts and a "Retry Upload" feature.
#
# === October 2025: Work Resumes & Major Features ===
#
# # 6 Oct 2025 :
# # - Development resumes after a break (no commits in August or September).
#
# # 29 Oct 2025 :
# # - A significant update adds "more robust feature[s]":
# # - Adds "Clone Session" capability.
# # - Adds the ability to upload multiple CR folders.
# # - A remaining issue is noted: site_list.txt files merge incorrectly.
#
# # 30 Oct 2025 (Latest):
# # - A large, well-documented update for the "Before/After Report Tool" is committed.
# # - Adds real-time progress tracking.
# # - Fixes multi-level headers in the KPI Excel output.
# # - Simplifies the UI with a single "Browse" button.
# # - Improves path formatting and color-coding in the Excel report.
# -----------------------------------------------------------------------------

  **CR Tools New** is a comprehensive Python-based application designed for network engineers to streamline various tasks. It
  features a user-friendly Graphical User Interface (GUI) that provides robust SSH connectivity for managing multiple server sessions.

  Key functionalities include:

   * Graphical User Interface (GUI):
       * The tool provides a user-friendly GUI for easy operation, with a main window that includes a menu bar for accessing different
         features and a central area for displaying different tool widgets.

   * Upload CR:
       * Menu: CR EXECUTOR TRUE or CR EXECUTOR DTAC -> Button: UPLOAD CR
       * This is a main feature that allows you to upload and execute CR commands to multiple server sessions simultaneously.
       * It opens a dialog where you can:
           * Browse and select a parent folder containing CRs.
           * Select multiple subfolders to upload.
           * Select multiple SSH sessions to upload to.
           * Choose a mode for splitting nodes (TRUE, DTAC, or SPLIT_RANDOMLY).
           * Select a Mobatch execution mode (PYTHON_MOBATCH, REGULAR_MOBATCH, etc.).
           * Customize the command format for SEND_BASH_COMMAND mode.
           * Set mobatch_paralel and mobatch_timeout values.
           * Optionally, collect pre-post check data.

   * SSH Connectivity:
       * Menu: CR EXECUTOR TRUE or CR EXECUTOR DTAC
       * The tool provides a robust SSH client to connect to network devices securely.
       * Connect to a single session: Click the `Connect` button within a session tab.
       * Connect to multiple sessions: Click the `Connect Selected Sessions` button to open a dialog where you can select and connect to
         multiple sessions at once.
       * Each SSH session is opened in its own tab within the "CR EXECUTOR" widgets.
       * Within each tab, you can:
           * Send individual commands using the input line at the bottom.
           * Send a batch of commands using the "Send Batch" button.
           * View screen sessions and connect to them using the "Screen Sessions" button.

   * Log Checking:
       * Menu: CR EXECUTOR TRUE or CR EXECUTOR DTAC -> Button: Download LOG
       * This feature allows you to download and analyze log files from remote servers.
       * It opens a dialog where you can:
           * Select multiple SSH sessions from which to download logs.
           * Specify the remote path to the log files.
           * Choose a log checking mode from a dropdown list, including "Normal Log Checking", "collect data Hygiene", "Normal Compare Before
             Checking", and more.
       * After downloading, the tool automatically checks the logs and exports the results to an Excel file.

   * 3G RNC Rehoming Tools:
       * Menu: Other Tools -> Rehoming SCRIPT Tools
       * This feature provides tools to assist with network rehoming procedures.
       * It includes options to:
           * Select a DUMP file and a DATA_CELL.xlsx file to generate rehoming scripts.
           * Browse and select multiple DUMP files to merge.

   * File Merging:
       * Menu: Other Tools -> CMBULK FILE MERGE
       * This tool allows you to merge multiple CMBULK files into a single file.
       * You can select multiple CMBULK files, and the tool will merge them according to predefined ENM names.

   * Report Generation:
       * Menu: Other Tools -> CR REPORT GENERATOR
       * This feature allows you to generate a CR report from a selected folder.
       * You can select a folder containing log files, and the tool will process them and generate a detailed Excel report.

  ---

  New and Enhanced Features: (updated 30 October 2025)

   * Duplicate Session:
       * Menu: CR EXECUTOR TRUE or CR EXECUTOR DTAC -> Button: Duplicate Session
       * This feature allows you to create a complete copy of an existing session group (e.g., "CR EXECUTOR TRUE" or "CR EXECUTOR DTAC"),
         including all its tabs and settings. This is useful when you want to work with the same set of servers but with different
         configurations or for different tasks.
           * When you trigger this feature, it identifies the currently active session group.
           * It then opens a "Duplicate Session" dialog box, which allows you to customize the "Folder CR" and "Screen CR" values for the new,
              duplicated group. These values are pre-filled with the values from the original group.
           * After you confirm, the tool creates a new session group with a unique name (e.g., "CR EXECUTOR TRUE CLONE 1").
           * This new group is an exact copy of the original, containing all the same SSH tabs and targets.
           * A new entry for the duplicated group is added to the "CR EXECUTOR" menu, allowing you to easily switch between the original and
             the cloned session groups.

   * Before and After Report Generation:
       * Menu: Other Tools -> Before After REPORT
       * This new feature allows you to generate a detailed report comparing network configuration and performance data from two different
         points in time ("Before" and "After").

   * Key Performance Indicator (KPI) Analysis:
       * This is part of the "Before and After Report Generation" feature.
       * The tool now performs KPI analysis for both LTE and 5G technologies.
       * The KPI data is presented in a corrected and improved Excel report format for better readability.

   * Comprehensive Excel Reports:
       * The tool generates multi-sheet Excel reports that provide:
           * A summary of the changes.
           * Detailed comparisons of configuration data.
           * In-depth KPI analysis.
