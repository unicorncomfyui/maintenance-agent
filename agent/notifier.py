"""
Notifier for creating GitHub issues and sending notifications
"""

import os
import requests
from typing import Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GitHubNotifier:
    """Create GitHub issues for updates"""

    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN not found in environment")

        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: Optional[list] = None,
    ) -> Optional[Dict]:
        """Create a GitHub issue"""

        url = f"{self.base_url}/repos/{owner}/{repo}/issues"

        data = {"title": title, "body": body}

        if labels:
            data["labels"] = labels

        try:
            response = requests.post(url, headers=self.headers, json=data, timeout=10)

            if response.status_code == 201:
                issue = response.json()
                logger.info(
                    f"✅ Created issue #{issue['number']}: {title} in {owner}/{repo}"
                )
                return issue
            else:
                logger.error(f"Failed to create issue: {response.status_code}")
                logger.error(response.text)
                return None

        except Exception as e:
            logger.error(f"Error creating issue: {e}")
            return None

    def check_existing_issue(
        self, owner: str, repo: str, search_title: str
    ) -> Optional[Dict]:
        """Check if an issue with similar title already exists"""

        # Search for open issues with keywords from the title
        url = f"{self.base_url}/search/issues"
        query = f"repo:{owner}/{repo} is:issue is:open {search_title}"
        params = {"q": query, "per_page": 5}

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=10
            )

            if response.status_code == 200:
                results = response.json()
                items = results.get("items", [])

                # Check if any existing issue matches
                for item in items:
                    if search_title.lower() in item["title"].lower():
                        logger.info(
                            f"Found existing issue #{item['number']}: {item['title']}"
                        )
                        return item

                return None
            else:
                logger.error(f"Failed to search issues: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error searching issues: {e}")
            return None

    def get_labels_for_update(self, analysis: Dict) -> list:
        """Determine appropriate labels based on analysis"""

        labels = ["maintenance-agent", "dependencies"]

        recommendation = analysis.get("recommendation", "EVALUATE")
        priority = analysis.get("priority", 5)
        breaking_changes = analysis.get("breaking_changes", False)

        # Add recommendation label
        label_map = {
            "UPDATE": "enhancement",
            "EVALUATE": "needs-testing",
            "BLOCK": "blocked",
            "IGNORE": "wontfix",
        }
        if recommendation in label_map:
            labels.append(label_map[recommendation])

        # Add priority label
        if priority >= 9:
            labels.append("priority:critical")
        elif priority >= 7:
            labels.append("priority:high")
        elif priority >= 5:
            labels.append("priority:medium")

        # Add breaking changes label
        if breaking_changes:
            labels.append("breaking-change")

        return labels

    def create_update_notification(
        self,
        target_owner: str,
        target_repo: str,
        source_repo: str,
        current: str,
        new: str,
        analysis: Dict,
        changelog: str,
        analyzer,  # UpdateAnalyzer instance
    ) -> bool:
        """
        Create a notification issue for an update

        Returns:
            True if issue was created, False otherwise
        """

        # Format issue title and body
        title = analyzer.format_issue_title(source_repo, new, analysis)
        body = analyzer.format_issue_body(
            source_repo, current, new, analysis, changelog
        )

        # Check if similar issue already exists
        search_term = f"{source_repo} {new}"
        existing = self.check_existing_issue(target_owner, target_repo, search_term)

        if existing:
            logger.info(
                f"Skipping - similar issue already exists: #{existing['number']}"
            )
            return False

        # Get appropriate labels
        labels = self.get_labels_for_update(analysis)

        # Create the issue
        issue = self.create_issue(target_owner, target_repo, title, body, labels)

        return issue is not None
