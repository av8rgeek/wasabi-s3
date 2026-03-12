import logging
import json
from datetime import datetime, date, timezone, timedelta
from enum import Enum
from os import getenv
import requests
import boto3
import botocore.client
from botocore.exceptions import ClientError


class DateTimeEncoder(json.JSONEncoder):
    # Override the default method
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


class WasabiEndpoints(Enum):
    """
    This class is an Enum of Wasabi endpoints.  It is used when determining the
    endpoint for the Wasabi client based on the region.
    """

    S3: str = "https://s3.wasabisys.com"  # Actually the primary for us-east-1
    US_EAST_1: str = "https://s3.us-east-1.wasabisys.com"
    US_EAST_2: str = "https://s3.us-east-2.wasabisys.com"
    US_CENTRAL_1: str = "https://s3.us-central-1.wasabisys.com"
    US_WEST_1: str = "https://s3.us-west-1.wasabisys.com"
    US_WEST_2: str = "https://s3.us-west-2.wasabisys.com"
    CA_CENTRAL_1: str = "https://s3.ca-central-1.wasabisys.com"
    EU_CENTRAL_1: str = "https://s3.eu-central-1.wasabisys.com"
    EU_CENTRAL_2: str = "https://s3.eu-central-2.wasabisys.com"
    EU_WEST_1: str = "https://s3.eu-west-1.wasabisys.com"
    EU_WEST_2: str = "https://s3.eu-west-2.wasabisys.com"
    AP_NORTHEAST_1: str = "https://s3.ap-northeast-1.wasabisys.com"
    AP_NORTHEAST_2: str = "https://s3.ap-northeast-2.wasabisys.com"
    AP_SOUTHEAST_1: str = "https://s3.ap-southeast-1.wasabisys.com"
    AP_SOUTHEAST_2: str = "https://s3.ap-southeast-2.wasabisys.com"
    IAM: str = "https://iam.wasabisys.com"  # (AWS SDK)
    STS: str = "https://sts.wasabisys.com"  # (AWS SDK)
    BILLING: str = "https://billing.wasabisys.com"  # Wasabi-specific, no AWS SDK
    # CONSOLE: str = https://console.wasabisys.com"

    @staticmethod
    def to_lower(name: str) -> str:
        return name.lower().replace("_", "-")

    @staticmethod
    def to_upper(name: str = "") -> str:
        return name.upper().replace("-", "_")


WasabiEndpoints.S3_ENDPOINTS = [
    # This has to be defined outside the enum class because the WasabiEndpoints class
    # is not fully defined until the end of the class definition
    WasabiEndpoints.S3.value,
    WasabiEndpoints.US_EAST_1.value,
    WasabiEndpoints.US_EAST_2.value,
    WasabiEndpoints.US_CENTRAL_1.value,
    WasabiEndpoints.US_WEST_1.value,
    WasabiEndpoints.US_WEST_2.value,
    WasabiEndpoints.CA_CENTRAL_1.value,
    WasabiEndpoints.EU_CENTRAL_1.value,
    WasabiEndpoints.EU_CENTRAL_2.value,
    WasabiEndpoints.EU_WEST_1.value,
    WasabiEndpoints.EU_WEST_2.value,
    WasabiEndpoints.AP_NORTHEAST_1.value,
    WasabiEndpoints.AP_NORTHEAST_2.value,
    WasabiEndpoints.AP_SOUTHEAST_1.value,
    WasabiEndpoints.AP_SOUTHEAST_2.value,
]


