# plex-posterdb-helper

plex-posterdb-helper is a tool to help upload sets of posters from theposterdb to your Plex server in seconds!

## Installation

1. Extract all files into a folder (can delete the .gitignore)

2. Open a terminal in the folder

3. Install the required dependencies using

```bash
pip install -r requirements.txt
```

4. Rename `exampleconfig.json` to `config.json`, and populate with the proper information
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

Run `plex-posterdb-helper.py`

