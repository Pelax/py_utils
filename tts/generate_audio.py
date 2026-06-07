import argparse
import asyncio
import edge_tts
from pathlib import Path
import re

USER_VOICE = "es-MX-JorgeNeural"  # Friend
AI_VOICE = "es-MX-DaliaNeural"    # AI

def clean_text_for_tts(text):
    """Removes invisible characters and fixes spacing."""
    text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def chunk_text(text, max_length=2500):
    """Splits long text into smaller chunks at sentence boundaries."""
    if len(text) <= max_length:
        return [text]
    
    sentences = re.split(r'(?<=[.!?¡¿])\s+', text)
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            current_chunk += " " + sentence if current_chunk else sentence
            
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

async def generate_audio(text_file: Path, output_file: Path):
    print("Reading and parsing text...")
    with open(text_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Step 1: Parse the file into blocks
    blocks = []
    current_speaker = None
    current_text = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line == "[USER]":
            if current_speaker and current_text:
                blocks.append((current_speaker, " ".join(current_text)))
            current_speaker = USER_VOICE
            current_text = []
        elif line == "[AI]":
            if current_speaker and current_text:
                blocks.append((current_speaker, " ".join(current_text)))
            current_speaker = AI_VOICE
            current_text = []
        else:
            current_text.append(line)
            
    if current_speaker and current_text:
        blocks.append((current_speaker, " ".join(current_text)))

    # Step 2: Pre-calculate all chunks to get an exact total for the progress bar
    print("Calculating total audio chunks...")
    tasks = []
    for speaker, text in blocks:
        text = clean_text_for_tts(text)
        if text:
            # Escape XML characters that break edge-tts
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            chunks = chunk_text(text, max_length=2500)
            for chunk in chunks:
                if chunk.strip():
                    tasks.append((speaker, chunk))

    total_tasks = len(tasks)
    print(f"Total chunks to generate: {total_tasks}\n")

    # Step 3: Generate audio with live progress tracking
    print("Generating audio. Please wait...")
    with open(output_file, 'wb') as out_f:
        for i, (voice, chunk) in enumerate(tasks):
            success = False
            retries = 2
            
            for attempt in range(retries):
                try:
                    communicate = edge_tts.Communicate(chunk, voice)
                    audio_received = False
                    
                    async for chunk_data in communicate.stream():
                        if chunk_data["type"] == "audio":
                            out_f.write(chunk_data["data"])
                            audio_received = True
                            
                    if audio_received:
                        success = True
                        break
                except Exception as e:
                    if attempt < retries - 1:
                        await asyncio.sleep(1.5)
                        
            if not success:
                print(f"\n  -> [SKIPPED] Failed chunk: '{chunk[:50]}...'")
            
            # Update Progress Bar
            progress = ((i + 1) / total_tasks) * 100
            bar_length = 30
            filled = int(bar_length * (i + 1) / total_tasks)
            bar = "=" * filled + "-" * (bar_length - filled)
            
            # \r returns the cursor to the start of the line to overwrite it
            print(f"\r[{bar}] {progress:.1f}% | Chunk {i+1}/{total_tasks} | {voice.split('-')[-1]}", end="", flush=True)

    print(f"\n\nSuccess! Audio saved as: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate TTS audio from a formatted chat text file.")
    parser.add_argument("text_file", type=Path, help="Path to the input .txt file")
    parser.add_argument("output_file", type=Path, help="Path to the output .mp3 file")
    args = parser.parse_args()
    asyncio.run(generate_audio(args.text_file, args.output_file))