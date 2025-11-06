# Plex Poster Set Helper - Developer Documentation

## Project Overview

A Python application that automates bulk uploading of poster artwork to Plex Media Server from ThePosterDB and MediUX. The tool scrapes poster sets from creators and intelligently uploads them to matching content in your Plex library.

**Key Features:**
- Bulk upload posters from ThePosterDB user profiles
- Smart handling of TV shows with multiple poster sets per show
- Crash recovery and resume functionality
- Persistent cache system to prevent duplicate uploads
- Intelligent missing items tracking
- Rate limiting to avoid service bans
- Both CLI and GUI interfaces

## Architecture

### Core Design Principles

1. **First Creator Wins**: Once a show/movie/season gets a poster from one creator, subsequent runs skip it (cached)
2. **Cross-Page Grouping**: Collects all posters from all pages before processing to handle shows split across multiple pages
3. **Set-Aware Grouping**: When a creator has multiple poster sets for the same show, automatically chooses the most complete set
4. **Three-State Returns**: Upload functions return `True` (uploaded), `False` (not found), or `None` (cached) to distinguish between failure types

### File Structure

```
plex-poster-set-helper/
├── plex_poster_set_helper.py    # Main application (~2226 lines)
├── AGENTS.md                    # Current assistant reference
├── CLAUDE.md                    # Legacy assistant reference
├── README.md                    # Usage and setup guide
├── generate_bulk_import.py      # Helper for creating bulk URL lists
├── requirements.txt             # Python dependencies
├── config.json                  # User configuration (gitignored)
├── example_config.json          # Template configuration
├── .poster_cache.json           # Persistent cache (gitignored)
├── bulk_import.txt              # Default bulk URL list
├── assets/                      # README screenshots
├── icons/                       # GUI assets (e.g., Plex.ico)
├── dist/                        # PyInstaller build outputs
├── transcripts/                 # Saved chat transcripts
└── _PlexPosterSetHelper.spec    # PyInstaller configuration
```

Additional developer files such as `test_module.py`, `venv/`, and other tooling artefacts may also be present depending on your local environment.

## Main Application Structure

### Global State
```python
# Cache tracking (persistent across runs)
processed_items = {
    'tv_shows': set(),      # Stores (title, season) tuples
    'movies': set(),        # Stores title strings
    'collections': set()    # Stores collection name strings
}

# Missing items tracking (per creator session)
missing_items = {
    'shows_no_match': [],           # Shows with no poster matches at all
    'shows_partial_match': {},      # Shows with missing seasons
    'movies_no_match': [],          # Movies with no matches
    'collections_no_match': []      # Collections with no matches
}

# Rate limiting configuration
RATE_LIMIT_CONFIG = {
    'upload_delay_min': 5.0,      # Min seconds between uploads
    'upload_delay_max': 8.0,      # Max seconds between uploads
    'scrape_delay_min': 0.8,      # Min seconds between page scrapes
    'scrape_delay_max': 1.5,      # Max seconds between page scrapes
    'max_retries': 3,
    'backoff_factor': 2.0,
    'respect_429': True
}
```

### Key Components

#### 1. Cache Management (Lines 156-268)
- **`load_cache()`**: Loads `.poster_cache.json` at startup
- **`save_cache(scanning_state, preserve_scanning)`**: Saves cache with optional scanning state
- **`clear_cache()`**: Wipes cache for fresh start
- **`load_scanning_state()`**: Loads incomplete scan progress
- **`clear_scanning_state()`**: Removes scanning state after successful completion

**Cache Structure:**
```json
{
  "tv_shows": [["Show Title", "Season"], ["Show Title", 2]],
  "movies": ["Movie Title"],
  "collections": ["Collection Name"],
  "scanning": {
    "creator": "username",
    "url": "https://theposterdb.com/user/username",
    "current_page": 120,
    "total_pages": 437,
    "collected_movies": [...],
    "collected_shows": [...],
    "collected_collections": [...]
  }
}
```

