"""
The WasabiUser class is used to represent and manage a single Wasabi user.
It is a child class of the Wasabi class.
"""
import logging
from .client import Client
import botocore.client
from botocore.exceptions import ClientError


class User(Client):
    def __init__(self, user_name: str = "") -> None:
        """
        Initialize the WasabiUser class.
        """
        if not isinstance(user_name, str) or not user_name.strip():
            raise ValueError("user_name must be a non-empty string")
        super().__init__()
        self.__logger = logging.getLogger(__name__)
        self._client: botocore.client.BaseClient = self._create_client(self.iam_region)
        self.username: str = user_name
        self.__properties: dict = self._schema_user
        self.__properties["name"] = user_name
        if self.user_exists():
            self.__update_arn_property()
            self.update_api_keys()
        
    def to_dict(self) -> dict:
        """
        Export the properties of the user.
        """
        return self.__properties

    def user_exists(self) -> bool:
        """
        Check if the user exists, return a boolean value.
        """
        response: bool = False
        try:
            self._client.get_user(UserName=self.username)
            response = True
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchEntity":
                self.__logger.error(f"Error checking user existence: {e}")
        return response

    def get_user(self) -> dict:
        """
        Get the user object and return it.
        """
        try:
            return self._client.get_user(UserName=self.username)
        except ClientError as e:
            self.__logger.error(f"Error getting user: {e}")
            return {}

    def create_user(self) -> dict:
        """
        Create a new user if it does not already exist.
        """
        user: dict = {}
        if not self.user_exists():
            try:
                user = self._client.create_user(UserName=self.username)
                self.__properties["arn"] = user["User"]["Arn"]
            except ClientError as e:
                self.__logger.error(f"Error creating user: {e}")
        else:
            self.__logger.warning(f"{self.username} already exists")
            user = self.get_user()
        return user

    def delete_user(self) -> bool:
        """
        Delete the user and return a boolean response.
        """
        response: bool = False
        if self.user_exists():
            try:
                if self.delete_all_api_keys():
                    self._client.delete_user(UserName=self.username)
                    response = True
            except ClientError as e:
                self.__logger.error(f"Error deleting user: {e}")
        return response

    def __update_arn_property(self) -> None:
        """
        Update the ARN property for the user.
        """
        self.__properties["arn"] = self.get_user()["User"]["Arn"]

    def get_arn(self) -> str:
        """
        Return the current user's ARN.
        """
        return self.__properties["arn"]

    def get_api_keys(self) -> dict:
        """
        Get the API keys for the user.
        """
        key: dict = {}
        try:
            response: dict = self._client.list_access_keys(UserName=self.username)
            for access_key in response["AccessKeyMetadata"]:
                key[access_key["AccessKeyId"]] = {
                    "secret-key": "",
                    "status": access_key["Status"]
                }
        except ClientError as e:
            self.__logger.error(f"Error getting API keys: {e}")
        return key

    def update_api_keys(self) -> None:
        """
        Update the user's API keys properties.
        """
        try:
            response: dict = self._client.list_access_keys(UserName=self.username)
            for access_key in response["AccessKeyMetadata"]:
                key: str = access_key["AccessKeyId"]
                if key in self.__properties["api-keys"].keys():
                    self.__properties["api-keys"][key]["status"] = access_key["Status"]
                else:
                    self.__properties["api-keys"][key] = {
                        "secret-key": "",
                        "status": access_key["Status"]
                    }
        except ClientError as e:
            self.__logger.error(f"Error updating API keys: {e}")

    def create_api_key(self) -> dict:
        """
        Create a new API key and secret for the user if they have less than 2 keys.
        """
        key: dict = {}
        if len(self.get_api_keys()) >= 2:
            self.__logger.warning("User already has 2 API keys")
        else:
            try:
                access_key: dict = self._client.create_access_key(UserName=self.username)
                self.__properties["api-keys"][access_key["AccessKey"]["AccessKeyId"]] = {
                    "secret-key": access_key["AccessKey"]["SecretAccessKey"],
                    "status": access_key["AccessKey"]["Status"],
                }
                key[access_key["AccessKey"]["AccessKeyId"]] = {
                    "secret-key": access_key["AccessKey"]["SecretAccessKey"],
                    "status": access_key["AccessKey"]["Status"],
                }
            except ClientError as e:
                self.__logger.error(f"Error creating API key: {e}")
        return key

    def delete_api_key(self, access_key: str) -> bool:
        """
        Delete an API key for the user.
        """
        response: bool = False
        try:
            self._client.delete_access_key(
                UserName=self.username, AccessKeyId=access_key
            )
            response = True
        except ClientError as e:
            self.__logger.error(f"Error deleting API key: {e}")
        return response

    def delete_all_api_keys(self) -> bool:
        """
        Delete all API keys for the user.
        """
        response: bool = False
        metadata: list = []
        try:
            metadata = self._client.list_access_keys(UserName=self.username)[
                "AccessKeyMetadata"
            ]
        except ClientError as e:
            self.__logger.error(f"Error getting API keys: {e}")
            response = False
        count: int = 0
        while count < len(metadata):
            for key in metadata:
                self.__logger.debug(f"Count: {count + 1} / {len(metadata)}")
                try:
                    self._client.delete_access_key(
                        UserName=self.username, AccessKeyId=key["AccessKeyId"]
                    )
                    count += 1
                except ClientError as e:
                    self.__logger.error(f"Error deleting API key {key['AccessKeyId']}: {e}")
        if count == len(metadata):
            response = True
            self.__properties["api-keys"] = {}
        else:
            self.__logger.warning("Not all API keys were deleted")
        return response

    def list_groups(self) -> list[str]:
        """
        List the groups the user belongs to.
        """
        groups: list[str] = []
        try:
            response: dict = self._client.list_groups_for_user(UserName=self.username)
            for group in response["Groups"]:
                groups.append(group["GroupName"])
        except ClientError as e:
            self.__logger.error(f"Error getting groups for user: {e}")
        return groups

    def enable_api_key(self, access_key: str) -> bool:
        """
        Activate an API key for the user.
        """
        response: bool = False
        try:
            self._client.update_access_key(
                UserName=self.username, AccessKeyId=access_key, Status="Active"
            )
            if access_key in self.__properties["api-keys"]:
                self.__properties["api-keys"][access_key]["status"] = "Active"
            response = True
        except ClientError as e:
            self.__logger.error(f"Error enabling API key: {e}")
        return response

    def disable_api_key(self, access_key: str) -> bool:
        """
        Deactivate an API key for the user.
        """
        response: bool = False
        try:
            self._client.update_access_key(
                UserName=self.username, AccessKeyId=access_key, Status="Inactive"
            )
            if access_key in self.__properties["api-keys"]:
                self.__properties["api-keys"][access_key]["status"] = "Inactive"
            response = True
        except ClientError as e:
            self.__logger.error(f"Error disabling API key: {e}")
        return response
