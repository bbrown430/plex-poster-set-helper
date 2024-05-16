# plex-poster-set-helper

plex-poster-set-helper is a tool to help upload sets of posters from ThePosterDB or MediUX to your Plex server in seconds!

## Installation

1. [Install Python](https://www.python.org/downloads/) (if not installed already)

2. Extract all files into a folder

3. Open a terminal in the folder

4. Install the required dependencies using

```bash
pip install -r requirements.txt
```

5. Rename `example_config.json` to `config.json`, and populate with the proper information
   - "base_url"
        - the IP and port of your plex server. (e.g. "http://12.345.67.890:32400/"
   - "token"
        - your Plex token
        - **NOTE: this can be found [here](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)**
   - "tv_library"
        - the name of your TV Shows library (e.g. "TV Shows")
        - multiple libraries are also supported, check the `Multiple Libraries` section of the README
    - "movie_library"
        - the name of your Movies library (e.g. "Movies")
        - multiple libraries are also supported, check the `Multiple Libraries` section of the README

## Usage

Run `plex_poster_set_helper.py`

## Supported Features
### Multiple Libraries

To utilize multiple libraries, update the `config.json` as follows:

```bash
"tv_library": ["TV Shows", "Kids TV Shows"],
"movie_library": ["Movies", "Kids Movies"]
```

To clarify, use the names of your own libraries, those are just placeholders. Currently, this does not account for the same media being in both libraries. If the same media is included in both libraries, the poster will only be replaced for the topmost library in that list.

### Mediux Filters

To utilize Mediux filters, modify the `config.json` as follows:

- `show_cover`: will replace the show cover
- `background`: will replace backgrounds
- `season_cover`: will replace season covers
- `title_card`: will replace episode title cards

Including any of these flags in the `config.json` will have the script *replace* those media types.

```bash
"mediux_filters": ["title_card", "background", "season_cover", "show_cover"]
```

### Bulk Import

1. Enter `bulk` in the first input prompt
2. Enter the path to a .txt file (reference example_bulk_import)

### Using args
Command line arguments are supported.

1. Passing a single link e.g.`plex_poster_set_helper.py https://mediux.pro/sets/9242`

2. Passing a bulk import file e.g. `plex_poster_set_helper.py bulk example_bulk_import.txt`
