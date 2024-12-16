import glob
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple, Self

import fleep
import requests
import math
import os
import sys
import json
from bs4 import BeautifulSoup
from pathvalidate import sanitize_filename
from plexapi.server import PlexServer
import plexapi.exceptions
import time
import re
import customtkinter as ctk
import tkinter as tk
import threading
import xml.etree.ElementTree
import atexit
from PIL import Image
from pathlib import Path

#! Interactive CLI mode flag
interactive_cli = True   # Set to False when building the executable with PyInstaller for it launches the GUI by default


#@ ---------------------- CORE FUNCTIONS ----------------------
@dataclass
class MediaMetadata:
    url: str = ""
    source: str = ""
    title: str = ""
    year: int = None
    season: int = None
    episode: int = None
    show_backdrop: bool = False
    show_cover_art: bool = False
    season_cover_art: bool = False

    uploaded_to_plex: bool = False
    uploaded_datetime: datetime = None

    path: str = ""
    metadata_path: str = ""

    def is_show(self) -> bool:
        return (bool(self.episode) or (self.season is not None and self.season >= 0) or
                self.show_cover_art or self.show_backdrop or self.season_cover_art)

    def is_movie(self) -> bool:
        return not self.is_show() and bool(self.year)

    def is_collection(self) -> bool:
        return not self.is_show() and self.year is None

    def build_asset_path(self, cache_location: str) -> str:
        path_sans_extension = ""
        if self.is_collection():
            path_sans_extension = os.path.join(cache_location, "collections", f"{sanitize_filename(self.title)}", "poster")
        elif self.is_movie():
            path_sans_extension = os.path.join(cache_location, "movies", f"{sanitize_filename(self.title)} ({self.year})", "poster")
        elif self.is_show():
            path_sans_extension = os.path.join(cache_location, "tv_shows",
                                               f"{sanitize_filename(self.title)} ({self.year})")
            if self.show_cover_art:
                path_sans_extension = os.path.join(path_sans_extension, "cover")
            if self.show_backdrop:
                path_sans_extension = os.path.join(path_sans_extension, "backdrop")
            elif self.season is not None and self.season == 0:
                path_sans_extension = os.path.join(path_sans_extension, "specials", "poster")
            elif self.season is not None and self.season >= 1:
                if self.season_cover_art:
                    path_sans_extension = os.path.join(path_sans_extension, f"s{self.season}", "cover")
                elif bool(self.episode):
                    path_sans_extension = os.path.join(path_sans_extension, f"s{self.season}",
                                                       f"s{self.season}e{self.episode}")
        return path_sans_extension

    def load_from_cache(self, cache_location) -> bool:
        asset_path_sans_extension = self.build_asset_path(cache_location)
        metadata_path = f"{asset_path_sans_extension}.json"
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as f:
                data = json.load(f)
                for key, value in data.items():
                    # Convert uploaded_datetime back to datetime if it exists
                    if key == "uploaded_datetime" and value:
                        value = datetime.fromisoformat(value)
                    setattr(self, key, value)
                return True
        else:
            print(f"Cache file not found: {metadata_path}")
            return False

    def save_to_cache(self, cache_location) -> None:
        asset_path_sans_extension = self.build_asset_path(cache_location)
        metadata_path = f"{asset_path_sans_extension}.json"
        """Save the instance to a JSON file."""
        with open(metadata_path, "w") as f:
            json.dump({
                key: (value.isoformat() if isinstance(value, datetime) else value)
                for key, value in self.__dict__.items()
            }, f, indent=4)

    def save_asset(self, cache_location, data):
        """
        Downloads the poster url, saving both the media and the poster metadata to files.

        The extension will be determined based on the contents of the media in poster['url'].

        Args:
            asset_path_sans_extension (str): the path including the name without extension to save to
            poster (MediaMetadata): metadata for the media

        Returns:
            dict: Paths to the media and the metadata files
                 - "asset" (str): the media path
                 - "metadata" (str): the json path

        Examples:
            >>> p = {
            ...    "title": "3 Body Problem",
            ...    "season": 1,
            ...    "episode": 1,
            ...    "url": "https://mediux.pro/_next/image?url=https%3A%2F%2Fapi.mediux.pro%2Fassets%2F64ba0b05-78ad-4866-b20c-0af80062a6b3&w=3840&q=80",
            ...    "source": "mediux",
            ...    "year": 2024
            ...    }
            >>> result = save_asset("cache/tv_shows/3 Body Problem (2024)/s1/s1e1", p)
            File downloaded and saved to cache/tv_shows/3 Body Problem (2024)/s1/s1e1.jpg
            File downloaded and saved to cache/tv_shows/3 Body Problem (2024)/s1/s1e1.json
            >>> print(json.dumps(result, indent=4))
            {
                "asset": "cache/tv_shows/3 Body Problem (2024)/s1/s1e1.jpg",
                "metadata": "cache/tv_shows/3 Body Problem (2024)/s1/s1e1.json"
            }
        """
        try:
            asset_path_sans_extension = self.build_asset_path(cache_location)
            directory = os.path.dirname(asset_path_sans_extension)
            if not Path(directory).exists():
                os.makedirs(directory, exist_ok=True)
            content_info = fleep.get(data[:128])
            image_path = asset_path_sans_extension + f".{content_info.extension[0]}"
            with open(image_path, "wb") as file:
                file.write(data)
            print(f"File downloaded and saved to {image_path}")
            self.path = image_path
            json_path = asset_path_sans_extension + ".json"
            self.metadata_path = json_path
            self.save_to_cache(cache_location)
            print(f"File downloaded and saved to {json_path}")

        except Exception as e:
            print(f"Something happened during the save asset process: {e}")


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


