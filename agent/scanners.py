"""
Scanners for monitoring external sources (GitHub, PyPI, etc.)
"""

import os
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GitHubScanner:
    """Scan GitHub repositories for new releases and updates"""

    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        if self.github_token:
            self.headers["Authorization"] = f"Bearer {self.github_token}"

    def get_latest_release(self, owner: str, repo: str) -> Optional[Dict]:
        """Get the latest release for a repository"""
        url = f"{self.base_url}/repos/{owner}/{repo}/releases/latest"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.info(f"No releases found for {owner}/{repo}")
                return None
            else:
                logger.error(f"GitHub API error: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching release for {owner}/{repo}: {e}")
            return None

    def get_latest_tag(self, owner: str, repo: str) -> Optional[Dict]:
        """Get the latest tag for a repository"""
        url = f"{self.base_url}/repos/{owner}/{repo}/tags"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                tags = response.json()
                return tags[0] if tags else None
            else:
                logger.error(f"GitHub API error: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching tags for {owner}/{repo}: {e}")
            return None

    def get_recent_commits(
        self, owner: str, repo: str, since_days: int = 7
    ) -> List[Dict]:
        """Get recent commits from a repository"""
        since_date = (datetime.now() - timedelta(days=since_days)).isoformat()
        url = f"{self.base_url}/repos/{owner}/{repo}/commits"
        params = {"since": since_date, "per_page": 10}

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=10
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"GitHub API error: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching commits for {owner}/{repo}: {e}")
            return []

    def get_repo_info(self, owner: str, repo: str) -> Optional[Dict]:
        """Get basic repository information"""
        url = f"{self.base_url}/repos/{owner}/{repo}"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"GitHub API error: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching repo info for {owner}/{repo}: {e}")
            return None

    def check_for_updates(self, owner: str, repo: str, current_version: str) -> Dict:
        """
        Check if there's a new version available

        Returns:
            {
                'has_update': bool,
                'current': str,
                'latest': str,
                'release_data': dict,
                'changelog': str
            }
        """
        latest_release = self.get_latest_release(owner, repo)

        if not latest_release:
            # Try tags if no releases
            latest_tag = self.get_latest_tag(owner, repo)
            if latest_tag:
                latest_version = latest_tag.get("name", "unknown")
                return {
                    "has_update": latest_version != current_version,
                    "current": current_version,
                    "latest": latest_version,
                    "release_data": latest_tag,
                    "changelog": "",
                }

            return {
                "has_update": False,
                "current": current_version,
                "latest": "unknown",
                "release_data": {},
                "changelog": "",
            }

        latest_version = latest_release.get("tag_name", "unknown")
        changelog = latest_release.get("body", "")

        return {
            "has_update": latest_version != current_version,
            "current": current_version,
            "latest": latest_version,
            "release_data": latest_release,
            "changelog": changelog,
        }


class StateManager:
    """Manage the state of what we've already seen"""

    def __init__(self, state_file: str = "agent/.agent_state.json"):
        self.state_file = state_file
        self.state = self._load_state()

    def _load_state(self) -> Dict:
        """Load state from file"""
        import json

        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading state: {e}")
                return {}
        return {}

    def _save_state(self):
        """Save state to file"""
        import json

        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def get_last_seen(self, repo_key: str) -> Optional[str]:
        """Get last seen version for a repository"""
        return self.state.get(repo_key, {}).get("last_version")

    def update_last_seen(self, repo_key: str, version: str):
        """Update last seen version"""
        if repo_key not in self.state:
            self.state[repo_key] = {}

        self.state[repo_key]["last_version"] = version
        self.state[repo_key]["last_checked"] = datetime.now().isoformat()
        self._save_state()

    def is_new_version(self, repo_key: str, version: str) -> bool:
        """Check if this is a new version we haven't seen"""
        last_seen = self.get_last_seen(repo_key)
        return last_seen is None or last_seen != version


class RedditScanner:
    """Scan Reddit subreddits for technical updates"""

    def __init__(self):
        self.base_url = "https://www.reddit.com"
        self.headers = {
            "User-Agent": "linux:maintenance-agent:v1.0.0 (by /u/maintenance_bot)"
        }

    def get_recent_posts(
        self, subreddit: str, max_posts: int = 20, hours: int = 168
    ) -> List[Dict]:
        """
        Get recent posts from a subreddit

        Args:
            subreddit: Subreddit name (without r/)
            max_posts: Maximum number of posts to fetch
            hours: Only fetch posts from last N hours (default: 7 days)

        Returns:
            List of post dictionaries
        """
        url = f"{self.base_url}/r/{subreddit}/new.json"
        params = {"limit": max_posts}

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                posts = []

                cutoff_time = datetime.now().timestamp() - (hours * 3600)

                for child in data.get("data", {}).get("children", []):
                    post_data = child.get("data", {})
                    created_utc = post_data.get("created_utc", 0)

                    # Only include recent posts
                    if created_utc >= cutoff_time:
                        posts.append(
                            {
                                "title": post_data.get("title", ""),
                                "url": f"{self.base_url}{post_data.get('permalink', '')}",
                                "author": post_data.get("author", ""),
                                "created": datetime.fromtimestamp(created_utc),
                                "flair": post_data.get("link_flair_text", ""),
                                "selftext": post_data.get("selftext", ""),
                                "score": post_data.get("score", 0),
                                "num_comments": post_data.get("num_comments", 0),
                            }
                        )

                logger.info(f"Found {len(posts)} recent posts in r/{subreddit}")
                return posts
            else:
                logger.error(f"Reddit API error: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Error fetching Reddit posts: {e}")
            return []

    def filter_technical_posts(
        self,
        posts: List[Dict],
        flairs: List[str] = None,
        keywords: List[str] = None,
    ) -> List[Dict]:
        """
        Filter posts to keep only technical/release posts

        Args:
            posts: List of posts
            flairs: List of allowed flairs (case-insensitive)
            keywords: List of keywords to match in title/body

        Returns:
            Filtered list of posts
        """
        if not flairs and not keywords:
            return posts

        filtered = []

        for post in posts:
            # Check flair filter
            if flairs:
                post_flair = post.get("flair", "").lower()
                if not any(flair.lower() in post_flair for flair in flairs):
                    continue

            # Check keyword filter
            if keywords:
                title = post.get("title", "").lower()
                body = post.get("selftext", "").lower()
                text = f"{title} {body}"

                if not any(keyword.lower() in text for keyword in keywords):
                    continue

            filtered.append(post)

        logger.info(f"Filtered to {len(filtered)} technical posts")
        return filtered
