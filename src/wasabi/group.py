import json
import logging
from .wasabi import Wasabi, DateTimeEncoder
from botocore.exceptions import ClientError
import botocore.client


class WasabiGroup(Wasabi):
    def __init__(self, group_name: str) -> None:
        if not isinstance(group_name, str) or not group_name.strip():
            raise ValueError("group_name must be a non-empty string")
        super().__init__()
        self.__logger = logging.getLogger(__name__)
        self._client: botocore.client = self._new_client(self.iam_region)
        self.group_name: str = group_name
        self.arn: str = ""
        self.__properties: dict = self._Wasabi__schema_group.copy()
        self.__properties["name"] = group_name
        if self.group_exists():
            self.__properties["arn"] = self.arn
            # TODO: Is this really the best way to set the arn?
            self.__properties["members"] = self.get_members_arn()
            self.__properties["attached-policies"] = self.get_attached_policies()
            self.__properties["inline-policies"] = self.get_inline_group_policies()

    def export_properties(self) -> dict:
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

    def create_group(self):
        group_created: bool = False
        if not self.group_exists():
            response: dict = self._client.create_group(GroupName=self.group_name)
            self.arn: str = response["Group"]["Arn"]
            # TODO: Is this really the best way to set the arn?
            self.__properties["arn"] = self.arn
            group_created = True
        return group_created

    def get_group(self):
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

    def get_members_username(self) -> list:
        """
        Return the users in the group as a list of usernames
        """
        members: list = []
        try:
            users: list = self._client.get_group(GroupName=self.group_name)["Users"]
        except ClientError as e:
            self.__logger.error(f"Error getting group members: {e}")
            return []
        for user in users:
            members.append(user["UserName"])
        return members

    def get_members_arn(self) -> list:
        """
        Return the users in the group as a list of ARNs
        """
        members: list = []
        try:
            users: list = self._client.get_group(GroupName=self.group_name)["Users"]
        except ClientError as e:
            self.__logger.error(f"Error getting group members: {e}")
            return []
        for user in users:
            members.append(user["Arn"])
        return members

    def delete_group(self) -> None:
        if self.group_exists():
            try:
                for user in self.get_members_username():
                    self.remove_member(username=user)
                for policy in self.get_attached_policies():
                    self.detach_managed_policy(policy_arn=policy)
                self._client.delete_group(GroupName=self.group_name)
                self.__properties["members"] = []
                self.__properties["attached-policies"] = []
            except ClientError as e:
                self.__logger.error(f"Error deleting group: {e}")

    def get_inline_group_policies(self) -> dict:
        policies: dict = {}
        policy_names: dict = {}
        try:
            policy_names = self._client.list_group_policies(GroupName=self.group_name)
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
            return {}
        return policies

    def get_inline_group_policy(self) -> dict:
        return_value: dict = {}
        try:
            return_value = self._client.get_group_policy(GroupName=self.group_name)
            # self.__logger.debug(json.dumps(return_value, indent=4, cls=DateTimeEncoder))
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchEntity":
                self.__logger.error(f"Error getting inline group policy: {e}")
        return return_value

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

    def delete_inline_group_policy(self, inline_policy_name:str = "") -> None:
        if self.get_inline_group_policies():
            try:
                self._client.delete_group_policy(GroupName=self.group_name, PolicyName=inline_policy_name)
                self.__properties["inline-policies"] = {}
            except ClientError as e:
                self.__logger.error(f"Error deleting inline group policy: {e}")
        else:
            self.__logger.warning(f"No inline policies for group {self.group_name}")

    def get_attached_policies(self) -> list:
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

    def attach_managed_policy(self, policy_arn: str) -> None:
        try:
            self._client.attach_group_policy(
                GroupName=self.group_name, PolicyArn=policy_arn
            )
            self.__properties["attached-policies"].append(policy_arn)
        except ClientError as e:
            self.__logger.error(f"Error attaching managed policy: {e}")

    def detach_managed_policy(self, policy_arn: str) -> None:
        try:
            self._client.detach_group_policy(
                GroupName=self.group_name, PolicyArn=policy_arn
            )
            self.__properties["attached-policies"].remove(policy_arn)
        except ClientError as e:
            self.__logger.error(f"Error detaching managed policy: {e}")

    def add_member(self, username: str) -> None:
        try:
            waiter = self._client.get_waiter('user_exists')
            self._client.add_user_to_group(GroupName=self.group_name, UserName=username)
            waiter.wait(UserName=username)
            self.__properties["members"].append(username)
        except ClientError as e:
            self.__logger.error(f"Error adding member: {e}")

    def remove_member(self, username: str) -> None:
        try:
            self._client.remove_user_from_group(
                GroupName=self.group_name, UserName=username
            )
            self.__properties["members"].remove(username)
        except ClientError as e:
            self.__logger.error(f"Error removing member: {e}")
