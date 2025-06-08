#!/usr/bin/python
from datetime import datetime, timedelta
import enmscripting
import sys
import os


# current time minus 7 hours
dt = datetime.now() - timedelta(hours=12)

# format as ISO8601 without timezone info (the T is literal)
date_str = dt.strftime("%Y-%m-%dT%H:%M:%S")
##print(date_str)

def safe_find_value(row, label, default="N/A"):
    items = row.find_by_label(label)
    return items[0].value() if items else default

operation = sys.argv[1]
# Assume param2 is the third argument
if len(sys.argv) >= 3:
    param2 = sys.argv[2]

    # Option 1: it's a .txt file
    if param2.lower().endswith(".txt"):
        file_txt = param2
        command = 'cmedit import -f file:%s --filetype dynamic --error stop' % os.path.basename(file_txt)

    # Option 2: it's NOT a number (e.g., 'status')
    elif not param2.isdigit():
        command = 'cmedit import --status --begin %s' % date_str
    elif param2.isdigit():
        command = 'cmedit import --status --job %s --verbose' % param2
    # Option 3: it IS a number (job ID)
    else:
        print("UNKNOWN OPERATION, please check your COMMAND")
        exit()

elif len(sys.argv) == 2 and operation == "stat":
    command = 'cmedit import --status --begin %s' % date_str
        
else:
    print("UNKNOWN OPERATION, please check your COMMAND")
    exit()    

session = enmscripting.open()
terminal = session.terminal()
cmd = session.command()


##command2 = 'cmedit import --status  --begin'
##command2 = 'cmedit import --status  --begin %s' % ( date_str )

if operation == "upload" and os.path.isfile(file_txt) and file_txt.lower().endswith(".txt"):
    with open(file_txt, 'rb') as fileUpload:
      result = terminal.execute(command, fileUpload)
      if result.is_command_result_available():
        for line in result.get_output():
          print(line)
      else:
        print('\nFailure for ' + command + '\n')

elif operation == "stat" and ('param2' not in locals() or not param2.isdigit()):
    result = cmd.execute(command).get_output()
    all_rows = []

    for element in result:
        if type(element) is enmscripting.ElementGroup:
            for table in result.groups():
                for row in table:
                    ##elapsed_time_items = row.find_by_label('Managed objects created') + "/" + row.find_by_label('Managed objects deleted')


                    created = safe_find_value(row, 'Managed objects created')
                    update = safe_find_value(row, 'Managed objects updated')
                    deleted = safe_find_value(row, 'Managed objects deleted')
                    ACTION = safe_find_value(row, 'Actions performed')

                    CHECK_MO_items = created + "/" + update  + "/" + deleted  + "/" + ACTION                    
                    CHECK_MO_value = CHECK_MO_items if CHECK_MO_items else "N/A"
                                        
                    datas = [
                        row.find_by_label('Job ID')[0].value(),
                        row.find_by_label('Status')[0].value(),
                        row.find_by_label('Start date/time')[0].value(),
                        row.find_by_label('End date/time')[0].value(),
                        row.find_by_label('File Name')[0].value(),
                        CHECK_MO_value
                    ]
                    all_rows.append(datas)

    # Add header for the new column
    headers = ["Job ID", "Status", "Start date/time", "End date/time", "File", "MO created/UPD/DEL/ACT"]
    all_rows.insert(0, headers)

    # Calculate max width for each column (6 columns now)
    col_widths = [max(len(str(row[i])) for row in all_rows) + 6 for i in range(6)]

    # Create format string dynamically for 6 columns
    fmt_str = " ".join(["%-{}s".format(width) for width in col_widths])

    # Print all rows using the format string
    for row in all_rows:
        print(fmt_str % tuple(row))

elif operation == "stat" and param2.isdigit():
    result7 = cmd.execute(command).get_output()
    first_row = True  # Flag to control header printing

    for table in result7.groups():
        for row in table:
            import_status_value = row.find_by_label('Import status message')[0].value() if row.find_by_label('Import status message') else None
            operation_type_value = row.find_by_label('Operation Type')[0].value() if row.find_by_label('Operation Type') else None
            update_time_value = row.find_by_label('Update Time')[0].value() if row.find_by_label('Update Time') else None
            fdn_value = row.find_by_label('FDN')[0].value() if row.find_by_label('FDN') else None
            failure_reason_value = row.find_by_label('Failure Reason')[0].value() if row.find_by_label('Failure Reason') else None
            line_number_value = row.find_by_label('Line Number')[0].value() if row.find_by_label('Line Number') else None

            # Skip this row if FDN is missing or empty
            if not fdn_value:
                continue

            # Print header once before any valid data row
            if first_row:
                header = [
                    "Import status message",
                    "Operation Type",
                    "Update Time",
                    "FDN",
                    "Failure Reason",
                    "Line Number"
                ]
                print(";".join(header))
                first_row = False

            datas = [import_status_value, operation_type_value, update_time_value, fdn_value, failure_reason_value, line_number_value]


            print(";".join(str(item) if item is not None else "" for item in datas))





else:
    if os.path.isfile(file_txt) == False:
        print("your CMBULK FILE not exist")
    else:
        print("UNKNOWN OPERATION, please check your COMMAND")






enmscripting.close(session)



