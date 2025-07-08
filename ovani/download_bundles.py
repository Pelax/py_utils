# Usage: python download_bundles.py <htm-file> <destination-folder>
import os
import re
import sys
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path
from typing import List, Dict
import argparse
from tqdm import tqdm

async def download_file(session: aiohttp.ClientSession, 
                       url: str, 
                       dest_path: Path,
                       progress_bar: tqdm):
    try:
        async with session.get(url, allow_redirects=True) as response:
            if response.status == 200:
                total_size = int(response.headers.get('content-length', 0))
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                progress_bar.reset(total=total_size)
                progress_bar.set_description(f"Downloading {dest_path.name[:20]}...")
                
                with open(dest_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                        progress_bar.update(len(chunk))
                
                return True
            else:
                print(f"\nFailed to download {url}: HTTP {response.status}")
                return False
    except Exception as e:
        print(f"\nError downloading {url}: {str(e)}")
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
    
    # Find all download containers
    download_items = soup.find_all('div', class_='dda-order__item')
    results = []
    
    for item in download_items:
        # Find the filename from the asset-filename div
        filename_div = item.find('div', class_='dda-order__asset-filename')
        if not filename_div:
            continue
            
        # Clean up the filename (remove any extra whitespace or newlines)
        filename = filename_div.get_text(strip=True)
        
        # Find the download link
        link = item.find('a', href=pattern)
        if link and filename:
            results.append((link['href'], filename))
    
    return results

async def download_all_files(downloads: List[tuple[str, str]], dest_folder: Path):
    progress_bar = tqdm(unit='B', unit_scale=True, unit_divisor=1024)
    
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
            
            progress_bar.close()
            print(f"\nDownload complete! {successful}/{total_files} files downloaded successfully.")
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