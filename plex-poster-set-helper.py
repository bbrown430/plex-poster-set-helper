import requests
import sys
import os.path
import json
from bs4 import BeautifulSoup
from plexapi.server import PlexServer
import plexapi.exceptions
import time
import re
import json

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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
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
    input_string = input_string.replace("\\","")
    input_string = input_string.replace("u0026", "&")

    json_start_index = input_string.find('{')
    json_end_index = input_string.rfind('}')
    json_data = input_string[json_start_index:json_end_index+1]

    parsed_dict = json.loads(json_data)
    return parsed_dict


def find_in_library(library, poster):
    for lib in library:
        try:
            if "year" in poster:
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
                print("Uploaded cover art for {} - {}.".format(poster['title'], poster['season']))
            elif poster["season"] == 0:
                upload_target = tv_show.season("Specials")
                print("Uploaded art for {} - Specials.".format(poster['title']))
            elif poster["season"] == "Backdrop":
                upload_target = tv_show
                print("Uploaded background art for {}.".format(poster['title']))
            elif poster["season"] >= 1:
                if poster["episode"] == "Cover":
                    upload_target = tv_show.season(poster["season"])
                    print("Uploaded art for {} - Season {}.".format(poster['title'], poster['season']))
                elif poster["episode"] is None:
                    upload_target = tv_show.season(poster["season"])
                    print("Uploaded art for {} - Season {}.".format(poster['title'], poster['season']))
                elif poster["episode"] is not None:
                    try:
                        upload_target = tv_show.season(poster["season"]).episode(poster["episode"])
                        print("Uploaded art for {} - Season {} Episode {}.".format(poster['title'], poster['season'], poster['episode']))
                    except:
                        print("{} - Season {} Episode {} not found, skipping.".format(poster['title'], poster['season'], poster['episode']))
            if poster["season"] == "Backdrop":
                upload_target.uploadArt(url=poster['url'])
            else:
                upload_target.uploadPoster(url=poster['url'])
            if poster["source"] == "posterdb":
                time.sleep(6) # too many requests prevention
        except:
            print("{} - Season {} not found, skipping.".format(poster['title'], poster['season']))


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


def scrape_mediux(soup):
    base_url = "https://mediux.pro/_next/image?url=https%3A%2F%2Fapi.mediux.pro%2Fassets%2F"
    quality_suffix = "&w=3840&q=80"
    
    scripts = soup.find_all('script')

    media_type = None
    showposters = []
    movieposters = []
    collectionposters = []
    poster_data = []
        
    for script in scripts:
        if 'filename_disk' in script.text:
            if 'title' in script.text:
                if 'Set Link\\' not in script.text:
                    data_dict = parse_string_to_dict(script.text)
                    poster_data.append(data_dict)
    
    for data in poster_data:
        if data["show_id"] is not None or data["show_id_backdrop"] is not None or data["episode_id"] is not None or data["season_id"] is not None or data["show_id"] is not None:
            media_type = "Show"
        else:
            media_type = "Movie"
                    
    for data in poster_data:        
        if media_type == "Show":
            if data["fileType"] == "title_card":
                identifier = data["title"].split(" - ")[1]
                pattern = r'S(\d+) E(\d+)'
                match = re.search(pattern, identifier)
                if match:
                    season = int(match.group(1))
                    episode = int(match.group(2))
            elif data["fileType"] == "backdrop":
                season = "Backdrop"
                episode = None
            elif data["season_id"] is not None:
                season = int((data["title"].split("Season "))[1])
                episode = "Cover"
            elif data["show_id"] is not None:
                season = "Cover"
                episode = None

        elif media_type == "Movie":
            if " (" in data["title"]:
                title_split = data["title"].split(" (")
                if len(title_split[1]) >= 8:
                    title = title_split[0] + " (" + title_split[1]
                else:
                    title = title_split[0]
                year = title_split[-1].split(")")[0]
            else:
                title = data["title"]
            
        image_stub = data["filename_disk"]
        poster_url = f"{base_url}{image_stub}{quality_suffix}"
        title = title_cleaner(data["title"])
        
        if media_type == "Show":
            showposter = {}
            showposter["title"] = title
            showposter["season"] = season
            showposter["episode"] = episode
            showposter["url"] = poster_url
            showposter["source"] = "mediux"
            showposters.append(showposter)
        
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
    if ("theposterdb.com" in url) and ("set" in url or "user" in url):
        soup = cook_soup(url)
        return scrape_posterdb(soup)
    elif ("mediux.pro" in url) and ("sets" in url):
        soup = cook_soup(url)
        return scrape_mediux(soup)
    else:
        sys.exit("Poster set not found. Check the link you are inputting.")  



def is_valid_url(url):
    # Regular expression to check if the URL is valid
    regex = r"^(http|https):\/\/[^\/]+\/sets\/\d+\/?$"
    # Compile the regex pattern
    pattern = re.compile(regex)
    # Check if the URL matches the pattern
    if re.match(pattern, url):
        return True
    else:
        return False


if __name__ == "__main__":
    tv, movies = plex_setup()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command.lower() == 'bulk':
            if len(sys.argv) > 2:
                file_path = sys.argv[2]
                try:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        urls = file.readlines()
                    for url in urls:
                        url = url.strip()
                        if is_valid_url(url):
                            set_posters(url, tv, movies)
                except FileNotFoundError:
                    print("File not found. Please enter a valid file path.")
            else:
                print("Please provide the path to the file.")
        else:
            set_posters(command, tv, movies)
    else:
        while True:
            user_input = input("Enter a ThePosterDB set (or user) or a MediUX set url: ")
            
            if user_input.lower() == 'stop':
                print("Stopping...")
                break
            elif user_input.lower() == 'bulk':
                file_path = input("Enter the path to the .txt file: ")
                try:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        urls = file.readlines()
                    for url in urls:
                        url = url.strip()
                        if is_valid_url(url):
                            set_posters(url, tv, movies)
                except FileNotFoundError:
                    print("File not found. Please enter a valid file path.")
            else:
                set_posters(user_input, tv, movies)