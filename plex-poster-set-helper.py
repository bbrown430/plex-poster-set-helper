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


def upload_tv_poster2(poster, tv):
    tv_show = tv.get(poster["title"])
    if poster["season"] == "Cover":
        upload_target = tv_show
        print(f"Uploading cover art for {poster['title']} - {poster['season']}.")
    elif poster["season"] == "0":
        upload_target = tv_show.season("Specials")
        print(f"Uploading art for {poster['title']} - Specials.")
    elif poster["season"] == "Backdrop":
        upload_target = tv_show
        print(f"Uploading background art for {poster['title']}.")
    elif poster["season"] >= 1:
        if poster["episode"] == "Cover":
            upload_target = tv_show.season(poster["season"])
            print(f"Uploading art for {poster['title']} - Season {poster['season']}.")
        elif poster["episode"] is not None:
            upload_target = tv_show.season(poster["season"]).episode(poster["episode"])
            print(f"Uploading art for {poster['title']} - Season {poster['season']} Episode {poster['episode']}.")
    else:
        return None
    if poster["season"] != "Backdrop":
        upload_target.uploadPoster(url=poster['url'])
    elif poster["season"] == "Backdrop":
        upload_target.uploadArt(url=poster['url'])

def upload_tv_poster(poster, tv):
    try:
        tv_show = tv.get(poster["title"])
        try:
            if poster["season"] == "Cover":
                upload_target = tv_show
                print(f"Uploading cover art for {poster['title']} - {poster['season']}.")
            elif poster["season"] == 0:
                upload_target = tv_show.season("Specials")
                print(f"Uploading art for {poster['title']} - Specials.")
            elif poster["season"] == "Backdrop":
                upload_target = tv_show
                print(f"Uploading background art for {poster['title']}.")
            elif poster["season"] >= 1:
                if poster["episode"] == "Cover":
                    upload_target = tv_show.season(poster["season"])
                    print(f"Uploading art for {poster['title']} - Season {poster['season']}.")
                elif poster["episode"] is None:
                    upload_target = tv_show.season(poster["season"])
                    print(f"Uploading art for {poster['title']} - Season {poster['season']}.")
                elif poster["episode"] is not None:
                    try:
                        upload_target = tv_show.season(poster["season"]).episode(poster["episode"])
                        print(f"Uploading art for {poster['title']} - Season {poster['season']} Episode {poster['episode']}.")
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
                    poster_data.append(script.text)
    
    for data in poster_data:
        if "Season" in data:
            media_type = "Show"
            break
        else:
            media_type = "Movie"
                    
    for data in poster_data:
        metadata = data.split('title')[1].split('"')[2]
        
        if media_type == "Show":
            if " - " in metadata:
                identifier = metadata.split(" - ")[1]
                pattern = r'S(\d+) E(\d+)'
                match = re.search(pattern, identifier)
                if match:
                    season = int(match.group(1))
                    episode = int(match.group(2))
                elif "Season" in identifier:
                    season = int((identifier.split("Season "))[1].split("\\")[0])
                    episode = "Cover"
                elif "Backdrop" in identifier:
                    season = "Backdrop"
                    episode = None
            else:
                season = "Cover"
                episode = None
                
            if " (" in metadata:
                title = metadata.split(" (")[0].strip()
            elif " -" in metadata:
                title = metadata.split(" -")[0].strip()
            else:
                title = metadata.split(" \\")[0]
        
        elif media_type == "Movie":
            if " (" in metadata:
                title_split = metadata.split(" (")
                if len(title_split[1]) >= 8:
                    title = title_split[0] + " (" + title_split[1]
                else:
                    title = title_split[0]
                year = title_split[-1].split(")")[0]
            else:
                title = metadata.split(" \\")[0]
            
        image_stub = data.split('filename_disk')[1].split('"')[2].split("\\")[0]
        poster_url = f"{base_url}{image_stub}{quality_suffix}"
        
        if("\\u") in title:
            title = title.encode('utf-8').decode('unicode_escape')
        
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


if __name__ == "__main__":
    tv, movies = plex_setup()
    
    while True:
        user_input = input("Enter ThePosterDB or MediUX set url (type 'stop' to end): ")
        
        if user_input.lower() == 'stop':
            print("Stopping...")
            break

        set_posters(user_input, tv, movies)