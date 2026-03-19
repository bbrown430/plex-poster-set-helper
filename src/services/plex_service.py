"""Plex service for managing Plex server connections and operations."""

from typing import List, Optional, Tuple
import xml.etree.ElementTree

from plexapi.server import PlexServer
import plexapi.exceptions
import requests

from ..core.config import Config


class PlexService:
    """Service for interacting with Plex Media Server."""
    
    def __init__(self, config: Config = None):
        """Initialize Plex service.
        
        Args:
            config: Configuration object containing Plex settings.
        """
        self.config = config
        self.plex: Optional[PlexServer] = None
        self.tv_libraries: List = []
        self.movie_libraries: List = []
    
    def setup(self, gui_mode: bool = False) -> Tuple[List, List]:
        """Setup Plex server connection and libraries.
        
        Args:
            gui_mode: Whether running in GUI mode for error handling.
            
        Returns:
            Tuple of (tv_libraries, movie_libraries).
        """
        if not self.config or not self.config.base_url or not self.config.token:
            error_msg = "Invalid Plex token or base URL. Please provide valid values in config.json or via the GUI."
            self._handle_error(error_msg, gui_mode)
            return None, None
        
        try:
            self.plex = PlexServer(self.config.base_url, self.config.token)
        except requests.exceptions.RequestException as e:
            self._handle_error(f"Unable to connect to Plex server: {str(e)}", gui_mode)
            return None, None
        except plexapi.exceptions.Unauthorized as e:
            self._handle_error(f"Invalid Plex token: {str(e)}", gui_mode)
            return None, None
        except xml.etree.ElementTree.ParseError as e:
            self._handle_error(f"Received invalid XML from Plex server: {str(e)}", gui_mode)
            return None, None
        except Exception as e:
            self._handle_error(f"Unexpected error: {str(e)}", gui_mode)
            return None, None
        
        # Setup TV libraries
        self.tv_libraries = self._setup_libraries(
            self.config.tv_library, 
            "TV library",
            gui_mode
        )
        
        # Setup movie libraries
        self.movie_libraries = self._setup_libraries(
            self.config.movie_library,
            "Movie library",
            gui_mode
        )
        
        return self.tv_libraries, self.movie_libraries
    
    def _setup_libraries(self, library_names: any, library_type: str, gui_mode: bool) -> List:
        """Setup library sections.
        
        Args:
            library_names: String or list of library names.
            library_type: Type description for error messages.
            gui_mode: Whether in GUI mode.
            
        Returns:
            List of library objects.
        """
        if isinstance(library_names, str):
            library_names = [library_names]
        elif not isinstance(library_names, list):
            error_msg = f"{library_type} must be either a string or a list"
            self._handle_error(error_msg, gui_mode)
            return []
        
        libraries = []
        for lib_name in library_names:
            try:
                plex_lib = self.plex.library.section(lib_name)
                libraries.append(plex_lib)
            except plexapi.exceptions.NotFound as e:
                error_msg = f'{library_type} named "{lib_name}" not found: {str(e)}'
                self._handle_error(error_msg, gui_mode)
        
        return libraries
    
    def find_in_library(self, libraries: List, title: str, year: Optional[int] = None) -> Optional[List]:
        """Find item in library by title and optional year.
        
        Args:
            libraries: List of library objects to search.
            title: Title to search for.
            year: Optional year to filter by.
            
        Returns:
            List of found items or None.
        """
        from difflib import get_close_matches
        
        # Check if there's a manual mapping for this title
        mapped_title = self.config.title_mappings.get(title, title)
        if mapped_title != title:
            print(f"ℹ Using title mapping: '{title}' -> '{mapped_title}'")
        
        items = []
        
        # Try exact year, then previous year, then next year
        # Help reduce mismatches due to release date differences that were resulting in unnecessary fuzzy matches
        def fetch_with_year_window(library, target_title, target_year):
            years_to_try = [target_year, target_year - 1, target_year + 1]
            
            for y in years_to_try:
                try:
                    found = library.get(target_title, year=y)
                    if found:
                        if y != target_year:
                            print(f"ℹ Found '{target_title}' with year {y} (requested {target_year})")
                        return found
                except:
                    continue
            return None
        
        # Try exact match first with mapped title
        for lib in libraries:
            try:
                if year is not None:
                    library_item = fetch_with_year_window(lib, mapped_title, year)
                else:
                    library_item = lib.get(mapped_title)
                
                if library_item:
                    items.append(library_item)
            except:
                pass
        
        if items:
            return items
        
        # Try fuzzy matching if exact match failed
        for lib in libraries:
            try:
                all_titles = [item.title for item in lib.all()]
                matches = get_close_matches(mapped_title, all_titles, n=1, cutoff=0.8)
                
                if matches:
                    fuzzy_title = matches[0]
                    print(f"ℹ Fuzzy matched '{mapped_title}' to '{fuzzy_title}'")
                    library_item = None
                    
                    # Try with year first if provided
                    if year is not None:
                        library_item = fetch_with_year_window(lib, fuzzy_title, year)
                    
                        # If strictly failed year window, fallback to ANY year
                        if not library_item:
                            print(f"ℹ Year mismatch for '{fuzzy_title}', trying without year filter")
                            try:
                                library_item = lib.get(fuzzy_title)
                            except:
                                pass
                    else:
                        library_item = lib.get(fuzzy_title)
                    
                    if library_item:
                        items.append(library_item)
            except Exception as e:
                pass
        
        if items:
            return items
        
        print(f"{title} not found, skipping.")
        return None
    
    def find_collection(self, libraries: List, title: str) -> Optional[List]:
        """Find collection in library by title.
        
        Args:
            libraries: List of library objects to search.
            title: Collection title to search for.
            
        Returns:
            List of found collections or None.
        """
        collections = []
        
        # Try different title variations
        search_titles = [title]
        
        # If title ends with " Collection", also try without it
        if title.endswith(" Collection"):
            search_titles.append(title[:-11].strip())
        # If title doesn't end with " Collection", also try adding it
        else:
            search_titles.append(f"{title} Collection")
        
        for lib in libraries:
            try:
                movie_collections = lib.collections()
                for plex_collection in movie_collections:
                    # Check exact matches first
                    if plex_collection.title in search_titles:
                        collections.append(plex_collection)
                        continue
                    
                    # Try case-insensitive match
                    for search_title in search_titles:
                        if plex_collection.title.lower() == search_title.lower():
                            collections.append(plex_collection)
                            break
            except:
                pass
        
        if collections:
            return collections
        
        # If no exact matches found, print available collections for debugging
        if not collections:
            print(f"Available collections in library: {[c.title for lib in libraries for c in lib.collections()][:10]}")
        
        return None
    
    def _handle_error(self, message: str, gui_mode: bool):
        """Handle errors consistently.
        
        Args:
            message: Error message.
            gui_mode: Whether in GUI mode.
        """
        if gui_mode:
            # In GUI mode, we'll need to handle this with a callback
            # For now, just print
            print(message)
        else:
            print(message)
    
    def get_items_by_label(self, label: str) -> List:
        """Get all items with a specific label.
        
        Args:
            label: Label to search for.
            
        Returns:
            List of items with the specified label.
        """
        items = []
        
        # Search in all configured libraries
        all_libraries = self.tv_libraries + self.movie_libraries
        
        for library in all_libraries:
            try:
                # Search for items with the label
                labeled_items = library.search(label=label)
                items.extend(labeled_items)
            except Exception as e:
                print(f"Error searching library {library.title}: {str(e)}")
        
        return items
    
    def remove_label_from_items(self, items: List, label: str) -> int:
        """Remove a label from a list of items.
        
        Note: Only shows have labels, not their seasons/episodes.
        
        Args:
            items: List of Plex items.
            label: Label to remove.
            
        Returns:
            Number of items successfully processed.
        """
        count = 0
        for item in items:
            try:
                item.removeLabel(label)
                count += 1
            except Exception as e:
                # Silently continue if label doesn't exist
                pass
        
        return count
    
    def delete_posters_from_items(self, items: List) -> int:
        """Reset items to use their default posters.
        
        Note: This does not delete uploaded poster files from Plex's database,
        it only selects the default poster from metadata agents.
        Use a tool like ImageMaid to clean up orphaned uploaded files.
        
        Args:
            items: List of Plex items.
            
        Returns:
            Number of items successfully processed.
        """
        count = 0
        for item in items:
            # If this is a show, also reset all its labeled seasons and episodes
            if item.type == 'show':
                count += self._reset_show_and_children(item)
            else:
                count += self._reset_single_item(item)
        
        return count
    
    def _reset_show_and_children(self, show) -> int:
        """Reset a show and all its seasons/episodes.
        
        Args:
            show: TV show item.
            
        Returns:
            Number of items successfully processed.
        """
        count = 0
        
        # Reset the show poster itself
        count += self._reset_single_item(show)
        
        # Reset ALL seasons and episodes (they don't have labels, only the show does)
        try:
            for season in show.seasons():
                # Reset season poster
                count += self._reset_single_item(season)
                
                # Reset all episodes in this season
                try:
                    for episode in season.episodes():
                        count += self._reset_single_item(episode)
                except Exception as e:
                    print(f"⚠ Could not process episodes in season {season.index}: {str(e)}")
        except Exception as e:
            print(f"✗ Error processing seasons for {show.title}: {str(e)}")
        
        return count
    
    def _reset_single_item(self, item) -> int:
        """Reset a single item's poster and background art to default.
        
        Args:
            item: Plex item to reset.
            
        Returns:
            1 if successful, 0 if failed.
        """
        try:
            # Unlock the poster/art so we can modify it
            try:
                item.edit(**{'poster.locked': 0, 'art.locked': 0})
            except:
                pass  # If locking not supported, continue anyway
            
            # Reset poster
            all_posters = item.posters()
            
            if all_posters:
                # Find the first non-uploaded poster (from agents/providers)
                default_poster = None
                
                for poster in all_posters:
                    if poster.provider != 'upload':
                        default_poster = poster
                        break
                
                # Set the default poster as active
                if default_poster:
                    try:
                        item.setPoster(default_poster)
                        item_desc = f"{item.title}"
                        if item.type == 'episode':
                            item_desc = f"episode {item.title}"
                        print(f"✓ Reset to default poster: {item_desc}")
                    except Exception as e:
                        print(f"✗ Could not set default poster for {item.title}: {str(e)}")
                else:
                    print(f"⚠ No default poster found for: {item.title} (only uploaded posters exist)")
            else:
                print(f"ℹ No posters found for: {item.title}")
            
            # Reset background art (for shows, movies, etc.)
            # Episodes don't typically have background art
            if item.type in ['show', 'movie', 'season']:
                try:
                    all_arts = item.arts()
                    
                    if all_arts:
                        # Find the first non-uploaded art (from agents/providers)
                        default_art = None
                        
                        for art in all_arts:
                            if art.provider != 'upload':
                                default_art = art
                                break
                        
                        # Set the default art as active
                        if default_art:
                            try:
                                item.setArt(default_art)
                                print(f"✓ Reset to default background: {item.title}")
                            except Exception as e:
                                print(f"✗ Could not set default background for {item.title}: {str(e)}")
                        else:
                            print(f"⚠ No default background found for: {item.title} (only uploaded backgrounds exist)")
                except Exception as e:
                    # Don't fail the whole operation if background reset fails
                    print(f"ℹ Could not reset background for {item.title}: {str(e)}")
            
            return 1
        except Exception as e:
            print(f"✗ Error processing {item.title}: {str(e)}")
            return 0