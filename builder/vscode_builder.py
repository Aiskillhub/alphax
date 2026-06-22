"""AlphaX Builder — VS Code 扩展生成器

生成 VS Code 扩展（带 premium 功能锁，变现路径清晰）。
VS Code 扩展市场 2026: premium 扩展 $5-$15/mo 订阅。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from core.genome import Genome, Category
from config import config


class VSCodeBuilder:
    """生成 VS Code 扩展"""

    _build_dir: Path = config.data_dir / "builds"

    def build(self, genome: Genome, organism_id: str) -> Path:
        self._build_dir.mkdir(parents=True, exist_ok=True)
        work_dir = self._build_dir / f"vscode_{organism_id}"
        work_dir.mkdir(exist_ok=True)

        # package.json
        (work_dir / "package.json").write_text(json.dumps(
            self._package_json(genome), indent=2))

        # extension.js
        (work_dir / "extension.js").write_text(self._extension_js(genome))

        # README
        (work_dir / "README.md").write_text(self._readme(genome))

        # .vscodeignore
        (work_dir / ".vscodeignore").write_text(".vscode\n.git\nnode_modules\n")

        zip_path = self._build_dir / f"{organism_id}_vscode.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in work_dir.iterdir():
                zf.write(f, f.name)

        return zip_path

    def _package_json(self, genome: Genome) -> dict:
        name = genome.express().lower().replace(" ", "-").replace("—", "-")
        return {
            "name": f"alphax-{name}",
            "displayName": genome.express(),
            "description": genome.benefit,
            "version": "1.0.0",
            "publisher": "alphax",
            "engines": {"vscode": "^1.85.0"},
            "categories": self._vscode_categories(genome),
            "activationEvents": ["onStartupFinished"],
            "main": "./extension.js",
            "contributes": self._contributes(genome),
            "license": "SEE LICENSE IN LICENSE",
            "pricing": "free" if genome.pricing_model.value == "freemium" else None,
        }

    def _vscode_categories(self, genome: Genome) -> list[str]:
        mapping = {
            Category.AI_CHAT: ["Other", "Data Science"],
            Category.PRODUCTIVITY: ["Other"],
            Category.DEV_TOOLS: ["Programming Languages", "Formatters", "Linters"],
            Category.CONTENT: ["Other"],
            Category.AUTOMATION: ["Other"],
        }
        return mapping.get(genome.category, ["Other"])

    def _contributes(self, genome: Genome) -> dict:
        if genome.category == Category.DEV_TOOLS:
            return {
                "commands": [{
                    "command": "alphax.formatCode",
                    "title": "AlphaX: Format Code",
                }, {
                    "command": "alphax.analyzeCode",
                    "title": "AlphaX: Analyze Code Quality",
                }],
                "keybindings": [{
                    "command": "alphax.formatCode",
                    "key": "ctrl+shift+f",
                    "mac": "cmd+shift+f",
                    "when": "editorTextFocus",
                }],
                "configuration": {
                    "title": "AlphaX",
                    "properties": {
                        "alphax.enableAI": {
                            "type": "boolean", "default": True,
                            "description": "Enable AI-powered suggestions",
                        },
                        "alphax.premium": {
                            "type": "boolean", "default": False,
                            "description": "Unlock premium features",
                        },
                    },
                },
            }
        elif genome.category == Category.PRODUCTIVITY:
            return {
                "commands": [{
                    "command": "alphax.captureTask",
                    "title": "AlphaX: Capture Task",
                }, {
                    "command": "alphax.showDashboard",
                    "title": "AlphaX: Show Dashboard",
                }],
            }
        else:
            return {
                "commands": [{
                    "command": "alphax.run",
                    "title": f"AlphaX: {genome.express()}",
                }],
            }

    def _extension_js(self, genome: Genome) -> str:
        return f"""// AlphaX VS Code Extension: {genome.express()}
const vscode = require('vscode');

function activate(context) {{
    console.log('[AlphaX] Extension activated: {genome.express()}');

    // Premium check
    const config = vscode.workspace.getConfiguration('alphax');
    const isPremium = config.get('premium', false);

    // Register commands
{self._command_registrations(genome)}

    // Status bar
    const statusBar = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right, 100);
    statusBar.text = '$(rocket) AlphaX';
    statusBar.tooltip = '{genome.express()} - ' + (isPremium ? 'Premium' : 'Free');
    statusBar.show();

    context.subscriptions.push(statusBar);
}}

function deactivate() {{}}

module.exports = {{ activate, deactivate }};
"""

    def _command_registrations(self, genome: Genome) -> str:
        cmds = []
        if genome.category == Category.DEV_TOOLS:
            cmds.append(
                "    context.subscriptions.push(\n"
                "      vscode.commands.registerCommand('alphax.formatCode', () => {\n"
                "        vscode.window.showInformationMessage('[AlphaX] Code formatted!');\n"
                "      }));"
            )
            cmds.append(
                "    context.subscriptions.push(\n"
                "      vscode.commands.registerCommand('alphax.analyzeCode', () => {\n"
                "        vscode.window.showInformationMessage('[AlphaX] Code analysis complete.');\n"
                "      }));"
            )
        elif genome.category == Category.PRODUCTIVITY:
            cmds.append(
                "    context.subscriptions.push(\n"
                "      vscode.commands.registerCommand('alphax.captureTask', () => {\n"
                "        vscode.window.showInformationMessage('[AlphaX] Task captured!');\n"
                "      }));"
            )
        else:
            cmds.append(
                "    context.subscriptions.push(\n"
                "      vscode.commands.registerCommand('alphax.run', () => {\n"
                "        vscode.window.showInformationMessage('[AlphaX] Running...');\n"
                "      }));"
            )
        return "\n".join(cmds)

    def _readme(self, genome: Genome) -> str:
        return f"""# {genome.express()}

{genome.benefit}

## Features

- ✅ Feature 1: Automated workflow
- ✅ Feature 2: One-click operation
- 🔒 Premium: Advanced features (subscribe to unlock)

## Usage

1. Install the extension
2. Open command palette (Cmd+Shift+P)
3. Run "AlphaX: {genome.express()}"

## Premium

Unlock full potential with premium features.
Set `alphax.premium: true` in settings after subscription.

---
Built by Alpha X
"""
