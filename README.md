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

5. Rename `exampleconfig.json` to `config.json`, and populate with the proper information
   - "base_url"
        - the IP and port of your plex server. (e.g. "http://12.345.67.890:32400/"
   - "token"
        - your Plex token
        - **NOTE: this can be found [here](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)**
   - "tv_library"
        - the name of your TV Shows library (e.g. "TV Shows")
    - "movie_library"
        - the name of your Movies library (e.g. "Movies")

## Usage

Run `plex-poster-set-helper.py`

## Modes
**Multiple Libraries**

To utilize multiple libraries, update the `config.json` as follows:

```bash
"tv_library": ["TV Shows", "Kids TV Shows"],
"movie_library": ["Movies", "Kids Movies"]
```

To clarify, use the names of your own libraries, those are just placeholders. Currently, this does not account for the same media being in both libraries. If the same media is included in both libraries, the poster will only be replaced for the topmost library in that list.

**Bulk Import**

1. Enter `bulk` in the first input prompt
2. Enter the path to a .txt file with multiple links (on separate lines)