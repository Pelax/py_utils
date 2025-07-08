# Usage: python extract_bundle.py <path_to_folder_with_zip_files>

import glob, zipfile, sys, os, io, shutil, re


def extract_rt_value(filename):
    # This pattern looks for (RT followed by numbers and decimal points) inside parentheses
    match = re.search(r'\(RT\s+([\d.]+)\)', filename)
    if match:
        return match.group(1)  # Returns just the number part
    return ""

def extract_wavs(zip_file_path, extract_to_path):
    print("Extracting " + zip_file_path)
    with zipfile.ZipFile(zip_file_path, "r") as zip_file:
        file_list = zip_file.infolist()
        for file in file_list:
            file_name_lc = file.filename.lower()
            # print(file_name_lc)
            path_to_extract = ""
            if "main" in file_name_lc:
                path_to_extract = extract_to_path + "/Music"
            else:
                path_to_extract = extract_to_path + "/Sfx"
            if (".wav" in file_name_lc 
                and "__macosx" not in file_name_lc 
                and "cut 30" not in file_name_lc
                and "cut 60" not in file_name_lc
                and "intensity 1" not in file_name_lc
                and "intensity 2" not in file_name_lc
            ):
                file.filename = file.filename.replace(") /", ")/")
                print("will extract " + file.filename)
                rt_value = str(extract_rt_value(file.filename))
                zip_file.extract(file, path_to_extract)
                if "main" in file_name_lc:
                    file_path = os.path.join(path_to_extract, file.filename)
                    file_name = os.path.basename(file_path)
                    parent_dir = os.path.dirname(file_path)
                    target_dir = os.path.dirname(parent_dir)
                    target_path = os.path.join(target_dir, file_name)
                    # removing "main" from the name and deleting the extra directory
                    target_path = target_path.replace(" Main", "").replace(" main", "")
                    target_path = target_path.replace(".wav", "-RT " + rt_value + ".wav")
                    shutil.move(file_path, target_path)
                    os.rmdir(parent_dir)
            # else:
            #     print("will skip " + file.filename)

            if ".zip" in file_name_lc:
                with zip_file.open(file) as inner_zip_file:
                    inner_zip_data = io.BytesIO(inner_zip_file.read())
                    extract_wavs(inner_zip_data, extract_to_path)


if len(sys.argv) < 1:
    print("Usage: python extract_bundle.py <path_to_folder_with_zip_files>")
    exit(1)

folder_path = sys.argv[0]

if not os.path.exists(folder_path):
    print("Folder " + folder_path + " does not exist")
    exit(1)

# use folder path as extract path, since "Music" and "Sfx" subfolders will be created
extract_to_path = folder_path

zip_files_paths = glob.glob(f"{folder_path}/*.zip")
print("Found " + str(len(zip_files_paths)) + " zip files")

for zip_file_path in zip_files_paths:
    extract_wavs(zip_file_path, extract_to_path)