class Wasabi:
    """
    This class is for general Wasabi operations that do not require a specific object.
    It's also the parent class for the specific classes of Wasabi objects.

    Chld classes:
    - WasabiBucket
    - WasabiGroup
    - WasabiUser
    - WasabiPolicy
    """

    def __init__(self) -> None:
        """
        Initialize the Wasabi class.  We don't need to create a client here
        because that will be set up in child classes and
        """
        self.__schema_example: str = """
An complete schema would look similar to this example:
{
    "users": [
        {
            "name": "jimbob",
            "arn": "arn:aws:iam::123456789012:user/jimbob",
            "api-keys": {
                "<WASABI_KEY_ID_1>": {
                    "secret-key": "",
                    "status": "Active"
                },
                "<WASABI_KEY_ID_2>": {
                    "secret-key": "",
                    "status": "Disabled"
                }
            }
        },
        {
            "name": "jane",
            "arn": "arn:aws:iam::123456789012:user/jane",
            "api-keys": {
                "<WASABI_KEY_ID_1>": {
                    "secret-key": "",
                    "status": "Active"
                },
                "<WASABI_KEY_ID_2>": {
                    "secret-key": "",
                    "status": "Disabled"
                }
            }
        }
    ],
    "groups": [
        {
            "name": "admins",
            "arn": "arn:aws:iam::123456789012:group/admins",
            "members": [
                "jimbob",
                "jane"
            ],
            "attached-policies": [
                "arn:aws:iam::123456789012:policy/admin-policy"
            ],
            "inline-policies": {
                "admin-policy": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": "s3:*",
                            "Resource": "*"
                        }
                    ]
                }
            }
        },
        {
            "name": "devs",
            "arn": "arn:aws:iam::123456789012:group/devs",
            "members": [
                "jimbob"
            ],
            "attached-policies": [
                "arn:aws:iam::123456789012:policy/dev-policy"
            ],
            "inline-policies": {
                "dev-policy": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": "s3:*",
                            "Resource": "*"
                        }
                    ]
                }
            }
        }
    ],
    "policies": [
        {
            "name": "admin-policy",
            "arn": "arn:aws:iam::123456789012:policy/admin-policy",
            "version": "v1",
            "is-default-version": true,
            "actions": [
                "s3:*"
            ],
            "resources": [
                "arn:aws:s3::123456789012:bucket1"
            ]
        },
        {
            "name": "dev-policy",
            "arn": "arn:aws:iam::123456789012:policy/dev-policy",
            "version": "v1",
            "is-default-version": true,
            "actions": [
                "s3:AbortMultiPartUpload",
                "s3:DeleteObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:PutObject"
            ],
            "resources": [
                "arn:aws:s3::123456789012:bucket1"
            ]
        }
    ],
    "buckets": [
        { 
            "name": "my_bucket",
            "arn": "arn:aws:s3:::my_bucket",
            "region": "us-west-1",
            "storage_class": "hot",
            "bucket_policy": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "FullAccess",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": [
                                "arn:aws:iam::123456789012:group/devs"
                            ]
                        },
                        "Action": [
                            "s3:GetObject",
                            "s3:ListBucket"
                        ],
                        "Resource": [
                            "arn:aws:s3::123456789012:my_bucket"
                            "arn:aws:s3::123456789012:my_bucket/*",
                        ]
                    }
                ]
            },
            "lifecycle-rules": {},
            "versioning": False,
            "gb_used": 1234.567,
            "object_count": 381579
        }
    ]
}
"""
        self.__schema_user: dict = {
            # Example:
            #     {
            #         "name": "jimbob",
            #         "arn": "arn:aws:iam::123456789012:user/jimbob",
            #         "api-keys": {
            #             "<WASABI_KEY_ID_1>": {
            #                 "secret-key": "",
            #                 "status": "Active"
            #             },
            #             "<WASABI_KEY_ID_2>": {
            #                 "secret-key": "",
            #                 "status": "Disabled"
            #             }
            #         }
            #     }
            "name": "",
            "arn": "",
            "api-keys": {}  #*  Max 2 keys per user
        }
        self.__schema_group: dict = {
            # Example:
            #     {
            #         "name: "admins"
            #         "arn": "arn:aws:iam::123456789012:group/admins",
            #         "members": [
            #             "jimbob",
            #             "jane"
            #         ],
            #         "attached-policies": [
            #             "arn:aws:iam::123456789012:policy/admin-policy"
            #         ],
            #         "inline-policies": {
            #             "admin-policy": {
            #                 "Version": "2012-10-17",
            #                 "Statement": [
            #                     {
            #                         "Effect": "Allow",
            #                         "Action": "s3:*",
            #                         "Resource": "*"
            #                     }
            #                 ]
            #             }
            #         }
            #     }
            "name": "",
            "arn": "",
            "members": [],
            "attached-policies": [],
            "inline-policies": {}
        }
        self.__schema_policy: dict = {
            # Example:
            #     {
            #         "name": "dev-policy": {
            #         "arn": "arn:aws:iam::123456789012:policy/dev-policy",
            #         "version": "v1",
            #         "is-default-version": true,
            #         "actions": [
            #             "s3:AbortMultiPartUpload",
            #             "s3:DeleteObject",
            #             "s3:GetObject",
            #             "s3:ListBucket",
            #             "s3:PutObject"
            #         ],
            #         "resources": [
            #             "arn:aws:s3::123456789012:bucket1"
            #         ]
            #     }
            "name": "",
            "arn": "",
            "version": "",
            "is-default-version": True,  # This is a boolean, value is a default
            "actions": [],
            "resources": [],
        }
        self.__schema_bucket: dict = {
            # The key is the bucket name and this dict is the value.
            #
            # Example:
            #     {
            #         "name": "my_bucket",
            #         "arn": "arn:aws:s3:::my_bucket",
            #         "region": "us-east-1",
            #         "storage_class": "hot",
            #         "bucket_policy": {
            #             "Version": "2012-10-17",
            #             "Statement": [
            #                 {
            #                     "Sid": "FullAccess",
            #                     "Effect": "Allow",
            #                     "Principal": {
            #                         "AWS": "arn:aws:iam::123456789012:group/devs"
            #                     },
            #                     "Action": "*",
            #                     "Resource": [
            #                         "arn:aws:s3::123456789012:my_bucket"
            #                         "arn:aws:s3::123456789012:my_bucket/*",
            #                     ]
            #                 }
            #             ]
            #         },
            #         "lifecycle-rules": {},
            #         "versioning": False,
            #         "gb_used": 1234.567,
            #         "object_count": 381579
            #     }
            "name": "",
            "arn": "",
            "region": "",
            "storage_class": "hot",
            # Bucket policies are not normally used, but if they are they
            # will be in a policy document format
            "bucket_policy": {},
            "lifecycle-rules": {},
            "versioning": False,  # By default, no versioning is enabled
            "gb_used": 0,
            "object_count": 0
        }
        self.__logger = logging.getLogger(__name__)
        self._access_key_id: str = getenv("WASABI_ACCESS_KEY", "")
        self._secret_access_key: str = getenv("WASABI_SECRET_KEY", "")
        # Getting the billing data is a slow operation,
        # so we only want to do it once and only if needed.
        self._billing_data: dict = {}
        self.request_timeout: int = 30
        self.iam_region: str = WasabiEndpoints.to_lower(WasabiEndpoints.IAM.name)
        self.sts_region: str = WasabiEndpoints.to_lower(WasabiEndpoints.STS.name)

    def get_example_schema(self) -> str:
        return self.__schema_example

    def _new_client(self, region: str) -> botocore.client:
        if not self._access_key_id or not self._secret_access_key:
            raise ValueError("Missing Wasabi credentials")

        if WasabiEndpoints.to_upper(region) in WasabiEndpoints.__members__:
            region = WasabiEndpoints.to_lower(region)
        else:
            raise Exception(f"Invalid Wasabi region ({region})")

        endpoint: str = WasabiEndpoints[WasabiEndpoints.to_upper(region)].value
        client_type: str = self.__determine_client_type(region)

        # This is a special case where "s3" is not a valid region for the AWS SDK/API, but I want
        # to use it while retaining the primary endpoint for us-east-1
        if region == "s3" or region == "iam" or region == "sts":
            region = WasabiEndpoints.to_lower(WasabiEndpoints.US_EAST_1.name)

        if client_type == "billing":
            raise ValueError("Billing API does not use a boto3 client. Use get_billing_data() instead.")

        client = boto3.client(
            client_type,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            endpoint_url=endpoint,
            region_name=region,
        )
        return client

    def __determine_client_type(self, region: str = "") -> str:
        """
        Use this to determine the client type based on the region.
        """
        uppercase_region: str = WasabiEndpoints.to_upper(region)
        endpoint: str = WasabiEndpoints[uppercase_region].value
        endpoint_hostname: str = endpoint.split("/")[-1]
        client_type: str = endpoint_hostname.split(".")[0]
        return client_type

    def get_buckets(self) -> dict:
        """
        Gets a list of buckets and iterates over the bucket names to get the bucket's
        location. It returns a dict of the bucket names and locations.
        """
        bucket_list: dict = {}
        s3_client: botocore.client = self._new_client("s3")
        buckets: dict = s3_client.list_buckets()
        for bucket in buckets["Buckets"]:
            bucket_location: str = self.__get_bucket_location(bucket["Name"])
            bucket_list[bucket["Name"]] = bucket_location
        return bucket_list

    def __get_bucket_location(self, bucket_name: str = "") -> str:
        """
        Get the location of a bucket
        """
        location = ""
        s3_client: botocore.client = self._new_client("s3")
        try:
            bucket_location: dict = s3_client.get_bucket_location(Bucket=bucket_name)
            # Wasabi returns a LocationConstraint null (None) value for us-east-1
            # This is an AWS SDK quirk
            if bucket_location["LocationConstraint"] is None:
                location = "us-east-1"
            else:
                location = bucket_location["LocationConstraint"]
        except ClientError as e:
            self.__logger.error(f"Error getting bucket location: {e}")
        return location

    def get_managed_policies(self, scope: str = "Local") -> list[dict]:
        """
        Gets a list of managed policies
        # TODO: annoptate scope possible values
        """
        try:
            iam_client: botocore.client = self._new_client(self.iam_region)
            response: list[dict] = iam_client.list_policies(Scope=scope)
            return response["Policies"]
        except ClientError as e:
            self.__logger.error(f"Error getting managed policies: {e}")
            return []

    def get_groups(self) -> list[dict]:
        """
        List the groups
        """
        try:
            iam_client: botocore.client = self._new_client(self.iam_region)
            groups: list[dict] = iam_client.list_groups()
            return groups["Groups"]
        except ClientError as e:
            self.__logger.error(f"Error getting groups: {e}")
            return []

    def get_users(self) -> list[dict]:
        """
        List the groups
        """
        try:
            iam_client: botocore.client = self._new_client(self.iam_region)
            users: list[dict] = iam_client.list_users()
            return users["Users"]
        except ClientError as e:
            self.__logger.error(f"Error getting users: {e}")
            return []

    def get_billing_data(self) -> dict:
        """
        Gets a snapshot of bucket usage/billing data from Wasabi's Billing API and
        returns it as a JSON object.

        By default, it returns the data for the current day for all buckets
        """
        billing_data: dict = {}
        reporting_period_length: int = 1  # the number of days to report on
        end_date: datetime = datetime.now(tz=timezone.utc)
        # the trailing slash is critical to this API endpoint
        url: str = "https://billing.wasabisys.com/utilization/bucket/"
        credentials: dict = {
            "id": self._access_key_id,
            "secret": self._secret_access_key,
        }
        to_date: str = end_date.strftime("%Y-%m-%d")
        from_date: str = (end_date - timedelta(days=reporting_period_length)).strftime(
            "%Y-%m-%d"
        )
        params: dict = {"withname": "true", "from": from_date, "to": to_date}

        response: requests.Response = requests.get(
            url, params=params, auth=WasabiBillingApiAuthorization(credentials),
            timeout=self.request_timeout
        )
        if response.status_code != 200:
            raise Exception(
                f"Failed to get query Wasabi API: HTTP Error {response.status_code}"
            )
        # self.__logger.debug(f"{len(response.json())} buckets found in Wasabi billing data")
        # self.__logger.debug(list(response.json()[0].keys()))
        self._billing_data = response.json()
        return self._billing_data

    def export_billing_data(self, path: str = "billing_data.json") -> None:
        with open(path, "w") as f:
            json.dump(self._billing_data, f, indent=4, cls=DateTimeEncoder)


class WasabiBillingApiAuthorization(requests.auth.AuthBase):
    """
    A custom requests authorization class for Wasabi Billing API
    Returns the authorization header in a format Wasabi's Billing API expects.
    This will not work for the S3 API, as those requests require AWS v4 signatures.
    """

    def __init__(self, credentials: dict) -> None:
        """
        Initialize the WasabiBillingApiAuthorization class
        """
        self.access_key_id: str = credentials["id"]
        self.secret_access_key: str = credentials["secret"]

    def __call__(self, r) -> requests.Request:
        """
        This is the method that is called when the class is used as an
        authorization object.
        """
        r.headers["Authorization"] = f"{self.access_key_id}:{self.secret_access_key}"
        return r
