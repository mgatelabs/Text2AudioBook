# Text 2 Audiobook

Sinple project to convert JSON to Audiobook compatiable files.

# Requirements

- Python 3
- FFMPEG (Must be available on the path)

# Installation

## To install the require python libraries

```bash
pip install -r requirements.txt
```

## FFMPEG

You need to download a copy of [https://www.ffmpeg.org/download.html](FFMPEG) and place ffmpeg.exe in the same folder as booker.py.

# Example Usage

The app comes with a sample book, the KJB that you can convert into a series of MP3 files.

Here is an example windows command to convert the sample.json file into an audio book.  Each conversion needs three things:
1. JSON file to convert
2. TEMP folder, must already exist, for the app to create wav files
3. OUTPUT folder, must already exist, where to save the book to

```bash
mkdir temp
mkdir kjb
python booker.py --input sample.json --temp ".\temp" --output ".\kjb"
```

Executing this will create the following files:
- ./kjb/001 - Genesis 1.mp3
- ./kjb/002 - Genesis 2.mp3
- ./kjb/003 - Genesis 3.mp3
- ./kjb/004 ...

# JSON Format

```json
{
  "info": {
    "title": "Your book title",
    "author": "THe book author",
    "year": "Publish year",
    "icon": "PATH_TO_JPG_OR_BLANK"
  },
  "chapters": [
        {
            "title": "Chapter Title",
            "lines": [
                "This is a line",
                "This is another line"
            ]
       }
 ]
}
```

