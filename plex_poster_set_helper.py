import requests
import math
import sys
import os.path
import json
from bs4 import BeautifulSoup
from plexapi.server import PlexServer
import plexapi.exceptions
import time
import re
import customtkinter as ctk
import threading


# Global variables for UI elements
app = None
base_url_entry = None
token_entry = None
tv_library_entry = None
movie_library_entry = None
url_entry = None
status_label = None
mediux_filters_text = None
error_label = None
bulk_import_text = None
bulk_import_button = None
clear_button = None
scrape_button = None


def plex_setup():
    if os.path.exists("config.json"):
        try:
            config = json.load(open("config.json"))
            base_url = config["base_url"]
            token = config["token"]
            tv_library = config["tv_library"]
            movie_library = config["movie_library"]
        except:
            sys.exit("Error with config.json file. Please consult the readme.md.") 
        try:
            plex = PlexServer(base_url, token)
        except requests.exceptions.RequestException:
            sys.exit('Unable to connect to Plex server. Please check the "base_url" in config.json, and consult the readme.md.')
        except plexapi.exceptions.Unauthorized:
            sys.exit('Invalid Plex token. Please check the "token" in config.json, and consult the readme.md.')
        if isinstance(tv_library, str):
            tv_library = [tv_library] 
        elif not isinstance(tv_library, list):
            sys.exit("tv_library must be either a string or a list")
        tv = []
        for tv_lib in tv_library:
            try:
                plex_tv = plex.library.section(tv_lib)
                tv.append(plex_tv)
            except plexapi.exceptions.NotFound:
                sys.exit(f'TV library named "{tv_lib}" not found. Please check the "tv_library" in config.json, and consult the readme.md.')        
        if isinstance(movie_library, str):
            movie_library = [movie_library] 
        elif not isinstance(movie_library, list):
            sys.exit("movie_library must be either a string or a list")
        movies = []
        for movie_lib in movie_library:
            try:
                plex_movie = plex.library.section(movie_lib)
                movies.append(plex_movie)
            except plexapi.exceptions.NotFound:
                sys.exit(f'Movie library named "{movie_lib}" not found. Please check the "movie_library" in config.json, and consult the readme.md.')
        return tv, movies
    else:
        sys.exit("No config.json file found. Please consult the readme.md.")   



