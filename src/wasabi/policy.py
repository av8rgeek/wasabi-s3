import json
import logging
from .client import Client
from botocore.exceptions import ClientError
import botocore.client


class Policy(Client):
    """
    Creates a new managed policy to attach to a group/user
    """

    def __init__(self, policy_name: str = "") -> None:
        """
        Initialize the WasabiPolicy class
        """
        if not isinstance(policy_name, str) or not policy_name.strip():
            raise ValueError("policy_name must be a non-empty string")
        super().__init__()
        self.__logger = logging.getLogger(__name__)
        self._client: botocore.client = self._create_client(self.iam_region)
        self.policy_name: str = policy_name
        self.__properties: dict = self._schema_policy
        self.__properties["name"] = policy_name
        self.__properties["arn"] = self.get_arn()
        self.__properties["document"] = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": policy_name,
                    "Effect": "Allow",
                    "Action": [],
                    "Resource": [],
                }
            ]
        }
        if self.policy_exists():
            self.__properties["version"] = self.get_policy_version_id()
            self.__properties["document"] = self.get_policy_document()
            self.__properties["is-default-version"] = self.is_default_version()
            self.__properties["actions"] = self.get_policy_actions()
            self.__properties["resources"] = self.get_policy_resources()

    def to_dict(self) -> dict:
        """
        Export the properties of the policy
        """
        return self.__properties

    def get_arn(self) -> str:
        """
        Use this to get the ARN for the bucket
        """
        try:
            sts_client: botocore.client = self._create_client(self.sts_region)
            account_id: str = sts_client.get_caller_identity()["Account"]
            return f"arn:aws:iam::{account_id}:policy/{self.policy_name}"
        except ClientError as e:
            self.__logger.error(f"Error getting ARN: {e}")
            return ""

    def policy_exists(self) -> bool:
        """
        Check if the policy exists, return a boolean value
        """
        response: bool = False
        try:
            response = bool(self._client.get_policy(PolicyArn=self.__properties["arn"]))
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchEntity":
                self.__logger.error(f"Error getting policy: {e}")
        return response

        
    def create_policy(self, document: dict):
        """
        Create a new managed policy if it does not already exist
        """
        policy: dict = {}
        try:
            policy= self._client.create_policy(PolicyName=self.policy_name, PolicyDocument=json.dumps(document))
            self.__properties["arn"] = policy["Policy"]["Arn"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityAlreadyExists":
                self.__logger.error(f"Policy already exists")
                policy = self.get_policy()
            else:
                self.__logger.error(f"Error creating policy: {e}")
        return policy

    def update_policy(
        self, document: dict
    ) -> dict:  # TODO: Verify function return type
        return self._client.create_policy_version(
            PolicyArn=self.__properties["arn"], PolicyDocument=json.dumps(document), SetAsDefault=True
        )

    def get_policy_version_id(self) -> str:
        policy_version: str = ""
        try:
            policy: dict = self._client.get_policy(PolicyArn=self.__properties["arn"])
            policy_version = policy["Policy"]["DefaultVersionId"]
        except ClientError as e:
            self.__logger.error(f"Error getting policy version: {e}")
        return policy_version

    def is_default_version(self) -> bool:
        arn = self.__properties["arn"]
        version = self.__properties["version"]
        response: dict = {}
        answer: bool = False
        try:
            response = self._client.get_policy_version(PolicyArn=arn, VersionId=version)
            answer = bool(response["PolicyVersion"]["IsDefaultVersion"])
        except ClientError as e:
            self.__logger.error(f"Error getting policy version: {e}")
        return answer

    def get_policy(self) -> dict:
        """
        Queries the Wasabi IAM API and returns a specific managed policy.  The
        policy document is not available through this method due to boto3 limitations.
        """        
        policy: dict = {}
        try:
            policy = self._client.get_policy(PolicyArn=self.__properties["arn"])
            policy = policy["Policy"]
        except ClientError as e:
            self.__logger.error(f"Error getting policy: {e}")
        return policy

    def get_policy_document(self) -> dict:
        """
        Returns the policy document stored in self.__properties["document"].
        """
        policy: dict = {}
        document: dict = {}
        arn = self.__properties["arn"]
        version = self.__properties["version"]
        if self.policy_exists():
            policy = self._client.get_policy_version(PolicyArn=arn, VersionId=version)
            document = policy["PolicyVersion"]["Document"]
        return document

    def get_policy_actions(self) -> list:
        """
        Returns the actions allowed by the policy document in
        in self.__properties["document"].
        """
        return self.__properties["document"]["Statement"][0]["Action"]

    def get_policy_resources(self) -> list:
        """
        Returns the resources that the policy document applies to
        in self.__properties["document"].
        """
        return self.__properties["document"]["Statement"][0]["Resource"]

    def delete_policy(self) -> None:
        """
        Delete the managed policy.
        This will only succeed if it not attached to any groups or users.
        """
        if self.policy_exists():
            try:
                self._client.delete_policy(PolicyArn=self.__properties["arn"])
            except ClientError as e:
                self.__logger.error(f"Error deleting policy: {e}")
