#!/usr/bin/env python3
# Usage: python extract_bundle.py <path_to_folder_with_zip_files>

import glob
import zipfile
import sys
import os
import io
import shutil
import re
import logging
from datetime import datetime
from typing import Optional, BinaryIO, List, Tuple

# Configure logging with a null handler by default
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extraction_errors.log')
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

def setup_logging():
    """Configure logging to file and console, but only if not already set up."""
    if not logger.handlers:  # Only add handlers if they haven't been added yet
        # Clear any existing handlers
        logger.handlers.clear()
        
        # Set up file handler
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.ERROR)
        
        # Set up console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.ERROR)
        
        # Create formatter and add it to the handlers
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers to the logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.setLevel(logging.ERROR)


def extract_rt_value(filename):
    # This pattern looks for (RT followed by numbers and decimal points) inside parentheses
    match = re.search(r'\(RT\s+([\d.]+)\)', filename)
    if match:
        return match.group(1)  # Returns just the number part
    return ""

def is_zip_valid(zip_path: str) -> bool:
    """Check if a ZIP file is valid and can be opened."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Test the ZIP integrity
            return zf.testzip() is None
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as e:
        error_msg = f"Corrupted or invalid ZIP file: {zip_path} - {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False

def process_zip_member(zip_file: zipfile.ZipFile, file: zipfile.ZipInfo, extract_to_path: str) -> None:
    """Process a single file within a ZIP archive."""
    try:
        file_name_lc = file.filename.lower()
        
        # Skip unwanted files
        if any(x in file_name_lc for x in ["__macosx", "cut 30", "cut 60", "intensity 1", "intensity 2"]):
            return
            
        # Determine extraction path
        path_to_extract = os.path.join(extract_to_path, "Music" if "main" in file_name_lc else "Sfx")
        os.makedirs(path_to_extract, exist_ok=True)
        
        # Process WAV files
        if file_name_lc.endswith('.wav'):
            file.filename = file.filename.replace(") /", ")/")
            print(f"Extracting {file.filename}")
            
            try:
                zip_file.extract(file, path_to_extract)
                
                if "main" in file_name_lc:
                    file_path = os.path.join(path_to_extract, file.filename)
                    if os.path.exists(file_path):  # Ensure file was extracted
                        rt_value = str(extract_rt_value(file.filename))
                        file_name = os.path.basename(file_path)
                        parent_dir = os.path.dirname(file_path)
                        target_dir = os.path.dirname(parent_dir)
                        
                        # Create new filename with RT value
                        new_filename = file_name.replace(" Main", "").replace(" main", "")
                        new_filename = new_filename.replace(".wav", f"-RT {rt_value}.wav")
                        target_path = os.path.join(target_dir, new_filename)
                        
                        shutil.move(file_path, target_path)
                        try:
                            os.rmdir(parent_dir)
                        except OSError:
                            pass  # Directory not empty, leave it
            except Exception as e:
                logger.error(f"Error processing {file.filename}: {str(e)}", exc_info=True)
        
        # Handle nested ZIP files
        elif file_name_lc.endswith('.zip'):
            try:
                with zip_file.open(file) as inner_zip_file:
                    inner_zip_data = io.BytesIO(inner_zip_file.read())
                    extract_wavs(inner_zip_data, extract_to_path)
            except Exception as e:
                logger.error(f"Error processing nested ZIP {file.filename}: {str(e)}", exc_info=True)
                
    except Exception as e:
        logger.error(f"Unexpected error processing {file.filename if 'file' in locals() else 'unknown file'}: {str(e)}", exc_info=True)

def extract_wavs(zip_file_path, extract_to_path) -> Tuple[bool, str]:
    """Extract WAV files from a ZIP archive, handling nested ZIPs."""
    try:
        if isinstance(zip_file_path, (str, os.PathLike)):
            if not os.path.exists(zip_file_path):
                error_msg = f"File not found: {zip_file_path}"
                logger.error(error_msg)
                return False, error_msg
                
            if not is_zip_valid(zip_file_path):
                return False
                
            with zipfile.ZipFile(zip_file_path, 'r') as zip_file:
                success, error_msg = _process_zip_file(zip_file, extract_to_path)
                return success, error_msg
                
        elif isinstance(zip_file_path, (io.BytesIO, io.BufferedReader)):
            try:
                with zipfile.ZipFile(zip_file_path, 'r') as zip_file:
                    return _process_zip_file(zip_file, extract_to_path)
            except zipfile.BadZipFile as e:
                error_msg = f"Corrupted ZIP data in {zip_file_path if isinstance(zip_file_path, str) else 'stream'}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return False, error_msg
                
    except Exception as e:
        error_msg = f"Error processing {zip_file_path if isinstance(zip_file_path, str) else 'ZIP data'}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg
    
    return True

def _process_zip_file(zip_file: zipfile.ZipFile, extract_to_path: str) -> Tuple[bool, str]:
    """Process a ZIP file that has already been opened."""
    try:
        file_list = zip_file.infolist()
        for file in file_list:
            process_zip_member(zip_file, file, extract_to_path)
        return True, "Success"
    except Exception as e:
        error_msg = f"Error processing ZIP file: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_bundle.py <path_to_folder_with_zip_files>")
        return 1

    folder_path = sys.argv[1]
    # Uncomment for testing
    # folder_path = r"C:\Projects\art\Ovani\Music\TEST"

    if not os.path.exists(folder_path):
        print(f"Error: Folder does not exist: {folder_path}")
        return 1

    if not os.path.isdir(folder_path):
        print(f"Error: Not a directory: {folder_path}")
        return 1

    # Use folder path as extract path, since "Music" and "Sfx" subfolders will be created
    extract_to_path = os.path.abspath(folder_path)
    print(f"Processing ZIP files in: {extract_to_path}")

    # Create output directories if they don't exist
    for subdir in ["Music", "Sfx"]:
        os.makedirs(os.path.join(extract_to_path, subdir), exist_ok=True)

    # Find all ZIP files in the directory
    zip_files_paths = glob.glob(os.path.join(folder_path, "*.zip"))
    
    if not zip_files_paths:
        print("No ZIP files found in the specified directory.")
        return 0

    print(f"Found {len(zip_files_paths)} ZIP files to process")

    success_count = 0
    failed_files = []
    
    for zip_file_path in zip_files_paths:
        print(f"\nProcessing: {os.path.basename(zip_file_path)}")
        success, error_msg = extract_wavs(zip_file_path, extract_to_path)
        if success:
            success_count += 1
        else:
            # Set up logging only when we encounter the first error
            if not failed_files:
                setup_logging()
            failed_files.append((os.path.basename(zip_file_path), error_msg))

    # Log summary
    total_files = len(zip_files_paths)
    success_rate = (success_count / total_files) * 100 if total_files > 0 else 0
    
    summary_msg = f"\nProcessing complete. Successfully processed {success_count} of {total_files} files ({success_rate:.1f}%)."
    print(summary_msg)
    
    # Log failed files if any
    if failed_files:
        print("\nFailed files:")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write("\n" + "="*50 + "\n")
            f.write(f"Extraction Summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*50 + "\n")
            f.write(summary_msg + "\n\n")
            f.write("Failed files:\n")
            
            for idx, (filename, error) in enumerate(failed_files, 1):
                error_line = f"{idx}. {filename}: {error}\n"
                print(f"  {idx}. {filename}")
                f.write(error_line)
            
            f.write("\nEnd of report\n" + "="*50 + "\n")
        
        print(f"\nDetailed error log has been saved to: {log_file}")
    
    return 0 if success_count == total_files else 1

if __name__ == "__main__":
    main()