def cache_setup(gui_mode=False) -> bool:
    # Check if config.json exists
    if os.path.exists("config.json"):
        try:
            config = json.load(open("config.json"))
            cache_enabled = config.get("cache_enabled", False)
            cache_folder = config.get("cache_folder", "")
        except Exception as e:
            if gui_mode:
                app.after(300, update_error, f"Error with config.json: {str(e)}")
                return False
            sys.exit("Error with config.json file. Please consult the readme.md.")
    else:
        cache_enabled, cache_folder = False, ""

    # Validate the fields
    if not cache_enabled:
        return True
    if not create_cache_folder(cache_folder):
        if gui_mode:
            app.after(100, update_error,
                      "Error accessing the cache folder. Ensure the path is correct and your user can read/write to it.")
            return False
        sys.exit("Error accessing the cache folder. Ensure the path is correct and your user can read/write to it.")
    return True


def cook_soup(url):  
    headers = { 
               'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36', 
               'Sec-Ch-Ua-Mobile': '?0', 
               'Sec-Ch-Ua-Platform': 'Windows' 
            }

    response = requests.get(url, headers=headers)

    if response.status_code == 200 or (response.status_code == 500 and "mediux.pro" in url):
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup
    else:
        sys.exit(f"Failed to retrieve the page. Status code: {response.status_code}")    


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
        library_item = None
        try:
            if poster.year is not None:
                try:
                    library_item = lib.get(poster.title, year=poster.year)
                except:
                    pass
                if not library_item and ": " in poster.title: # title might not include a prefix like Star Wars:
                    library_item = lib.get(poster.title.split(": "[1]))
            else:
                try:
                    library_item = lib.get(poster.title)
                except:
                    pass
                if not library_item and ": " in poster.title: # title might not include a prefix like Star Wars:
                    library_item = lib.get(poster.title.split(": "[1]))
            
            if library_item:
                items.append(library_item)
        except Exception as e:
            pass

    if items:
        return items
    
    print(f"{poster.title} not found, skipping.")
    return None


def find_collection(library, poster):
    collections = []
    for lib in library:
        try:
            movie_collections = lib.collections()
            for plex_collection in movie_collections:
                if plex_collection.title == poster.title:
                    collections.append(plex_collection)
        except:
            pass

    if collections:
        return collections

    #print(f"{poster['title']} collection not found, skipping.")
    return None


