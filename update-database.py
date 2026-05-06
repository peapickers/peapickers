#!/usr/bin/env python3
"""
update-database.py
Reads all JPG files in publicdomain/thumbnails/, extracts metadata via ExifTool,
and writes an incremental images.json database.
Incremental: only processes new/changed files based on modification time.
All keys are in English, matching the front‑end.
"""

import json, subprocess, os, sys, re, unicodedata
from pathlib import Path

DB_FILE   = Path('images.json')
THUMB_DIR = Path('publicdomain/thumbnails')       # ← CORRECT PATH

def normalize_filename(name):
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r'[^a-zA-Z0-9]', '-', name)
    name = re.sub(r'-+', '-', name)
    return name.strip('-').lower()

def extract_year(filename):
    years = re.findall(r'\b(1[6-9]\d{2}|20[0-2]\d)\b', filename)
    if years:
        return years[-1]
    circa = re.findall(r'c\.?\s*(\d{4})', filename, re.IGNORECASE)
    if circa:
        return 'c. ' + circa[0]
    decade = re.findall(r'\b(1[6-9]\d0)s\b', filename)
    if decade:
        return decade[0] + 's'
    return ''

def extract_title(filename):
    name = filename.replace('.jpg', '').replace('.JPG', '')
    name = re.sub(r'\s*[-–]\s*(?:printed\s+)?c?\.?\s*\d{4}(?:[-–]\d{2,4})?(?:s)?\s*(?:[-–]\d+)?\s*$', '', name)
    name = re.sub(r'\s*[-–]?\s*Edit\s*$', '', name, flags=re.IGNORECASE)
    return name.strip(' -–')

def clean_credit(credit):
    if not credit:
        return ''
    return re.sub(r'\s*\(Source\)\s*$', '', credit).strip().lstrip('\n')

def run_exiftool(files):
    cmd = [
        'exiftool', '-json', '-charset', 'UTF8',
        '-FileName', '-FileModifyDate',
        '-Creator', '-By-line',
        '-Credit', '-Source',
        '-CopyrightNotice', '-Rights',
        '-Caption-Abstract',
        '-XMP:Description',
        '-Description',
        '-ImageDescription',
        '-Keywords', '-Subject',
        '-DateCreated', '-CreateDate',
        '-Title', '-ObjectName',
    ] + [str(f) for f in files]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0 and not result.stdout:
        print(f"ExifTool error: {result.stderr}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

def pick(*values):
    for v in values:
        if v and str(v).strip():
            return str(v).strip()
    return ''

def process_exif(exif):
    filename = exif.get('FileName', '')
    stem = Path(filename).stem

    title = pick(
        exif.get('Title'), exif.get('ObjectName'),
        extract_title(filename)
    )

    maker = pick(
        exif.get('Creator'), exif.get('By-line')
    ) or 'Unknown'

    credit_line = clean_credit(exif.get('Credit') or '')
    source_val  = clean_credit(exif.get('Source') or '')

    copyright_val = pick(
        exif.get('CopyrightNotice'), exif.get('Rights'),
        'Public Domain'
    )

    description = pick(
        exif.get('Caption-Abstract'),
        exif.get('XMP:Description'),
        exif.get('Description'),
        exif.get('ImageDescription'),
    )

    keywords_raw = exif.get('Keywords') or exif.get('Subject') or []
    if isinstance(keywords_raw, str):
        keywords = [k.strip() for k in keywords_raw.split(',') if k.strip()]
    elif isinstance(keywords_raw, list):
        keywords = [str(k).strip() for k in keywords_raw if str(k).strip()]
    else:
        keywords = []

    year = pick(exif.get('DateCreated'), exif.get('CreateDate')) or extract_year(filename)
    year_match = re.search(r'\b(1[6-9]\d{2}|20[0-2]\d)\b', str(year))
    if year_match:
        year = year_match.group(1)

    return {
        "filename":       filename,
        "title":          title,
        "year":           year,
        "maker":          maker,
        "credit":         credit_line,
        "source":         source_val,
        "description":    description,
        "copyright":      copyright_val,
        "keywords":       keywords,
        "file":           normalize_filename(stem),
        "_mtime":         exif.get('FileModifyDate', '')
    }

def main():
    if not THUMB_DIR.exists():
        print(f"Error: '{THUMB_DIR}' folder not found. Run this script from your project root.")
        sys.exit(1)

    existing = {}
    if DB_FILE.exists():
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for entry in data:
                existing[entry.get('filename', '')] = entry
            print(f"Loaded existing database: {len(existing)} entries")
        except Exception as e:
            print(f"Could not read existing database, rebuilding. ({e})")

    jpg_files = list(THUMB_DIR.glob('*.jpg')) + list(THUMB_DIR.glob('*.JPG'))
    print(f"Found {len(jpg_files)} JPG files in publicdomain/thumbnails/")

    to_process = []
    current_filenames = set()
    for jpg in jpg_files:
        fname = jpg.name
        current_filenames.add(fname)
        mtime = str(jpg.stat().st_mtime)
        if fname not in existing:
            to_process.append(jpg)
        else:
            stored_mtime = existing[fname].get('_mtime_raw', '')
            if stored_mtime != mtime:
                to_process.append(jpg)

    deleted = set(existing.keys()) - current_filenames
    if deleted:
        print(f"Removing {len(deleted)} deleted files from database")
        for d in deleted:
            del existing[d]

    print(f"Processing {len(to_process)} new/changed files...")

    batch_size = 50
    for i in range(0, len(to_process), batch_size):
        batch = to_process[i:i+batch_size]
        exif_data = run_exiftool(batch)
        for exif in exif_data:
            entry = process_exif(exif)
            fname = exif.get('FileName', '')
            jpg_path = THUMB_DIR / fname
            if jpg_path.exists():
                entry['_mtime_raw'] = str(jpg_path.stat().st_mtime)
            existing[fname] = entry
        print(f"  Processed {min(i+batch_size, len(to_process))}/{len(to_process)}")

    def sort_key(e):
        year_str = re.sub(r'[^0-9]', '', str(e.get('year', '0'))) or '0'
        return (year_str, e.get('title', ''))

    final = sorted(existing.values(), key=sort_key)

    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"\nDone. Database written: {len(final)} entries → {DB_FILE}")

    makers = {}
    for e in final:
        m = e.get('maker', 'Unknown')
        makers[m] = makers.get(m, 0) + 1
    print("\nMakers in database:")
    for maker, count in sorted(makers.items(), key=lambda x: -x[1])[:10]:
        print(f"  {count:3d}  {maker}")

if __name__ == '__main__':
    main()