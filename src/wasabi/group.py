import json
import logging
from .client import Client
from botocore.exceptions import ClientError
import botocore.client


class Group(Client):
    def __init__(self, group_name: str) -> None:
        if not isinstance(group_name, str) or not group_name.strip():
            raise ValueError("group_name must be a non-empty string")
        super().__init__()
        self.__logger = logging.getLogger(__name__)
        self._client: botocore.client.BaseClient = self._create_client(self.iam_region)
        self.group_name: str = group_name
        self.arn: str = ""
        self.__properties: dict = self._schema_group
        self.__properties["name"] = group_name
        if self.group_exists():
            self.__properties["arn"] = self.arn
            # TODO: Is this really the best way to set the arn?
            self.__properties["members"] = self.get_members_arn()
            self.__properties["attached-policies"] = self.get_attached_policies()
            self.__properties["inline-policies"] = self.get_inline_group_policies()

    def to_dict(self) -> dict:
        return self.__properties

    def group_exists(self) -> bool:
        group_exists: bool = False
        group_list: dict = self.get_groups()
        for group in group_list:
            if group["GroupName"] == self.group_name:
                self.arn: str = group["Arn"]
                # TODO: Is this really the best way to set the arn?
                group_exists = True
        return group_exists

    def create_group(self) -> bool:
        group_created: bool = False
        if not self.group_exists():
            response: dict = self._client.create_group(GroupName=self.group_name)
            self.arn: str = response["Group"]["Arn"]
            # TODO: Is this really the best way to set the arn?
            self.__properties["arn"] = self.arn
            group_created = True
        return group_created

    def get_group(self) -> dict:
        """
        Get the group by name. Test for existence first.
        """
        group: dict = {}
        if self.group_exists():
            try:
                group = self._client.get_group(GroupName=self.group_name)
                self.arn = group["Group"]["Arn"]  # TODO: Is this really the best way to set the arn?
            except ClientError as e:
                if e.response["Error"]["Code"] != "NoSuchEntity":
                    self.__logger.error(f"Error getting group: {e}")
        return group

    def get_members_username(self) -> list[str]:
        """
        Return the users in the group as a list of usernames
        """
        members: list[str] = []
        try:
            users: list = self._client.get_group(GroupName=self.group_name)["Users"]
            for user in users:
                members.append(user["UserName"])
        except ClientError as e:
            self.__logger.error(f"Error getting group members: {e}")
        return members

    def get_members_arn(self) -> list[str]:
        """
        Return the users in the group as a list of ARNs
        """
        members: list[str] = []
        try:
            users: list = self._client.get_group(GroupName=self.group_name)["Users"]
            for user in users:
                members.append(user["Arn"])
        except ClientError as e:
            self.__logger.error(f"Error getting group members: {e}")
        return members

    def delete_group(self) -> bool:
        response: bool = False
        if self.group_exists():
            try:
                for user in self.get_members_username():
                    self.remove_member(username=user)
                for policy in self.get_attached_policies():
                    self.detach_managed_policy(policy_arn=policy)
                self._client.delete_group(GroupName=self.group_name)
                self.__properties["members"] = []
                self.__properties["attached-policies"] = []
                response = True
            except ClientError as e:
                self.__logger.error(f"Error deleting group: {e}")
        return response

    def get_inline_group_policies(self) -> dict:
        policies: dict = {}
        try:
            policy_names: dict = self._client.list_group_policies(GroupName=self.group_name)
            for policy_name in policy_names["PolicyNames"]:
                policy: dict = self._client.get_group_policy(
                    GroupName=self.group_name, PolicyName=policy_name
                )
                policies[policy_name] = policy["PolicyDocument"]
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchEntity":
                self.__logger.error(f"Error getting inline group policies: {e}")
            else:
                self.__logger.warning(f"No inline policies for group {self.group_name}")
        return policies

    def get_inline_group_policy(self, policy_name: str) -> dict:
        """
        Return a single inline group policy document by name.
        Checks local properties first, falls back to fetching from the API.
        """
        response: dict = {}
        if policy_name in self.__properties["inline-policies"]:
            response = self.__properties["inline-policies"][policy_name]
        else:
            policies: dict = self.get_inline_group_policies()
            if policy_name in policies:
                response = policies[policy_name]
        return response

    def put_inline_group_policy(self, policy: dict) -> dict:
        return_value: dict = {}
        policy_name = policy["Statement"][0]["Sid"]
        try:
            return_value = self._client.put_group_policy(GroupName=self.group_name, PolicyName=policy_name, PolicyDocument=json.dumps(policy))
            self.__properties["inline-policies"][policy_name] = policy
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchEntity":
                self.__logger.error(f"Error writing inline group policy: {e}")
        return return_value

    def delete_inline_group_policy(self, inline_policy_name: str = "") -> bool:
        response: bool = False
        if self.get_inline_group_policies():
            try:
                self._client.delete_group_policy(GroupName=self.group_name, PolicyName=inline_policy_name)
                self.__properties["inline-policies"] = {}
                response = True
            except ClientError as e:
                self.__logger.error(f"Error deleting inline group policy: {e}")
        else:
            self.__logger.warning(f"No inline policies for group {self.group_name}")
        return response

    def get_attached_policies(self) -> list[str]:
        policies: list = []
        try:
            attached_policies: dict = self._client.list_attached_group_policies(
                GroupName=self.group_name
            )
            for policy in attached_policies["AttachedPolicies"]:
                policies.append(policy["PolicyArn"])
        except ClientError as e:
            self.__logger.error(f"Error getting attached policies: {e}")
        return policies

    def attach_managed_policy(self, policy_arn: str) -> bool:
        response: bool = False
        try:
            self._client.attach_group_policy(
                GroupName=self.group_name, PolicyArn=policy_arn
            )
            self.__properties["attached-policies"].append(policy_arn)
            response = True
        except ClientError as e:
            self.__logger.error(f"Error attaching managed policy: {e}")
        return response

    def detach_managed_policy(self, policy_arn: str) -> bool:
        response: bool = False
        try:
            self._client.detach_group_policy(
                GroupName=self.group_name, PolicyArn=policy_arn
            )
            self.__properties["attached-policies"].remove(policy_arn)
            response = True
        except ClientError as e:
            self.__logger.error(f"Error detaching managed policy: {e}")
        return response

    def add_member(self, username: str) -> bool:
        response: bool = False
        try:
            waiter = self._client.get_waiter('user_exists')
            self._client.add_user_to_group(GroupName=self.group_name, UserName=username)
            waiter.wait(UserName=username)
            self.__properties["members"].append(username)
            response = True
        except ClientError as e:
            self.__logger.error(f"Error adding member: {e}")
        return response

    def remove_member(self, username: str) -> bool:
        response: bool = False
        try:
            self._client.remove_user_from_group(
                GroupName=self.group_name, UserName=username
            )
            self.__properties["members"].remove(username)
            response = True
        except ClientError as e:
            self.__logger.error(f"Error removing member: {e}")
        return response