#### 2. Scraping Functions (Lines 519-1199)

**`cook_soup(url)`** - HTTP fetching with retry logic
- Implements exponential backoff
- Handles HTTP 429 rate limiting
- Uses connection pooling via `requests.Session`
- Respects `Retry-After` headers

**`scrape_posterdb(soup)`** - Parses ThePosterDB HTML (Lines 970-1059)
- Extracts poster metadata (title, year, season, set_id)
- Handles shows, movies, and collections
- **Critical**: Returns empty arrays if poster grid is missing (prevents crash)

**`scrape_mediux(soup)`** - Parses MediUX HTML (Lines 1069-1176)
- Different HTML structure than ThePosterDB
- Filters content by `mediux_filters` config
- Handles title cards, backgrounds, season covers

**`scrape_entire_user(url)`** - Main orchestrator (Lines 1202-1408)
- Fetches all pages from creator profile
- Offers resume functionality for interrupted scans
- Saves progress every 10 pages
- Groups posters before uploading
- Tracks elapsed time during execution

#### 3. Poster Grouping (Lines 355-408)

**`group_posters_by_show(showposters)`** - Critical function for handling edge cases

**Problem Solved**: Some creators have multiple poster sets for the same show with different visual styles (e.g., fwlolx has 3 different sets for "For All Mankind"). Without smart grouping, you'd get mixed styles (S1-3 from one set, S4 from another).

**Solution**:
1. Group by both show title AND set_id
2. Score each set: `season_count + (10 if has_cover else 0)`
3. Choose set with highest score (most complete coverage)
4. Print info message when multiple sets detected

**Returns**:
```python
{
    "Show Title": {
        'cover': poster_dict,
        'seasons': {1: poster_dict, 2: poster_dict, ...}
    }
}
```

#### 4. Upload Functions (Lines 652-783)

