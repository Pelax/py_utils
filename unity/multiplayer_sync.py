# This script synchronizes 2 git repository folders (same repo and rev) to ensure the content from work_folder
# is propagated to copy_folder. But just in case, it also confirms that the content in copy_folder is older.
# The intention is to test multi-player changes in 2 Unity instances.
# This currently doesn't support new folders added.
# Adding  'f' at the end skips confirmation

# Usage: python multiplayer_sync.py <work_folder> <copy_folder> [f]

import os
import subprocess
import shutil
import sys
from tkinter import filedialog

if len(sys.argv) < 3:
    print("Usage: python multiplayer_sync.py <work_folder> <copy_folder>")
    sys.exit(1)

work_folder = sys.argv[1]
copy_folder = sys.argv[2]
ask_confirmation = True
if len(sys.argv) > 3:
    ask_confirmation = sys.argv[3] != "f"

if ask_confirmation:
    choice_str = input(
        "Will copy content from  "
        + work_folder
        + " to "
        + copy_folder
        + ", continue? [y/n]"
    )
    if choice_str != "y":
        print("Aborting...")
        exit()

ADDED = "added"
MODIFIED = "modified"
DELETED = "deleted"

def populate_dict(folder_to_check):
    process = subprocess.Popen(
        ["git", "status"], stdout=subprocess.PIPE, cwd=folder_to_check
    )
    output = str(process.communicate()[0])
    output_array = output.split("\\n")
    dict_a = {}
    for line in output_array:
        # print(line)
        if line.startswith("\\t") and not line.endswith("/"):

            file_to_sync = line[2:]
            # print("need to sync: " + file_to_sync)
            action = file_to_sync[0 : file_to_sync.find(":")]
            file_relative_path = file_to_sync[file_to_sync.rfind(": ") + 1 :].strip()
            if file_to_sync == file_relative_path:
                action = ADDED
            # print("adding key" + file_to_sync)
            dict_a[file_relative_path] = action
    return dict_a


def compare_dates(key, action_a, action_b, path_a, path_b):
    if action_a == action_b:  # files' action are the same
        if action_a == MODIFIED or action_a == ADDED:  # deleted action is not a problem
            if os.path.getmtime(path_a) < os.path.getmtime(path_b):
                # file in path_b is more recent, check size and inform if it's different
                # (if they're are the same is most likely the same file and we can skip silently)
                if os.path.getsize(path_a) != os.path.getsize(path_b):
                    print(
                        "WARNING: the file '"
                        + key
                        + "' in copy_folder seems to be newer, and it's different from the one in work_folder"
                    )
                return False
    elif action_a == DELETED and action_b == MODIFIED:
        print(
            "You modified a file and now you are trying to delete it, please reset copy_folder first!"
        )
        return False
    # good to go
    return True


dict_a = populate_dict(work_folder)
dict_b = populate_dict(copy_folder)
files_copied = []

for key in dict_a:
    path_a = os.path.join(work_folder, key)
    path_b = os.path.join(copy_folder, key)
    # print("key and paths: " + key + " " + path_a + " " + path_b)
    action_a = dict_a[key]
    # print("path_a to take action with: " + path_a)
    if key not in dict_b or compare_dates(key, action_a, dict_b[key], path_a, path_b):
        if action_a == DELETED:
            try:
                os.remove(path_b)
            except OSError:
                pass
        else:
            files_copied.append(key)
            shutil.copyfile(path_a, path_b)

if len(files_copied) > 0:
    print("Files copied:")
    for file_name in files_copied:
        print(file_name)
else:
    print("No files copied.")


print("Done!")
exit(0)
