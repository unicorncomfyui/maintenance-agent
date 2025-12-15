# Maintenance Agent

AI-powered maintenance agent that monitors dependencies and proposes updates for RunPod ComfyUI deployments.

## Overview

This agent automatically:
- Monitors GitHub repositories for updates (ComfyUI, SageAttention, PyTorch, custom nodes)
- Uses Claude API to analyze changelogs and provide intelligent recommendations
- Creates GitHub issues with priority scoring and actionable insights
- Runs daily via GitHub Actions

## Architecture

```
Sources (GitHub) → Agent (Claude API) → Actions (GitHub Issues)
```

**Monitored Sources**:
- ComfyUI (comfyanonymous/ComfyUI)
- SageAttention (thu-ml/SageAttention)
- PyTorch (pytorch/pytorch)
- Custom nodes and other dependencies

**Target Repositories**:
- [serverless_runpod](https://github.com/unicorncomfyui/serverless_runpod)
- [pod-comfyui-vscode](https://github.com/unicorncomfyui/pod-comfyui-vscode)

## Setup

### 1. Configure GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

**GH_PAT** (GitHub Personal Access Token):
- Needs `repo` scope to create issues
- Generate at: https://github.com/settings/tokens

**ANTHROPIC_API_KEY**:
- Get from: https://console.anthropic.com/

### 2. Configuration

Edit [config.yaml](config.yaml) to customize:
- Target repositories to maintain
- Sources to monitor
- Priority thresholds
- Notification settings
- Claude model settings

### 3. Run

The agent runs automatically:
- **Daily**: Every day at 9 AM UTC
- **Manual**: Click "Run workflow" in Actions tab
- **On push**: When `agent/` or `config.yaml` changes

## How It Works

### 1. Scanning

The agent scans each configured source repository for:
- New releases
- New tags
- Recent commits (last 7 days)

State is persisted in [agent/.agent_state.json](agent/.agent_state.json) to avoid duplicate notifications.

### 2. Analysis

For each update, Claude API analyzes:
- **Priority Score** (0-10): Urgency of the update
- **Recommendation**: UPDATE / EVALUATE / BLOCK / IGNORE
- **Breaking Changes**: Detection of breaking changes
- **Risks**: Potential issues with updating
- **Benefits**: Advantages of updating
- **Action Items**: Specific steps to take

### 3. Notification

If priority ≥ 4 and recommendation is not IGNORE:
- Creates GitHub issue in target repositories
- Adds labels based on priority and component
- Includes detailed analysis and action items

### 4. Pull Request Creation (Phase 2)

If `auto_create_pr: true` and priority ≥ 6:
- **Automatically creates PRs** with dependency updates
- Modifies relevant files (Dockerfile, requirements.txt, etc.)
- Includes full analysis in PR description
- Only for UPDATE and EVALUATE recommendations (not BLOCK)
- You review and merge manually

## Issue Format

```markdown
## 📊 Update Analysis

**Priority**: 🔥 8/10 (High)
**Recommendation**: ⚠️ EVALUATE
**Breaking Changes**: ❌ None detected

## 📝 Summary
[Claude's analysis of the update]

## ⚠️ Risks
- Risk 1
- Risk 2

## ✅ Benefits
- Benefit 1
- Benefit 2

## 🔧 Action Items
- [ ] Action 1
- [ ] Action 2
```

## Development

### Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GITHUB_TOKEN="your_token"
export ANTHROPIC_API_KEY="your_api_key"

# Run agent
cd agent
python main.py
```

### File Structure

```
maintenance-agent/
├── agent/
│   ├── main.py          # Main orchestrator
│   ├── scanners.py      # GitHub scanning + state management
│   ├── analyzer.py      # Claude API integration
│   ├── notifier.py      # GitHub issue creation
│   └── .agent_state.json # State persistence (auto-generated)
├── .github/
│   └── workflows/
│       └── daily-scan.yml # GitHub Actions workflow
├── config.yaml          # Configuration
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Configuration Reference

### Priority Levels

| Score | Label | Meaning |
|-------|-------|---------|
| 0-3 | Low | Minor updates, can wait |
| 4-6 | Medium | Should evaluate soon |
| 7-8 | High | Important, update soon |
| 9-10 | Critical | Security/critical fixes |

### Recommendations

- **UPDATE**: Safe to update, beneficial
- **EVALUATE**: Needs testing before update
- **BLOCK**: Breaking changes, don't update yet
- **IGNORE**: Not relevant or too minor

### Watch Types

- `releases`: Official releases
- `tags`: Version tags
- `commits`: Recent commits (last 7 days)

## Features

### Phase 1 (MVP) ✅
✅ Monitor GitHub releases, tags, and commits
✅ Intelligent analysis with Claude API
✅ Priority scoring (0-10) and recommendations
✅ Breaking change detection
✅ Automated issue creation with labels
✅ State persistence to avoid duplicates
✅ Manual workflow triggers

### Phase 2 (Current) ✅
✅ **Automated PR creation** with file modifications
✅ Smart file detection (Dockerfile, requirements.txt, init.sh)
✅ Configurable PR creation rules
✅ Priority-based PR filtering (min priority: 6)

### Phase 3 (Future)
- Additional sources (Reddit, HuggingFace, PyPI)
- Dependency graph analysis
- CI/CD integration with tests
- Auto-merge for safe updates
- Rollback capabilities

## Cost Estimation

**Claude API** (~$0.003 per analysis):
- Daily scan: ~5-10 updates analyzed
- Monthly cost: ~$0.45-$0.90

**GitHub Actions**: Free tier (2000 min/month)

## License

AGPL-3.0 (inherited from ComfyUI)

---

**Developed for RunPod Deployments**
- Python 3.11
- Anthropic Claude API (Sonnet 4.5)
- GitHub Actions
- YAML configuration

*Last update: December 2025*
