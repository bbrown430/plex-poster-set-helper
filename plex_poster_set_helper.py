import requests
import math
import os
import sys
import json
from bs4 import BeautifulSoup
from plexapi.server import PlexServer
import plexapi.exceptions
import time
import re
import customtkinter as ctk
import tkinter as tk
import threading
import xml.etree.ElementTree
import atexit
import signal
from PIL import Image
from itertools import cycle
from collections import defaultdict
import random


#! Interactive CLI mode flag
interactive_cli = True   # Set to False when building the executable with PyInstaller for it launches the GUI by default

#! Global tracking for "first creator wins" behavior
# Tracks which shows/movies/collections have already been processed
# This is loaded from/saved to .poster_cache.json for persistence
CACHE_FILE = ".poster_cache.json"
processed_items = {
    'tv_shows': set(),      # Stores (title, season) tuples
    'movies': set(),        # Stores title strings
    'collections': set()    # Stores collection name strings
}

#! Tracking for missing/unmatched items (per creator session)
missing_items = {
    'shows_no_match': [],           # Shows with no poster matches at all
    'shows_partial_match': {},      # Shows with missing seasons: {show_title: [missing_seasons]}
    'movies_no_match': [],          # Movies with no matches
    'collections_no_match': []      # Collections with no matches
}

#! Rate limiting configuration (best practices for avoiding bans)
RATE_LIMIT_CONFIG = {
    'upload_delay_min': 5.0,      # Minimum seconds between uploads (randomized)
    'upload_delay_max': 8.0,      # Maximum seconds between uploads
    'scrape_delay_min': 0.8,      # Minimum seconds between page scrapes
    'scrape_delay_max': 1.5,      # Maximum seconds between page scrapes
    'max_retries': 3,             # Maximum retry attempts on errors
    'backoff_factor': 2.0,        # Exponential backoff multiplier
    'respect_429': True           # Respect HTTP 429 Rate Limit responses
}

# Session for connection pooling and better performance
http_session = None

#@ ---------------------- SIGNAL HANDLERS ----------------------
def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully by saving cache before exit."""
    print("\n\n⚠️  Interrupted by user. Saving progress...")
    save_cache()
    print("✓ Cache saved successfully. Exiting.")
    sys.exit(0)

# Register signal handler for Ctrl+C
signal.signal(signal.SIGINT, signal_handler)


#@ ---------------------- CORE FUNCTIONS ----------------------

#@ ---------------------- PROGRESS SPINNER ----------------------
class Spinner:
    """Animated spinner for showing progress without cluttering output."""
    def __init__(self, message="Processing"):
        self.spinner = cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
        self.message = message
        self.running = False
        self.thread = None

    def spin(self):
        while self.running:
            sys.stdout.write(f'\r{next(self.spinner)} {self.message}...')
            sys.stdout.flush()
            time.sleep(0.1)
        sys.stdout.write('\r' + ' ' * (len(self.message) + 10) + '\r')
        sys.stdout.flush()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.spin)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

#@ ---------------------- TIME FORMATTING ----------------------
def format_elapsed_time(seconds):
    """Format elapsed time in a human-readable format.

    Args:
        seconds: Number of seconds elapsed

    Returns:
        Formatted string like "1h 23m 45s" or "5m 30s" or "45s"
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

#@ ---------------------- MISSING ITEMS TRACKING ----------------------
def clear_missing_items_tracking():
    """Clear the missing items tracking for a new creator session."""
    global missing_items
    missing_items = {
        'shows_no_match': [],
        'shows_partial_match': {},
        'movies_no_match': [],
        'collections_no_match': []
    }

def print_missing_items_summary():
    """Print a summary of items that couldn't be matched."""
    global missing_items

    has_missing = (
        missing_items['shows_no_match'] or
        missing_items['shows_partial_match'] or
        missing_items['movies_no_match'] or
        missing_items['collections_no_match']
    )

    if not has_missing:
        return  # Nothing to report

    print(f"\n{'─'*60}")
    print("📋 Missing Posters Summary")
    print(f"{'─'*60}")

    # Shows with no posters at all
    if missing_items['shows_no_match']:
        print(f"\n❌ Shows in your library with no posters found ({len(missing_items['shows_no_match'])}):")
        for show in sorted(missing_items['shows_no_match']):
            print(f"   • {show}")

    # Shows with missing seasons
    if missing_items['shows_partial_match']:
        print(f"\n⚠️  Shows in your library with missing seasons ({len(missing_items['shows_partial_match'])}):")
        for show, seasons in sorted(missing_items['shows_partial_match'].items()):
            season_list = ", ".join(f"S{s}" for s in sorted(seasons))
            print(f"   • {show}: {season_list}")

    # Movies with no posters
    if missing_items['movies_no_match']:
        print(f"\n❌ Movies in your library with no posters found ({len(missing_items['movies_no_match'])}):")
        for movie in sorted(missing_items['movies_no_match']):
            print(f"   • {movie}")

    # Collections with no posters
    if missing_items['collections_no_match']:
        print(f"\n❌ Collections in your library with no posters found ({len(missing_items['collections_no_match'])}):")
        for collection in sorted(missing_items['collections_no_match']):
            print(f"   • {collection}")

    print(f"{'─'*60}\n")

#@ ---------------------- CACHE MANAGEMENT ----------------------
def load_cache():
    """Load the processed items cache from disk."""
    global processed_items

    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)

            # Convert lists back to sets (JSON doesn't support sets)
            processed_items['tv_shows'] = set(tuple(item) for item in data.get('tv_shows', []))
            processed_items['movies'] = set(data.get('movies', []))
            processed_items['collections'] = set(data.get('collections', []))

            total_items = len(processed_items['tv_shows']) + len(processed_items['movies']) + len(processed_items['collections'])
            print(f"📂 Loaded cache: {total_items} items already processed")
            print(f"   TV shows: {len(processed_items['tv_shows'])}, Movies: {len(processed_items['movies'])}, Collections: {len(processed_items['collections'])}")
            return True
        except Exception as e:
            print(f"⚠️  Warning: Could not load cache file: {e}")
            return False
    return False

def save_cache(scanning_state=None, preserve_scanning=True):
    """Save the processed items cache to disk for crash recovery.

    Args:
        scanning_state: Optional dict with scanning progress data to update
        preserve_scanning: If True and scanning_state is None, preserve existing scanning state
    """
    try:
        # Convert sets to lists for JSON serialization
        data = {
            'tv_shows': [list(item) for item in processed_items['tv_shows']],
            'movies': list(processed_items['movies']),
            'collections': list(processed_items['collections'])
        }

        # Handle scanning state
        if scanning_state:
            # Explicitly provided scanning state - use it
            data['scanning'] = scanning_state
        elif preserve_scanning and os.path.exists(CACHE_FILE):
            # Preserve existing scanning state from cache file
            try:
                with open(CACHE_FILE, 'r') as f:
                    old_data = json.load(f)
                if 'scanning' in old_data:
                    data['scanning'] = old_data['scanning']
            except:
                pass  # If we can't read old data, just continue without scanning state

        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)

        return True
    except Exception as e:
        print(f"⚠️  Warning: Could not save cache file: {e}")
        return False

def clear_cache():
    """Clear the cache file and in-memory tracking."""
    global processed_items

    processed_items = {
        'tv_shows': set(),
        'movies': set(),
        'collections': set()
    }

    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
            print("✓ Cache cleared successfully")
            return True
        except Exception as e:
            print(f"⚠️  Warning: Could not delete cache file: {e}")
            return False
    else:
        print("ℹ️  No cache file to clear")
        return True

def load_scanning_state():
    """Load incomplete scanning state from cache."""
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        with open(CACHE_FILE, 'r') as f:
            data = json.load(f)
        return data.get('scanning')
    except Exception as e:
        print(f"⚠️  Warning: Could not load scanning state: {e}")
        return None

def clear_scanning_state():
    """Clear scanning state from cache after successful completion."""
    if not os.path.exists(CACHE_FILE):
        return

    try:
        with open(CACHE_FILE, 'r') as f:
            data = json.load(f)

        # Remove scanning key if it exists
        if 'scanning' in data:
            del data['scanning']

            with open(CACHE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
    except Exception as e:
        print(f"⚠️  Warning: Could not clear scanning state: {e}")

#@ ---------------------- RATE LIMITING ----------------------
def get_http_session():
    """Get or create a persistent HTTP session for connection pooling."""
    global http_session
    if http_session is None:
        http_session = requests.Session()
        # Configure session with retries (but we'll handle rate limiting manually)
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0  # We handle retries manually
        )
        http_session.mount('http://', adapter)
        http_session.mount('https://', adapter)
    return http_session

def smart_delay(operation_type='scrape'):
    """
    Implement human-like delays with randomization.

    Args:
        operation_type: 'scrape' for page fetches, 'upload' for poster uploads
    """
    if operation_type == 'upload':
        delay = random.uniform(
            RATE_LIMIT_CONFIG['upload_delay_min'],
            RATE_LIMIT_CONFIG['upload_delay_max']
        )
    else:  # scrape
        delay = random.uniform(
            RATE_LIMIT_CONFIG['scrape_delay_min'],
            RATE_LIMIT_CONFIG['scrape_delay_max']
        )

    time.sleep(delay)

def exponential_backoff(attempt, base_delay=1.0):
    """
    Calculate exponential backoff delay with jitter.

    Args:
        attempt: Retry attempt number (0-indexed)
        base_delay: Base delay in seconds

    Returns:
        Delay in seconds with random jitter
    """
    # Exponential backoff: base * (backoff_factor ^ attempt)
    delay = base_delay * (RATE_LIMIT_CONFIG['backoff_factor'] ** attempt)
    # Add jitter (±20% randomness)
    jitter = delay * random.uniform(-0.2, 0.2)
    return delay + jitter

