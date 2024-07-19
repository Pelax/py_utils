# Usage: python extract_bundle.py <path_to_folder_with_zip_files> [main_only]
# Adding 'main_only' parameter means different intensities and cuts files won't be extracted
# Examples:
# python extract_bundle.py "C:/Ovani Sound"
# python extract_bundle.py "C:/Ovani Sound" main_only

import glob, zipfile, sys, os, io, shutil


def extract_wavs(zip_file_path, extract_to_path):
    with zipfile.ZipFile(zip_file_path, "r") as zip_file:
        file_list = zip_file.infolist()
        for file in file_list:
            file_name_lc = file.filename.lower()
            # print(file_name_lc)
            if ".wav" in file_name_lc and "__macosx" not in file_name_lc and (
                not main_only
                or "main" in file_name_lc
                or "sound fx" in file_name_lc
                or "sfx" in file_name_lc
            ):
                file.filename = file.filename.replace(") /", ")/")
                print("will extract " + file.filename)
                zip_file.extract(file, extract_to_path)
                if main_only and "main" in file_name_lc:
                    file_path = os.path.join(extract_to_path, file.filename)
                    file_name = os.path.basename(file_path)
                    parent_dir = os.path.dirname(file_path)
                    target_dir = os.path.dirname(parent_dir)
                    target_path = os.path.join(target_dir, file_name)
                    # removing "main" from the name and deleting the extra directory
                    target_path = target_path.replace(" Main", "").replace(" main", "")
                    shutil.move(file_path, target_path)
                    os.rmdir(parent_dir)

            if ".zip" in file_name_lc:
                with zip_file.open(file) as inner_zip_file:
                    inner_zip_data = io.BytesIO(inner_zip_file.read())
                    extract_wavs(inner_zip_data, extract_to_path)


if len(sys.argv) < 2:
    print("Usage: python extract_bundle.py <path_to_folder_with_zip_files> [main_only]")
    exit(1)

main_only = False
if len(sys.argv) > 2:
    if sys.argv[2] == "main_only":
        main_only = True

folder_path = sys.argv[1]

if not os.path.exists(folder_path):
    print("Folder " + folder_path + " does not exist")
    exit(1)

extract_to_path = os.path.join(folder_path, "output")
os.makedirs(extract_to_path, exist_ok=True)

zip_files_paths = glob.glob(f"{folder_path}/*.zip")


for zip_file_path in zip_files_paths:
    extract_wavs(zip_file_path, extract_to_path)
