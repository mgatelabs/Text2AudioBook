import argparse
import json
import os
import re
import sys
import wave

import pyttsx3
import requests
from mutagen.id3 import ID3, TDRC, TIT2, TPE1, TALB, APIC, TCON
from mutagen.mp3 import MP3
from unidecode import unidecode
import time

class GeneratorInterface:
    def process(self, text, output_file):
        """Extract text from the currently loaded file."""
        pass


class PyttsxGenerator(GeneratorInterface):
    def __init__(self):
        self.engine = pyttsx3.init()

    def process(self, text, output_file):
        self.engine.save_to_file(text, output_file)
        self.engine.runAndWait()


class PiperTtsGenerator(GeneratorInterface):
    def __init__(self, server_url: str = "http://localhost:5000"):
        """
        :param server_url: Base URL of the Piper server (default: http://localhost:5000).
        """
        self.server_url = server_url

    def process(self, text, output_file):
        """
        Send text to a Piper-TTS web server and save audio to output_file.

        :param text: The text to synthesize.
        :param output_file: Path to the WAV file to save.
        """

        # print(f'Working on {output_file}')

        response = requests.post(
            self.server_url,
            json={"text": text},
            stream=True  # stream so we can write binary audio
        )
        response.raise_for_status()  # raises error if the request failed

        with open(output_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)


def get_wav_duration(file_path):
    with wave.open(file_path, 'r') as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        duration = frames / float(rate)
        return duration


def sanitize_filename(filename):
    """
    Remove any characters from the filename that are not:
    - Letters (a-z, A-Z)
    - Numbers (0-9)
    - Parentheses ()
    - Hyphens -
    - Spaces
    - Period
    """
    sanitized = re.sub(r'[^a-zA-Z0-9().\-\s]', '', filename)
    return sanitized


def format_title(title: str, index: int, force_chapters: bool = False) -> str:
    if force_chapters:
        return str(index).zfill(4) + " - " + title

    # Handle "Chapter X" pattern
    title = re.sub(
        r'(Chapter )(\d+)(\.\d+)?',
        lambda m: f"{m.group(1)}{int(m.group(2)):04}{m.group(3) if m.group(3) else ''}",
        title
    )
    # Handle standalone numbers at the start
    title = re.sub(
        r'^(\d+)(\.\d+)?',
        lambda m: f"{int(m.group(1)):04}{m.group(2) if m.group(2) else ''}",
        title
    )
    return title


def print_progress(current, total, bar_len=40):
    filled = int(bar_len * current / total)
    bar = "=" * filled + " " * (bar_len - filled)
    percent = 100 * current / total
    sys.stdout.write(f"\r[{bar}] {percent:6.2f}%")
    sys.stdout.flush()
    if current == total:  # end of loop
        print()


