"""
Generate SCHEMA.md from the actual schema definitions in Client.

Usage:
    uv run python scripts/generate_schema.py
"""
import json
from datetime import datetime, timezone
from wasabi_s3.client import Client

# Descriptions for each key in each schema.
# If you add a key to a schema, add a description here too.
KEY_DESCRIPTIONS: dict[str, dict[str, tuple[str, str]]] = {
    "user": {
        "name": ("str", "Username"),
        "arn": ("str", "IAM ARN"),
        "api-keys": ("dict", 'Access key ID mapped to `{"secret-key": str, "status": str}`. Max 2 keys per user.'),
    },
    "group": {
        "name": ("str", "Group name"),
        "arn": ("str", "IAM ARN"),
        "members": ("list[str]", "Member ARNs"),
        "attached-policies": ("list[str]", "Attached managed policy ARNs"),
        "inline-policies": ("dict", "Policy name mapped to policy document"),
    },
    "policy": {
        "name": ("str", "Policy name"),
        "arn": ("str", "IAM ARN"),
        "version": ("str", 'Version ID (e.g. `"v1"`)'),
        "is-default-version": ("bool", "Whether this is the default version"),
        "actions": ("list[str]", "Allowed S3 actions"),
        "resources": ("list[str]", "Resource ARNs the policy applies to"),
    },
    "bucket": {
        "name": ("str", "Bucket name"),
        "arn": ("str", "S3 ARN"),
        "region": ("str", 'Wasabi region (e.g. `"us-east-1"`)'),
        "storage_class": ("str", 'Always `"hot"` for Wasabi'),
        "bucket_policy": ("dict", "Bucket policy document (empty if none)"),
        "lifecycle-rules": ("dict", "Lifecycle configuration (empty if none)"),
        "versioning": ("bool", "Whether versioning is enabled"),
        "gb_used": ("float", "Storage used in GB"),
        "object_count": ("int", "Number of objects"),
    },
}

# Example JSON for each schema type
EXAMPLES: dict[str, dict] = {
    "user": {
        "name": "jimbob",
        "arn": "arn:aws:iam::123456789012:user/jimbob",
        "api-keys": {
            "AKIAIOSFODNN7EXAMPLE": {
                "secret-key": "",
                "status": "Active"
            },
            "AKIAI44QH8DHBEXAMPLE": {
                "secret-key": "",
                "status": "Disabled"
            }
        }
    },
    "group": {
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
    "policy": {
        "name": "dev-policy",
        "arn": "arn:aws:iam::123456789012:policy/dev-policy",
        "version": "v1",
        "is-default-version": True,
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
    },
    "bucket": {
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
                        "arn:aws:s3:::my_bucket",
                        "arn:aws:s3:::my_bucket/*"
                    ]
                }
            ]
        },
        "lifecycle-rules": {},
        "versioning": False,
        "gb_used": 1234.567,
        "object_count": 381579
    },
}


def generate_section(title: str, schema: dict, descriptions: dict[str, tuple[str, str]], example: dict) -> str:
    """Generate a markdown section for one schema type."""
    lines: list[str] = []
    lines.append(f"## {title}")
    lines.append("")
    lines.append("| Key | Type | Description |")
    lines.append("|-----|------|-------------|")
    for key in schema:
        if key not in descriptions:
            raise ValueError(
                f"Schema key '{key}' in {title.lower()} has no description in "
                f"KEY_DESCRIPTIONS. Add it to scripts/generate_schema.py."
            )
        type_str, desc = descriptions[key]
        lines.append(f"| `{key}` | `{type_str}` | {desc} |")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(example, indent=4))
    lines.append("```")
    return "\n".join(lines)


def generate() -> str:
    """Generate the full SCHEMA.md content from live schema definitions."""
    client = Client()
    schemas = {
        "User": client._schema_user,
        "Group": client._schema_group,
        "Policy": client._schema_policy,
        "Bucket": client._schema_bucket,
    }

    lines: list[str] = []
    lines.append("# Wasabi SDK Schema Reference")
    lines.append("")
    lines.append("Each resource class exposes a `to_dict()` method that returns its properties as a dictionary.")
    lines.append("The schemas below document the shape of those dictionaries.")
    lines.append("")
    timestamp: str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.append("> This file is auto-generated from the schema definitions in `src/wasabi_s3/client.py`.")
    lines.append(f"> Last generated: {timestamp}")
    lines.append("> To regenerate: `uv run python scripts/generate_schema.py`")
    lines.append("")

    for title, schema in schemas.items():
        key = title.lower()
        lines.append(generate_section(title, schema, KEY_DESCRIPTIONS[key], EXAMPLES[key]))
        lines.append("")

    lines.append("## Full Example")
    lines.append("")
    lines.append("A complete state export combining all resource types:")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps({
        "users": ["..."],
        "groups": ["..."],
        "policies": ["..."],
        "buckets": ["..."],
    }, indent=4))
    lines.append("```")
    lines.append("")
    lines.append("See `to_dict()` on each class (`User`, `Group`, `Policy`, `Bucket`) to export individual resources.")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    from pathlib import Path
    output = Path(__file__).parent.parent / "SCHEMA.md"
    content = generate()
    output.write_text(content)
    print(f"Generated {output}")
