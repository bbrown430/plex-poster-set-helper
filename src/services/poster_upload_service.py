import time
import requests
import tempfile
import os
import threading
from ..core.models import PosterInfo


class PosterUploadService:
    """Service for downloading and uploading posters to Plex."""
    
    def __init__(self, plex_service):
        self.plex_service = plex_service
        self.session = requests.Session()
        # Add headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://mediux.pro/',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'same-origin',
        })
        self._item_cache = {}
        self._cache_lock = threading.Lock()
        
    def _get_cached_item(self, title, year, search_func, *args):
        """Helper to avoid hitting Plex API for the same item repeatedly."""
        cache_key = f"{title}_{year if year else 'None'}_{search_func.__name__}"
        
        with self._cache_lock:
            if cache_key not in self._item_cache:
                self._item_cache[cache_key] = search_func(*args)
        
        return self._item_cache[cache_key]
    
    def _download_image(self, url: str) -> str | None:
        """
        Download image to a temporary file.
        
        Args:
            url: Image URL to download
            
        Returns:
            Path to temporary file, or None if download failed
        """
        try:
            print(f"⬇ Downloading image from: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Create temporary file with proper suffix
            suffix = '.jpg'
            if url.lower().endswith('.png'):
                suffix = '.png'
            elif url.lower().endswith('.webp'):
                suffix = '.webp'
            
            # Create temporary file (delete=False so we can use it)
            temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            temp_path = temp_file.name
            
            # Write the image data
            temp_file.write(response.content)
            temp_file.close()
            
            # Verify file was written
            if os.path.exists(temp_path):
                file_size = os.path.getsize(temp_path)
                print(f"✓ Successfully downloaded image ({file_size:,} bytes) to {os.path.basename(temp_path)}")
                return temp_path
            else:
                print(f"✗ Failed to create temporary file")
                return None
                
        except Exception as e:
            print(f"✗ Error downloading image: {str(e)}")
            return None
    
    def _cleanup_temp_file(self, filepath: str):
        """Delete temporary file after a small delay to ensure Plex has processed it."""
        try:
            if filepath and os.path.exists(filepath):
                # Give Plex a moment to process the file
                time.sleep(0.1)
                os.remove(filepath)
                print(f"🗑 Cleaned up temporary file: {os.path.basename(filepath)}")
        except Exception as e:
            print(f"⚠ Warning: Could not delete temporary file {filepath}: {str(e)}")
    
    def _rate_limit(self, source: str):
        """Apply rate limiting based on source."""
        if source == 'mediux':
            time.sleep(1)
        elif source == 'posterdb':
            time.sleep(0.5)
    
    def _add_label(self, item, label: str):
        """Add a label to a Plex item.
        
        Args:
            item: Plex item (movie, show, season, episode, or collection)
            label: Label string to add
        """
        try:
            item.addLabel(label)
        except Exception as e:
            # Silently fail if labels aren't supported or there's an error
            pass
    
    def _add_source_labels(self, item, source: str):
        """Add both main label and source-specific label.
        Remove old source labels to prevent duplicates.
        
        Args:
            item: Plex item to label
            source: Source of the poster (mediux, posterdb, etc.)
        """
        # Remove ALL old source labels first to prevent duplicates
        try:
            # List of all possible source labels (Plex capitalizes them)
            all_source_labels = [
                'Plex_poster_set_helper_mediux',
                'Plex_poster_set_helper_posterdb'
            ]
            
            # Remove ALL source-specific labels
            for old_label in all_source_labels:
                try:
                    item.removeLabel(old_label)
                except Exception:
                    # Label might not exist, that's fine
                    pass
        except Exception:
            # Silently fail if there's an error
            pass
        
        # Add the main label and new source-specific label
        self._add_label(item, 'plex_poster_set_helper')
        self._add_label(item, f'plex_poster_set_helper_{source}')
    
    def upload_movie_poster(self, poster: PosterInfo):
        """Upload poster to a movie."""

        libraries = self.plex_service.movie_libraries    
        movie_items = self._get_cached_item(poster.title, poster.year, self.plex_service.find_in_library, libraries, poster.title, poster.year)
        if not movie_items:
            print(f'Movie {poster.title} not found, skipping.')
            return
        
        # Download the image first
        image_path = self._download_image(poster.url)
        if not image_path:
            print(f'Unable to download poster for {poster.title}')
            return
        
        try:
            for movie_item in movie_items:
                try:
                    # Read file and upload via Plex API
                    with open(image_path, 'rb') as img_file:
                        movie_item.uploadPoster(filepath=image_path)
                    # Add label to track posters uploaded by this app
                    self._add_source_labels(movie_item, poster.source)
                    print(f'✓ Uploaded art for {poster.title} in {movie_item.librarySectionTitle} library.')
                    self._rate_limit(poster.source)
                except Exception as e:
                    print(f'✗ Unable to upload art for {poster.title} in {movie_item.librarySectionTitle} library: {str(e)}')
        finally:
            # Clean up temporary file
            self._cleanup_temp_file(image_path)
    
    def upload_collection_poster(self, poster: PosterInfo):
        """Upload poster to a collection."""

        libraries = self.plex_service.movie_libraries + self.plex_service.tv_libraries
        collection_items = self._get_cached_item(poster.title, None, self.plex_service.find_collection, libraries, poster.title)
        if not collection_items:
            print(f'Collection {poster.title} not found, skipping.')
            return
        
        # Download the image first
        image_path = self._download_image(poster.url)
        if not image_path:
            print(f'Unable to download poster for {poster.title}')
            return
        
        try:
            for collection in collection_items:
                try:
                    # Read file and upload via Plex API
                    with open(image_path, 'rb') as img_file:
                        collection.uploadPoster(filepath=image_path)
                    # Add label to track posters uploaded by this app
                    self._add_source_labels(collection, poster.source)
                    print(f'✓ Uploaded art for {poster.title} in {collection.librarySectionTitle} library.')
                    self._rate_limit(poster.source)
                except Exception as e:
                    print(f'✗ Unable to upload art for {poster.title} in {collection.librarySectionTitle} library: {str(e)}')
        finally:
            # Clean up temporary file
            self._cleanup_temp_file(image_path)
    
    def _get_tv_upload_target(self, tv_show, poster: PosterInfo):
        """Determine the correct upload target for TV show poster.
        
        Returns:
            Upload target object or None if target not found.
        """
        # Episode thumbnails (title cards)
        if poster.episode is not None and isinstance(poster.episode, int):
            try:
                season_obj = tv_show.season(season=poster.season)
                episode_obj = season_obj.episode(episode=poster.episode)
                return episode_obj
            except Exception as e:
                print(f"⚠ Could not find S{poster.season}E{poster.episode}: {str(e)}")
                return None  # Don't fallback to show level
        
        # Season posters (season is int, episode is "Cover")
        if isinstance(poster.season, int) and poster.episode == "Cover":
            try:
                return tv_show.season(season=poster.season)
            except Exception as e:
                print(f"⚠ Could not find season {poster.season}: {str(e)}")
                return None
        
        # Show poster (season is "Cover")
        if poster.season == "Cover":
            return tv_show
        
        # Backdrop
        if poster.season == "Backdrop":
            return tv_show
        
        # If we have a season number but no episode info, treat as season poster
        if isinstance(poster.season, int):
            try:
                return tv_show.season(season=poster.season)
            except Exception as e:
                print(f"⚠ Could not find season {poster.season}: {str(e)}")
                return None
        
        # Default to show
        return tv_show
    
    def upload_tv_poster(self, poster: PosterInfo):
        """Upload poster to a TV show or season."""
        
        libraries = self.plex_service.tv_libraries
        tv_shows = self._get_cached_item(poster.title, poster.year, self.plex_service.find_in_library, libraries, poster.title, poster.year)
        if not tv_shows:
            print(f'TV show {poster.title} not found, skipping.')
            return
        
        # Download the image first
        image_path = self._download_image(poster.url)
        if not image_path:
            print(f'Unable to download poster for {poster.title}')
            return
        
        try:
            for tv_show in tv_shows:
                try:
                    upload_target = self._get_tv_upload_target(tv_show, poster)
                    
                    # Skip if target not found
                    if upload_target is None:
                        print(f"⊘ Skipping upload - target not found in Plex")
                        continue
                    
                    # Determine what we're uploading to
                    if poster.episode is not None and isinstance(poster.episode, int):
                        target_desc = f"{poster.title} S{poster.season}E{poster.episode}"
                    elif isinstance(poster.season, int):
                        target_desc = f"{poster.title} Season {poster.season}"
                    elif poster.season == "Backdrop":
                        target_desc = f"{poster.title} (backdrop)"
                    else:
                        target_desc = f"{poster.title} (show poster)"
                    
                    # Read file and upload via Plex API
                    with open(image_path, 'rb') as img_file:
                        if poster.season == "Backdrop":
                            upload_target.uploadArt(filepath=image_path)
                        else:
                            upload_target.uploadPoster(filepath=image_path)
                    
                    # Add label to track posters uploaded by this app
                    self._add_source_labels(upload_target, poster.source)
                    print(f"✓ Uploaded art for {target_desc}")
                    self._rate_limit(poster.source)
                except Exception as e:
                    print(f"✗ Unable to upload poster: {str(e)}")
        finally:
            # Clean up temporary file
            self._cleanup_temp_file(image_path)
    
    def process_poster(self, poster: PosterInfo):
        """Process a poster and upload it to the appropriate library."""
        if poster.is_collection():
            self.upload_collection_poster(poster)
        elif poster.is_movie():
            self.upload_movie_poster(poster)
        elif poster.is_tv_show():
            self.upload_tv_poster(poster)