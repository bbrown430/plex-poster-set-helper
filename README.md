
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

5. Rename `example_config.json` to `config.json`, and populate with the proper information:
   - **"base_url"**  
     - The IP and port of your Plex server. e.g. `"http://12.345.67.890:32400/"`.
   - **"token"**  
     - Your Plex token (can be found [here](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)).
   - **"tv_library"**  
     - The name of your TV Shows library (e.g., `"TV Shows"`). Multiple libraries are also supported (see the **Multiple Libraries** section below).
   - **"movie_library"**  
     - The name of your Movies library (e.g., `"Movies"`). Multiple libraries are also supported (see the **Multiple Libraries** section below).
   - **"mediux_filters"**  
     - Specify which media types to upload by including these flags:
       - `show_cover`
       - `background`
       - `season_cover`
       - `title_card`

## Usage

Run `python plex_poster_set_helper.py` in a terminal, using one of the following options:

### Command Line Arguments

The script supports various command-line arguments for flexible use.

1. **Launch the GUI**  
   Use the `gui` argument to open the graphical user interface:
   ```bash
   python plex_poster_set_helper.py gui
   ```

2. **Single Link Import**  
   Provide a link directly to set posters from a single MediUX or ThePosterDB set:
   ```bash
   python plex_poster_set_helper.py https://mediux.pro/sets/9242
   ```

3. **Bulk Import**  
   Import multiple links from a `.txt` file using the `bulk` argument:
   ```bash
   python plex_poster_set_helper.py bulk example_bulk_import.txt
   ```

   - The `.txt` file should contain one URL per line. Lines starting with `#` or `//` will be ignored as comments.

### Interactive CLI Mode

If no arguments are provided, the script will enter an interactive CLI mode where you can:
- Manually enter URLs or commands.
- Type `bulk` to perform bulk import by providing a `.txt` file.
- Type `gui` to launch the graphical interface directly.

## Supported Features

### GUI Mode

The GUI provides a more user-friendly interface for managing poster uploads. Users can run the script with `python plex_poster_set_helper.py gui` to launch the CustomTkinter-based interface, where they can:
- Easily enter single or bulk URLs.
- View progress, status updates, and more in an intuitive layout.

### Multiple Libraries

To target multiple Plex libraries, modify `config.json` as follows:

```json
"tv_library": ["TV Shows", "Kids TV Shows"],
"movie_library": ["Movies", "Kids Movies"]
```

Using these options, the tool will apply posters to the same media in all specified libraries.

### Bulk Import

1. Enter `bulk` in the first input prompt in CLI mode, or use the `bulk` argument.
2. Specify the path to a `.txt` file containing URLs. Each URL will be processed to set posters for the corresponding media.

### Filters

The `mediux_filters` option in `config.json` allows you to control which media types get posters:
- `show_cover`: Upload covers for TV shows.
- `background`: Upload background images.
- `season_cover`: Set posters for each season.
- `title_card`: Add title cards.

