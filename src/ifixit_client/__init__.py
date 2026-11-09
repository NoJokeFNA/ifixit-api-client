from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ifixit-api-client")
except PackageNotFoundError:
    __version__ = "0+unknown"

from .client import IFixitAPIClient
from .models import Guide, Image, User, Wiki
