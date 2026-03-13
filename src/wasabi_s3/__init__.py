from importlib.metadata import version

from .bucket import Bucket
from .group import Group
from .user import User
from .policy import Policy
from .client import Client, Endpoint, DateTimeEncoder

__version__ = version("wasabi-s3-sdk")

# For those people who want to leverage the
# from wasabi_s3 import * syntax:
__all__ = ["Client", "Bucket", "Group", "User", "Policy", "Endpoint", "DateTimeEncoder"]
