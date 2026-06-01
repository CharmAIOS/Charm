from pathlib import Path
from typing import Dict
from urllib.parse import urlparse, urlunparse

import git


class GitError(Exception):
    pass


def get_repo_info(project_path: Path) -> Dict[str, str]:
    try:
        repo = git.Repo(project_path, search_parent_directories=True)
    except git.exc.InvalidGitRepositoryError as e:
        raise GitError("Current directory is not a git repository.") from e

    try:
        remote_url = repo.remotes.origin.url
        if remote_url.startswith("git@"):
            remote_url = remote_url.replace(":", "/").replace("git@", "https://")
            
        parsed = urlparse(remote_url)
        if parsed.netloc and (parsed.username or parsed.password):
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc += f":{parsed.port}"
            parsed = parsed._replace(netloc=netloc)
            remote_url = urlunparse(parsed)
            
        if remote_url.endswith(".git"):
            remote_url = remote_url[:-4]
    except AttributeError as e:
        raise GitError("No remote 'origin' found. Please add a remote pointing to GitHub.") from e

    try:
        branch = repo.active_branch.name
    except TypeError:
        branch = "HEAD"

    commit = repo.head.commit.hexsha

    is_dirty = repo.is_dirty(untracked_files=True)

    return {"url": remote_url, "branch": branch, "commit": commit, "is_dirty": str(is_dirty)}
