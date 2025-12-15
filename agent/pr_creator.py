"""
PR Creator for maintenance agent
Automatically creates Pull Requests for dependency updates
"""

import os
import re
import requests
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class PRCreator:
    """Create Pull Requests for dependency updates"""

    def __init__(self):
        self.github_token = os.environ.get("GITHUB_TOKEN")
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN environment variable not set")

        self.headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        self.base_url = "https://api.github.com"

    def create_update_pr(
        self,
        owner: str,
        repo: str,
        update_info: Dict,
        analysis: Dict,
    ) -> Optional[str]:
        """
        Create a PR for a dependency update

        Args:
            owner: Repository owner
            repo: Repository name
            update_info: Update information (repo, version, type, etc.)
            analysis: Claude's analysis of the update

        Returns:
            PR URL if created, None otherwise
        """
        try:
            # Determine if we should create a PR based on recommendation
            recommendation = analysis.get("recommendation", "IGNORE")
            if recommendation == "BLOCK":
                logger.info(
                    f"Skipping PR creation for {update_info['repo']} - recommendation: BLOCK"
                )
                return None

            # Create branch name
            branch_name = self._generate_branch_name(update_info)

            # Get file modifications
            modifications = self._determine_modifications(owner, repo, update_info)

            if not modifications:
                logger.warning(f"No modifications determined for {update_info['repo']}")
                return None

            # Create branch and apply changes
            base_branch = self._get_default_branch(owner, repo)
            success = self._create_branch_with_changes(
                owner, repo, base_branch, branch_name, modifications
            )

            if not success:
                logger.error(f"Failed to create branch {branch_name}")
                return None

            # Create PR
            pr_url = self._create_pull_request(
                owner, repo, base_branch, branch_name, update_info, analysis
            )

            return pr_url

        except Exception as e:
            logger.error(f"Error creating PR: {e}")
            return None

    def _generate_branch_name(self, update_info: Dict) -> str:
        """Generate a branch name for the update"""
        repo_name = update_info["repo"].replace("/", "-")
        version = update_info["version"].replace(".", "-").replace("v", "")
        return f"update/{repo_name}-{version}"

    def _get_default_branch(self, owner: str, repo: str) -> str:
        """Get the default branch of a repository"""
        url = f"{self.base_url}/repos/{owner}/{repo}"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json().get("default_branch", "main")
            return "main"
        except Exception as e:
            logger.error(f"Error getting default branch: {e}")
            return "main"

    def _determine_modifications(
        self, owner: str, repo: str, update_info: Dict
    ) -> List[Dict]:
        """
        Determine which files need to be modified

        Returns:
            List of modifications: [{'path': str, 'old_content': str, 'new_content': str}]
        """
        modifications = []
        update_repo = update_info["repo"]
        new_version = update_info["version"]

        # Map of dependency repos to file patterns
        file_patterns = {
            "comfyanonymous/ComfyUI": ["Dockerfile"],
            "thu-ml/SageAttention": ["Dockerfile", "init.sh"],
            "pytorch/pytorch": ["Dockerfile", "requirements.txt"],
        }

        files_to_check = file_patterns.get(update_repo, [])

        for file_path in files_to_check:
            content = self._get_file_content(owner, repo, file_path)
            if content:
                new_content = self._update_file_content(
                    content, update_repo, new_version
                )
                if new_content != content:
                    modifications.append(
                        {
                            "path": file_path,
                            "old_content": content,
                            "new_content": new_content,
                        }
                    )

        return modifications

    def _get_file_content(self, owner: str, repo: str, path: str) -> Optional[str]:
        """Get content of a file from GitHub"""
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                import base64

                content = response.json().get("content", "")
                return base64.b64decode(content).decode("utf-8")
            return None
        except Exception as e:
            logger.error(f"Error getting file content for {path}: {e}")
            return None

    def _update_file_content(
        self, content: str, update_repo: str, new_version: str
    ) -> str:
        """
        Update file content with new version

        This is a smart replacement that handles different file formats
        """
        if update_repo == "comfyanonymous/ComfyUI":
            # Update ComfyUI commit hash in Dockerfile
            # Pattern: COMFYUI_COMMIT=36357bb or ARG COMFYUI_COMMIT=36357bb
            pattern = r"(COMFYUI_COMMIT=)([a-f0-9]+)"
            # Extract commit hash from version (assuming format like v1.2.3 or commit hash)
            commit_hash = new_version.lstrip("v")[:7]
            content = re.sub(pattern, rf"\g<1>{commit_hash}", content)

        elif update_repo == "thu-ml/SageAttention":
            # Update SageAttention commit in Dockerfile or init.sh
            pattern = r"(SAGEATTENTION_COMMIT=)([a-f0-9]+)"
            commit_hash = new_version.lstrip("v")[:7]
            content = re.sub(pattern, rf"\g<1>{commit_hash}", content)

        elif update_repo == "pytorch/pytorch":
            # Update PyTorch version in Dockerfile or requirements.txt
            # Pattern: torch==2.5.1 or torch>=2.5.0
            pattern = r"(torch[>=]=)(\d+\.\d+\.\d+)"
            clean_version = new_version.lstrip("v")
            content = re.sub(pattern, rf"\g<1>{clean_version}", content)

        return content

    def _create_branch_with_changes(
        self,
        owner: str,
        repo: str,
        base_branch: str,
        new_branch: str,
        modifications: List[Dict],
    ) -> bool:
        """
        Create a new branch with file changes using GitHub API

        Uses the GitHub API to create a branch and commit changes
        """
        try:
            # Get base branch SHA
            base_sha = self._get_branch_sha(owner, repo, base_branch)
            if not base_sha:
                logger.error(f"Could not get SHA for branch {base_branch}")
                return False

            # Create new branch
            success = self._create_branch_ref(owner, repo, new_branch, base_sha)
            if not success:
                logger.error(f"Could not create branch {new_branch}")
                return False

            # Apply modifications
            for mod in modifications:
                success = self._update_file(
                    owner,
                    repo,
                    new_branch,
                    mod["path"],
                    mod["new_content"],
                    f"chore: update {mod['path']}",
                )
                if not success:
                    logger.error(f"Failed to update {mod['path']}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error creating branch with changes: {e}")
            return False

    def _get_branch_sha(self, owner: str, repo: str, branch: str) -> Optional[str]:
        """Get SHA of a branch"""
        url = f"{self.base_url}/repos/{owner}/{repo}/git/refs/heads/{branch}"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()["object"]["sha"]
            return None
        except Exception as e:
            logger.error(f"Error getting branch SHA: {e}")
            return None

    def _create_branch_ref(
        self, owner: str, repo: str, branch: str, sha: str
    ) -> bool:
        """Create a new branch reference"""
        url = f"{self.base_url}/repos/{owner}/{repo}/git/refs"

        data = {"ref": f"refs/heads/{branch}", "sha": sha}

        try:
            response = requests.post(
                url, headers=self.headers, json=data, timeout=10
            )
            return response.status_code == 201
        except Exception as e:
            logger.error(f"Error creating branch ref: {e}")
            return False

    def _update_file(
        self,
        owner: str,
        repo: str,
        branch: str,
        path: str,
        content: str,
        message: str,
    ) -> bool:
        """Update a file in a repository"""
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"

        # Get current file SHA
        try:
            response = requests.get(
                url, headers=self.headers, params={"ref": branch}, timeout=10
            )
            file_sha = None
            if response.status_code == 200:
                file_sha = response.json()["sha"]

            # Prepare update
            import base64

            encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

            data = {
                "message": message,
                "content": encoded_content,
                "branch": branch,
            }

            if file_sha:
                data["sha"] = file_sha

            response = requests.put(url, headers=self.headers, json=data, timeout=10)
            return response.status_code in [200, 201]

        except Exception as e:
            logger.error(f"Error updating file {path}: {e}")
            return False

    def _create_pull_request(
        self,
        owner: str,
        repo: str,
        base_branch: str,
        head_branch: str,
        update_info: Dict,
        analysis: Dict,
    ) -> Optional[str]:
        """Create a pull request"""
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"

        title = self._format_pr_title(update_info, analysis)
        body = self._format_pr_body(update_info, analysis)

        data = {
            "title": title,
            "head": head_branch,
            "base": base_branch,
            "body": body,
        }

        try:
            response = requests.post(
                url, headers=self.headers, json=data, timeout=10
            )

            if response.status_code == 201:
                pr_data = response.json()
                pr_url = pr_data["html_url"]
                logger.info(f"✅ Created PR: {pr_url}")
                return pr_url
            else:
                logger.error(f"Failed to create PR: {response.status_code}")
                logger.error(response.text)
                return None

        except Exception as e:
            logger.error(f"Error creating PR: {e}")
            return None

    def _format_pr_title(self, update_info: Dict, analysis: Dict) -> str:
        """Format PR title"""
        recommendation = analysis.get("recommendation", "UPDATE")
        priority = analysis.get("priority", 5)

        emoji_map = {
            "UPDATE": "✨",
            "EVALUATE": "⚠️",
            "BLOCK": "🚫",
        }

        emoji = emoji_map.get(recommendation, "🔄")

        repo_name = update_info["repo"].split("/")[-1]
        version = update_info["version"]

        return f"{emoji} chore(deps): update {repo_name} to {version}"

    def _format_pr_body(self, update_info: Dict, analysis: Dict) -> str:
        """Format PR body with analysis"""
        repo = update_info["repo"]
        version = update_info["version"]
        changelog = update_info.get("changelog", "No changelog available")

        priority = analysis.get("priority", 5)
        recommendation = analysis.get("recommendation", "UPDATE")
        breaking_changes = analysis.get("breaking_changes", False)
        summary = analysis.get("summary", "")
        risks = analysis.get("risks", [])
        benefits = analysis.get("benefits", [])
        action_items = analysis.get("action_items", [])

        # Format priority indicator
        if priority >= 9:
            priority_label = "🔥 CRITICAL"
        elif priority >= 7:
            priority_label = "⚠️ HIGH"
        elif priority >= 4:
            priority_label = "📊 MEDIUM"
        else:
            priority_label = "📝 LOW"

        # Format recommendation
        rec_map = {
            "UPDATE": "✅ UPDATE",
            "EVALUATE": "⚠️ EVALUATE",
            "BLOCK": "🚫 BLOCK",
        }
        rec_label = rec_map.get(recommendation, recommendation)

        # Format breaking changes
        breaking_label = "❌ Yes" if breaking_changes else "✅ No"

        body = f"""## 🤖 Automated Dependency Update

**Repository**: `{repo}`
**Version**: `{version}`

---

## 📊 Update Analysis

**Priority**: {priority_label} ({priority}/10)
**Recommendation**: {rec_label}
**Breaking Changes**: {breaking_label}

## 📝 Summary
{summary}

## ⚠️ Risks
"""
        for risk in risks:
            body += f"- {risk}\n"

        if not risks:
            body += "- None identified\n"

        body += "\n## ✅ Benefits\n"
        for benefit in benefits:
            body += f"- {benefit}\n"

        if not benefits:
            body += "- None identified\n"

        body += "\n## 🔧 Action Items\n"
        for item in action_items:
            body += f"- [ ] {item}\n"

        if not action_items:
            body += "- [ ] Review changes\n- [ ] Run tests\n- [ ] Deploy to staging\n"

        body += f"\n## 📖 Changelog\n\n```\n{changelog[:1000]}\n```\n"

        body += """
---

🤖 This PR was automatically created by the [Maintenance Agent](https://github.com/unicorncomfyui/maintenance-agent)

Generated with [Claude Code](https://claude.com/claude-code)
"""

        return body
