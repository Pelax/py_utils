# Usage: python download_bundles.py <htm-file> <destination-folder>
import os
import re
import sys
import asyncio
import aiohttp
import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path
from typing import List, Dict, Tuple
import argparse
from tqdm import tqdm

def log_failed_download(url: str, filename: str, error: str, log_file: Path = Path("failed_downloads.log")):
    """Log failed download attempts to a file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] Failed: {filename}\n")
        f.write(f"  URL: {url}\n")
        f.write(f"  Error: {error}\n\n")

async def download_file(session: aiohttp.ClientSession, 
                       url: str, 
                       dest_path: Path,
                       progress_bar: tqdm,
                       log_errors: bool = True,
                       max_retries: int = 2) -> bool:
    """Download a file with retry logic.
    
    Args:
        session: aiohttp client session
        url: URL of the file to download
        dest_path: Local path to save the file
        progress_bar: tqdm progress bar instance
        log_errors: Whether to log errors to file
        max_retries: Maximum number of retry attempts
        
    Returns:
        bool: True if download was successful, False otherwise
    """
    filename = dest_path.name
    last_error = None
    
    for attempt in range(max_retries + 1):  # +1 for the initial attempt
        if attempt > 0:
            print(f"\nRetry {attempt}/{max_retries} for {filename}...")
            await asyncio.sleep(1 * attempt)  # Exponential backoff
            
        try:
            async with session.get(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=300)) as response:
                if response.status == 200:
                    total_size = int(response.headers.get('content-length', 0))
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Use a temporary file during download to prevent partial files
                    temp_path = dest_path.with_suffix(dest_path.suffix + '.tmp')
                    
                    progress_bar.reset(total=total_size)
                    progress_bar.set_description(f"Downloading {filename[:20]}...")
                    
                    try:
                        with open(temp_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                                progress_bar.update(len(chunk))
                        
                        # Only rename if download was successful
                        if temp_path.exists():
                            if dest_path.exists():
                                dest_path.unlink()  # Remove existing file if any
                            temp_path.rename(dest_path)
                            return True
                    except Exception as e:
                        # Clean up temp file if download failed
                        if temp_path.exists():
                            temp_path.unlink()
                        raise e
                else:
                    last_error = f"HTTP {response.status}"
        except Exception as e:
            last_error = str(e)
    
    # If we get here, all attempts failed
    if log_errors and last_error is not None:
        log_failed_download(url, filename, last_error)
    print(f"\nFailed to download {filename} after {max_retries + 1} attempts: {last_error}")
    # stop script execution, we want to have the files in the exact "date modified" order
    sys.exit(1)
    return False

async def download_all_files(urls: List[str], dest_folder: Path, max_concurrent: int = 2):
    semaphore = asyncio.Semaphore(max_concurrent)
    progress_bars: Dict[str, tqdm] = {}
    
    try:
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i, url in enumerate(urls, 1):
                filename = f"bundle_{i}.zip"
                dest_path = dest_folder / filename
                task = asyncio.create_task(
                    download_file(session, url, dest_path, semaphore, progress_bars)
                )
                tasks.append(task)
            
            # Wait for all downloads to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Print summary
            successful = sum(1 for r in results if r is True)
            print(f"\nDownload complete! {successful}/{len(urls)} files downloaded successfully.")
            return all(results)
    except Exception as e:
        print(f"\nAn error occurred during downloads: {str(e)}")
        return False

def extract_links_and_filenames(html_content: str) -> List[tuple[str, str]]:
    """Extract download links and their corresponding filenames from HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    pattern = re.compile(r'https://ovanisound\.com/apps/digital-downloads/download/[a-f0-9-]+\?from=Download%20Page')
    
    # Find all download items
    download_items = soup.find_all('div', class_='dda-order__item')
    results = []
    
    for item in download_items:
        download_assets = item.find_all('div', class_='dda-order__asset')
        for asset in download_assets:
            # Find the filename from the asset-filename div
            filename_div = asset.find('div', class_='dda-order__asset-filename')
            if not filename_div:
                continue
                
            # Clean up the filename (remove any extra whitespace or newlines)
            filename = filename_div.get_text(strip=True)
            
            # Find the download link
            link = asset.find('a', href=pattern)
            if link and filename:
                results.append((link['href'], filename))
    
    return results

async def download_all_files(downloads: List[tuple[str, str]], dest_folder: Path):
    progress_bar = tqdm(unit='B', unit_scale=True, unit_divisor=1024)
    failed_downloads = []
    
    try:
        async with aiohttp.ClientSession() as session:
            successful = 0
            total_files = len(downloads)
            
            for i, (url, filename) in enumerate(downloads, 1):
                dest_path = dest_folder / filename
                if dest_path.exists():
                    print(f"\n[{i}/{total_files}] Skipping {filename} - file already exists", flush=True)
                    successful += 1
                    continue
                
                print(f"\n[{i}/{total_files}] Starting download: {filename}")
                result = await download_file(session, url, dest_path, progress_bar)
                if result:
                    successful += 1
                else:
                    failed_downloads.append((url, filename))
            
            progress_bar.close()
            
            # Print summary
            print(f"\n{'='*50}")
            print(f"Download Complete!")
            print(f"Successfully downloaded: {successful}/{total_files}")
            print(f"Failed downloads: {len(failed_downloads)}")
            
            if failed_downloads:
                print("\nFailed downloads have been logged to 'failed_downloads.log'")
                print("You can retry these downloads using the log file.")
            
            print('='*50)
            
            return successful == total_files
    except Exception as e:
        print(f"\nAn error occurred during downloads: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Download OVANI sound bundles from HTML file')
    parser.add_argument('html_file', type=str, help='Path to the HTML file containing download links')
    parser.add_argument('dest_folder', type=str, help='Destination folder for downloaded files')
    args = parser.parse_args()

    try:
        with open(args.html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading HTML file: {e}")
        sys.exit(1)

    dest_folder = Path(args.dest_folder)
    dest_folder.mkdir(parents=True, exist_ok=True)

    downloads = extract_links_and_filenames(html_content)
    if not downloads:
        print("No valid download links found in the HTML file.")
        sys.exit(1)

    print(f"Found {len(downloads)} download links. Starting downloads...")
    try:
        asyncio.run(download_all_files(downloads, dest_folder))
    except KeyboardInterrupt:
        print("\nDownload cancelled by user.")
        sys.exit(1)

if __name__ == "__main__":
    main()