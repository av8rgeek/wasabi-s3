import json
import requests
import logging
from .client import Client, Endpoint, S3_ENDPOINTS
import botocore.client
import botocore.waiter
from botocore.exceptions import ClientError
from requests_aws4auth import AWS4Auth


class Bucket(Client):
    """
    This bucket is for creating, deleting, and managing individual Wasabi buckets.
    """
    def __init__(self, bucket_name: str, region: str = "", billing_data: dict | None = None) -> None:
        if not isinstance(bucket_name, str) or not bucket_name.strip():
            raise ValueError("bucket_name must be a non-empty string")
        self.__logger = logging.getLogger(__name__)
        if billing_data is None:
            billing_data = {}
        # Deal with making sure the region has a valid value
        if region == "":
            region = Endpoint.to_lower("us-east-1")
            self.endpoint: str = Endpoint[Endpoint.to_upper(region)].value
        else:
            if Endpoint.to_upper(region) in Endpoint.__members__:
                region = Endpoint.to_lower(region)
                endpoint: str = Endpoint[Endpoint.to_upper(region)].value
                if endpoint in S3_ENDPOINTS:
                    self.endpoint = endpoint
                else:
                    self.__logger.exception(f"Invalid Wasabi S3 region ({region})")
        super().__init__()
        region = Endpoint.to_lower(region)
        self.bucket_name: str = bucket_name
        self._client: botocore.client.BaseClient = self._create_client(region)
        self.__properties: dict = self._schema_bucket
        self.__properties["name"] = bucket_name
        self.__properties["arn"] = f"arn:aws:s3:::{self.__properties['name']}"
        self.__properties["region"] = region
        if self.bucket_exists():
            self.__properties["region"] = self.get_bucket_location()
            self.__properties["bucket_policy"] = self.get_bucket_policy()
            self.__properties["lifecycle-rules"] = self.get_lifecycle()
            self.__properties["versioning"] = self.get_versioning()
            self.__properties["gb_used"] = self.get_size_gb(billing_data=billing_data)
            self.__properties["object_count"] = self.get_object_count(billing_data=billing_data)
        self.arn: str = self.__properties["arn"]

    def to_dict(self) -> dict:
        """
        Export the properties of the bucket
        """
        return self.__properties

    def update_properties(self) -> None:
        """
        Update the properties of the bucket
        """
        if self.bucket_exists():
            self.__properties["region"] = self.get_bucket_location()
            self.__properties["bucket_policy"] = self.get_bucket_policy()
            self.__properties["lifecycle-rules"] = self.get_lifecycle()
            self.__properties["versioning"] = self.get_versioning()

    def bucket_exists(self) -> bool:
        """
        Check if the bucket exists in any region
        """
        bucket_exists: bool = False
        response: dict = self._client.list_buckets()
        for bucket in response["Buckets"]:
            if bucket["Name"] == self.bucket_name:
                bucket_exists = True
        return bucket_exists

    def get_bucket_location(self) -> str:
        """
        Get the location of a bucket, corrects for the caller providing
        the wrong region when the class was instantiated
        """
        location: str = ""
        try:
            bucket_location: dict = self._client.get_bucket_location(
                Bucket=self.bucket_name
            )
            location = bucket_location["LocationConstraint"]
            # Wasabi returns None when the LocationConstraint for us-east-1
            # This is an AWS SDK quirk
            if location is None:
                location = "us-east-1"
            else:
                if location != self.__properties["region"]:
                    self.__logger.debug("Region value was incorrect. Correcting.")
                    self.__properties["region"] = location
                else:
                    location = self.__properties["region"]
            self.endpoint = Endpoint[Endpoint.to_upper(location)].value
            self._client = self._create_client(location)
        except ClientError as e:
            self.__logger.error(f"Error getting bucket location: {e}")
        return location

    def create_bucket(self) -> bool:
        """
        Create a new bucket, if it does not exist
        """
        return_value = False
        if self.bucket_exists():
            self.__logger.warning(f"Bucket {self.bucket_name} already exists")
        else:
            self.__logger.debug(f"Creating bucket: {self.bucket_name}")
            try:
                waiter: botocore.waiter = self._client.get_waiter("bucket_exists")
                self._client.create_bucket(Bucket=self.bucket_name)
                waiter.wait(Bucket=self.bucket_name)
                self.__properties["region"] = self.get_bucket_location()
                return_value = True
            except ClientError as e:
                self.__logger.error(f"Error creating bucket: {e}")
        return return_value

    def delete_bucket(self) -> bool:
        """
        Delete the bucket, if it exists.
        Non-empty buckets cannot not be deleted.
        """
        response: bool = False
        if not self.bucket_exists():
            self.__logger.warning(f"Bucket {self.bucket_name} does not exist, skipping")
            response = True
        else:
            try:
                waiter: botocore.waiter = self._client.get_waiter("bucket_not_exists")
                self._client.delete_bucket(Bucket=self.bucket_name)
                waiter.wait(Bucket=self.bucket_name)
                response = True
            except ClientError as e:
                if e.response["Error"]["Code"] == "BucketNotEmpty":
                    self.__logger.error(f"Bucket {self.bucket_name} is not empty")
        return response

    def force_delete_bucket(self) -> bool:
        """
        Delete the bucket, even if it is not empty.
        """
        response: bool = False
        if not self.bucket_exists():
            self.__logger.warning(f"Bucket {self.bucket_name} does not exist, skipping")
            response = True
        else:
            try:
                waiter: botocore.waiter = self._client.get_waiter("bucket_not_exists")
                url: str = f"https://{self.endpoint.split('/')[-1]}/{self.bucket_name}"
                params: dict = {"force_delete": "true"}
                credentials: AWS4Auth = AWS4Auth(
                    self._access_key_id,
                    self._secret_access_key,
                    self.__properties["region"],
                    "s3",
                )
                http_response: requests.Response = requests.delete(
                    url, params=params, auth=credentials, timeout=self.request_timeout
                )
                if http_response.status_code == 204:
                    waiter.wait(Bucket=self.bucket_name)
                    response = True
                else:
                    self.__logger.error(
                        f"Error deleting bucket: ({http_response.status_code}) {http_response.text}"
                    )
            except ClientError as e:
                self.__logger.error(f"Error deleting bucket: {e}")
        return response

    def get_bucket_policy(self) -> dict:
        """
        Returns the bucket policy as a dict
        Note the policy is a string in the response, but we convert it to a dict

        If there is no bucket policy, return an empty dict
        """
        try:
            bucket_policy: dict = self._client.get_bucket_policy(
                Bucket=self.bucket_name
            )
            return json.loads(bucket_policy["Policy"])
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
                return {}
            self.__logger.error(f"Error getting bucket policy: {e}")
            return {}

    def get_lifecycle(self) -> dict:
        """
        Returns the bucket lifecycle configuration as a dict
        """
        lifecycle: dict = {}
        try:
            lifecycle = self._client.get_bucket_lifecycle_configuration(
                Bucket=self.bucket_name
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchLifecycleConfiguration":
                self.__logger.error(f"Error getting bucket lifecycle: {e}")
        return lifecycle

    def get_versioning(self) -> bool:
        """
        Returns the versioning status of the bucket
        """
        response: bool = False
        try:
            versioning: dict = self._client.get_bucket_versioning(Bucket=self.bucket_name)
            if "Status" in versioning.keys():
                if versioning["Status"] == "Enabled":
                    response = True
        except ClientError as e:
            self.__logger.error(f"Error getting versioning: {e}")
        return response

    def set_versioning(self, enabled: bool) -> bool:
        """
        Enable or suspend versioning on the bucket.
        """
        response: bool = False
        status: str = "Enabled" if enabled else "Suspended"
        try:
            self._client.put_bucket_versioning(
                Bucket=self.bucket_name,
                VersioningConfiguration={"Status": status}
            )
            self.__properties["versioning"] = enabled
            response = True
        except ClientError as e:
            self.__logger.error(f"Error setting versioning: {e}")
        return response

    def set_lifecycle(self, rules: dict) -> bool:
        """
        Set the lifecycle configuration on the bucket.
        """
        response: bool = False
        try:
            self._client.put_bucket_lifecycle_configuration(
                Bucket=self.bucket_name,
                LifecycleConfiguration=rules
            )
            self.__properties["lifecycle-rules"] = rules
            response = True
        except ClientError as e:
            self.__logger.error(f"Error setting lifecycle: {e}")
        return response

    def set_bucket_policy(self, policy: dict) -> bool:
        """
        Set the bucket policy.
        """
        response: bool = False
        try:
            self._client.put_bucket_policy(
                Bucket=self.bucket_name,
                Policy=json.dumps(policy)
            )
            self.__properties["bucket_policy"] = policy
            response = True
        except ClientError as e:
            self.__logger.error(f"Error setting bucket policy: {e}")
        return response

    def delete_bucket_policy(self) -> bool:
        """
        Remove the bucket policy.
        """
        response: bool = False
        try:
            self._client.delete_bucket_policy(Bucket=self.bucket_name)
            self.__properties["bucket_policy"] = {}
            response = True
        except ClientError as e:
            self.__logger.error(f"Error deleting bucket policy: {e}")
        return response

    def list_objects(self) -> dict:
        """
        List the objects in the bucket
        """
        try:
            return self._client.list_objects(Bucket=self.bucket_name)
        except ClientError as e:
            self.__logger.error(f"Error listing objects: {e}")
            return {}

    def put_object(self, key: str, body: str) -> bool:
        """
        Put an object in the bucket
        """
        response: bool = False
        try:
            waiter: botocore.waiter = self._client.get_waiter("object_exists")
            self._client.put_object(Bucket=self.bucket_name, Key=key, Body=body)
            waiter.wait(Bucket=self.bucket_name, Key=key)
            response = True
        except ClientError as e:
            self.__logger.error(f"Error putting object: {e}")
        return response

    def delete_object(self, key: str) -> bool:
        """
        Delete an object from the bucket
        """
        response: bool = False
        try:
            waiter: botocore.waiter = self._client.get_waiter("object_not_exists")
            self._client.delete_object(Bucket=self.bucket_name, Key=key)
            waiter.wait(Bucket=self.bucket_name, Key=key)
            response = True
        except ClientError as e:
            self.__logger.error(f"Error deleting object: {e}")
        return response

    def get_size_gb(self, billing_data: dict | None = None) -> float:
        """
        Returns the size of the bucket in GB rounded to 3 decimal places.
        Since getting the billing data is a slow process, we only get it if we have not
        retrieved it previously.
        """
        total_storage_gb: float = 0
        if billing_data:
            self._billing_data = billing_data
        if not self._billing_data:
            self.__logger.info("Getting billing data in the bucket class")
            self._billing_data = self.get_billing_data()
        for bucket in self._billing_data:
            if bucket["Bucket"] == self.bucket_name:
                active_storage: int = (
                    bucket["PaddedStorageSizeBytes"]
                    + bucket["MetadataStorageSizeBytes"]
                )
                active_storage_gb: float = active_storage / 1073741824
                deleted_storage_gb: float = (
                    bucket["DeletedStorageSizeBytes"] / 1073741824
                )
                total_storage_gb = active_storage_gb + deleted_storage_gb
        return round(total_storage_gb, 3)

    def get_object_count(self, billing_data: dict | None = None) -> int:
        """
        Get the number of objects in the bucket
        Since getting the billing data is a slow process, we only get it if we have not
        retrieved it previously.
        """
        total_objects: int = 0
        if billing_data:
            self._billing_data = billing_data
        if not self._billing_data:
            self.__logger.info("Getting billing data in the bucket class")
            self._billing_data = self.get_billing_data()
        for bucket in self._billing_data:
            if bucket["Bucket"] == self.bucket_name:
                active: int = bucket["NumBillableObjects"]
                deleted: int = bucket["NumBillableDeletedObjects"]
                total_objects = active + deleted
        return total_objects