def handle_rate_limit_response(response):
    """
    Check if response indicates rate limiting and handle appropriately.

    Args:
        response: requests.Response object

    Returns:
        True if rate limited and we should retry, False otherwise
    """
    if response.status_code == 429:  # Too Many Requests
        if RATE_LIMIT_CONFIG['respect_429']:
            # Check for Retry-After header
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                try:
                    wait_time = int(retry_after)
                    print(f"⚠️  Rate limited by server. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    return True
                except ValueError:
                    # Retry-After might be a date, just use default backoff
                    pass

            # No Retry-After header, use exponential backoff
            wait_time = exponential_backoff(1, base_delay=10.0)
            print(f"⚠️  Rate limited by server. Waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            return True

    return False

#@ ---------------------- POSTER GROUPING ----------------------
def group_posters_by_show(showposters):
    """
    Group TV show posters by show title, handling multiple sets intelligently.

    When a creator has multiple poster sets for the same show (different styles),
    this function chooses the set with the most complete season coverage.

    Returns: {show_title: {'cover': poster, 'seasons': {season_num: poster}}}
    """
    # First, group by show title AND set ID
    sets_by_show = defaultdict(lambda: defaultdict(lambda: {'cover': None, 'seasons': {}}))

    for poster in showposters:
        title = poster['title']
        season = poster['season']
        set_id = poster.get('set_id', 'unknown')  # Default to 'unknown' if no set_id

        if season == "Cover":
            sets_by_show[title][set_id]['cover'] = poster
        else:
            sets_by_show[title][set_id]['seasons'][season] = poster

    # Now choose the best set for each show (most complete coverage)
    final_grouped = {}

    for show_title, sets in sets_by_show.items():
        if len(sets) == 1:
            # Only one set for this show, use it
            final_grouped[show_title] = list(sets.values())[0]
        else:
            # Multiple sets - choose the one with the most seasons
            best_set_id = None
            best_season_count = 0

            for set_id, set_data in sets.items():
                season_count = len(set_data['seasons'])
                # Prioritize sets that have a cover poster
                has_cover = set_data['cover'] is not None

                # Score: season count + bonus for having cover
                score = season_count + (10 if has_cover else 0)

                if score > best_season_count:
                    best_season_count = score
                    best_set_id = set_id

            # Print info about multiple sets being detected
            set_info = ", ".join([f"Set {sid}: {len(data['seasons'])} seasons" for sid, data in sets.items()])
            print(f"  ℹ️  Multiple poster sets found for '{show_title}' - choosing Set {best_set_id} ({len(sets[best_set_id]['seasons'])} seasons)")
            print(f"      Available: {set_info}")

            final_grouped[show_title] = sets[best_set_id]

    return final_grouped

def extract_username_from_url(url):
    """Extract username from ThePosterDB user URL."""
    match = re.search(r'/user/([^/?]+)', url)
    return match.group(1) if match else "Unknown"

#@ ---------------------- PLEX SETUP ----------------------

def plex_setup(gui_mode=False):
    global plex
    plex = None
    
    # Check if config.json exists
    if os.path.exists("config.json"):
        try:
            config = json.load(open("config.json"))
            base_url = config.get("base_url", "")
            token = config.get("token", "")
            tv_library = config.get("tv_library", [])
            movie_library = config.get("movie_library", [])
        except Exception as e:
            if gui_mode:
                app.after(300, update_error, f"Error with config.json: {str(e)}")
            else:
                sys.exit("Error with config.json file. Please consult the readme.md.")
            return None, None
    else:
        # No config file, skip setting up Plex for now
        base_url, token, tv_library, movie_library = "", "", [], []

    # Validate the fields
    if not base_url or not token:
        if gui_mode:
            app.after(100, update_error, "Invalid Plex token or base URL. Please provide valid values in config.json or via the GUI.")
        else:
            print('Invalid Plex token or base URL. Please provide valid values in config.json or via the GUI.')
        return None, None

    try:
        plex = PlexServer(base_url, token)  # Initialize the Plex server connection
    except requests.exceptions.RequestException as e:
        # Handle network-related errors (e.g., unable to reach the server)
        if gui_mode:
            app.after(100, update_error, f"Unable to connect to Plex server: {str(e)}")
        else:
            sys.exit('Unable to connect to Plex server. Please check the "base_url" in config.json or provide one.')
        return None, None
    except plexapi.exceptions.Unauthorized as e:
        # Handle authentication-related errors (e.g., invalid token)
        if gui_mode:
            app.after(100, update_error, f"Invalid Plex token: {str(e)}")
        else:
            sys.exit('Invalid Plex token. Please check the "token" in config.json or provide one.')
        return None, None
    except xml.etree.ElementTree.ParseError as e:
        # Handle XML parsing errors (e.g., invalid XML response from Plex)
        if gui_mode:
            app.after(100, update_error, f"Received invalid XML from Plex server: {str(e)}")
        else:
            print("Received invalid XML from Plex server. Check server connection.")
        return None, None
    except Exception as e:
        # Handle any other unexpected errors
        if gui_mode:
            app.after(100, update_error, f"Unexpected error: {str(e)}")
        else:
            sys.exit(f"Unexpected error: {str(e)}")
        return None, None

    # Continue with the setup (assuming plex server is successfully initialized)
    if isinstance(tv_library, str):
        tv_library = [tv_library] 
    elif not isinstance(tv_library, list):
        if gui_mode:
            app.after(100, update_error, "tv_library must be either a string or a list")
        sys.exit("tv_library must be either a string or a list")

    tv = []
    for tv_lib in tv_library:
        try:
            plex_tv = plex.library.section(tv_lib)
            tv.append(plex_tv)
        except plexapi.exceptions.NotFound as e:
            if gui_mode:
                app.after(100, update_error, f'TV library named "{tv_lib}" not found: {str(e)}')
            else:
                sys.exit(f'TV library named "{tv_lib}" not found. Please check the "tv_library" in config.json or provide one.')

    if isinstance(movie_library, str):
        movie_library = [movie_library] 
    elif not isinstance(movie_library, list):
        if gui_mode:
            app.after(100, update_error, "movie_library must be either a string or a list")
        sys.exit("movie_library must be either a string or a list")

    movies = []
    for movie_lib in movie_library:
        try:
            plex_movie = plex.library.section(movie_lib)
            movies.append(plex_movie)
        except plexapi.exceptions.NotFound as e:
            if gui_mode:
                app.after(100, update_error, f'Movie library named "{movie_lib}" not found: {str(e)}')
            else:
                sys.exit(f'Movie library named "{movie_lib}" not found. Please check the "movie_library" in config.json or provide one.')

    return tv, movies



def cook_soup(url):
    """
    Fetch and parse a webpage with improved rate limiting and retry logic.

    Args:
        url: URL to fetch

    Returns:
        BeautifulSoup object or exits on failure
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': 'Windows'
    }

    session = get_http_session()

    # Implement retry logic with exponential backoff
    for attempt in range(RATE_LIMIT_CONFIG['max_retries']):
        try:
            # Add delay before request (human-like behavior)
            if attempt > 0:
                # Exponential backoff on retries
                backoff_delay = exponential_backoff(attempt)
                time.sleep(backoff_delay)
            else:
                # Normal scrape delay (randomized)
                smart_delay('scrape')

            response = session.get(url, headers=headers, timeout=30)

            # Handle rate limiting
            if handle_rate_limit_response(response):
                continue  # Retry after waiting

            # Success cases
            if response.status_code == 200 or (response.status_code == 500 and "mediux.pro" in url):
                soup = BeautifulSoup(response.text, 'html.parser')
                return soup

            # Other errors
            if attempt < RATE_LIMIT_CONFIG['max_retries'] - 1:
                print(f"⚠️  HTTP {response.status_code} for {url}. Retrying (attempt {attempt + 1}/{RATE_LIMIT_CONFIG['max_retries']})...")
                continue
            else:
                sys.exit(f"Failed to retrieve the page after {RATE_LIMIT_CONFIG['max_retries']} attempts. Status code: {response.status_code}")

        except requests.exceptions.Timeout:
            if attempt < RATE_LIMIT_CONFIG['max_retries'] - 1:
                print(f"⚠️  Request timeout. Retrying (attempt {attempt + 1}/{RATE_LIMIT_CONFIG['max_retries']})...")
                continue
            else:
                sys.exit(f"Failed to retrieve the page after {RATE_LIMIT_CONFIG['max_retries']} attempts: Timeout")

        except requests.exceptions.RequestException as e:
            if attempt < RATE_LIMIT_CONFIG['max_retries'] - 1:
                print(f"⚠️  Request error: {e}. Retrying (attempt {attempt + 1}/{RATE_LIMIT_CONFIG['max_retries']})...")
                continue
            else:
                sys.exit(f"Failed to retrieve the page after {RATE_LIMIT_CONFIG['max_retries']} attempts: {e}")

    sys.exit(f"Failed to retrieve the page. Exhausted all retry attempts.")    


def title_cleaner(string):
    if " (" in string:
        title = string.split(" (")[0]
    elif " -" in string:
        title = string.split(" -")[0]
    else:
        title = string

    title = title.strip()

    return title


def parse_string_to_dict(input_string):
    # Remove unnecessary replacements
    input_string = input_string.replace('\\\\\\\"', "")
    input_string = input_string.replace("\\","")
    input_string = input_string.replace("u0026", "&")

    # Find JSON data in the input string
    json_start_index = input_string.find('{')
    json_end_index = input_string.rfind('}')
    json_data = input_string[json_start_index:json_end_index+1]

    # Parse JSON data into a dictionary
    parsed_dict = json.loads(json_data)
    return parsed_dict


def find_in_library(library, poster):
    items = []
    for lib in library:
        try:
            if poster["year"] is not None:
                library_item = lib.get(poster["title"], year=poster["year"])
            else:
                library_item = lib.get(poster["title"])
            
            if library_item:
                items.append(library_item)
        except:
            pass
    
    if items:
        return items

    # Silently return None - tracking happens in upload functions
    return None


def find_collection(library, poster):
    collections = []
    for lib in library:
        try:
            movie_collections = lib.collections()
            for plex_collection in movie_collections:
                if plex_collection.title == poster["title"]:
                    collections.append(plex_collection)
        except:
            pass

    if collections:
        return collections

    #print(f"{poster['title']} collection not found, skipping.")
    return None


def upload_tv_poster(poster, tv, creator="Unknown", silent=False):
    """Upload TV poster and return success status.

    Returns:
        True: Successfully uploaded
        False: Not found in Plex library
        None: Already in cache (skip)
    """
    global processed_items

    # Create a unique key for this show+season combination
    item_key = (poster['title'], poster['season'])

    # Check if already processed by a previous creator
    if item_key in processed_items['tv_shows']:
        return None  # Already processed, skip silently

    tv_show_items = find_in_library(tv, poster)
    if tv_show_items:
        for tv_show in tv_show_items:
            try:
                if poster["season"] == "Cover":
                    upload_target = tv_show
                    if not silent:
                        print(f"✓ [{creator}] Uploaded cover art for {poster['title']} - {poster['season']} in {tv_show.librarySectionTitle} library.")
                elif poster["season"] == 0:
                    upload_target = tv_show.season("Specials")
                    if not silent:
                        print(f"✓ [{creator}] Uploaded art for {poster['title']} - Specials in {tv_show.librarySectionTitle} library.")
                elif poster["season"] == "Backdrop":
                    upload_target = tv_show
                    if not silent:
                        print(f"✓ [{creator}] Uploaded background art for {poster['title']} in {tv_show.librarySectionTitle} library.")
                elif poster["season"] >= 1:
                    if poster["episode"] == "Cover":
                        upload_target = tv_show.season(poster["season"])
                        if not silent:
                            print(f"✓ [{creator}] Uploaded art for {poster['title']} - Season {poster['season']} in {tv_show.librarySectionTitle} library.")
                    elif poster["episode"] is None:
                        upload_target = tv_show.season(poster["season"])
                        if not silent:
                            print(f"✓ [{creator}] Uploaded art for {poster['title']} - Season {poster['season']} in {tv_show.librarySectionTitle} library.")
                    elif poster["episode"] is not None:
                        try:
                            upload_target = tv_show.season(poster["season"]).episode(poster["episode"])
                            if not silent:
                                print(f"✓ [{creator}] Uploaded art for {poster['title']} - Season {poster['season']} Episode {poster['episode']} in {tv_show.librarySectionTitle} library.")
                        except:
                            pass  # Silent failure
                if poster["season"] == "Backdrop":
                    try:
                        upload_target.uploadArt(url=poster['url'])
                    except:
                        pass  # Silent failure
                else:
                    try:
                        upload_target.uploadPoster(url=poster['url'])
                    except:
                        pass  # Silent failure
                if poster["source"] == "posterdb":
                    smart_delay('upload')  # Human-like delay with randomization

                # Mark as processed after successful upload
                processed_items['tv_shows'].add(item_key)
                return True
            except:
                pass  # Silent failure, no "not found" spam
        return False
    else:
        return False  # Not found, but don't print anything


def upload_movie_poster(poster, movies, creator="Unknown", silent=False):
    """Upload movie poster and return success status.

    Returns:
        True: Successfully uploaded
        False: Not found in Plex library
        None: Already in cache (skip)
    """
    global processed_items

    # Check if already processed by a previous creator
    if poster['title'] in processed_items['movies']:
        return None  # Already processed, skip silently

    movie_items = find_in_library(movies, poster)
    if movie_items:
        for movie_item in movie_items:
            try:
                movie_item.uploadPoster(poster["url"])
                if not silent:
                    print(f'✓ [{creator}] Uploaded art for {poster["title"]} in {movie_item.librarySectionTitle} library.')
                if poster["source"] == "posterdb":
                    smart_delay('upload')  # Human-like delay with randomization

                # Mark as processed after successful upload
                processed_items['movies'].add(poster['title'])
                return True
            except:
                pass  # Silent failure
        return False
    else:
        return False  # Not found, but don't print anything


def upload_collection_poster(poster, movies, creator="Unknown", silent=False):
    """Upload collection poster and return success status.

    Returns:
        True: Successfully uploaded
        False: Not found in Plex library
        None: Already in cache (skip)
    """
    global processed_items

    # Check if already processed by a previous creator
    if poster['title'] in processed_items['collections']:
        return None  # Already processed, skip silently

    collection_items = find_collection(movies, poster)
    if collection_items:
        for collection in collection_items:
            try:
                collection.uploadPoster(poster["url"])
                if not silent:
                    print(f'✓ [{creator}] Uploaded art for {poster["title"]} in {collection.librarySectionTitle} library.')
                if poster["source"] == "posterdb":
                    smart_delay('upload')  # Human-like delay with randomization

                # Mark as processed after successful upload
                processed_items['collections'].add(poster['title'])
                return True
            except:
                pass  # Silent failure
        return False
    else:
        return False  # Not found, but don't print anything


def get_plex_seasons(tv_libraries, show_title, show_year=None):
    """
    Get all season numbers that exist in Plex for a given show.

    Args:
        tv_libraries: List of Plex TV library sections
        show_title: Title of the show
        show_year: Optional year to help with matching

    Returns:
        Set of season numbers (integers) that exist in Plex
    """
    seasons = set()

    for lib in tv_libraries:
        try:
            # Try to find the show
            if show_year:
                results = lib.search(title=show_title, year=show_year)
            else:
                results = lib.search(title=show_title)

            # Get the first match
            if results:
                show = results[0]
                # Get all season numbers (including Season 0 for Specials)
                for season in show.seasons():
                    seasons.add(season.seasonNumber)
                break  # Found the show, no need to check other libraries
        except:
            continue

    return seasons

def set_posters(url, tv, movies, creator="Unknown"):
    """
    Scrape and upload posters with improved grouping logic.
    Groups TV shows together and uploads all seasons systematically.
    Applies main poster to seasons that don't have specific posters (optional).
    """
    # Start timing
    start_time = time.time()

    movieposters, showposters, collectionposters = scrape(url)

    # Load config to check fallback setting
    try:
        config = json.load(open("config.json"))
        use_fallback = config.get("use_main_poster_for_missing_seasons", True)
    except:
        use_fallback = True  # Default to True if config can't be loaded

    # Upload collections (silent, no grouping needed)
    for poster in collectionposters:
        success = upload_collection_poster(poster, movies, creator=creator)
        if success is False:  # Only track if not found (not if cached with None)
            # Check if this collection actually exists in Plex (to filter out collections user doesn't have)
            if find_collection(movies, poster):
                # Collection exists in Plex but poster wasn't uploaded (true miss)
                missing_items['collections_no_match'].append(poster['title'])

    # Upload movies (silent, no grouping needed)
    for poster in movieposters:
        success = upload_movie_poster(poster, movies, creator=creator)
        if success is False:  # Only track if not found (not if cached with None)
            # Check if this movie actually exists in Plex (to filter out movies user doesn't have)
            if find_in_library(movies, poster):
                # Movie exists in Plex but poster wasn't uploaded (true miss)
                missing_items['movies_no_match'].append(poster['title'])

    # Group TV shows by title for systematic processing
    grouped_shows = group_posters_by_show(showposters)

    # Process each show with all its seasons together
    for show_title, show_data in sorted(grouped_shows.items()):
        # Try to upload the main cover first
        uploaded_any = False
        main_poster = show_data['cover']

        if main_poster:
            success = upload_tv_poster(main_poster, tv, creator=creator)
            if success is not False:  # Count both True (uploaded) and None (cached) as uploaded
                uploaded_any = True

        # Then upload all seasons in order
        uploaded_seasons = set()
        for season_num in sorted(show_data['seasons'].keys()):
            season_poster = show_data['seasons'][season_num]
            success = upload_tv_poster(season_poster, tv, creator=creator)
            if success is not False:  # Count both True (uploaded) and None (cached) as uploaded
                uploaded_any = True
                uploaded_seasons.add(season_num)

        # Track if show had NO matches at all
        if not uploaded_any:
            # Check if this show actually exists in Plex (to filter out shows user doesn't have)
            test_poster = {'title': show_title, 'year': main_poster.get('year') if main_poster else None}
            if find_in_library(tv, test_poster):
                # Show exists in Plex but no posters were uploaded (true miss)
                missing_items['shows_no_match'].append(show_title)
            continue  # Skip fallback logic for shows not in library

        # SMART FALLBACK: Apply main poster to missing seasons
        if use_fallback and main_poster and uploaded_any:
            # Get what seasons exist in Plex for this show
            show_year = main_poster.get('year')
            plex_seasons = get_plex_seasons(tv, show_title, show_year)

            # Find seasons that exist in Plex but weren't in the poster set
            missing_seasons = plex_seasons - uploaded_seasons

            if missing_seasons:
                # Track shows with missing seasons (before applying fallback)
                missing_items['shows_partial_match'][show_title] = sorted(missing_seasons)

                for season_num in sorted(missing_seasons):
                    # Create a fallback poster using the main poster's URL
                    fallback_poster = {
                        'title': show_title,
                        'season': season_num,
                        'episode': None,
                        'year': show_year,
                        'url': main_poster['url'],
                        'source': main_poster['source'],
                        'set_id': main_poster.get('set_id')  # Preserve set_id
                    }

                    success = upload_tv_poster(fallback_poster, tv, creator=creator, silent=False)
                    if success:
                        print(f"  ↳ [Fallback] Season {season_num} → using main poster")

    # Print duration at the end
    total_duration = format_elapsed_time(time.time() - start_time)
    print(f"\n⏱️  Completed in {total_duration}")

def scrape_posterdb_set_link(soup):
    try:
        view_all_div = soup.find('a', class_='rounded view_all')['href']
    except:
        return None
    return view_all_div


def scrape_posterdb_set_link(soup):
    try:
        view_all_div = soup.find("a", class_="rounded view_all")["href"]
    except:
        return None
    return view_all_div

def scrape_posterd_user_info(soup):
    try:
        span_tag = soup.find('span', class_='numCount')
        number_str = span_tag['data-count']
        
        upload_count = int(number_str)
        pages = math.ceil(upload_count/24)
        return pages
    except:
        return None

def scrape_posterdb(soup):
    movieposters = []
    showposters = []
    collectionposters = []

    # find the poster grid
    poster_div = soup.find('div', class_='row d-flex flex-wrap m-0 w-100 mx-n1 mt-n1')

    # Handle empty pages or missing poster grid
    if poster_div is None:
        return movieposters, showposters, collectionposters

    # find all poster divs
    posters = poster_div.find_all('div', class_='col-6 col-lg-2 p-1')

    # loop through the poster divs
    for poster in posters:
        # get if poster is for a show or movie
        media_type = poster.find('a', class_="text-white", attrs={'data-toggle': 'tooltip', 'data-placement': 'top'})['title']
        # get high resolution poster image
        overlay_div = poster.find('div', class_='overlay')
        poster_id = overlay_div.get('data-poster-id')
        poster_url = "https://theposterdb.com/api/assets/" + poster_id
        # get metadata
        title_p = poster.find('p', class_='p-0 mb-1 text-break').string

        # Extract set ID from the set link (for handling multiple sets per show)
        set_id = None
        try:
            set_link = poster.find('a', attrs={'title': 'Posters in Set'})
            if set_link and 'href' in set_link.attrs:
                # Extract set ID from URL like '/set/368794'
                set_url = set_link['href']
                set_id = set_url.split('/set/')[-1].split('?')[0] if '/set/' in set_url else None
        except:
            pass  # If we can't extract set ID, continue without it

        if media_type == "Show":
            title = title_p.split(" (")[0]
            try:
                year = int(title_p.split(" (")[1].split(")")[0])
            except:
                year = None
                
            if " - " in title_p:
                split_season = title_p.split(" - ")[-1]
                if split_season == "Specials":
                    season = 0
                elif "Season" in split_season:
                    season = int(split_season.split(" ")[1])
                else:
                    season = "Cover"
            else:
                season = "Cover"
            
            showposter = {}
            showposter["title"] = title
            showposter["url"] = poster_url
            showposter["season"] = season
            showposter["episode"] = None
            showposter["year"] = year
            showposter["source"] = "posterdb"
            showposter["set_id"] = set_id  # Add set ID for multi-set handling
            showposters.append(showposter)

        elif media_type == "Movie":
            title_split = title_p.split(" (")
            if len(title_split[1]) != 5:
                title = title_split[0] + " (" + title_split[1]
            else:
                title = title_split[0]
            year = title_split[-1].split(")")[0]

            movieposter = {}
            movieposter["title"] = title
            movieposter["url"] = poster_url
            movieposter["year"] = int(year)
            movieposter["source"] = "posterdb"
            movieposter["set_id"] = set_id  # Add set ID for multi-set handling
            movieposters.append(movieposter)

        elif media_type == "Collection":
            collectionposter = {}
            collectionposter["title"] = title_p
            collectionposter["url"] = poster_url
            collectionposter["source"] = "posterdb"
            collectionposter["set_id"] = set_id  # Add set ID for multi-set handling
            collectionposters.append(collectionposter)
    
    return movieposters, showposters, collectionposters

def get_mediux_filters():
    config = json.load(open("config.json"))
    return config.get("mediux_filters", None)


def check_mediux_filter(mediux_filters, filter):
    return filter in mediux_filters if mediux_filters else True

def scrape_mediux(soup):
    base_url = "https://mediux.pro/_next/image?url=https%3A%2F%2Fapi.mediux.pro%2Fassets%2F"
    quality_suffix = "&w=3840&q=80"
    scripts = soup.find_all('script')
    media_type = None
    showposters = []
    movieposters = []
    collectionposters = []
    mediux_filters = get_mediux_filters()
    year = 0    # Default year value
    title = "Untitled" # Default title value
        
    for script in scripts:
        if 'files' in script.text:
            if 'set' in script.text:
                if 'Set Link\\' not in script.text:
                    data_dict = parse_string_to_dict(script.text)
                    poster_data = data_dict["set"]["files"]              

    for data in poster_data:
        if data["show_id"] is not None or data["show_id_backdrop"] is not None or data["episode_id"] is not None or data["season_id"] is not None or data["show_id"] is not None:
            media_type = "Show"
        else:
            media_type = "Movie"
                    
    for data in poster_data:        
        if media_type == "Show":

            episodes = data_dict["set"]["show"]["seasons"]
            show_name = data_dict["set"]["show"]["name"]
            try:
                year = int(data_dict["set"]["show"]["first_air_date"][:4])
            except:
                year = None

            if data["fileType"] == "title_card":
                episode_id = data["episode_id"]["id"]
                season = data["episode_id"]["season_id"]["season_number"]
                title = data["title"]
                try:
                    episode = int(title.rsplit(" E",1)[1])
                except:
                    print(f"Error getting episode number for {title}.")
                file_type = "title_card"
                
            elif data["fileType"] == "backdrop":
                season = "Backdrop"
                episode = None
                file_type = "background"
            elif data["season_id"] is not None:
                season_id = data["season_id"]["id"]
                season_data = [episode for episode in episodes if episode["id"] == season_id][0]
                episode = "Cover"
                season = season_data["season_number"]
                file_type = "season_cover"
            elif data["show_id"] is not None:
                season = "Cover"
                episode = None
                file_type = "show_cover"

        elif media_type == "Movie":

            if data["movie_id"]:
                if data_dict["set"]["movie"]:
                    title = data_dict["set"]["movie"]["title"]
                    year = int(data_dict["set"]["movie"]["release_date"][:4])
                elif data_dict["set"]["collection"]:
                    movie_id = data["movie_id"]["id"]
                    movies = data_dict["set"]["collection"]["movies"]
                    movie_data = [movie for movie in movies if movie["id"] == movie_id][0]
                    title = movie_data["title"]
                    year = int(movie_data["release_date"][:4])
            elif data["collection_id"]:
                title = data_dict["set"]["collection"]["collection_name"]
            
        image_stub = data["id"]
        poster_url = f"{base_url}{image_stub}{quality_suffix}"
        
        if media_type == "Show":
            showposter = {}
            showposter["title"] = show_name
            showposter["season"] = season
            showposter["episode"] = episode
            showposter["url"] = poster_url
            showposter["source"] = "mediux"
            showposter["year"] = year

            if check_mediux_filter(mediux_filters=mediux_filters, filter=file_type):
                showposters.append(showposter)
            # else: silently skip items not matching mediux_filters
        
        elif media_type == "Movie":
            if "Collection" in title:
                collectionposter = {}
                collectionposter["title"] = title
                collectionposter["url"] = poster_url
                collectionposter["source"] = "mediux"
                collectionposters.append(collectionposter)
            
            else:
                movieposter = {}
                movieposter["title"] = title
                movieposter["year"] = int(year)
                movieposter["url"] = poster_url
                movieposter["source"] = "mediux"
                movieposters.append(movieposter)
            
    return movieposters, showposters, collectionposters


def scrape(url):
    if ("theposterdb.com" in url):
        if("/set/" in url or "/user/" in url):
            soup = cook_soup(url)
            return scrape_posterdb(soup)
        elif("/poster/" in url):
            soup = cook_soup(url)
            set_url = scrape_posterdb_set_link(soup)
            if set_url is not None:
                set_soup = cook_soup(set_url)
                return scrape_posterdb(set_soup)
            else:
                sys.exit("Poster set not found. Check the link you are inputting.")
            #menu_selection = input("You've provided the link to a single poster, rather than a set. \n \t 1. Upload entire set\n \t 2. Upload single poster \nType your selection: ")
    elif ("mediux.pro" in url) and ("sets" in url):
        soup = cook_soup(url)
        return scrape_mediux(soup)
    elif (".html" in url):
        with open(url, 'r', encoding='utf-8') as file:
            html_content = file.read()
        soup = BeautifulSoup(html_content, 'html.parser')
        return scrape_posterdb(soup)
    else:
        sys.exit("Poster set not found. Check the link you are inputting.")


def scrape_entire_user(url):
    '''Scrape all pages of a user's uploads with progress indicator.'''
    global processed_items

    # Start timing
    start_time = time.time()

    # Clear missing items tracking for this creator
    clear_missing_items_tracking()

    # Extract username from URL
    creator = extract_username_from_url(url)

    if "?" in url:
        cleaned_url = url.split("?")[0]
        url = cleaned_url

    # Check for incomplete scan and offer to resume
    scanning_state = load_scanning_state()
    resume = False
    start_page = 0
    all_movieposters = []
    all_showposters = []
    all_collectionposters = []

    if scanning_state and scanning_state.get('url') == url:
        print(f"\n🔄 Found incomplete scan for {creator}")
        print(f"   Last scanned: page {scanning_state['current_page']}/{scanning_state['total_pages']}")
        print(f"   Collected: {len(scanning_state['collected_shows'])} show posters, {len(scanning_state['collected_movies'])} movies, {len(scanning_state['collected_collections'])} collections")
        response = input("   Resume from where it left off? [Y/n]: ").strip().lower()

        if response != 'n':
            resume = True
            start_page = scanning_state['current_page']
            all_movieposters = scanning_state['collected_movies']
            all_showposters = scanning_state['collected_shows']
            all_collectionposters = scanning_state['collected_collections']
            print(f"   ✓ Resuming from page {start_page + 1}\n")
        else:
            print(f"   Starting fresh scan...\n")

    if not resume:
        print(f"\n{'='*60}")
        print(f"Processing creator: {creator}")
        print(f"{'='*60}\n")

    # Track items before processing this creator
    start_tv_count = len(processed_items['tv_shows'])
    start_movie_count = len(processed_items['movies'])
    start_collection_count = len(processed_items['collections'])

    # Get total pages (only if not resuming)
    if not resume:
        soup = cook_soup(url)
        pages = scrape_posterd_user_info(soup)
    else:
        pages = scanning_state['total_pages']

    if not pages:
        print(f"Could not determine the number of pages for {url}")
        return

    # Collect ALL posters from ALL pages first (for proper grouping)
    for page in range(start_page, pages):
        elapsed = format_elapsed_time(time.time() - start_time)
        spinner = Spinner(f"Scanning page {page + 1}/{pages} for {creator} [{elapsed}]")
        spinner.start()

        try:
            page_url = f"{url}?section=uploads&page={page + 1}"
            movieposters, showposters, collectionposters = scrape(page_url)
            all_movieposters.extend(movieposters)
            all_showposters.extend(showposters)
            all_collectionposters.extend(collectionposters)
        finally:
            spinner.stop()

        # Save scanning progress every 10 pages for crash recovery
        if (page + 1) % 10 == 0:
            scanning_state_data = {
                'creator': creator,
                'url': url,
                'current_page': page + 1,
                'total_pages': pages,
                'collected_movies': all_movieposters,
                'collected_shows': all_showposters,
                'collected_collections': all_collectionposters
            }
            save_cache(scanning_state=scanning_state_data)

    # Now process all collected posters with proper grouping
    elapsed = format_elapsed_time(time.time() - start_time)
    print(f"\n📦 Processing {len(all_movieposters)} movies, {len(all_showposters)} show posters, {len(all_collectionposters)} collections... [{elapsed}]")

    # Upload collections (silent, no grouping needed)
    for poster in all_collectionposters:
        success = upload_collection_poster(poster, movies, creator=creator)
        if success is False:  # Only track if not found (not if cached with None)
            # Check if this collection actually exists in Plex (to filter out collections user doesn't have)
            if find_collection(movies, poster):
                # Collection exists in Plex but poster wasn't uploaded (true miss)
                missing_items['collections_no_match'].append(poster['title'])

    # Upload movies (silent, no grouping needed)
    for poster in all_movieposters:
        success = upload_movie_poster(poster, movies, creator=creator)
        if success is False:  # Only track if not found (not if cached with None)
            # Check if this movie actually exists in Plex (to filter out movies user doesn't have)
            if find_in_library(movies, poster):
                # Movie exists in Plex but poster wasn't uploaded (true miss)
                missing_items['movies_no_match'].append(poster['title'])

    # Group TV shows by title for systematic processing (across ALL pages)
    grouped_shows = group_posters_by_show(all_showposters)

    # Load config to check fallback setting
    try:
        config = json.load(open("config.json"))
        use_fallback = config.get("use_main_poster_for_missing_seasons", True)
    except:
        use_fallback = True  # Default to True if config can't be loaded

    # Process each show with all its seasons together
    for show_title, show_data in sorted(grouped_shows.items()):
        # Try to upload the main cover first
        uploaded_any = False
        main_poster = show_data['cover']

        if main_poster:
            success = upload_tv_poster(main_poster, tv, creator=creator)
            if success is not False:  # Count both True (uploaded) and None (cached) as uploaded
                uploaded_any = True

        # Then upload all seasons in order
        uploaded_seasons = set()
        for season_num in sorted(show_data['seasons'].keys()):
            season_poster = show_data['seasons'][season_num]
            success = upload_tv_poster(season_poster, tv, creator=creator)
            if success is not False:  # Count both True (uploaded) and None (cached) as uploaded
                uploaded_any = True
                uploaded_seasons.add(season_num)

        # Track if show had NO matches at all
        if not uploaded_any:
            # Check if this show actually exists in Plex (to filter out shows user doesn't have)
            test_poster = {'title': show_title, 'year': main_poster.get('year') if main_poster else None}
            if find_in_library(tv, test_poster):
                # Show exists in Plex but no posters were uploaded (true miss)
                missing_items['shows_no_match'].append(show_title)
            continue  # Skip fallback logic for shows not in library

        # SMART FALLBACK: Apply main poster to missing seasons
        if use_fallback and main_poster and uploaded_any:
            # Get what seasons exist in Plex for this show
            show_year = main_poster.get('year')
            plex_seasons = get_plex_seasons(tv, show_title, show_year)

            # Find seasons that exist in Plex but weren't in the poster set
            missing_seasons = plex_seasons - uploaded_seasons

            if missing_seasons:
                # Track shows with missing seasons (before applying fallback)
                missing_items['shows_partial_match'][show_title] = sorted(missing_seasons)

                for season_num in sorted(missing_seasons):
                    # Create a fallback poster using the main poster's URL
                    fallback_poster = {
                        'title': show_title,
                        'season': season_num,
                        'episode': None,
                        'year': show_year,
                        'url': main_poster['url'],
                        'source': main_poster['source'],
                        'set_id': main_poster.get('set_id')  # Preserve set_id
                    }

                    success = upload_tv_poster(fallback_poster, tv, creator=creator, silent=False)
                    if success:
                        print(f"  ↳ [Fallback] Season {season_num} → using main poster")

    # Calculate items uploaded by this creator
    new_tv_count = len(processed_items['tv_shows']) - start_tv_count
    new_movie_count = len(processed_items['movies']) - start_movie_count
    new_collection_count = len(processed_items['collections']) - start_collection_count

    # Save cache after completing this creator (crash recovery)
    save_cache()

    # Clear scanning state after successful completion
    clear_scanning_state()

    # Calculate total duration
    total_duration = format_elapsed_time(time.time() - start_time)

    # Print summary
    print(f"\n{'='*60}")
    print(f"✓ Completed processing {creator}")
    print(f"  TV show posters uploaded: {new_tv_count}")
    print(f"  Movie posters uploaded: {new_movie_count}")
    print(f"  Collection posters uploaded: {new_collection_count}")
    print(f"  💾 Progress saved to cache")
    print(f"  ⏱️  Total duration: {total_duration}")
    print(f"{'='*60}\n")

    # Print missing items summary
    print_missing_items_summary()


def is_not_comment(url):
    '''Check if the URL is not a comment or empty line.'''
    regex = r"^(?!\/\/|#|^$)"
    pattern = re.compile(regex)
    return True if re.match(pattern, url) else False


def parse_urls(bulk_import_list):
    '''Parse the URLs from a list and scrape them.'''
    valid_urls = []
    for line in bulk_import_list:
        url = line.strip()
        if url and not url.startswith(("#", "//")):
            valid_urls.append(url)

    for url in valid_urls:
        if "/user/" in url: 
            print(f"Scraping user data from: {url}")
            scrape_entire_user(url)
        else:
            print(f"Returning non-user URL: {url}")
            # If it's not a /user/ URL, return it as before
            return valid_urls

    return valid_urls


def parse_cli_urls(file_path, tv, movies):
    '''Parse the URLs from a file and scrape them.'''
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            urls = file.readlines()
        for url in urls:
            url = url.strip()
            if is_not_comment(url):
                if "/user/" in url:
                    scrape_entire_user(url)
                else:
                    set_posters(url, tv, movies)
    except FileNotFoundError:
        print("File not found. Please enter a valid file path.")


def cleanup():
    '''Function to handle cleanup tasks on exit.'''
    if plex:
        print("Closing Plex server connection...")
    print("Exiting application. Cleanup complete.")
    
atexit.register(cleanup)

#@ ---------------------- GUI FUNCTIONS ----------------------



# * UI helper functions ---

def get_exe_dir():
    """Get the directory of the executable or script file."""
    if getattr(sys, 'frozen', False):  
        return os.path.dirname(sys.executable)  # Path to executable
    else:
        return os.path.dirname(__file__)  # Path to script file

def resource_path(relative_path):
    """Get the absolute path to resource, works for dev and for PyInstaller bundle."""
    try:
        # PyInstaller creates a temp folder for the bundled app, MEIPASS is the path to that folder
        base_path = sys._MEIPASS
    except Exception:
        # If running in a normal Python environment, use the current working directory
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_full_path(relative_path):
    '''Helper function to get the absolute path based on the script's location.'''
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, relative_path)

def update_status(message, color="white"):
    '''Update the status label with a message and color.'''
    app.after(0, lambda: status_label.configure(text=message, text_color=color))

def update_error(message):
    '''Update the error label with a message, with a small delay.'''
    # app.after(500, lambda: status_label.configure(text=message, text_color="red"))
    status_label.configure(text=message, text_color="red")
      
def clear_url():
    '''Clear the URL entry field.'''
    url_entry.delete(0, ctk.END)
    status_label.configure(text="URL cleared.", text_color="orange")      
     
def set_default_tab(tabview):
    '''Set the default tab to the Settings tab.'''
    plex_base_url = base_url_entry.get()
    plex_token = token_entry.get()
    
    if plex_base_url and plex_token:
        tabview.set("Bulk Import") 
    else:
        tabview.set("Settings")
        
def bind_context_menu(widget):
    '''Bind the right-click context menu to the widget.'''
    widget.bind("<Button-3>", clear_placeholder_on_right_click)
    widget.bind("<Control-1>", clear_placeholder_on_right_click)
        
def clear_placeholder_on_right_click(event):
    """Clears placeholder text and sets focus before showing the context menu."""
    widget = event.widget
    if isinstance(widget, ctk.CTkEntry) and widget.get() == "":
        widget.delete(0, tk.END) 
    widget.focus() 
    show_global_context_menu(event) 
    
def show_global_context_menu(event):
    '''Show the global context menu at the cursor position.'''
    widget = event.widget
    global_context_menu.entryconfigure("Cut", command=lambda: widget.event_generate("<<Cut>>"))
    global_context_menu.entryconfigure("Copy", command=lambda: widget.event_generate("<<Copy>>"))
    global_context_menu.entryconfigure("Paste", command=lambda: widget.event_generate("<<Paste>>"))
    global_context_menu.tk_popup(event.x_root, event.y_root)
      
      
# * Configuration file I/O functions  ---

def load_config(config_path="config.json"):
    '''Load the configuration from the JSON file. If it doesn't exist, create it with default values.'''
    default_config = {
        "base_url": "",
        "token": "",
        "bulk_txt": "bulk_import.txt",
        "tv_library": ["TV Shows", "Anime"],
        "movie_library": ["Movies"],
        "mediux_filters": ["title_card", "background", "season_cover", "show_cover"],
        "use_main_poster_for_missing_seasons": True
    }

    # Create the config.json file if it doesn't exist
    if not os.path.isfile(config_path):
        try:
            with open(config_path, "w") as config_file:
                json.dump(default_config, config_file, indent=4)
            print(f"Config file '{config_path}' created with default settings.")
        except Exception as e:
            update_error(f"Error creating config: {str(e)}")
            return {}

    # Load the configuration from the config.json file
    try:
        with open(config_path, "r") as config_file:
            config = json.load(config_file)

        base_url = config.get("base_url", "")
        token = config.get("token", "")
        tv_library = config.get("tv_library", [])
        movie_library = config.get("movie_library", [])
        mediux_filters = config.get("mediux_filters", [])
        bulk_txt = config.get("bulk_txt", "bulk_import.txt")

        return {
            "base_url": base_url,
            "token": token,
            "tv_library": tv_library,
            "movie_library": movie_library,
            "mediux_filters": mediux_filters,
            "bulk_txt": bulk_txt
        }
    except Exception as e:
        update_error(f"Error loading config: {str(e)}")
        return {}

def save_config():
    '''Save the configuration from the UI fields to the file and update the in-memory config.'''

    new_config = {
        "base_url": base_url_entry.get().strip(),
        "token": token_entry.get().strip(),
        "tv_library": [item.strip() for item in tv_library_text.get().strip().split(",")],
        "movie_library": [item.strip() for item in movie_library_text.get().strip().split(",")],
        "mediux_filters": mediux_filters_text.get().strip().split(", "), 
        "bulk_txt": bulk_txt_entry.get().strip()
    }

    try:
        with open("config.json", "w") as f:
            json.dump(new_config, f, indent=4)
            
        # Update the in-memory config dictionary
        global config
        config = new_config
        
        load_and_update_ui()
        
        update_status("Configuration saved successfully!", color="#E5A00D")
    except Exception as e:
        update_status(f"Error saving config: {str(e)}", color="red")

def load_and_update_ui():
    '''Load the configuration and update the UI fields.'''
    config = load_config()

    if base_url_entry is not None:
        base_url_entry.delete(0, ctk.END)
        base_url_entry.insert(0, config.get("base_url", ""))

    if token_entry is not None:
        token_entry.delete(0, ctk.END)
        token_entry.insert(0, config.get("token", ""))

    if bulk_txt_entry is not None:
        bulk_txt_entry.delete(0, ctk.END)
        bulk_txt_entry.insert(0, config.get("bulk_txt", "bulk_import.txt"))

    if tv_library_text is not None:
        tv_library_text.delete(0, ctk.END) 
        tv_library_text.insert(0, ", ".join(config.get("tv_library", [])))

    if movie_library_text is not None:
        movie_library_text.delete(0, ctk.END)
        movie_library_text.insert(0, ", ".join(config.get("movie_library", [])))

    if mediux_filters_text is not None:
        mediux_filters_text.delete(0, ctk.END) 
        mediux_filters_text.insert(0, ", ".join(config.get("mediux_filters", []))) 
        
    load_bulk_import_file()
    


# * Threaded functions for scraping and setting posters ---  

def run_url_scrape_thread():
    '''Run the URL scrape in a separate thread.'''
    global scrape_button, clear_button, bulk_import_button
    url = url_entry.get()

    if not url:
        update_status("Please enter a valid URL.", color="red")
        return

    scrape_button.configure(state="disabled")
    clear_button.configure(state="disabled")
    bulk_import_button.configure(state="disabled")

    threading.Thread(target=process_scrape_url, args=(url,)).start()
    
def run_bulk_import_scrape_thread():
    '''Run the bulk import scrape in a separate thread.'''
    global bulk_import_button
    bulk_import_list = bulk_import_text.get(1.0, ctk.END).strip().split("\n")
    valid_urls = parse_urls(bulk_import_list)

    if not valid_urls:
        app.after(0, lambda: update_status("No bulk import entries found.", color="red"))
        return

    scrape_button.configure(state="disabled")
    clear_button.configure(state="disabled")
    bulk_import_button.configure(state="disabled")

    threading.Thread(target=process_bulk_import, args=(valid_urls,)).start()



# * Processing functions for scraping and setting posters ---

def process_scrape_url(url):
    '''Process the URL scrape.'''
    try:
        # Perform plex setup
        tv, movies = plex_setup(gui_mode=True)

        # Check if plex setup returned valid values
        if tv is None or movies is None:
            update_status("Plex setup incomplete. Please configure your settings.", color="red")
            return

        soup = cook_soup(url)
        update_status(f"Scraping: {url}", color="#E5A00D")
        
        # Proceed with setting posters
        set_posters(url, tv, movies)
        update_status(f"Posters successfully set for: {url}", color="#E5A00D")

    except Exception as e:
        update_status(f"Error: {e}", color="red")

    finally:
        app.after(0, lambda: [
            scrape_button.configure(state="normal"),
            clear_button.configure(state="normal"),
            bulk_import_button.configure(state="normal"),
        ])

def process_bulk_import(valid_urls):
    '''Process the bulk import scrape.'''
    try:
        tv, movies = plex_setup(gui_mode=True)

        # Check if plex setup returned valid values
        if tv is None or movies is None:
            update_status("Plex setup incomplete. Please configure your settings.", color="red")
            return

        for i, url in enumerate(valid_urls):
            status_text = f"Processing item {i+1} of {len(valid_urls)}: {url}"
            update_status(status_text, color="#E5A00D")
            set_posters(url, tv, movies)
            update_status(f"Completed: {url}", color="#E5A00D")

        update_status("Bulk import scraping completed.", color="#E5A00D")
    except Exception as e:
        update_status(f"Error during bulk import: {e}", color="red")
    finally:
        app.after(0, lambda: [
            scrape_button.configure(state="normal"),
            clear_button.configure(state="normal"),
            bulk_import_button.configure(state="normal"),
        ])



# * Bulk import file I/O functions ---

def load_bulk_import_file():
    '''Load the bulk import file into the text area.'''
    try:
        # Get the current bulk_txt value from the config
        bulk_txt_path = config.get("bulk_txt", "bulk_import.txt")
        
        # Use get_exe_dir() to determine the correct path for both frozen and non-frozen cases
        bulk_txt_path = os.path.join(get_exe_dir(), bulk_txt_path)

        if not os.path.exists(bulk_txt_path):
            print(f"File does not exist: {bulk_txt_path}")
            bulk_import_text.delete(1.0, ctk.END)
            bulk_import_text.insert(ctk.END, "Bulk import file path is not set or file does not exist.")
            status_label.configure(text="Bulk import file path not set or file not found.", text_color="red")
            return
        
        with open(bulk_txt_path, "r", encoding="utf-8") as file:
            content = file.read()
        
        bulk_import_text.delete(1.0, ctk.END)
        bulk_import_text.insert(ctk.END, content)
    
    except FileNotFoundError:
        bulk_import_text.delete(1.0, ctk.END)
        bulk_import_text.insert(ctk.END, "File not found or empty.")
    except Exception as e:
        bulk_import_text.delete(1.0, ctk.END)
        bulk_import_text.insert(ctk.END, f"Error loading file: {str(e)}")


def save_bulk_import_file():
    '''Save the bulk import text area content to a file relative to the executable location.'''
    try:
        exe_path = get_exe_dir()
        bulk_txt_path = os.path.join(exe_path, config.get("bulk_txt", "bulk_import.txt"))

        os.makedirs(os.path.dirname(bulk_txt_path), exist_ok=True)

        with open(bulk_txt_path, "w", encoding="utf-8") as file:
            file.write(bulk_import_text.get(1.0, ctk.END).strip())

        status_label.configure(text="Bulk import file saved!", text_color="#E5A00D")
    except Exception as e:
        status_label.configure(
            text=f"Error saving bulk import file: {str(e)}", text_color="red"
        )



# * Button Creation ---

def create_button(container, text, command, color=None, primary=False, height=35):
    """Create a custom button with hover effects for a CustomTkinter GUI."""
    
    button_height = height 
    button_fg = "#2A2B2B" if color else "#1C1E1E"
    button_border = "#484848"
    button_text_color = "#CECECE" if color else "#696969"
    plex_orange = "#E5A00D"
    

    if primary:
        button_fg = plex_orange 
        button_text_color, button_border = "#1C1E1E", "#1C1E1E"
    
    button = ctk.CTkButton(
        container,
        text=text,
        command=command,
        border_width=1,
        text_color=button_text_color, 
        fg_color=button_fg,
        border_color=button_border, 
        hover_color="#333333", 
        width=80,
        height=button_height,
        font=("Roboto", 13, "bold"),
    )
    
    def on_enter(event):
        """Change button appearance when mouse enters."""
        if color:
            button.configure(fg_color="#2A2B2B", text_color=lighten_color(color, 0.3), border_color=lighten_color(color, 0.5))
        else:
            button.configure(fg_color="#1C1E1E", text_color=plex_orange, border_color=plex_orange)

    def on_leave(event):
        """Reset button appearance when mouse leaves."""
        if color:
            button.configure(fg_color="#2A2B2B", text_color="#CECECE", border_color=button_border)
        else:
            if primary:
                button.configure(fg_color=plex_orange, text_color="#1C1E1E", border_color="#1C1E1E")
            else:
                button.configure(fg_color="#1C1E1E", text_color="#696969", border_color=button_border)
                
    def lighten_color(color, amount=0.5):
        """Lighten a color by blending it with white."""
        hex_to_rgb = lambda c: tuple(int(c[i:i+2], 16) for i in (1, 3, 5))
        r, g, b = hex_to_rgb(color)
            
        r = int(r + (255 - r) * amount)
        g = int(g + (255 - g) * amount)
        b = int(b + (255 - b) * amount)

        return f"#{r:02x}{g:02x}{b:02x}"

    button.bind("<Enter>", on_enter)
    button.bind("<Leave>", on_leave)
    
    return button



# * Main UI Creation function ---

def create_ui():
    '''Create the main UI window.'''
    global app, global_context_menu, scrape_button, clear_button, mediux_filters_text, bulk_import_text, base_url_entry, token_entry, status_label, url_entry, app, bulk_import_button, tv_library_text, movie_library_text, bulk_txt_entry

    app = ctk.CTk()
    ctk.set_appearance_mode("dark")
    
    app.title("Plex Poster Upload Helper")
    app.geometry("850x600")
    app.iconbitmap(resource_path("icons/Plex.ico"))
    app.configure(fg_color="#2A2B2B")
    
    global_context_menu = tk.Menu(app, tearoff=0)
    global_context_menu.add_command(label="Cut")
    global_context_menu.add_command(label="Copy")
    global_context_menu.add_command(label="Paste")
    
    def open_url(url):
        '''Open a URL in the default web browser.'''
        import webbrowser
        webbrowser.open(url)


    # ! Create a frame for the link bar --
    link_bar = ctk.CTkFrame(app, fg_color="transparent")
    link_bar.pack(fill="x", pady=5, padx=10)
    
    # ? Link to Plex Media Server from the base URL
    base_url = config.get("base_url", None)
    target_url = base_url if base_url else "https://www.plex.tv"

    plex_icon = ctk.CTkImage(light_image=Image.open(resource_path("icons/Plex.ico")), size=(24, 24))
    plex_icon_image = Image.open(resource_path("icons/Plex.ico"))

    icon_label = ctk.CTkLabel(link_bar, image=plex_icon, text="", anchor="w") 
    icon_label.pack(side="left", padx=0, pady=0)
    url_text = base_url if base_url else "Plex Media Server"
    url_label = ctk.CTkLabel(link_bar, text=url_text, anchor="w", font=("Roboto", 14, "bold"), text_color="#CECECE")
    url_label.pack(side="left", padx=(5, 10))

    def on_hover_enter(event):
        app.config(cursor="hand2")
        rotated_image = plex_icon_image.rotate(15, expand=True)
        rotated_ctk_icon = ctk.CTkImage(light_image=rotated_image, size=(24, 24))
        icon_label.configure(image=rotated_ctk_icon)
        
    def on_hover_leave(event):
        app.config(cursor="")
        icon_label.configure(image=plex_icon)

    def on_click(event):
        open_url(target_url)

    for widget in (icon_label, url_label):
        widget.bind("<Enter>", on_hover_enter)
        widget.bind("<Leave>", on_hover_leave)
        widget.bind("<Button-1>", on_click)

    # ? Links to Mediux and ThePosterDB
    mediux_button = create_button(
        link_bar, 
        text="MediUX.pro", 
        command=lambda: open_url("https://mediux.pro"),
        color="#945af2",
        height=30
    )
    mediux_button.pack(side="right", padx=5)

    posterdb_button = create_button(
        link_bar, 
        text="ThePosterDB", 
        command=lambda: open_url("https://theposterdb.com"),
        color="#FA6940",
        height=30
    )
    posterdb_button.pack(side="right", padx=5)


    #! Create Tabview --
    tabview = ctk.CTkTabview(app)
    tabview.pack(fill="both", expand=True, padx=10, pady=0)

    tabview.configure(
        fg_color="#2A2B2B",
        segmented_button_fg_color="#1C1E1E",
        segmented_button_selected_color="#2A2B2B",
        segmented_button_selected_hover_color="#2A2B2B",
        segmented_button_unselected_color="#1C1E1E",
        segmented_button_unselected_hover_color="#1C1E1E",
        text_color="#CECECE",
        text_color_disabled="#777777",
        border_color="#484848",
        border_width=1,
    )
    
    #! Form row label hover
    LABEL_HOVER = "#878787"
    def on_hover_in(label):
        label.configure(text_color=LABEL_HOVER)

    def on_hover_out(label):
        label.configure(text_color="#696969") 
    
    #! Settings Tab --
    settings_tab = tabview.add("Settings")
    settings_tab.grid_columnconfigure(0, weight=0)
    settings_tab.grid_columnconfigure(1, weight=1)

    # Plex Base URL
    base_url_label = ctk.CTkLabel(settings_tab, text="Plex Base URL", text_color="#696969", font=("Roboto", 15))
    base_url_label.grid(row=0, column=0, pady=5, padx=10, sticky="w")
    base_url_entry = ctk.CTkEntry(settings_tab, placeholder_text="Enter Plex Base URL", fg_color="#1C1E1E", text_color="#A1A1A1", border_width=0, height=40)
    base_url_entry.grid(row=0, column=1, pady=5, padx=10, sticky="ew")
    base_url_entry.bind("<Enter>", lambda event: on_hover_in(base_url_label))
    base_url_entry.bind("<Leave>", lambda event: on_hover_out(base_url_label))
    bind_context_menu(base_url_entry)

    # Plex Token
    token_label = ctk.CTkLabel(settings_tab, text="Plex Token", text_color="#696969", font=("Roboto", 15))
    token_label.grid(row=1, column=0, pady=5, padx=10, sticky="w")
    token_entry = ctk.CTkEntry(settings_tab, placeholder_text="Enter Plex Token", fg_color="#1C1E1E", text_color="#A1A1A1", border_width=0, height=40)
    token_entry.grid(row=1, column=1, pady=5, padx=10, sticky="ew")
    token_entry.bind("<Enter>", lambda event: on_hover_in(token_label))
    token_entry.bind("<Leave>", lambda event: on_hover_out(token_label))
    bind_context_menu(token_entry)

    # Bulk Import File
    bulk_txt_label = ctk.CTkLabel(settings_tab, text="Bulk Import File", text_color="#696969", font=("Roboto", 15))
    bulk_txt_label.grid(row=2, column=0, pady=5, padx=10, sticky="w")
    bulk_txt_entry = ctk.CTkEntry(settings_tab, placeholder_text="Enter bulk import file path", fg_color="#1C1E1E", text_color="#A1A1A1", border_width=0, height=40)
    bulk_txt_entry.grid(row=2, column=1, pady=5, padx=10, sticky="ew")
    bulk_txt_entry.bind("<Enter>", lambda event: on_hover_in(bulk_txt_label))
    bulk_txt_entry.bind("<Leave>", lambda event: on_hover_out(bulk_txt_label))
    bind_context_menu(bulk_txt_entry)

    # TV Library Names
    tv_library_label = ctk.CTkLabel(settings_tab, text="TV Library Names", text_color="#696969", font=("Roboto", 15))
    tv_library_label.grid(row=3, column=0, pady=5, padx=10, sticky="w")
    tv_library_text = ctk.CTkEntry(settings_tab, fg_color="#1C1E1E", text_color="#A1A1A1", border_width=0, height=40)
    tv_library_text.grid(row=3, column=1, pady=5, padx=10, sticky="ew")
    tv_library_text.bind("<Enter>", lambda event: on_hover_in(tv_library_label))
    tv_library_text.bind("<Leave>", lambda event: on_hover_out(tv_library_label))
    bind_context_menu(tv_library_text)

    # Movie Library Names
    movie_library_label = ctk.CTkLabel(settings_tab, text="Movie Library Names", text_color="#696969", font=("Roboto", 15))
    movie_library_label.grid(row=4, column=0, pady=5, padx=10, sticky="w")
    movie_library_text = ctk.CTkEntry(settings_tab, fg_color="#1C1E1E", text_color="#A1A1A1", border_width=0, height=40)
    movie_library_text.grid(row=4, column=1, pady=5, padx=10, sticky="ew")
    movie_library_text.bind("<Enter>", lambda event: on_hover_in(movie_library_label))
    movie_library_text.bind("<Leave>", lambda event: on_hover_out(movie_library_label))
    bind_context_menu(movie_library_text)

    # Mediux Filters
    mediux_filters_label = ctk.CTkLabel(settings_tab, text="Mediux Filters", text_color="#696969", font=("Roboto", 15))
    mediux_filters_label.grid(row=5, column=0, pady=5, padx=10, sticky="w")
    mediux_filters_text = ctk.CTkEntry(settings_tab, fg_color="#1C1E1E", text_color="#A1A1A1", border_width=0, height=40)
    mediux_filters_text.grid(row=5, column=1, pady=5, padx=10, sticky="ew")
    mediux_filters_text.bind("<Enter>", lambda event: on_hover_in(mediux_filters_label))
    mediux_filters_text.bind("<Leave>", lambda event: on_hover_out(mediux_filters_label))
    bind_context_menu(mediux_filters_text)

    settings_tab.grid_rowconfigure(0, weight=0)
    settings_tab.grid_rowconfigure(1, weight=0)
    settings_tab.grid_rowconfigure(2, weight=0)
    settings_tab.grid_rowconfigure(3, weight=0)
    settings_tab.grid_rowconfigure(4, weight=0)
    settings_tab.grid_rowconfigure(5, weight=0) 
    settings_tab.grid_rowconfigure(6, weight=1) 

    # ? Load and Save Buttons (Anchored to the bottom)
    load_button = create_button(settings_tab, text="Reload", command=load_and_update_ui)
    load_button.grid(row=7, column=0, pady=5, padx=5, ipadx=30, sticky="ew")
    save_button = create_button(settings_tab, text="Save", command=save_config, primary=True)
    save_button.grid(row=7, column=1, pady=5, padx=5, sticky="ew")

    settings_tab.grid_rowconfigure(7, weight=0, minsize=40)


    #! Bulk Import Tab --
    bulk_import_tab = tabview.add("Bulk Import")

    bulk_import_tab.grid_columnconfigure(0, weight=0) 
    bulk_import_tab.grid_columnconfigure(1, weight=3) 
    bulk_import_tab.grid_columnconfigure(2, weight=0) 

    # bulk_import_label = ctk.CTkLabel(bulk_import_tab, text=f"Bulk Import Text", text_color="#CECECE")
    # bulk_import_label.grid(row=0, column=0, pady=5, padx=10, sticky="w")
    bulk_import_text = ctk.CTkTextbox(
        bulk_import_tab,
        height=15,
        wrap="none",
        state="normal",
        fg_color="#1C1E1E", 
        text_color="#A1A1A1",
        font=("Courier", 14)
    )
    bulk_import_text.grid(row=1, column=0, padx=10, pady=5, sticky="nsew", columnspan=2)
    bind_context_menu(bulk_import_text)

    bulk_import_tab.grid_rowconfigure(0, weight=0)
    bulk_import_tab.grid_rowconfigure(1, weight=1) 
    bulk_import_tab.grid_rowconfigure(2, weight=0)

    # Button row: Load, Save, Run buttons
    load_bulk_button = create_button(bulk_import_tab, text="Reload", command=load_bulk_import_file)
    load_bulk_button.grid(row=2, column=0, pady=5, padx=5, ipadx=30, sticky="ew") 

    save_bulk_button = create_button(bulk_import_tab, text="Save", command=save_bulk_import_file)
    save_bulk_button.grid(row=2, column=1, pady=5, padx=5, sticky="ew", columnspan=2) 

    bulk_import_button = create_button(bulk_import_tab, text="Run Bulk Import", command=run_bulk_import_scrape_thread, primary=True)
    bulk_import_button.grid(row=3, column=0, pady=5, padx=5, sticky="ew", columnspan=3)


    #! Poster Scrape Tab --
    poster_scrape_tab = tabview.add("Poster Scrape")

    poster_scrape_tab.grid_columnconfigure(0, weight=0)
    poster_scrape_tab.grid_columnconfigure(1, weight=1)
    poster_scrape_tab.grid_columnconfigure(2, weight=0)

    poster_scrape_tab.grid_rowconfigure(0, weight=0)
    poster_scrape_tab.grid_rowconfigure(1, weight=0)
    poster_scrape_tab.grid_rowconfigure(2, weight=1) 
    poster_scrape_tab.grid_rowconfigure(3, weight=0) 

    url_label = ctk.CTkLabel(poster_scrape_tab, text="Enter a ThePosterDB set URL, MediUX set URL, or ThePosterDB user URL", text_color="#696969", font=("Roboto", 15))
    url_label.grid(row=0, column=0, columnspan=2, pady=5, padx=5, sticky="w")

    url_entry = ctk.CTkEntry(poster_scrape_tab, placeholder_text="e.g., https://mediux.pro/sets/6527", fg_color="#1C1E1E", text_color="#A1A1A1", border_width=0, height=40)
    url_entry.grid(row=1, column=0, columnspan=2, pady=5, padx=5, sticky="ew")
    url_entry.bind("<Enter>", lambda event: on_hover_in(url_label))
    url_entry.bind("<Leave>", lambda event: on_hover_out(url_label))
    bind_context_menu(url_entry)

    clear_button = create_button(poster_scrape_tab, text="Clear", command=clear_url)
    clear_button.grid(row=3, column=0, pady=5, padx=5, ipadx=30, sticky="ew")

    scrape_button = create_button(poster_scrape_tab, text="Run URL Scrape", command=run_url_scrape_thread, primary=True)
    scrape_button.grid(row=3, column=1, pady=5, padx=5, sticky="ew", columnspan=2)

    poster_scrape_tab.grid_rowconfigure(2, weight=1)


    #! Status and Error Labels --
    status_label = ctk.CTkLabel(app, text="", text_color="#E5A00D")
    status_label.pack(side="bottom", fill="x", pady=(5))


    #! Load configuration and bulk import data at start, set default tab
    load_and_update_ui()
    load_bulk_import_file()
    
    set_default_tab(tabview) # default tab will be 'Settings' if base_url and token are not set, otherwise 'Bulk Import'
    
    app.mainloop()


# * CLI-based user input loop (fallback if no arguments were provided) ---
def interactive_cli_loop(tv, movies, bulk_txt):
    while True:
        print("\n--- Poster Scraper Interactive CLI ---")
        print("1. Enter a ThePosterDB set URL, MediUX set URL, or ThePosterDB user URL")
        print("2. Run Bulk Import from a file")
        print("3. Launch GUI")
        print("4. Stop")

        choice = input("Select an option (1-4): ")

        if choice == '1':
            url = input("Enter the URL: ")
            if check_libraries(tv, movies):
                if "/user/" in url.lower():
                    scrape_entire_user(url)
                else:
                    set_posters(url, tv, movies)

        elif choice == '2':
            file_path = input(f"Enter the path to the bulk import .txt file, or press [Enter] to use '{bulk_txt}': ")
            file_path = file_path.strip() or bulk_txt
            if check_libraries(tv, movies):
                parse_cli_urls(file_path, tv, movies)

        elif choice == '3':
            print("Launching GUI...")
            tv, movies = plex_setup(gui_mode=True)
            create_ui()
            break  # Exit CLI loop to launch GUI

        elif choice == '4':
            print("Stopping...")
            break

        else:
            print("Invalid choice. Please select an option between 1 and 4.")


def check_libraries(tv, movies):
    if not tv:
        print("No TV libraries initialized. Verify the 'tv_library' in config.json.")
    if not movies:
        print("No Movies libraries initialized. Verify the 'movie_library' in config.json.")
    return bool(tv) and bool(movies)


# * Main Initialization ---
if __name__ == "__main__":
    config = load_config()
    bulk_txt = config.get("bulk_txt", "bulk_import.txt")

    # Check for --clear-cache flag
    if '--clear-cache' in sys.argv:
        print("\n🗑️  Clearing poster cache...")
        clear_cache()
        # Remove the flag so it doesn't interfere with other processing
        sys.argv.remove('--clear-cache')
        print()

    # Load cache for crash recovery and duplicate prevention
    # (Skip loading if GUI mode, as GUI operations don't use the cache)
    if len(sys.argv) > 1 and sys.argv[1].lower() != 'gui':
        load_cache()
        print()
    elif len(sys.argv) == 1 and interactive_cli:
        # Load for interactive CLI mode too
        load_cache()
        print()

    # Check for CLI arguments regardless of interactive_cli flag
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        # Handle command-line arguments
        if command == 'gui':
            create_ui()
            tv, movies = plex_setup(gui_mode=True)

        elif command == 'bulk':
            tv, movies = plex_setup(gui_mode=False)
            if len(sys.argv) > 2:
                file_path = sys.argv[2]
                parse_cli_urls(file_path, tv, movies)
            else:
                print(f"Using bulk import file: {bulk_txt}")
                parse_cli_urls(bulk_txt, tv, movies)

        elif "/user/" in command:
            scrape_entire_user(command)
        else:
            tv, movies = plex_setup(gui_mode=False)
            set_posters(command, tv, movies)
    
    else:
        # If no CLI arguments, proceed with UI creation (if not in interactive CLI mode)
        if not interactive_cli:
            create_ui() 
            tv, movies = plex_setup(gui_mode=True)
        else:
            sys.stdout.reconfigure(encoding='utf-8') 
            gui_flag = (len(sys.argv) > 1 and sys.argv[1].lower() == 'gui')

            # Perform CLI plex_setup if GUI flag is not present
            if not gui_flag:
                tv, movies = plex_setup(gui_mode=False)

            # Handle interactive CLI
            interactive_cli_loop(tv, movies, bulk_txt)
