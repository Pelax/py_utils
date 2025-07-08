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
                       log_errors: bool = True):
    filename = dest_path.name
    try:
        async with session.get(url, allow_redirects=True) as response:
            if response.status == 200:
                total_size = int(response.headers.get('content-length', 0))
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                progress_bar.reset(total=total_size)
                progress_bar.set_description(f"Downloading {filename[:20]}...")
                
                with open(dest_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                        progress_bar.update(len(chunk))
                
                return True
            else:
                error_msg = f"HTTP {response.status}"
                if log_errors:
                    log_failed_download(url, filename, error_msg)
                print(f"\nFailed to download {filename}: {error_msg}")
                return False
    except Exception as e:
        error_msg = str(e)
        if log_errors:
            log_failed_download(url, filename, error_msg)
        print(f"\nError downloading {filename}: {error_msg}")
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