def handle_json_file(input_data, temp_folder: str, output_folder: str, generator: GeneratorInterface):
    # Verify
    if "info" not in input_data:
        raise FileNotFoundError(f"The specified input file does not have an info segment")

    if "title" not in input_data['info']:
        raise FileNotFoundError(f"The specified input file does not have an info.title value")

    book_title = unidecode(input_data['info']['title']).strip()

    if "author" not in input_data['info']:
        raise FileNotFoundError(f"The specified input file does not have an info.author value")

    book_author = unidecode(input_data['info']['author']).strip()

    if "year" not in input_data['info']:
        raise FileNotFoundError(f"The specified input file does not have an info.year value")

    book_year = unidecode(input_data['info']['year']).strip()

    if "icon" not in input_data['info']:
        raise FileNotFoundError(f"The specified input file does not have an info.icon value")

    book_icon = unidecode(input_data['info']['icon']).strip()

    if "chapters" not in input_data:
        raise FileNotFoundError(f"The specified input file does not have an chapters segment")

    file_number = 1
    skip_count = 0

    start_time = time.time()

    total_chapters = len(input_data['chapters'])

    for chapter in input_data['chapters']:
        try:
            audio_files = []
            # Skip duplicates, it can happen
            last_line = ''
            idx = 0

            # Try to merge smaller segments into larger ones, to limit the number of calls
            temp_lines = []
            temp_length = 0
            temp_values = None
            for line in chapter['lines']:
                if temp_values is None:
                    temp_values = [line]
                    temp_length = len(line)
                else:
                    temp_values.append(line)
                    temp_length += len(line)
                    if temp_length > 255:
                        temp_lines.append('  '.join(temp_values))
                        temp_length = 0
                        temp_values = None

            # Handle a dangling value
            if temp_values is not None:
                temp_lines.append('  '.join(temp_values))

            # Get the stats
            total_segments = len(temp_lines) + 1
            current_segment = 1

            chapter_name = format_title(chapter['title'], file_number, True)

            output_file = os.path.join(output_folder, sanitize_filename(chapter_name) + '.mp3')

            file_number = file_number + 1

            if os.path.exists(output_file):
                print(f'Skipping {chapter_name}')
                skip_count += 1
                continue
            else:

                print(f'Building Wav Files for {chapter_name}')

                for line in temp_lines:
                    line = unidecode(line).strip()
                    if line == last_line:
                        continue
                    last_line = line
                    filename = os.path.join(temp_folder, f"part_{idx:05}.wav")
                    idx = idx + 1

                    generator.process(line, filename)

                    # synthesize(line, filename)
                    print_progress(current_segment, total_segments)
                    audio_files.append({"file": filename, "text": line})

                    current_segment = current_segment + 1

            # Add durations to each audio file entry
            #for item in audio_files:
            #    # audio = MP3(item['file'])
            #    dur = get_wav_duration(item['file'])
            #    item['duration'] = dur  # Duration in seconds

            # Calculate cumulative timestamps
            #current_time = 0
            #for item in audio_files:
            #    item['start_time'] = int(current_time * 1000)  # Convert to ms
            #    current_time += item['duration']

            #print("Durations and timestamps calculated:")
            #for item in audio_files:
            #    print(f"{item['file']} starts at {item['start_time']}ms")

            # Create FFmpeg file list
            filelist = "file_list.txt"
            with open(filelist, 'w') as f:
                for item in audio_files:
                    f.write(f"file '{os.path.abspath(item['file'])}'\n")

            # Combine with FFmpeg
            os.system(
                f"ffmpeg -f concat -safe 0 -i \"{filelist}\" -c:a libmp3lame -ar 16000 -b:a 32k -ac 1 \"{output_file}\"")

            print(f"Audio files combined into {output_file}")

            # lyrics = []
            # for item in audio_files:
            #    minutes = (item['start_time'] // 60000) % 60
            #    seconds = (item['start_time'] // 1000) % 60
            #    milliseconds = item['start_time'] % 1000
            #    timestamp = f"[{minutes:02}:{seconds:02}.{milliseconds:03}]"
            #    lyrics.append(f"{timestamp} {item['text']}")

            # Save to lyrics file
            # with open("lyrics.txt", "w") as f:
            #    f.write("\n".join(lyrics))

            # print("Lyrics file generated with timestamps.")

            # Open the final audiobook
            audio = MP3(output_file, ID3=ID3)

            # Add SYLT tag
            # sylt = SYLT(
            #    encoding=Encoding.UTF8,
            #    lang='eng',
            #    format=2,  # Text with timestamps
            #    type=1,  # Lyrics/Text
            #    text=[]
            # )

            # quick_text = []

            # Add lyrics with timestamps
            # for item in audio_files:
            #    quick_text.append(item['text'])
            #    sylt.text.append((item['text'], item['start_time']))

            # audio.tags.add(sylt)

            # Add or update the USLT tag
            # uslt_tag = USLT(encoding=3, lang='eng', desc="Description", text='\n\n'.join(quick_text))
            # audio.tags.add(uslt_tag)

            # Set Title
            audio.tags["TIT2"] = TIT2(encoding=3, text=chapter_name)

            # Set Author (Artist)
            audio.tags["TPE1"] = TPE1(encoding=3, text=book_author)

            # Set Year
            audio.tags["TDRC"] = TDRC(encoding=3, text=book_year)

            # Set Album (Optional, you can use title again)
            audio.tags["TALB"] = TALB(encoding=3,
                                      text=book_title)

            # Set Genre as Audiobook
            audio.tags["TCON"] = TCON(encoding=3, text="Audiobook")

            # Add Cover Art
            if book_icon is not None and len(book_icon) > 0:
                with open(book_icon, "rb") as cover_art:
                    audio.tags["APIC"] = APIC(
                        encoding=3,  # UTF-8
                        mime="image/jpeg",  # MIME type of the cover art (use 'image/png' if PNG)
                        type=3,  # Front cover
                        desc="Cover",
                        data=cover_art.read()
                    )

            audio.save()

            elapsed = time.time() - start_time
            avg_time = elapsed / (file_number - skip_count)
            remaining = avg_time * (total_chapters - (file_number - 1))

            #print("Synchronized lyrics embedded into the audiobook.")

            print(f"Completed {(file_number - 1)}/{total_chapters} "
                  f"- Elapsed: {elapsed:.1f}s "
                  f"- Avg/iter: {avg_time:.2f}s "
                  f"- Est. remaining: {remaining:.1f}s")

        except Exception as e:
            print(f"Error {e}")
    pass


def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Process a JSON file and output results to a folder.")

    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help="The path to the JSON file to process."
    )

    parser.add_argument(
        '--temp',
        type=str,
        required=True,
        help="The folder to write temp file to."
    )

    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help="The folder to write the output to."
    )

    parser.add_argument(
        '--generator',
        choices=['pyttsx', 'pipertts'],
        default='pyttsx',
        help='Text-to-speech generator to use (default: pyttsx)'
    )

    # Parse arguments
    args = parser.parse_args()

    # Validate input file
    if not os.path.isfile(args.input):
        raise FileNotFoundError(f"The specified input file does not exist: {args.input}")

    # Validate output directory
    if not os.path.isdir(args.output):
        raise NotADirectoryError(f"The specified output path is not a directory: {args.output}")

    # Validate output directory
    if not os.path.isdir(args.temp):
        raise NotADirectoryError(f"The specified temp path is not a directory: {args.output}")

    # Example processing logic
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # print(f"Loaded JSON data: {data}")

    generator = None
    if args.generator == 'pipertts':
        generator = PiperTtsGenerator()
    else:
        generator = PyttsxGenerator()

    handle_json_file(data, args.temp, args.output, generator)


if __name__ == '__main__':
    main()

    # Example Call to produce the KJB, the sample file
    # python --input sample.json --temp c:\temp --output c:\output
