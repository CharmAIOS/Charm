import git
from pathlib import Path
from typing import Dict, Optional, Tuple

class GitError(Exception):
    pass

def get_repo_info(project_path: Path) -> Dict[str, str]:
    try:
        repo = git.Repo(project_path, search_parent_directories=True)
    except git.exc.InvalidGitRepositoryError:
        raise GitError("Current directory is not a git repository.")

    try:
        remote_url = repo.remotes.origin.url
        if remote_url.startswith("git@"):
            remote_url = remote_url.replace(":", "/").replace("git@", "https://")
        if remote_url.endswith(".git"):
            remote_url = remote_url[:-4]
    except AttributeError:
        raise GitError("No remote 'origin' found. Please add a remote pointing to GitHub.")

    try:
        branch = repo.active_branch.name
    except TypeError:
        branch = "HEAD"
        
    commit = repo.head.commit.hexsha

    is_dirty = repo.is_dirty(untracked_files=True)
    
    
    return {
        "url": remote_url,
        "branch": branch,
        "commit": commit,
        "is_dirty": str(is_dirty) 
    }