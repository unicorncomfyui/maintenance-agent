"""
Main maintenance agent script
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, List

from scanners import GitHubScanner, StateManager
from analyzer import UpdateAnalyzer
from notifier import GitHubNotifier

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MaintenanceAgent:
    """Main maintenance agent orchestrator"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.scanner = GitHubScanner()
        self.state_manager = StateManager()
        self.analyzer = UpdateAnalyzer()
        self.notifier = GitHubNotifier()

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise

    def scan_repository(self, repo_config: Dict) -> List[Dict]:
        """
        Scan a repository for updates

        Returns list of updates found
        """
        owner = repo_config["owner"]
        repo = repo_config["repo"]
        priority = repo_config.get("priority", "medium")
        watch_for = repo_config.get("watch_for", ["releases"])

        logger.info(f"Scanning {owner}/{repo} (priority: {priority})...")

        updates = []

        # Check releases
        if "releases" in watch_for:
            latest_release = self.scanner.get_latest_release(owner, repo)
            if latest_release:
                version = latest_release.get("tag_name", "unknown")
                repo_key = f"{owner}/{repo}"

                if self.state_manager.is_new_version(repo_key, version):
                    logger.info(f"Found new release: {version}")
                    updates.append(
                        {
                            "type": "release",
                            "repo": f"{owner}/{repo}",
                            "version": version,
                            "data": latest_release,
                            "changelog": latest_release.get("body", ""),
                        }
                    )

        # Check tags if no releases
        elif "tags" in watch_for:
            latest_tag = self.scanner.get_latest_tag(owner, repo)
            if latest_tag:
                version = latest_tag.get("name", "unknown")
                repo_key = f"{owner}/{repo}/tags"

                if self.state_manager.is_new_version(repo_key, version):
                    logger.info(f"Found new tag: {version}")
                    updates.append(
                        {
                            "type": "tag",
                            "repo": f"{owner}/{repo}",
                            "version": version,
                            "data": latest_tag,
                            "changelog": "",
                        }
                    )

        return updates

    def process_update(self, update: Dict, target_repos: List[Dict]) -> int:
        """
        Process an update: analyze and create notifications

        Returns number of notifications created
        """
        repo_name = update["repo"]
        new_version = update["version"]
        changelog = update.get("changelog", "")

        logger.info(f"Analyzing update for {repo_name} {new_version}...")

        # Get current version from state
        current_version = self.state_manager.get_last_seen(repo_name) or "unknown"

        # Analyze the update
        analysis = self.analyzer.analyze_update(
            repo_name=repo_name,
            current_version=current_version,
            new_version=new_version,
            changelog=changelog,
            context=self._get_context(),
        )

        logger.info(
            f"Analysis: Priority {analysis['priority']}/10, "
            f"Recommendation: {analysis['recommendation']}"
        )

        # Check if we should create issues
        min_priority = self.config.get("monitoring", {}).get("thresholds", {}).get(
            "min_priority_score", 5
        )

        if not self.analyzer.should_create_issue(analysis, min_priority):
            logger.info(f"Skipping notification (priority too low or IGNORE)")
            # Update state anyway
            self.state_manager.update_last_seen(repo_name, new_version)
            return 0

        # Create notifications for all target repositories
        notifications_created = 0

        for target in target_repos:
            owner = target["owner"]
            repo = target["repo"]

            logger.info(f"Creating notification in {owner}/{repo}...")

            success = self.notifier.create_update_notification(
                target_owner=owner,
                target_repo=repo,
                source_repo=repo_name,
                current=current_version,
                new=new_version,
                analysis=analysis,
                changelog=changelog,
                analyzer=self.analyzer,
            )

            if success:
                notifications_created += 1

        # Update state
        self.state_manager.update_last_seen(repo_name, new_version)

        return notifications_created

    def _get_context(self) -> str:
        """Get context about our deployment"""
        return """RunPod deployment with:
- CUDA 12.8.1 + cuDNN
- Python 3.11
- PyTorch nightly cu128
- ComfyUI (commit 36357bb)
- SageAttention (commit 68de379)
- Support for RTX 5090 (sm_120)"""

    def run(self):
        """Main run method"""
        logger.info("🤖 Starting Maintenance Agent...")

        # Get configuration
        sources = self.config.get("sources", {}).get("github_repos", [])
        target_repos = self.config.get("target_repos", [])

        if not target_repos:
            logger.warning("No target repositories configured!")
            return

        total_updates = 0
        total_notifications = 0

        # Scan each source repository
        for repo_config in sources:
            try:
                updates = self.scan_repository(repo_config)

                for update in updates:
                    total_updates += 1
                    notifications = self.process_update(update, target_repos)
                    total_notifications += notifications

            except Exception as e:
                logger.error(
                    f"Error processing {repo_config.get('owner')}/{repo_config.get('repo')}: {e}"
                )
                continue

        logger.info(
            f"✅ Scan complete: {total_updates} updates found, "
            f"{total_notifications} notifications created"
        )


if __name__ == "__main__":
    # Check required environment variables
    if not os.getenv("GITHUB_TOKEN"):
        logger.error("GITHUB_TOKEN environment variable not set!")
        exit(1)

    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY environment variable not set!")
        exit(1)

    # Run the agent
    agent = MaintenanceAgent()
    agent.run()
