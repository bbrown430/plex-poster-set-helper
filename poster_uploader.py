# poster_uploader.py
import time
import logging
from typing import List

logger = logging.getLogger(__name__)

def process_url(url: str, tv_libs, movie_libs):
    """Main processing function for a single URL"""
    try:
        movie_posters, show_posters, collection_posters = scrape(url)
        handle_posters(movie_posters, show_posters, collection_posters, tv_libs, movie_libs)
    except Exception as e:
        logger.error(f"Error processing {url}: {str(e)}")
        raise

def handle_posters(
    movie_posters: List[dict],
    show_posters: List[dict],
    collection_posters: List[dict],
    tv_libs,
    movie_libs
):
    """Handle different types of posters"""
    for poster in collection_posters:
        upload_collection_poster(poster, movie_libs)
        
    for poster in movie_posters:
        upload_movie_poster(poster, movie_libs)
    
    for poster in show_posters:
        upload_tv_poster(poster, tv_libs)

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