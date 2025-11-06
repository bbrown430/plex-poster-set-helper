#!/usr/bin/env python3
"""
Script to generate a bulk_import.txt file for ThePosterDB poster sets.
Searches for poster sets from specific creators that match your Plex shows.
"""

import os
import re
import requests
from bs4 import BeautifulSoup
import time
from urllib.parse import urljoin

# Configuration
SHOWS_DIR = "/Volumes/Multimedia/Shows"
CREATORS = ["fwlolx", "Sevi", "GrandSlam4Par"]
OUTPUT_FILE = "bulk_import.txt"
DELAY_BETWEEN_REQUESTS = 1.5  # Be nice to the server

# Headers to avoid being blocked
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Cache-Control': 'max-age=0'
}

def extract_show_name(folder_name):
    """
    Extract the show name from folder format: "Show Name (Year) {imdb-ttXXXXXXX}"
    Returns the show name and year.
    """
    # Match pattern: "Show Name (Year) {imdb-ttXXXXXXX}"
    match = re.match(r'(.+?)\s*\((\d{4})\)\s*\{imdb-', folder_name)
    if match:
        return match.group(1).strip(), match.group(2)

    # Fallback: just try to get name before year in parentheses
    match = re.match(r'(.+?)\s*\((\d{4})\)', folder_name)
    if match:
        return match.group(1).strip(), match.group(2)

    # Last resort: return the whole folder name
    return folder_name, None