**Three-State Return Values** (Critical Design Decision):
- `True`: Successfully uploaded in this run
- `None`: Already in cache from previous run (skip, don't track as missing)
- `False`: Not found in Plex library

This distinction prevents false positives when re-running with existing cache.

**`upload_tv_poster(poster, tv, creator, silent)`** (Lines 652-722)
- Handles shows, seasons, episodes, specials, backdrops
- Checks cache before attempting upload
- Adds delay after ThePosterDB uploads (rate limiting)
- Marks as processed after successful upload

**`upload_movie_poster(poster, movies, creator, silent)`** (Lines 724-756)

**`upload_collection_poster(poster, movies, creator, silent)`** (Lines 758-784)

#### 5. Missing Items Tracking (Lines 120-174)

**Problem Solved**: Original implementation showed 2006 "missing" shows and 840 "missing" movies - but these were items the creator had that the user doesn't have in their Plex library. Completely unhelpful noise.

**Solution**: Only track items that:
1. Exist in user's Plex library (`find_in_library()` check)
2. Failed to upload (`success is False`, not `None`)

**Critical Check Pattern**:
```python
success = upload_movie_poster(poster, movies, creator=creator)
if success is False:  # Only track if not found (not if cached with None)
    if find_in_library(movies, poster):
        # Movie exists in Plex but poster wasn't uploaded (true miss)
        missing_items['movies_no_match'].append(poster['title'])
```

**Output Format**:
```
────────────────────────────────────────────────────────────
📋 Missing Posters Summary
────────────────────────────────────────────────────────────

❌ Shows in your library with no posters found (3):
   • Show Name 1
   • Show Name 2

⚠️  Shows in your library with missing seasons (10):
   • Breaking Bad: S4, S5
   • Game of Thrones: S7, S8

❌ Movies in your library with no posters found (5):
   • Movie Title 1
```

#### 6. Fallback System (Lines 915-942, 1351-1377)

**Smart Fallback Feature**: If a show's poster set is incomplete (missing some seasons), automatically uses the main poster for missing seasons.

**Configurable**: `"use_main_poster_for_missing_seasons": true` in config.json

**How It Works**:
1. Upload all seasons that have specific posters
2. Query Plex to get actual season numbers in library
3. Find gap: `plex_seasons - uploaded_seasons`
4. For each missing season, create fallback using main poster URL
5. Track in `shows_partial_match` before applying fallback

#### 7. Time Tracking (Lines 99-118, 1207, 1266-1267, 1293-1294, 1393-1403)

**Added for visibility during long operations** (437 pages can take 1-2 hours)

**Features**:
- Shows elapsed time in spinner during page scanning
- Shows elapsed time when beginning upload phase
- Shows total duration in final summary

**Example Output**:
```
⠋ Scanning page 120/437 for fwlolx [12m 34s]...

📦 Processing 9437 show posters, 663 movies, 45 collections... [46m 10s]

============================================================
✓ Completed processing fwlolx
  TV show posters uploaded: 663
  Movie posters uploaded: 9
  Collection posters uploaded: 0
  💾 Progress saved to cache
  ⏱️  Total duration: 1h 45m 30s
============================================================
```

## Configuration

### config.json Format
```json
{
    "base_url": "",
    "token": "",
    "bulk_txt": "bulk_import.txt",
    "tv_library": ["TV Shows", "Anime"],
    "movie_library": ["Movies"],
    "mediux_filters": [
        "title_card",
        "background",
        "season_cover",
        "show_cover"
    ]
}
```

**Important Notes**:
- The application auto-creates `config.json` with the defaults above if the file is missing. `example_config.json` remains as a reference template.
- `tv_library` and `movie_library` accept multiple library names (arrays) if you want to target more than one section.
- `mediux_filters` controls which MediUX asset types to fetch; adjust the list to narrow uploads.
- `use_main_poster_for_missing_seasons` defaults to `true` in newly generated configs. Set it to `false` if you want to disable season fallback uploads.

## Critical Issues Solved

### 1. Script Crash After 437 Pages (AttributeError)

**Problem**: `AttributeError: 'NoneType' object has no attribute 'find_all'` at line 839

**Root Cause**: Last page (or empty pages) don't have the poster grid div, returning `None`

**Fix** (Lines 948-950):
```python
poster_div = soup.find('div', class_='row d-flex flex-wrap m-0 w-100 mx-n1 mt-n1')

# Handle empty pages or missing poster grid
if poster_div is None:
    return movieposters, showposters, collectionposters
```

### 2. Cache Not Persisting on Ctrl+C

**Problem**: User interrupted scan at page 200, but re-running started from page 0 and re-uploaded existing items

**Root Cause**: Cache only saved after full completion, not during scanning

**Fix**:
1. **Signal Handler** (Lines 59-67): Catches SIGINT (Ctrl+C) and saves cache before exit
2. **Scanning State Persistence** (Lines 1278-1290): Saves progress every 10 pages
3. **Resume Functionality** (Lines 1224-1237): Detects incomplete scan and offers to resume

### 3. Mixed Poster Styles (Multiple Sets Per Show)

**Problem**: "For All Mankind" got S1-3 from one set, S4 from different set - looks inconsistent

**Root Cause**: Poster sets split across pages. Original grouping logic took first match without considering set_id.

**Fix**: Set-aware grouping (Lines 355-408)
1. Extract `set_id` from HTML during scraping (Lines 967-976)
2. Group by `(show_title, set_id)` instead of just `show_title`
3. Score sets and choose most complete
4. Print info message when multiple sets detected

### 4. Unhelpful Missing Items Summary

**Problem**: Showed 2006 "missing shows" and 840 "missing movies" - but these were items the creator has that user doesn't have

**Root Cause**: Didn't verify item exists in Plex before marking as missing

**Fix**: Two-step verification (Lines 844-857, 1273-1286)
```python
if success is False:
    if find_in_library(movies, poster):  # Only if user has it
        missing_items['movies_no_match'].append(poster['title'])
```

### 5. Cache Causing False Positives

**Problem**: Re-running script with cache would show cached items as "missing"

**Root Cause**: Upload functions returned `False` for both "not found" and "cached", tracking logic couldn't distinguish

**Fix**: Three-state return values
- Changed cache check to return `None` instead of `False`
- Changed tracking logic from `if not success:` to `if success is False:`
- Changed uploaded check from `if success:` to `if success is not False:`

## Usage Examples

### CLI Mode - Single Set
```bash
python plex_poster_set_helper.py https://theposterdb.com/set/368794
```

### CLI Mode - Entire User
```bash
python plex_poster_set_helper.py https://theposterdb.com/user/fwlolx
```

### CLI Mode - Bulk Import
```bash
python plex_poster_set_helper.py bulk bulk_import.txt
```

### Clear Cache
```bash
python plex_poster_set_helper.py --clear-cache
```

### GUI Mode
```bash
python plex_poster_set_helper.py gui
```

## Performance Characteristics

### Rate Limiting
- **Page scraping**: 0.8-1.5 seconds between requests (randomized)
- **Poster uploads**: 5-8 seconds between uploads (randomized)
- **HTTP 429 handling**: Respects `Retry-After` header or uses exponential backoff

### Typical Durations
- **437 pages (fwlolx)**: ~45 minutes scanning + ~1 hour uploading = ~1h 45m total
- **Single set**: 30-60 seconds
- **Resume from page 200**: ~30 minutes scanning + upload time

### Memory Usage
- Collects all posters in memory before uploading (for cross-page grouping)
- ~10MB per 1000 posters
- 437 pages ≈ 10,000 posters ≈ 100MB memory usage

## Testing Recommendations

### Smoke Tests
1. Single set with 5-10 posters
2. User profile with 2-3 pages
3. Ctrl+C during scan, then resume
4. Re-run with existing cache (should skip everything)
5. Clear cache, re-run (should upload everything again)

### Edge Cases to Test
1. Show split across multiple pages
2. Show with multiple poster sets
3. Show with missing seasons (fallback behavior)
4. Empty last page (crash prevention)
5. HTTP 429 rate limiting

## Future Considerations

### Potential Enhancements
1. **Parallel processing**: Upload multiple items concurrently (requires careful rate limiting)
2. **Dry-run mode**: Preview what would be uploaded without actually uploading
3. **Selective sync**: Choose specific shows/movies to update
4. **Poster quality selection**: Choose between different resolutions
5. **Backup existing posters**: Save current posters before replacing

### Known Limitations
1. No support for episode-specific posters (only shows/seasons/movies/collections)
2. No automatic detection of new content (manual re-run required)
3. Cache grows indefinitely (no automatic cleanup)
4. No conflict resolution for duplicate titles in different libraries

## Debugging Tips

### Enable Verbose Logging
The spinner suppresses output. To debug scraping issues:
1. Comment out `spinner.start()` and `spinner.stop()` calls
2. Add print statements in `scrape_posterdb()` or `upload_tv_poster()`

### Inspect Cache
```python
import json
with open('.poster_cache.json') as f:
    cache = json.load(f)
print(f"TV shows: {len(cache['tv_shows'])}")
print(f"Movies: {len(cache['movies'])}")
```

### Check Plex Library Match
```python
from plexapi.server import PlexServer
plex = PlexServer('http://localhost:32400', 'your-token')
tv = plex.library.section('Shows')
show = tv.get('Breaking Bad')
print(f"Seasons: {[s.seasonNumber for s in show.seasons()]}")
```

## Dependencies

```
requests          # HTTP client with session support
beautifulsoup4    # HTML parsing
plexapi           # Plex Media Server API
customtkinter     # Modern tkinter GUI framework
Pillow            # Image handling for GUI
```

## Credits

Original script concept with enhancements for:
- Crash recovery and resume functionality
- Smart multi-set handling
- Accurate missing items tracking
- Three-state return value system
- Elapsed time tracking