def cook_soup(url):  
    headers = { 
               'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36', 'Sec-Ch-Ua-Mobile': '?0', 'Sec-Ch-Ua-Platform': 'Windows' 
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
    
    print(f"{poster['title']} not found, skipping.")
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


def upload_tv_poster(poster, tv):
    tv_show_items = find_in_library(tv, poster)
    if tv_show_items:
        for tv_show in tv_show_items:
            try:
                if poster["season"] == "Cover":
                    upload_target = tv_show
                    print(f"Uploaded cover art for {poster['title']} - {poster['season']} in {tv_show.librarySectionTitle} library.")
                elif poster["season"] == 0:
                    upload_target = tv_show.season("Specials")
                    print(f"Uploaded art for {poster['title']} - Specials in {tv_show.librarySectionTitle} library.")
                elif poster["season"] == "Backdrop":
                    upload_target = tv_show
                    print(f"Uploaded background art for {poster['title']} in {tv_show.librarySectionTitle} library.")
                elif poster["season"] >= 1:
                    if poster["episode"] == "Cover":
                        upload_target = tv_show.season(poster["season"])
                        print(f"Uploaded art for {poster['title']} - Season {poster['season']} in {tv_show.librarySectionTitle} library.")
                    elif poster["episode"] is None:
                        upload_target = tv_show.season(poster["season"])
                        print(f"Uploaded art for {poster['title']} - Season {poster['season']} in {tv_show.librarySectionTitle} library.")
                    elif poster["episode"] is not None:
                        try:
                            upload_target = tv_show.season(poster["season"]).episode(poster["episode"])
                            print(f"Uploaded art for {poster['title']} - Season {poster['season']} Episode {poster['episode']} in {tv_show.librarySectionTitle} library..")
                        except:
                            print(f"{poster['title']} - {poster['season']} Episode {poster['episode']} not found in {tv_show.librarySectionTitle} library, skipping.")
                if poster["season"] == "Backdrop":
                    try:
                        upload_target.uploadArt(url=poster['url'])
                    except:
                        print("Unable to upload last poster.")
                else:
                    try:
                        upload_target.uploadPoster(url=poster['url'])
                    except:
                        print("Unable to upload last poster.")
                if poster["source"] == "posterdb":
                    time.sleep(6)  # too many requests prevention
            except:
                print(f"{poster['title']} - Season {poster['season']} not found in {tv_show.librarySectionTitle} library, skipping.")
    else:
        print(f"{poster['title']} not found in any library.")


def upload_movie_poster(poster, movies):
    movie_items = find_in_library(movies, poster)
    if movie_items:
        for movie_item in movie_items:
            try:
                movie_item.uploadPoster(poster["url"])
                print(f'Uploaded art for {poster["title"]} in {movie_item.librarySectionTitle} library.')
                if poster["source"] == "posterdb":
                    time.sleep(6)  # too many requests prevention
            except:
                print(f'Unable to upload art for {poster["title"]} in {movie_item.librarySectionTitle} library.')
    else:
        print(f'{poster["title"]} not found in any library.')


def upload_collection_poster(poster, movies):
    collection_items = find_collection(movies, poster)
    if collection_items:
        for collection in collection_items:
            try:
                collection.uploadPoster(poster["url"])
                print(f'Uploaded art for {poster["title"]} in {collection.librarySectionTitle} library.')
                if poster["source"] == "posterdb":
                    time.sleep(6)  # too many requests prevention
            except:
                print(f'Unable to upload art for {poster["title"]} in {collection.librarySectionTitle} library.')
    else:
        print(f'{poster["title"]} collection not found in any library.')


def set_posters(url, tv, movies):
    movieposters, showposters, collectionposters = scrape(url)

    for poster in collectionposters:
        upload_collection_poster(poster, movies)
        
    for poster in movieposters:
        upload_movie_poster(poster, movies)
    
    for poster in showposters:
        upload_tv_poster(poster, tv)

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
            
            showposter = {}
            showposter["title"] = title
            showposter["url"] = poster_url
            showposter["season"] = season
            showposter["episode"] = None
            showposter["year"] = year
            showposter["source"] = "posterdb"
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
            movieposters.append(movieposter)
        
        elif media_type == "Collection":
            collectionposter = {}
            collectionposter["title"] = title_p
            collectionposter["url"] = poster_url
            collectionposter["source"] = "posterdb"
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
                    episode = int(title.split(" E")[1])
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
            else:
                print(f"{show_name} - skipping. '{file_type}' is not in 'mediux_filters'")
        
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
    regex = r"^(?!\/\/|#|^$)"
    pattern = re.compile(regex)
    return True if re.match(pattern, url) else False


def parse_urls(bulk_import_list):
    valid_urls = []
    for line in bulk_import_list:
        url = line.strip()
        if url and not url.startswith(("#", "//")):
            valid_urls.append(url)

    # Process each valid URL, including user URLs
    for url in valid_urls:
        if "/user/" in url:  # If it's a /user/ URL, scrape user data
            print(f"Scraping user data from: {url}")
            scrape_entire_user(url)
        else:
            print(f"Returning non-user URL: {url}")
            # If it's not a /user/ URL, return it as before
            return valid_urls

    # Return the list of valid URLs, unchanged for non-user URLs
    return valid_urls






#! ---------------------- GUI TESTING SECTION ----------------------



# * UI helper functions ---

def update_status(message, color="white"):
    '''Update the status label with a message and color.'''
    app.after(0, lambda: status_label.configure(text=message, text_color=color))


def update_error(message):
    '''Update the error label with a message.'''
    app.after(0, lambda: error_label.configure(text=message, text_color="red"))      
      
def clear_url():
    url_entry.delete(0, ctk.END)
    status_label.configure(text="URL cleared.", text_color="orange")      
     
     
      
# * Configuration file I/O functions  ---

def load_config():
    '''Load the configuration file into the UI fields.'''
    try:
        config = json.load(open("config.json"))
        base_url = config["base_url"]
        token = config["token"]
        tv_library = config["tv_library"]
        movie_library = config["movie_library"]
        mediux_filters = config["mediux_filters"]

        base_url_entry.delete(0, ctk.END)
        base_url_entry.insert(0, base_url)

        token_entry.delete(0, ctk.END)
        token_entry.insert(0, token)

        tv_library_entry.delete(0, ctk.END)
        tv_library_entry.insert(0, tv_library)

        movie_library_entry.delete(0, ctk.END)
        movie_library_entry.insert(0, movie_library)

        mediux_filters_text.delete(1.0, ctk.END)
        mediux_filters_text.insert(ctk.END, ", ".join(mediux_filters))

    except Exception as e:
        error_label.configure(text=f"Error loading config: {str(e)}", text_color="red")


def save_config():
    '''Save the configuration from the UI fields to the file.'''
    config = {
        "base_url": base_url_entry.get(),
        "token": token_entry.get(),
        "tv_library": tv_library_entry.get(),
        "movie_library": movie_library_entry.get(),
        "mediux_filters": mediux_filters_text.get(1.0, ctk.END).strip().split(", "),
    }
    try:
        with open("config.json", "w") as f:
            json.dump(config, f, indent=4)
        status_label.configure(
            text="Configuration saved successfully!", text_color="green"
        )
    except Exception as e:
        status_label.configure(text=f"Error saving config: {str(e)}", text_color="red")    
    


# * Threaded functions for scraping and setting posters ---  

def run_url_scrape_thread():
    '''Run the URL scrape in a separate thread.'''
    global scrape_button, clear_button, bulk_import_button
    url = url_entry.get()
    
    if not url:
        status_label.configure(text="Please enter a valid URL.")
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
        app.after(
            0,
            lambda: status_label.configure(
                text="No bulk import entries found.", text_color="red"
            ),
        )
        return
    
    scrape_button.configure(state="disabled")
    clear_button.configure(state="disabled")
    bulk_import_button.configure(state="disabled")
    
    threading.Thread(target=process_bulk_import, args=(valid_urls,)).start()



# * Processing functions for scraping and setting posters ---

def process_scrape_url(url):
    '''Process the URL scrape.'''
    try:
        tv, movies = plex_setup()
        soup = cook_soup(url)

        update_status(f"Scraping: {url}", color="#A1C6EA")
        set_posters(url, tv, movies)
        update_status(f"Posters successfully set for: {url}", color="green")
        
    except Exception as e:
        update_status(f"Error: {e}", color="red")
    finally:
        app.after(
            0,
            lambda: [
                scrape_button.configure(state="normal"),
                clear_button.configure(state="normal"),
                bulk_import_button.configure(state="normal"),
            ],
        )


def process_bulk_import(valid_urls):
    '''Process the bulk import scrape.'''
    try:
        tv, movies = plex_setup()
        for i, url in enumerate(valid_urls):
            status_text = f"Processing item {i+1} of {len(valid_urls)}: {url}"
            update_status(status_text, color="#A1C6EA")
            set_posters(url, tv, movies)
            update_status(f"Completed: {url}", color="green")

        update_status("Bulk import scraping completed.", color="green")
    except Exception as e:
        update_status(f"Error during bulk import: {e}", color="red")
    finally:
        app.after(
            0,
            lambda: [
                scrape_button.configure(state="normal"),
                clear_button.configure(state="normal"),
                bulk_import_button.configure(state="normal"),
            ],
        )



# * Bulk import file I/O functions ---

def load_bulk_import_file():
    '''Load the bulk import file into the text area.'''
    try:
        with open("bulk_import.txt", "r", encoding="utf-8") as file:
            content = file.read()
        bulk_import_text.delete(1.0, ctk.END)
        bulk_import_text.insert(ctk.END, content)
    except FileNotFoundError:
        bulk_import_text.delete(1.0, ctk.END)
        bulk_import_text.insert(ctk.END, "File not found or empty.")


def save_bulk_import_file():
    '''Save the bulk import text area content to a file.'''
    try:
        with open("bulk_import.txt", "w", encoding="utf-8") as file:
            file.write(bulk_import_text.get(1.0, ctk.END).strip())
        status_label.configure(text="Bulk import file saved!", text_color="green")
    except Exception as e:
        status_label.configure(
            text=f"Error saving bulk import file: {str(e)}", text_color="red"
        )



# * Main UI Creation function ---

def create_ui():
    '''Create the main UI window.'''
    global scrape_button, clear_button, mediux_filters_text, error_label, bulk_import_text, base_url_entry, token_entry, tv_library_entry, movie_library_entry, status_label, url_entry, app, bulk_import_button

    app = ctk.CTk()
    app.title("Plex Poster Upload Helper")
    app.geometry("800x500")

    #! Create Tabview
    tabview = ctk.CTkTabview(app)
    tabview.pack(fill="both", expand=True, padx=2, pady=0)

    #! Settings Tab --
    settings_tab = tabview.add("Settings")

    settings_tab.grid_columnconfigure(0, weight=1)
    settings_tab.grid_columnconfigure(1, weight=2)

    # ? Form Fields for Settings Tab
    base_url_label = ctk.CTkLabel(settings_tab, text="Plex Base URL:")
    base_url_label.grid(row=0, column=0, pady=5, padx=10, sticky="w")
    base_url_entry = ctk.CTkEntry(settings_tab, placeholder_text="Enter Plex Base URL")
    base_url_entry.grid(row=0, column=1, pady=5, padx=10, sticky="ew")

    token_label = ctk.CTkLabel(settings_tab, text="Plex Token:")
    token_label.grid(row=1, column=0, pady=5, padx=10, sticky="w")
    token_entry = ctk.CTkEntry(settings_tab, placeholder_text="Enter Plex Token")
    token_entry.grid(row=1, column=1, pady=5, padx=10, sticky="ew")

    tv_library_label = ctk.CTkLabel(settings_tab, text="TV Library Name:")
    tv_library_label.grid(row=2, column=0, pady=5, padx=10, sticky="w")
    tv_library_entry = ctk.CTkEntry(settings_tab, placeholder_text="Enter TV Library Name")
    tv_library_entry.grid(row=2, column=1, pady=5, padx=10, sticky="ew")

    movie_library_label = ctk.CTkLabel(settings_tab, text="Movie Library Name:")
    movie_library_label.grid(row=3, column=0, pady=5, padx=10, sticky="w")
    movie_library_entry = ctk.CTkEntry(settings_tab, placeholder_text="Enter Movie Library Name")
    movie_library_entry.grid(row=3, column=1, pady=5, padx=10, sticky="ew")

    mediux_filters_label = ctk.CTkLabel(settings_tab, text="Mediux Filters:")
    mediux_filters_label.grid(row=4, column=0, pady=5, padx=10, sticky="w")
    mediux_filters_text = ctk.CTkTextbox(settings_tab, height=5, width=40)
    mediux_filters_text.grid(row=4, column=1, pady=5, padx=10, sticky="ew")

    settings_tab.grid_rowconfigure(0, weight=0)
    settings_tab.grid_rowconfigure(1, weight=0)
    settings_tab.grid_rowconfigure(2, weight=0)
    settings_tab.grid_rowconfigure(3, weight=0)
    settings_tab.grid_rowconfigure(4, weight=0)
    settings_tab.grid_rowconfigure(5, weight=1)

    # ? Load and Save Buttons (Anchored to the bottom)
    load_button = ctk.CTkButton(settings_tab, text="Load Config", command=load_config)
    load_button.grid(row=6, column=0, pady=10, padx=10, sticky="ew")
    save_button = ctk.CTkButton(settings_tab, text="Save Config", command=save_config)
    save_button.grid(row=6, column=1, pady=10, padx=10, sticky="ew")
    settings_tab.grid_rowconfigure(5, weight=1)

    #! Bulk Import Tab --
    bulk_import_tab = tabview.add("Bulk Import")
    bulk_import_tab.grid_columnconfigure(0, weight=2)
    bulk_import_tab.grid_columnconfigure(1, weight=0)
    bulk_import_tab.grid_columnconfigure(2, weight=0)

    # ? Bulk URL Text Area
    bulk_import_label = ctk.CTkLabel(bulk_import_tab, text="Bulk Import Text:")
    bulk_import_label.grid(row=0, column=0, pady=5, padx=10, sticky="w")
    bulk_import_text = ctk.CTkTextbox(
        bulk_import_tab,
        height=15,
        wrap="none",
        corner_radius=10,
        border_width=2,
        state="normal",
    )
    bulk_import_text.grid(row=1, column=0, padx=10, pady=5, sticky="nsew", columnspan=2)

    bulk_import_tab.grid_rowconfigure(0, weight=0)  # ? Label row doesn't stretch
    bulk_import_tab.grid_rowconfigure(1, weight=1)  # ? Text area row expands and fills available space
    bulk_import_tab.grid_rowconfigure(2, weight=0)  # ? Button row takes minimal space

    # ? Button row: Load, Save, Run buttons
    load_bulk_button = ctk.CTkButton(bulk_import_tab, text="Load Bulk Import File", command=load_bulk_import_file)
    load_bulk_button.grid(row=2, column=0, pady=5, padx=5, sticky="ew")
    save_bulk_button = ctk.CTkButton(bulk_import_tab, text="Save Bulk Import File", command=save_bulk_import_file)
    save_bulk_button.grid(row=2, column=1, pady=5, padx=5, sticky="ew")
    bulk_import_button = ctk.CTkButton(bulk_import_tab, text="Run Bulk Import Scrape", command=run_bulk_import_scrape_thread)
    bulk_import_button.grid(row=3, column=0, pady=10, padx=5, sticky="ew", columnspan=3)

    #! Poster Scrape Tab --
    poster_scrape_tab = tabview.add("Poster Scrape")

    poster_scrape_tab.grid_columnconfigure(0, weight=0)
    poster_scrape_tab.grid_columnconfigure(1, weight=1)

    # ? URL entry field
    url_label = ctk.CTkLabel(poster_scrape_tab, text="Poster Scrape URL:")
    url_label.grid(row=0, column=0, pady=5, padx=5, sticky="w")
    url_entry = ctk.CTkEntry(poster_scrape_tab, placeholder_text="Enter URL for scraping posters")
    url_entry.grid(row=0, column=1, pady=5, padx=5, sticky="ew")

    # ? Buttons: Scrape and Clear
    scrape_button = ctk.CTkButton(poster_scrape_tab, text="Scrape and Set Posters", command=run_url_scrape_thread)
    scrape_button.grid(row=1, column=0, pady=5, padx=5, sticky="ew", columnspan=2)

    clear_button = ctk.CTkButton(poster_scrape_tab, text="Clear", command=clear_url)
    clear_button.grid(row=2, column=0, pady=5, padx=5, sticky="ew", columnspan=2)

    poster_scrape_tab.grid_rowconfigure(0, weight=1)  # ? URL entry field should expand and fill available space
    poster_scrape_tab.grid_rowconfigure(1, weight=0)  # ? Button row should take minimal space
    poster_scrape_tab.grid_rowconfigure(2, weight=0)  # ? Clear button should take minimal space

    #! Status and Error Labels --
    status_label = ctk.CTkLabel(app, text="", text_color="green")
    status_label.pack(side="bottom", fill="x", pady=(5))

    error_label = ctk.CTkLabel(app, text="", text_color="red")
    error_label.pack(side="bottom", fill="x", pady=5)

    #! Load configuration and bulk import data at start
    load_config()
    load_bulk_import_file()

    app.mainloop()



# * Initialization ---

if __name__ == "__main__":
    '''Main function to initialize the UI.'''
    create_ui()
