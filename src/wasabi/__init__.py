from importlib.metadata import version

from .bucket import Bucket
from .group import Group
from .user import User
from .policy import Policy
from .client import Client, Endpoint, DateTimeEncoder

__version__ = version("wasabi-cloud")

# For those people who want to leverage the
# from wasabi import * syntax:
__all__ = ["Client", "Bucket", "Group", "User", "Policy", "Endpoint", "DateTimeEncoder"]
