# plex_service.py
from plexapi.server import PlexServer
import plexapi.exceptions

class PlexService:
    def __init__(self, settings):
        self.settings = settings
        self._plex = None
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
        # TV Libraries
        tv_lib_names = self.settings.tv_library
        if isinstance(tv_lib_names, str):
            tv_lib_names = [tv_lib_names]
            
        for lib_name in tv_lib_names:
            try:
                self.tv_libraries.append(self._plex.library.section(lib_name))
            except plexapi.exceptions.NotFound:
                raise ValueError(f"TV library '{lib_name}' not found")

        # Movie Libraries
        movie_lib_names = self.settings.movie_library
        if isinstance(movie_lib_names, str):
            movie_lib_names = [movie_lib_names]
            
        for lib_name in movie_lib_names:
            try:
                self.movie_libraries.append(self._plex.library.section(lib_name))
            except plexapi.exceptions.NotFound:
                raise ValueError(f"Movie library '{lib_name}' not found")