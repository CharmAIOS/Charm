import hashlib
from typing import Any, Dict, List

from .protocol import EVENT_PREFIX


class SkillInstaller:
    @staticmethod
    def _calculate_skill_hash(source: str, version: str = "latest") -> str:
        """
        Calculate unique Hash for Skill, used for cache path.
        Same Source + Same Version = Same Hash (Cache Hit)
        """
        raw = f"{source}@{version}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    @staticmethod
    def generate_skill_install_block(skills: List[Dict[str, Any]]) -> str:
        """
        Generate Bash script block: handles cache checking, Skill installation, and linking.
        Now supports Git (Smart Update) and HTTP Zip (OpenClaw Hub).
        """
        if not skills:
            return ""

        script_lines = [
            "\n# --- Dynamic Skill Loading System ---",
            "mkdir -p ./skills",
            f'echo \'{EVENT_PREFIX}{{"type":"status","content":"Checking Skill Cache..."}}\'',
        ]

        for skill in skills:
            name = skill.get("name")
            source = skill.get("source", "")
            version = skill.get("version", "latest")

            # --- Handle Git and HTTP (Zip) Sources ---
            if source.startswith("git:") or source.startswith("http"):
                skill_hash = SkillInstaller._calculate_skill_hash(source, version)
                cache_path = f"/charm_cache/skills/{skill_hash}"
                local_link_path = f"./skills/{name}"

                # Identify Source Type
                is_zip = source.endswith(".zip") or ".zip?" in source
                clean_url = source.replace("git:", "")

                script_lines.append(f"\n# Skill: {name}")
                script_lines.append(f"if [ -d '{cache_path}' ]; then")

                # --- Cache Hit Logic ---
                if not is_zip and version in ["latest", "main", "master", ""]:
                    # Git Smart Update
                    script_lines.append(
                        f"    echo '⚡ Cache Hit. Checking Git updates for {name}...'"
                    )
                    script_lines.append(f"    cd '{cache_path}'")
                    script_lines.append(f"    git fetch -q origin {version or 'HEAD'}")
                    script_lines.append(
                        '    if [ "$(git rev-parse HEAD)" != "$(git rev-parse FETCH_HEAD)" ]; then'
                    )
                    script_lines.append("        echo '🔄 New version detected. Updating...'")
                    script_lines.append("        git merge FETCH_HEAD -q")
                    script_lines.append("        UPDATED=1")
                    script_lines.append("    else")
                    script_lines.append("        UPDATED=0")
                    script_lines.append("    fi")
                    script_lines.append("    cd - > /dev/null")
                else:
                    # Zip or Pinned Git: Trust Cache
                    script_lines.append(
                        f"    echo '⚡ Cache Hit ({'Zip' if is_zip else 'Pinned'}). Skipping download.'"
                    )
                    script_lines.append("    UPDATED=0")

                script_lines.append("else")

                # --- Cache Miss: Download Logic ---
                script_lines.append(f"    echo '⬇️ Installing Skill: {name}...'")
                script_lines.append(f"    rm -rf '{cache_path}' && mkdir -p '{cache_path}'")

                if is_zip:
                    # Zip Handling using Python
                    script_lines.append("    echo '📦 Downloading Zip artifact...'")
                    script_lines.append(
                        f"    curl -L -s '{clean_url}' -o /tmp/skill_{skill_hash}.zip"
                    )
                    script_lines.append(
                        f"    python3 -m zipfile -e /tmp/skill_{skill_hash}.zip '{cache_path}'"
                    )
                    script_lines.append(f"    rm /tmp/skill_{skill_hash}.zip")
                    # Handle nested folders: if zip contains a single folder, move contents up
                    script_lines.append(
                        f"    if [ $(ls '{cache_path}' | wc -l) -eq 1 ] && [ -d '{cache_path}/'$(ls '{cache_path}') ]; then"
                    )
                    script_lines.append(
                        f"        mv '{cache_path}/'*/* '{cache_path}/' && rm -rf '{cache_path}/'$(ls '{cache_path}')"
                    )
                    script_lines.append("    fi")
                else:
                    # Git Clone
                    script_lines.append(f"    git clone --depth 1 {clean_url} '{cache_path}'")

                script_lines.append("    UPDATED=1")
                script_lines.append("fi")

                # --- Dependency Management (Common) ---
                # Python
                script_lines.append(f"if [ -f '{cache_path}/requirements.txt' ]; then")
                script_lines.append(
                    f"    REQ_HASH=$(md5sum '{cache_path}/requirements.txt' | awk '{{print $1}}')"
                )
                script_lines.append(
                    f"    INSTALLED_HASH=$(cat '/tmp/{name}_req.hash' 2>/dev/null || echo '')"
                )
                script_lines.append(
                    '    if [ "$UPDATED" -eq 1 ] || [ "$REQ_HASH" != "$INSTALLED_HASH" ]; then'
                )
                script_lines.append(f"        echo '🐍 Installing Python deps for {name}...'")
                script_lines.append(f"        uv pip install -q -r '{cache_path}/requirements.txt'")
                script_lines.append(f"        echo \"$REQ_HASH\" > '/tmp/{name}_req.hash'")
                script_lines.append("    fi")
                script_lines.append("fi")

                # Node.js
                script_lines.append(f"if [ -f '{cache_path}/package.json' ]; then")
                script_lines.append(
                    f"    if [ \"$UPDATED\" -eq 1 ] || [ ! -d '{cache_path}/node_modules' ]; then"
                )
                script_lines.append(f"        echo '📦 Installing Node deps for {name}...'")
                script_lines.append(
                    f"        cd '{cache_path}' && npm install --production --no-audit --quiet && cd -"
                )
                script_lines.append("    fi")
                script_lines.append("fi")

                # Linking
                script_lines.append(f"rm -rf '{local_link_path}'")
                script_lines.append(f"ln -s '{cache_path}' '{local_link_path}'")

            # --- NPM Skills ---
            elif source.startswith("smithery:") or source.startswith("npm:"):
                pkg_name = source.replace("smithery:", "").replace("npm:", "")
                script_lines.append(f"\n# Skill (NPM): {name}")
                script_lines.append("if command -v npm &> /dev/null; then")
                script_lines.append(f"    echo '📦 Pre-installing NPM Package: {pkg_name}...'")
                script_lines.append(f"    npm install -g {pkg_name} --quiet")
                script_lines.append("else")
                script_lines.append(f"    echo '⚠️ Node.js not found. Skipping {name}.'")
                script_lines.append("fi")

            # --- PyPI Skills ---
            elif source.startswith("pip:") or source.startswith("pypi:"):
                pkg_name = source.replace("pip:", "").replace("pypi:", "")
                script_lines.append(f"\n# Skill (PyPI): {name}")
                script_lines.append(f"echo '🐍 Pre-installing PyPI Package: {pkg_name}...'")
                script_lines.append(f"uv pip install {pkg_name}")

        return "\n".join(script_lines)
