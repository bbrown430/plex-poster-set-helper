from plexapi.server import PlexServer
import plexapi.exceptions

class PlexService:
    def __init__(self, settings):
        self.settings = settings
        self._plex = None
        self.absolute_tv_libraries = []
        self.absolute_movie_libraries = []
        self.tv_libraries = []
        self.movie_libraries = []
        self._connect()

    def _connect(self):
        """Initialize Plex connection and libraries"""
        try:
            self._plex = PlexServer(self.settings.base_url, self.settings.token)
            self._load_libraries()
        except Exception as e:
            raise RuntimeError(f"Plex connection failed: {str(e)}")

    def _load_libraries(self):
        """Load configured libraries"""
        self.absolute_tv_libraries = self._get_libraries(self.settings.tv_library)
        self.absolute_movie_libraries = self._get_libraries(self.settings.movie_library)
        
        # Default to all libraries
        self.tv_libraries = self.absolute_tv_libraries[:]
        self.movie_libraries = self.absolute_movie_libraries[:]

    def _get_libraries(self, lib_names):
        """Retrieve and validate Plex libraries."""
        libraries = []
        if isinstance(lib_names, str):
            lib_names = [lib_names]
        
        for lib_name in lib_names:
            try:
                libraries.append(self._plex.library.section(lib_name))
            except plexapi.exceptions.NotFound:
                raise ValueError(f"Library '{lib_name}' not found")
        
        return libraries

    def filter_libraries(self, quality="all"):
        """Filter libraries based on their librarySectionTitle."""
        valid_categories = {"4k", "hd", "all"}
        if quality not in valid_categories:
            raise ValueError(f"Invalid category. Choose from {valid_categories}")
        
        def is_valid(lib, category):
            title = lib.title.lower()
            return (
                category == "all" or
                (category == "4k" and "4k" in title) or
                (category == "hd" and "4k" not in title)
            )
        
        self.tv_libraries = [lib for lib in self.absolute_tv_libraries if is_valid(lib, quality)]
        self.movie_libraries = [lib for lib in self.absolute_movie_libraries if is_valid(lib, quality)]
