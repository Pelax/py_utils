# Usage: python extract_bundle.py <path_to_folder_with_zip_files> [main_only]
# Adding 'main_only' parameter means different intensities and cuts files won't be extracted
# Examples:
# python extract_bundle.py "C:/Ovani Sound"
# python extract_bundle.py "C:/Ovani Sound" main_only

import glob, zipfile, sys, os, io

def extract_wavs(zip_file_path, extract_to_path):
    with zipfile.ZipFile(zip_file_path, "r") as zip_file:
        file_list = zip_file.infolist()
        for file in file_list:
            file_name = file.filename
            print(file_name)
            if file_name.find(".wav") > -1 and (
                not main_only
                or file_name.find("Main") > -1
                or file_name.find("Sound FX") > -1
                or file_name.find("SFX") > -1
            ):
                print("will extract " + file_name)
                zip_file.extract(file, extract_to_path)
            if file_name.find(".zip") > -1:
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

extract_to_path = folder_path + "/output"
os.makedirs(extract_to_path, exist_ok=True)

zip_files_paths = glob.glob(f"{folder_path}/*.zip")


for zip_file_path in zip_files_paths:
    extract_wavs(zip_file_path, extract_to_path)

