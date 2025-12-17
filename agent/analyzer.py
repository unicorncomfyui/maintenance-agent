"""
Analyzer using Claude API to evaluate updates and provide recommendations
"""

import os
from anthropic import Anthropic
from typing import Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UpdateAnalyzer:
    """Analyze updates using Claude API"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-sonnet-4-5-20250929"

    def analyze_update(
        self,
        repo_name: str,
        current_version: str,
        new_version: str,
        changelog: str,
        context: str = "",
    ) -> Dict:
        """
        Analyze an update and provide recommendations

        Returns:
            {
                'priority': int (0-10),
                'recommendation': str ('UPDATE', 'EVALUATE', 'BLOCK', 'IGNORE'),
                'breaking_changes': bool,
                'summary': str,
                'risks': list[str],
                'benefits': list[str],
                'action_items': list[str]
            }
        """

        prompt = f"""You are a maintenance agent analyzing software updates for a RunPod ComfyUI deployment.

Repository: {repo_name}
Current Version: {current_version}
New Version: {new_version}

Changelog:
```
{changelog if changelog else "No changelog available"}
```

Context:
{context if context else "Standard ComfyUI deployment with CUDA 12.8.1, PyTorch nightly, SageAttention"}

{"**SPECIAL NOTE FOR RUNPOD UPDATES:**" if "runpod" in repo_name.lower() else ""}
{"If this is a RunPod platform update, focus on new features and architectural implications." if "runpod" in repo_name.lower() else ""}
{"Examples: model caching, cold start optimizations, network storage changes, API changes." if "runpod" in repo_name.lower() else ""}
{"These are often EVALUATE recommendations requiring architectural review rather than direct code updates." if "runpod" in repo_name.lower() else ""}

Please analyze this update and provide:

1. **Priority Score** (0-10):
   - 0-3: Minor, can wait
   - 4-6: Moderate, should evaluate
   - 7-8: Important, should update soon
   - 9-10: Critical, update immediately

2. **Recommendation** (one of):
   - UPDATE: Safe to update, beneficial (direct dependency update)
   - EVALUATE: Needs architectural review (new platform features, breaking changes)
   - BLOCK: Breaking changes, do not update yet
   - IGNORE: Not relevant or too minor

3. **Breaking Changes**: Are there any breaking changes?

4. **Summary**: 2-3 sentence summary of the update

5. **Risks**: Potential risks of updating

6. **Benefits**: Benefits of this update

7. **Action Items**: Specific actions needed if updating (for RunPod features: architectural review, testing, documentation)

Respond in JSON format:
{{
  "priority": <0-10>,
  "recommendation": "<UPDATE|EVALUATE|BLOCK|IGNORE>",
  "breaking_changes": <true|false>,
  "summary": "<summary>",
  "risks": ["<risk1>", "<risk2>"],
  "benefits": ["<benefit1>", "<benefit2>"],
  "action_items": ["<action1>", "<action2>"]
}}"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract JSON from response
            response_text = response.content[0].text
            import json

            # Try to parse JSON from response
            # Claude might wrap it in markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            analysis = json.loads(response_text.strip())

            logger.info(
                f"Analysis for {repo_name}: Priority {analysis['priority']}/10, "
                f"Recommendation: {analysis['recommendation']}"
            )

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing update: {e}")
            # Return safe defaults
            return {
                "priority": 5,
                "recommendation": "EVALUATE",
                "breaking_changes": False,
                "summary": f"Update from {current_version} to {new_version} detected. Manual review needed.",
                "risks": ["Unable to analyze automatically"],
                "benefits": ["Unknown"],
                "action_items": ["Review changelog manually"],
            }

    def should_create_issue(self, analysis: Dict, min_priority: int = 5) -> bool:
        """Determine if we should create a GitHub issue for this update"""
        priority = analysis.get("priority", 0)
        recommendation = analysis.get("recommendation", "IGNORE")

        # Always create issue for critical updates or blocks
        if priority >= 9 or recommendation == "BLOCK":
            return True

        # Create issue if priority meets threshold and it's not IGNORE
        if priority >= min_priority and recommendation != "IGNORE":
            return True

        return False

    def format_issue_body(
        self, repo_name: str, current: str, new: str, analysis: Dict, changelog: str, update_info: Dict = None
    ) -> str:
        """Format the GitHub issue body"""

        # Priority emoji
        priority = analysis.get("priority", 5)
        if priority >= 9:
            priority_emoji = "🚨"
        elif priority >= 7:
            priority_emoji = "⚠️"
        elif priority >= 5:
            priority_emoji = "💡"
        else:
            priority_emoji = "ℹ️"

        # Recommendation emoji
        rec = analysis.get("recommendation", "EVALUATE")
        rec_emoji = {
            "UPDATE": "✅",
            "EVALUATE": "🔍",
            "BLOCK": "🛑",
            "IGNORE": "⏭️",
        }.get(rec, "❓")

        # Extract source info from update_info
        source_url = ""
        release_date = ""
        if update_info:
            data = update_info.get("data", {})
            source_url = data.get("html_url", "")
            published_at = data.get("published_at", "") or data.get("created_at", "")
            if published_at:
                # Format date nicely (GitHub returns ISO format)
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    release_date = dt.strftime('%Y-%m-%d %H:%M UTC')
                except:
                    release_date = published_at

        # Build header with source info
        header = f"""## {priority_emoji} Update Available: {repo_name}

**Current Version:** `{current}`
**New Version:** `{new}`"""

        if source_url:
            header += f"\n**Source:** [View on GitHub]({source_url})"

        if release_date:
            header += f"\n**Released:** {release_date}"

        # Format benefits, risks, and action items
        benefits = analysis.get('benefits', ['No benefits listed'])
        benefits_str = '\n'.join(f"- {b}" for b in benefits)

        risks = analysis.get('risks', ['No risks identified'])
        risks_str = '\n'.join(f"- {r}" for r in risks)

        action_items = analysis.get('action_items', ['Review update'])
        action_items_str = '\n'.join(f"- [ ] {a}" for a in action_items)

        summary = analysis.get('summary', 'No summary available')

        body = header + f"""

---

### {rec_emoji} Recommendation: **{rec}**

**Priority:** {priority}/10

{summary}

---

### Benefits
{benefits_str}

### Potential Risks
{risks_str}

### Action Items
{action_items_str}

---

### Changelog

<details>
<summary>View Full Changelog</summary>

```
{changelog if changelog else "No changelog available"}
```

</details>

---

*🤖 This issue was automatically generated by the Maintenance Agent*
"""

        return body

    def format_issue_title(
        self, repo_name: str, new_version: str, analysis: Dict
    ) -> str:
        """Format the GitHub issue title"""
        rec = analysis.get("recommendation", "EVALUATE")
        priority = analysis.get("priority", 5)

        # Add emoji based on priority
        if priority >= 9:
            emoji = "🚨"
        elif priority >= 7:
            emoji = "⚠️"
        elif rec == "BLOCK":
            emoji = "🛑"
        else:
            emoji = "📦"

        return f"{emoji} [{rec}] {repo_name} {new_version} available"