def create_cache_folder(cache_folder: str) -> bool:
    """Determines if we have necessary permissions to read/write to the cache folder"""
    path = cache_folder
    if path == "":
        print("Blank cache folder. Assuming we want to cache in the working directory")
    elif not os.path.exists(path):
        print(f"Path does not exist: {path}")
        try:
            os.makedirs(path)
        except PermissionError:
            print(f"Permission denied: Unable to create directory at {path}")
            return False
        except FileExistsError:
            print(f"A file with the same name already exists: {path}")
            return False
        except OSError as e:
            print(f"OS error occurred: {e}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return False

        # Check read and write permissions
    can_read = os.access(path, os.R_OK)
    can_write = os.access(path, os.W_OK)

    if can_read and can_write:
        print(f"Read and write access verified for path: {path}")
        return True
    elif can_read:
        print(f"Read access is available, but no write access for path: {path}")
    elif can_write:
        print(f"Write access is available, but no read access for path: {path}")
    else:
        print(f"No read or write access for path: {path}")
    return False


def upload_tv_poster(poster, url, filepath, tv) -> bool:
    tv_show_items = find_in_library(tv, poster)
    if tv_show_items:
        all_uploaded = True
        for tv_show in tv_show_items:
            try:
                if poster.show_cover_art:
                    upload_target = tv_show
                    print(f"Uploaded cover art for {poster.title} - {poster.season} in {tv_show.librarySectionTitle} library.")
                elif poster.season is not None and poster.season == 0:
                    upload_target = tv_show.season("Specials")
                    print(f"Uploaded art for {poster.title} - Specials in {tv_show.librarySectionTitle} library.")
                elif poster.show_backdrop:
                    upload_target = tv_show
                    print(f"Uploaded background art for {poster.title} in {tv_show.librarySectionTitle} library.")
                elif poster.season is None:
                    print(f"Unknown media type for {poster.title}: {poster.url}")
                    continue
                elif poster.season is not None and poster.season >= 1:
                    if poster.season_cover_art:
                        upload_target = tv_show.season(poster.season)
                        print(f"Uploaded art for {poster.title} - Season {poster.season} in {tv_show.librarySectionTitle} library.")
                    elif bool(poster.episode):
                        try:
                            upload_target = tv_show.season(poster.season).episode(poster.episode)
                            print(f"Uploaded art for {poster.title} - Season {poster.season} Episode {poster.episode} in {tv_show.librarySectionTitle} library..")
                        except:
                            print(f"{poster.title} - {poster.season} Episode {poster.episode} not found in {tv_show.librarySectionTitle} library, skipping.")
                            continue
                if poster.show_backdrop:
                    try:
                        upload_target.uploadArt(url=url, filepath=filepath)
                    except Exception as e:
                        print(f"Unable to upload last poster. {e}")
                        all_uploaded = False
                else:
                    try:
                        upload_target.uploadPoster(url=url, filepath=filepath)
                    except Exception as e:
                        print(f"Unable to upload last poster. {e}")
                        all_uploaded = False
                if poster.source == "posterdb":
                    time.sleep(6)  # too many requests prevention
            except:
                print(f"{poster.title} - Season {poster.season} not found in {tv_show.librarySectionTitle} library, skipping.")
        return all_uploaded
    else:
        print(f"{poster.title} not found in any library.")
    return False

def upload_movie_poster(poster, url, filepath, movies) -> bool:
    movie_items = find_in_library(movies, poster)
    if movie_items:
        all_uploaded = True
        for movie_item in movie_items:
            try:
                movie_item.uploadPoster(url=url, filepath=filepath)
                print(f'Uploaded art for {poster.title} in {movie_item.librarySectionTitle} library.')
                if poster.source == "posterdb":
                    time.sleep(6)  # too many requests prevention
            except Exception as e:
                print(f'Unable to upload art for {poster.title} in {movie_item.librarySectionTitle} library.')
                all_uploaded = False
            return all_uploaded
    else:
        print(f'{poster.title} not found in any library.')
    return False


def upload_collection_poster(poster, url, filepath, movies) -> bool:
    collection_items = find_collection(movies, poster)
    if collection_items:
        all_uploaded = True
        for collection in collection_items:
            try:
                collection.uploadPoster(url=url, filepath=filepath)
                print(f'Uploaded art for {poster.title} in {collection.librarySectionTitle} library.')
                if poster.source == "posterdb":
                    time.sleep(6)  # too many requests prevention
            except:
                print(f'Unable to upload art for {poster.title} in {collection.librarySectionTitle} library.')
                all_uploaded = False
        return all_uploaded
    else:
        print(f'{poster.title} collection not found in any library.')
    return False


def set_posters(url, tv, movies):
    movieposters, showposters, collectionposters = scrape(url)
    cache_folder = config.get("cache_folder")
    for poster in collectionposters:
        if config.get("cache_enabled"):
            cache_collection(cache_folder, movies, poster)
        else:
            upload_collection_poster(poster=poster, url=poster.url, filepath=None, movies=movies)

        
    for poster in movieposters:
        if config.get("cache_enabled"):
            cache_movie(cache_folder, movies, poster)
        else:
            upload_movie_poster(poster=poster, url=poster.url, filepath=None, movies=movies)
    
    for poster in showposters:
        if config.get("cache_enabled"):
            cache_tv(cache_folder, tv, poster)
        else:
            upload_tv_poster(poster=poster, url=poster.url, filepath=None, tv=tv)


def cache_collection(cache_folder, movies, poster):
    # if it is, check to see if both the media and a json file exist
    if poster.load_from_cache(cache_folder):
        # if both exist, check json for it being uploaded to plex
        if poster.uploaded_to_plex:
            # if uploaded do nothing
            print(f"poster {poster.path} already uploaded; nothing to do")
        else:  # if not uploaded, upload
            if upload_collection_poster(poster=poster, url=None, filepath=poster.path, movies=movies):
                poster.uploaded_to_plex = True
                poster.save_to_cache(cache_folder)
            else:
                print(f"{poster.title} was not uploaded to plex")
    else:  # if not cached, download
        try:
            response = requests.get(url=poster.url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0"})
        except Exception as e:
            print(f"Something happened downloading file at url: '{poster.url}'. {e}")
        if response and response.status_code == 200:
            poster.save_asset(cache_folder, response.content)
            if upload_collection_poster(poster=poster, url=None, filepath=poster.path, movies=movies):
                poster.uploaded_to_plex = True
                poster.save_to_cache(cache_folder)
            else:
                print(f"{poster.title} was not uploaded to plex")
        elif response:
            print(f"Failed to download file: {response.status_code}")


def cache_movie(cache_folder, movies, poster):
    # if it is, check to see if both the media and a json file exist
    if poster.load_from_cache(cache_folder):
        # if both exist, check json for it being uploaded to plex
        if poster.uploaded_to_plex:
            # if uploaded do nothing
            print(f"poster {poster.path} already uploaded; nothing to do")
        else:  # if not uploaded, upload
            if upload_movie_poster(poster=poster, url=None, filepath=poster.path, movies=movies):
                poster.uploaded_to_plex = True
                poster.save_to_cache(cache_folder)
            else:
                print(f"{poster.title} was not uploaded to plex")
    else:  # if not cached, download
        try:
            response = requests.get(url=poster.url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0"})
        except Exception as e:
            print(f"Something happened downloading file at url: '{poster.url}'. {e}")
        if response and response.status_code == 200:
            poster.save_asset(cache_folder, response.content)
            if upload_movie_poster(poster=poster, url=None, filepath=poster.path, movies=movies):
                poster.uploaded_to_plex = True
                poster.save_to_cache(cache_folder)
            else:
                print(f"{poster.title} was not uploaded to plex")
        elif response:
            print(f"Failed to download file: {response.status_code}")


def cache_tv(cache_folder, tv, poster):
    # if it is, check to see if both the media and a json file exist
    if poster.load_from_cache(cache_folder):
        # if both exist, check json for it being uploaded to plex
        if poster.uploaded_to_plex:
            # if uploaded do nothing
            print(f"poster {poster.path} already uploaded; nothing to do")
        else:  # if not uploaded, upload
            if upload_tv_poster(poster=poster, url=None, filepath=poster.path, tv=tv):
                poster.uploaded_to_plex = True
                poster.save_to_cache(cache_folder)
            else:
                print(f"{poster.title} was not uploaded to plex")
    else:  # if not cached, download
        try:
            response = requests.get(url=poster.url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0"})
        except Exception as e:
            print(f"Something happened downloading file at url: '{poster.url}'. {e}")
        if response and response.status_code == 200:
            poster.save_asset(cache_folder, response.content)
            if upload_tv_poster(poster=poster, url=None, filepath=poster.path, tv=tv):
                poster.uploaded_to_plex = True
                poster.save_to_cache(cache_folder)
            else:
                print(f"{poster.title} was not uploaded to plex")
        elif response:
            print(f"Failed to download file: {response.status_code}")


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

        if media_type == "Show":
            title = title_p.split(" (")[0]
            season = None
            is_show_backdrop, is_show_cover_art, is_season_cover_art = False, False, False
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
                is_show_cover_art = True

            showposter = MediaMetadata(title=title,
                                       url=poster_url,
                                       season=season,
                                       year=year,
                                       source="posterdb",
                                       show_cover_art=is_show_cover_art)
            showposters.append(showposter)

        elif media_type == "Movie":
            title_split = title_p.split(" (")
            if len(title_split[1]) != 5:
                title = title_split[0] + " (" + title_split[1]
            else:
                title = title_split[0]
            year = title_split[-1].split(")")[0]
                
            movieposter = MediaMetadata(title=title,
                                        url=poster_url,
                                        year=int(year),
                                        source="posterdb")
            movieposters.append(movieposter)
        
        elif media_type == "Collection":
            collectionposter = MediaMetadata(title=title_p,
                                             url=poster_url,
                                             source="posterdb")
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
        is_show_backdrop, is_show_cover_art, is_season_cover_art = False, False, False
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
                season = None
                episode = None
                is_show_backdrop = True
                file_type = "background"
            elif data["season_id"] is not None:
                season_id = data["season_id"]["id"]
                season_data = [episode for episode in episodes if episode["id"] == season_id][0]
                is_season_cover_art = True
                episode = None
                season = season_data["season_number"]
                file_type = "season_cover"
            elif data["show_id"] is not None:
                is_show_cover_art = True
                season = None
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
            showposter = MediaMetadata(title=show_name,
                                       url=poster_url,
                                       season=season,
                                       episode=episode,
                                       year=year,
                                       source="mediux",
                                       show_cover_art=is_show_cover_art,
                                       show_backdrop=is_show_backdrop,
                                       season_cover_art=is_season_cover_art)

            if check_mediux_filter(mediux_filters=mediux_filters, filter=file_type):
                showposters.append(showposter)
            else:
                print(f"{show_name} - skipping. '{file_type}' is not in 'mediux_filters'")
        
        elif media_type == "Movie":
            if "Collection" in title:
                collectionposter = MediaMetadata(title=title,
                                       url=poster_url,
                                       source="mediux")
                collectionposters.append(collectionposter)
            
            else:
                movieposter = MediaMetadata(title=title,
                                       url=poster_url,
                                       year=int(year),
                                       source="mediux")
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
    '''Scrape all pages of a user's uploads.'''
    soup = cook_soup(url) 
    pages = scrape_posterd_user_info(soup)
    
    if not pages:
        print(f"Could not determine the number of pages for {url}")
        return

    if "?" in url:
        cleaned_url = url.split("?")[0]
        url = cleaned_url
    
    for page in range(pages):
        print(f"Scraping page {page + 1}.")
        page_url = f"{url}?section=uploads&page={page + 1}"
        set_posters(page_url, tv, movies)


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
    print("relative_path", relative_path)
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
        "cache_enabled": True,
        "cache_folder": ""
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
        cache_enabled = config.get("cache_enabled", True)
        cache_folder = config.get("cache_folder", "")
        return {
            "base_url": base_url,
            "token": token,
            "tv_library": tv_library,
            "movie_library": movie_library,
            "mediux_filters": mediux_filters,
            "bulk_txt": bulk_txt,
            "cache_enabled": cache_enabled,
            "cache_folder": cache_folder
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
        "bulk_txt": bulk_txt_entry.get().strip(),
        "cache_enabled": cache_enabled_checkbox.get(),
        "cache_folder": cache_folder_text.get().strip()
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

    if cache_enabled_checkbox is not None:
        if config.get("cache_enabled"):
            cache_enabled_checkbox.select()
        else:
            cache_enabled_checkbox.deselect()

    if cache_folder_text is not None:
        cache_folder_text.delete(0, ctk.END)
        cache_folder_text.insert(0, config.get("cache_folder", []))

        
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
        if not cache_setup(gui_mode=True):
            return
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
        if not cache_setup(gui_mode=True):
            return
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
    global app, global_context_menu, scrape_button, clear_button, mediux_filters_text, bulk_import_text, base_url_entry, token_entry, status_label, url_entry, app, bulk_import_button, tv_library_text, movie_library_text, bulk_txt_entry, cache_enabled_checkbox, cache_folder_text

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

    # Cache Enabled Checkbox
    cache_enabled_label = ctk.CTkLabel(settings_tab, text="Cache Enabled", text_color="#696969", font=("Roboto", 15))
    cache_enabled_label.grid(row=6, column=0, pady=5, padx=10, sticky="w")
    cache_enabled_checkbox = ctk.CTkCheckBox(settings_tab, text="", fg_color="#1C1E1E", text_color="#A1A1A1", onvalue=True, offvalue=False)
    cache_enabled_checkbox.grid(row=6, column=1, pady=5, padx=10, sticky="ew")
    cache_enabled_checkbox.bind("<Enter>", lambda event: on_hover_in(cache_enabled_label))
    cache_enabled_checkbox.bind("<Leave>", lambda event: on_hover_out(cache_enabled_label))
    bind_context_menu(cache_enabled_checkbox)

    # Cache path
    cache_folder_label = ctk.CTkLabel(settings_tab, text="Cache Folder", text_color="#696969", font=("Roboto", 15))
    cache_folder_label.grid(row=7, column=0, pady=5, padx=10, sticky="w")
    cache_folder_text = ctk.CTkEntry(settings_tab, placeholder_text="Enter a cache folder path", fg_color="#1C1E1E",
                                     text_color="#A1A1A1", border_width=0, height=40)
    cache_folder_text.grid(row=7, column=1, pady=5, padx=10, sticky="ew")
    cache_folder_text.bind("<Enter>", lambda event: on_hover_in(cache_folder_label))
    cache_folder_text.bind("<Leave>", lambda event: on_hover_out(cache_folder_label))
    bind_context_menu(cache_folder_text)
    

    settings_tab.grid_rowconfigure(0, weight=0)
    settings_tab.grid_rowconfigure(1, weight=0)
    settings_tab.grid_rowconfigure(2, weight=0)
    settings_tab.grid_rowconfigure(3, weight=0)
    settings_tab.grid_rowconfigure(4, weight=0)
    settings_tab.grid_rowconfigure(5, weight=0) 
    settings_tab.grid_rowconfigure(6, weight=0)
    settings_tab.grid_rowconfigure(7, weight=0)
    settings_tab.grid_rowconfigure(9, weight=1)

    # ? Load and Save Buttons (Anchored to the bottom)
    load_button = create_button(settings_tab, text="Reload", command=load_and_update_ui)
    load_button.grid(row=10, column=0, pady=5, padx=5, ipadx=30, sticky="ew")
    save_button = create_button(settings_tab, text="Save", command=save_config, primary=True)
    save_button.grid(row=10, column=1, pady=5, padx=5, sticky="ew")

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
            cache_setup(gui_mode=True)
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
    
    # Check for CLI arguments regardless of interactive_cli flag
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        # Handle command-line arguments
        if command == 'gui':
            create_ui()
            cache_setup(gui_mode=True)
            tv, movies = plex_setup(gui_mode=True)

        elif command == 'bulk':
            cache_setup(gui_mode=False)
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
            cache_setup(gui_mode=False)
            tv, movies = plex_setup(gui_mode=False)
            set_posters(command, tv, movies)
    
    else:
        # If no CLI arguments, proceed with UI creation (if not in interactive CLI mode)
        if not interactive_cli:
            create_ui() 
            cache_setup(gui_mode=True)
            tv, movies = plex_setup(gui_mode=True)
        else:
            sys.stdout.reconfigure(encoding='utf-8') 
            gui_flag = (len(sys.argv) > 1 and sys.argv[1].lower() == 'gui')

            # Perform CLI plex_setup if GUI flag is not present
            if not gui_flag:
                cache_setup(gui_mode=False)
                tv, movies = plex_setup(gui_mode=False)

            # Handle interactive CLI
            interactive_cli_loop(tv, movies, bulk_txt)
