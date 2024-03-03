import requests
import sys
import os.path
import json
from bs4 import BeautifulSoup
from plexapi.server import PlexServer
import plexapi.exceptions
import time

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
        try:
            tv = plex.library.section(tv_library)
        except plexapi.exceptions.NotFound:
            sys.exit(f'TV library named "{tv_library}" not found. Please check the "tv_library" in config.json, and consult the readme.md.')
        try:
            movies = plex.library.section(movie_library)
        except:
            sys.exit(f'Movie library named "{movie_library}" not found. Please check the "movie_library" in config.json, and consult the readme.md.')
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

def scrape_posters(url):
    movieposters = []
    showposters = []
    collectionposters = []
    
    if ("theposterdb.com" in url) and ("set" in url):
        soup = cook_soup(url)
    else:
        sys.exit("Poster set not found. Check the link you are inputting.")
    
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
            else:
                split_season = "Cover"
            
            showposter = {}
            showposter["title"] = title
            showposter["url"] = poster_url
            showposter["season"] = split_season
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
            movieposters.append(movieposter)
        
        elif media_type == "Collection":
            collectionposter = {}
            collectionposter["title"] = title_p
            collectionposter["url"] = poster_url
            collectionposters.append(collectionposter)
    
    return movieposters, showposters, collectionposters


def upload_tv_poster(poster, tv):
    try:
        tv_show = tv.get(poster["title"])
        try:
            if poster["season"] == "Cover":
                upload_target = tv_show
                print(f"Uploading cover art for {poster['title']} - {poster['season']}.")
            elif poster["season"] == "Special":
                upload_target = tv_show.season("Specials")
                print(f"Uploading art for {poster['title']} - Specials.")
            else:
                upload_target = tv_show.season(poster["season"])
                print(f"Uploading art for {poster['title']} - Season {poster['season']}.")
            upload_target.uploadPoster(url=poster['url'])
            time.sleep(6) # too many requests prevention
        except:
            print(f"{poster['title']} - {poster['season']} not found, skipping.")
    except:
        print(f"{poster['title']} not found, skipping.")


def upload_movie_poster(poster, movies):
    try:
        plex_movie = movies.get(poster["title"], year=poster["year"])
        plex_movie.uploadPoster(poster["url"])
        print(f'Uploaded art for {poster["title"]}.')
        time.sleep(6) # too many requests prevention
    except:
        print(f"{poster['title']} not found in Plex library.")

def upload_collection_poster(poster, movies):
    try:
        movie_collections = movies.collections()
    except:
        print("No collections found in the movie_library selected.")
    found = False
    for plex_collection in movie_collections:
        if plex_collection.title == poster["title"]:
            plex_collection.uploadPoster(poster["url"])
            print(f'Uploading art for {poster["title"]}.')
            found = True
            time.sleep(6) # too many requests prevention
            break
    if not found:   
        print(f"{poster['title']} not found in Plex library.")

def set_posters(url, tv, movies):
    movieposters, showposters, collectionposters = scrape_posters(url)
    
    for poster in collectionposters:
        upload_collection_poster(poster, tv, movies)
        
    for poster in movieposters:
        upload_movie_poster(poster, movies)
        
    for poster in showposters:
        upload_tv_poster(poster, tv)
        
if __name__ == "__main__":
    tv, movies = plex_setup()
    
    while True:
        user_input = input("Enter theposterdb set url (type 'stop' to end): ")
        
        if user_input.lower() == 'stop':
            print("Stopping...")
            break

        set_posters(user_input, tv, movies)