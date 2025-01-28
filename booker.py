import argparse
import json
import os
import re
import wave

import pyttsx3
from mutagen.id3 import ID3, SYLT, Encoding, USLT, TDRC, TIT2, TPE1, TALB, APIC, TCON
from mutagen.mp3 import MP3
from unidecode import unidecode

engine = pyttsx3.init()


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
        return str(index).zfill(3) + " - " + title

    # Handle "Chapter X" pattern
    title = re.sub(
        r'(Chapter )(\d+)(\.\d+)?',
        lambda m: f"{m.group(1)}{int(m.group(2)):03}{m.group(3) if m.group(3) else ''}",
        title
    )
    # Handle standalone numbers at the start
    title = re.sub(
        r'^(\d+)(\.\d+)?',
        lambda m: f"{int(m.group(1)):03}{m.group(2) if m.group(2) else ''}",
        title
    )
    return title


def handle_json_file(input_data, temp_folder: str, output_folder: str):
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

    for chapter in input_data['chapters']:
        try:
            audio_files = []
            # Skip duplicates, it can happen
            last_line = ''
            idx = 0
            for line in chapter['lines']:
                line = unidecode(line).strip()
                if line == last_line:
                    continue
                last_line = line
                filename = os.path.join(temp_folder, f"part_{idx:05}.wav")
                idx = idx + 1
                engine.save_to_file(line, filename)
                audio_files.append({"file": filename, "text": line})
                engine.runAndWait()

            chapter_name = format_title(chapter['title'], file_number, True)

            output_file = os.path.join(output_folder, sanitize_filename(chapter_name) + '.mp3')

            if os.path.exists(output_file):
                print(f'Skipping {chapter_name}')
            else:

                # Add durations to each audio file entry
                for item in audio_files:
                    # audio = MP3(item['file'])
                    dur = get_wav_duration(item['file'])
                    item['duration'] = dur  # Duration in seconds

                # Calculate cumulative timestamps
                current_time = 0
                for item in audio_files:
                    item['start_time'] = int(current_time * 1000)  # Convert to ms
                    current_time += item['duration']

                print("Durations and timestamps calculated:")
                for item in audio_files:
                    print(f"{item['file']} starts at {item['start_time']}ms")

                # Create FFmpeg file list
                filelist = "file_list.txt"
                with open(filelist, 'w') as f:
                    for item in audio_files:
                        f.write(f"file '{os.path.abspath(item['file'])}'\n")

                # Combine with FFmpeg
                os.system(f"ffmpeg -f concat -safe 0 -i \"{filelist}\" -c:a libmp3lame -b:a 128k -ac 1 \"{output_file}\"")

                print(f"Audio files combined into {output_file}")

                lyrics = []
                for item in audio_files:
                    minutes = (item['start_time'] // 60000) % 60
                    seconds = (item['start_time'] // 1000) % 60
                    milliseconds = item['start_time'] % 1000
                    timestamp = f"[{minutes:02}:{seconds:02}.{milliseconds:03}]"
                    lyrics.append(f"{timestamp} {item['text']}")

                # Save to lyrics file
                with open("lyrics.txt", "w") as f:
                    f.write("\n".join(lyrics))

                print("Lyrics file generated with timestamps.")

                # Open the final audiobook
                audio = MP3(output_file, ID3=ID3)

                # Add SYLT tag
                sylt = SYLT(
                    encoding=Encoding.UTF8,
                    lang='eng',
                    format=2,  # Text with timestamps
                    type=1,  # Lyrics/Text
                    text=[]
                )

                quick_text = []

                # Add lyrics with timestamps
                for item in audio_files:
                    quick_text.append(item['text'])
                    sylt.text.append((item['text'], item['start_time']))

                audio.tags.add(sylt)

                # Add or update the USLT tag
                uslt_tag = USLT(encoding=3, lang='eng', desc="Description", text='\n\n'.join(quick_text))
                audio.tags.add(uslt_tag)

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

                print("Synchronized lyrics embedded into the audiobook.")

        except Exception as e:
            print(f"Error {e}")

        file_number = file_number + 1
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
    with open(args.input, 'r') as f:
        data = json.load(f)
        print(f"Loaded JSON data: {data}")

    handle_json_file(data, args.temp, args.output)


if __name__ == '__main__':
    main()

    # Example Call to produce the KJB, the sample file
    # python --input sample.json --temp c:\temp --output c:\output