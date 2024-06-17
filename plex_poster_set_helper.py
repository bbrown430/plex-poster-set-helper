import requests
import sys
import os.path
import json
from bs4 import BeautifulSoup
from plexapi.server import PlexServer
import plexapi.exceptions
import time
import re

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
    for lib in library:
        try:
            if poster["year"] is not None:
                library_item = lib.get(poster["title"], year=poster["year"])
            else:
                library_item = lib.get(poster["title"])
            return library_item
        except:
            pass
    print(f"{poster['title']} not found, skipping.")
    return None


def find_collection(library, poster):
    found = False
    for lib in library:
        try:
            movie_collections = lib.collections()
        except:
            pass
        for plex_collection in movie_collections:
            if plex_collection.title == poster["title"]:
                return plex_collection
    if not found:   
        print(f"{poster['title']} not found in Plex library.")
        

def upload_tv_poster(poster, tv):
    tv_show = find_in_library(tv, poster)
    if tv_show is not None:
        try:
            if poster["season"] == "Cover":
                upload_target = tv_show
                print(f"Uploaded cover art for {poster['title']} - {poster['season']}.")
            elif poster["season"] == 0:
                upload_target = tv_show.season("Specials")
                print(f"Uploaded art for {poster['title']} - Specials.")
            elif poster["season"] == "Backdrop":
                upload_target = tv_show
                print(f"Uploaded background art for {poster['title']}.")
            elif poster["season"] >= 1:
                if poster["episode"] == "Cover":
                    upload_target = tv_show.season(poster["season"])
                    print(f"Uploaded art for {poster['title']} - Season {poster['season']}.")
                elif poster["episode"] is None:
                    upload_target = tv_show.season(poster["season"])
                    print(f"Uploaded art for {poster['title']} - Season {poster['season']}.")
                elif poster["episode"] is not None:
                    try:
                        upload_target = tv_show.season(poster["season"]).episode(poster["episode"])
                        print(f"Uploaded art for {poster['title']} - Season {poster['season']} Episode {poster['episode']}.")
                    except:
                        print(f"{poster['title']} - {poster['season']} Episode {poster['episode']} not found, skipping.")
            if poster["season"] == "Backdrop":
                upload_target.uploadArt(url=poster['url'])
            else:
                upload_target.uploadPoster(url=poster['url'])
            if poster["source"] == "posterdb":
                time.sleep(6) # too many requests prevention
        except:
            print(f"{poster['title']} - Season {poster['season']} not found, skipping.")


def upload_movie_poster(poster, movies):
    movie = find_in_library(movies, poster)
    if movie is not None:
        movie.uploadPoster(poster["url"])
        print(f'Uploaded art for {poster["title"]}.')
        if poster["source"] == "posterdb":
            time.sleep(6) # too many requests prevention


def upload_collection_poster(poster, movies):
    collection = find_collection(movies, poster)
    if collection is not None:
        collection.uploadPoster(poster["url"])
        print(f'Uploaded art for {poster["title"]}.')
        if poster["source"] == "posterdb":
                time.sleep(6) # too many requests prevention


def set_posters(url, tv, movies):
    movieposters, showposters, collectionposters = scrape(url)
    
    for poster in collectionposters:
        upload_collection_poster(poster, movies)
        
    for poster in movieposters:
        upload_movie_poster(poster, movies)
    
    for poster in showposters:
        upload_tv_poster(poster, tv)
    
    # multi-library requires more debugging
    """
    for lib in tv:
        #for poster in collectionposters:
            #upload_collection_poster(poster, [lib])
        
        for poster in showposters:
            upload_tv_poster(poster, [lib])

    for lib in movies:
        for poster in collectionposters:
            upload_collection_poster(poster, [lib])
        
        for poster in movieposters:
            upload_movie_poster(poster, [lib])
    """

def scrape_posterdb_set_link(soup):
    try:
        view_all_div = soup.find('a', class_='rounded view_all')['href']
    except:
        return None
    return view_all_div

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
                split_season = title_p.split(" - ")[1]
                if split_season == "Specials":
                    season = 0
                else:
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
                season_data = [episode for episode in episodes if episode["season_number"] == season][0]
                episode_data = [episode for episode in season_data["episodes"] if episode["id"] == episode_id][0]
                episode = episode_data["episode_number"]
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
        if("set" in url or "user" in url):
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


# Checks if url does not start with "//", "#", or is blank
def is_not_comment(url):
    regex = r"^(?!\/\/|#|^$)"
    pattern = re.compile(regex)
    return True if re.match(pattern, url) else False

  
def parse_urls(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            urls = file.readlines()
        for url in urls:
            url = url.strip()
            if is_not_comment(url):
                set_posters(url, tv, movies)
    except FileNotFoundError:
        print("File not found. Please enter a valid file path.")


if __name__ == "__main__":
    tv, movies = plex_setup()
    
    # arguments were provided
    if len(sys.argv) > 1:
        command = sys.argv[1]
        # bulk command was used
        if command.lower() == 'bulk':
            if len(sys.argv) > 2:
                file_path = sys.argv[2]
                parse_urls(file_path)
            else:
                print("Please provide the path to the .txt file.")
        # a single url was provided
        else:
            set_posters(command, tv, movies)
    # user input
    else:
        while True:
            user_input = input("Enter a ThePosterDB set (or user) or a MediUX set url: ")
            
            if user_input.lower() == 'stop':
                print("Stopping...")
                break
            elif user_input.lower() == 'bulk':
                file_path = input("Enter the path to the .txt file: ")
                parse_urls(file_path)
            else:
                set_posters(user_input, tv, movies)
