import plex_poster_set_helper
import pytest

def test_scrapeposterdb_set_tv_series():
    soup = plex_poster_set_helper.cook_soup("https://theposterdb.com/set/8846")
    movieposters, showposters, collectionposters = plex_poster_set_helper.scrape_posterdb(soup)
    assert len(movieposters) == 0
    assert len(collectionposters) == 0
    assert len(showposters) == 10
    for showposter in showposters:
        assert showposter["title"] == "Brooklyn Nine-Nine"
        assert showposter["year"] == 2013
        assert showposter["episode"] == None
        assert showposter["season"] == "Cover" or (showposter["season"] >= 0 and showposter["season"] <= 8) 
        assert showposter["source"] == "posterdb"
        
def test_scrapeposterdb_set_movie_collection():
    soup = plex_poster_set_helper.cook_soup("https://theposterdb.com/set/13035")
    movieposters, showposters, collectionposters = plex_poster_set_helper.scrape_posterdb(soup)
    assert len(movieposters) == 3
    assert len(collectionposters) == 1
    assert len(showposters) == 0
    for collectionposter in collectionposters:
        assert collectionposter["title"] == "The Dark Knight Collection"
        assert collectionposter["source"] == "posterdb"
        
def test_scrape_mediux_set_tv_series():
    soup = plex_poster_set_helper.cook_soup("https://mediux.pro/sets/9242")
    movieposters, showposters, collectionposters = plex_poster_set_helper.scrape_mediux(soup)
    assert len(movieposters) == 0
    assert len(collectionposters) == 0
    assert len(showposters) == 11
    backdrop_count = 0
    episode_count = 0
    cover_count = 0
    for showposter in showposters:
        assert showposter["title"] == "Mr. & Mrs. Smith"
        assert showposter["year"] == 2024
        assert showposter["source"] == "mediux"
        if (isinstance(showposter["episode"], int)):
            episode_count+=1
        elif showposter["episode"] == "Cover":
            cover_count+=1
        elif showposter["season"] == "Cover":
            cover_count+=1
        elif showposter["season"] == "Backdrop":
            backdrop_count+=1
    assert backdrop_count == 1
    assert episode_count == 8
    assert cover_count == 2

def test_scrape_mediux_set_tv_series_long():
    soup = plex_poster_set_helper.cook_soup("https://mediux.pro/sets/13427")
    movieposters, showposters, collectionposters = plex_poster_set_helper.scrape_mediux(soup)
    assert len(movieposters) == 0
    assert len(collectionposters) == 0
    assert len(showposters) == 264
    backdrop_count = 0
    episode_count = 0
    cover_count = 0
    for showposter in showposters:
        assert showposter["title"] == "Modern Family"
        assert showposter["year"] == 2009
        assert showposter["source"] == "mediux"
        if (isinstance(showposter["episode"], int)):
            episode_count+=1
        elif showposter["episode"] == "Cover":
            cover_count+=1
        elif showposter["season"] == "Cover":
            cover_count+=1
        elif showposter["season"] == "Backdrop":
            backdrop_count+=1
    assert backdrop_count == 1
    assert episode_count == 250
    assert cover_count == 13

        
test_scrape_mediux_set_tv_series()