def get_user_shows(username, max_pages=50):
    """
    Scrape a ThePosterDB user's uploads to find TV show poster sets.
    Returns a dict: {show_name: [set_urls]}
    """
    print(f"\nSearching {username}'s uploads...")
    base_url = f"https://theposterdb.com/user/{username}"

    # First, get the total number of pages
    try:
        response = requests.get(base_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find upload count
        span_tag = soup.find('span', class_='numCount')
        if span_tag:
            upload_count = int(span_tag['data-count'])
            pages = min(max_pages, (upload_count + 23) // 24)  # 24 items per page
        else:
            pages = 1
    except Exception as e:
        print(f"  Warning: Could not determine page count for {username}: {e}")
        pages = 1

    show_sets = {}

    for page in range(1, pages + 1):
        print(f"  Scanning page {page}/{pages}...")
        page_url = f"{base_url}?section=uploads&page={page}"

        try:
            time.sleep(DELAY_BETWEEN_REQUESTS)
            response = requests.get(page_url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find the poster grid
            poster_div = soup.find('div', class_='row d-flex flex-wrap m-0 w-100 mx-n1 mt-n1')
            if not poster_div:
                continue

            # Find all poster items
            posters = poster_div.find_all('div', class_='col-6 col-lg-2 p-1')

            for poster in posters:
                # Check if it's a TV show
                media_type = poster.find('a', class_="text-white", attrs={'data-toggle': 'tooltip'})
                if not media_type or media_type.get('title') != 'Show':
                    continue

                # Get the title
                title_p = poster.find('p', class_='p-0 mb-1 text-break')
                if not title_p:
                    continue

                title_text = title_p.get_text(strip=True)

                # Extract show name (before year in parentheses)
                show_match = re.match(r'(.+?)\s*\((\d{4})\)', title_text)
                if show_match:
                    show_name = show_match.group(1).strip()

                    # Check if this is a set (has "view all" link)
                    set_link = poster.find('a', class_='rounded view_all')
                    if set_link:
                        set_url = urljoin("https://theposterdb.com", set_link['href'])

                        if show_name not in show_sets:
                            show_sets[show_name] = []
                        if set_url not in show_sets[show_name]:
                            show_sets[show_name].append(set_url)

        except Exception as e:
            print(f"  Error on page {page}: {e}")
            continue

    return show_sets

def normalize_show_name(name):
    """
    Normalize show name for comparison by removing special characters,
    converting to lowercase, and removing common articles.
    """
    # Remove special characters and convert to lowercase
    normalized = re.sub(r'[^a-z0-9\s]', '', name.lower())
    # Remove common articles at the start
    normalized = re.sub(r'^(the|a|an)\s+', '', normalized)
    # Remove extra whitespace
    normalized = ' '.join(normalized.split())
    return normalized

def find_matching_shows(user_shows, creator_shows):
    """
    Match user's shows with creator's poster sets.
    Returns a dict: {user_show_name: [(creator, set_url), ...]}
    """
    matches = {}

    # Create normalized lookup for creator shows
    creator_lookup = {}
    for creator, shows_dict in creator_shows.items():
        for show_name, set_urls in shows_dict.items():
            normalized = normalize_show_name(show_name)
            if normalized not in creator_lookup:
                creator_lookup[normalized] = []
            for url in set_urls:
                creator_lookup[normalized].append((creator, show_name, url))

    # Match user shows
    for user_show, year in user_shows:
        normalized = normalize_show_name(user_show)

        if normalized in creator_lookup:
            matches[user_show] = creator_lookup[normalized]

    return matches

def main():
    print("=" * 60)
    print("ThePosterDB Bulk Import Generator")
    print("=" * 60)

    # Step 1: Get user's shows
    print(f"\n[1/4] Reading shows from {SHOWS_DIR}...")
    try:
        show_folders = os.listdir(SHOWS_DIR)
        user_shows = [extract_show_name(folder) for folder in show_folders]
        print(f"  Found {len(user_shows)} shows in your library")
    except Exception as e:
        print(f"Error reading shows directory: {e}")
        return

    # Step 2: Scrape each creator's uploads
    print(f"\n[2/4] Scraping poster sets from {len(CREATORS)} creators...")
    creator_shows = {}

    for creator in CREATORS:
        try:
            creator_shows[creator] = get_user_shows(creator)
            show_count = len(creator_shows[creator])
            print(f"  {creator}: Found {show_count} TV show sets")
        except Exception as e:
            print(f"  Error scraping {creator}: {e}")
            creator_shows[creator] = {}

    # Step 3: Match shows
    print(f"\n[3/4] Matching your shows with creator poster sets...")
    matches = find_matching_shows(user_shows, creator_shows)

    print(f"  Found matches for {len(matches)} shows!")

    # Step 4: Generate bulk_import.txt
    print(f"\n[4/4] Generating {OUTPUT_FILE}...")

    with open(OUTPUT_FILE, 'w') as f:
        f.write("# ThePosterDB Bulk Import - Auto-generated\n")
        f.write(f"# Creators: {', '.join(CREATORS)}\n")
        f.write(f"# Total matches: {len(matches)}\n")
        f.write("#\n")
        f.write("# Format: One URL per line\n")
        f.write("# Lines starting with # or // are ignored as comments\n")
        f.write("\n")

        if not matches:
            f.write("# No matches found!\n")
            f.write("# This could mean:\n")
            f.write("#   - The creators don't have poster sets for your shows\n")
            f.write("#   - Show names don't match exactly (try manual search)\n")
        else:
            for user_show, creator_sets in sorted(matches.items()):
                f.write(f"\n# {user_show}\n")
                for creator, original_name, url in creator_sets:
                    f.write(f"# by {creator} (as: {original_name})\n")
                    f.write(f"{url}\n")

    print(f"\n✓ Done! Generated {OUTPUT_FILE}")
    print(f"  Matched shows: {len(matches)}")
    print(f"  Total set URLs: {sum(len(sets) for sets in matches.values())}")

    if matches:
        print(f"\nNext steps:")
        print(f"  1. Review the {OUTPUT_FILE} file")
        print(f"  2. Run: python plex_poster_set_helper.py bulk")
        print(f"     or: python plex_poster_set_helper.py bulk {OUTPUT_FILE}")
    else:
        print("\nNo matches found. You may need to:")
        print("  - Check if the creators have poster sets for your shows")
        print("  - Manually search ThePosterDB for specific shows")

if __name__ == "__main__":
    main()
