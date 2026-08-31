#!/usr/bin/env python3
""".github/labels.yml から GitHub リポジトリにラベルを同期します。
これにより、すべてのラベルが設定と一致することを保証します。.

使用方法:
    python scripts/maintenance/sync_labels.py [--dry-run]

必要な環境:
    pip install PyYAML requests
    export GITHUB_TOKEN=your_github_token
"""

import argparse
import os
import sys

import requests
import yaml


class GitHubLabelSync:
    def __init__(self, token: str, owner: str, repo: str):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.api_base = f"https://api.github.com/repos/{owner}/{repo}"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def get_existing_labels(self) -> dict[str, dict[str, str]]:
        """Fetch all existing labels from the repository."""
        labels = {}
        page = 1

        while True:
            response = requests.get(
                f"{self.api_base}/labels",
                headers=self.headers,
                params={"page": page, "per_page": 100},
            )
            response.raise_for_status()

            page_labels = response.json()
            if not page_labels:
                break

            for label in page_labels:
                labels[label["name"]] = {
                    "color": label["color"],
                    "description": label.get("description", ""),
                }

            page += 1

        return labels

    def create_label(self, name: str, color: str, description: str) -> None:
        """Create a new label."""
        data = {"name": name, "color": color.lstrip("#"), "description": description}

        response = requests.post(
            f"{self.api_base}/labels", headers=self.headers, json=data
        )
        response.raise_for_status()
        print(f"✅ Created label: {name}")

    def update_label(self, name: str, color: str, description: str) -> None:
        """Update an existing label."""
        data = {"color": color.lstrip("#"), "description": description}

        response = requests.patch(
            f"{self.api_base}/labels/{name}", headers=self.headers, json=data
        )
        response.raise_for_status()
        print(f"✅ Updated label: {name}")

    def sync_labels(
        self, config_labels: list[dict[str, str]], dry_run: bool = False
    ) -> None:
        """Sync labels from configuration to repository."""
        existing_labels = self.get_existing_labels()

        # Create or update labels from config
        for label in config_labels:
            name = label["name"]
            color = label["color"].lstrip("#")
            description = label.get("description", "")

            if name in existing_labels:
                existing = existing_labels[name]
                if existing["color"] != color or existing["description"] != description:
                    if dry_run:
                        print(f"Would update label: {name}")
                    else:
                        self.update_label(name, color, description)
            else:
                if dry_run:
                    print(f"Would create label: {name}")
                else:
                    self.create_label(name, color, description)


def load_label_config(config_path: str) -> list[dict[str, str]]:
    """Load label configuration from YAML file."""
    with open(config_path) as f:
        # Skip comment lines and parse YAML
        lines = [
            line
            for line in f
            if not line.strip().startswith("#") or line.strip() == "#"
        ]
        yaml_content = "".join(lines)
        return yaml.safe_load(yaml_content)


def main():
    parser = argparse.ArgumentParser(
        description="Sync GitHub labels from configuration"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--config",
        default=".github/labels.yml",
        help="Path to labels configuration file",
    )
    parser.add_argument("--owner", default="pi", help="GitHub repository owner")
    parser.add_argument(
        "--repo", default="coordinate-recorder", help="GitHub repository name"
    )
    args = parser.parse_args()

    # Get GitHub token from environment
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("❌ Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)

    # Load label configuration
    if not os.path.exists(args.config):
        print(f"❌ Error: Configuration file not found: {args.config}")
        sys.exit(1)

    try:
        config_labels = load_label_config(args.config)
        print(f"📋 Loaded {len(config_labels)} labels from configuration")
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        sys.exit(1)

    # Initialize syncer and sync labels
    syncer = GitHubLabelSync(token, args.owner, args.repo)

    if args.dry_run:
        print("\n🔍 Running in dry-run mode (no changes will be made)")

    try:
        syncer.sync_labels(config_labels, dry_run=args.dry_run)
        print("\n✨ Label sync completed successfully!")
    except Exception as e:
        print(f"\n❌ Error during sync: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
