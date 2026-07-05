"""
Git-backed version control service for master configuration files.

Provides transactional file commits with author attribution,
concurrency serialization via locking, file history, and rollback.
"""

import logging
import threading
from pathlib import Path

from git import Actor, GitCommandError, Repo

logger = logging.getLogger(__name__)


class GitService:
    """Manages a file-based Git repository for configuration storage."""

    def __init__(self, repo_path: str = "data/master_config"):
        self.repo_path = Path(repo_path).resolve()
        self.repo_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        try:
            if not (self.repo_path / ".git").exists():
                self.repo = Repo.init(self.repo_path)
                logger.info("Initialized new Git repository at %s", self.repo_path)
            else:
                self.repo = Repo(self.repo_path)
                logger.info("GitService connected to existing repo: %s", self.repo_path)
        except Exception as e:
            logger.error("Failed to initialize Git repository at %s: %s", self.repo_path, e)
            self.repo = None

    # ── helpers ──────────────────────────────────────────────────

    def _rel(self, abs_path: Path) -> str:
        """Return the repo-relative path as a string."""
        return str(abs_path.resolve().relative_to(self.repo_path))

    @staticmethod
    def _actor(name: str, email: str) -> Actor:
        return Actor(name, email)

    # ── commit operations ────────────────────────────────────────

    def commit_file(
        self,
        file_path: str,
        message: str,
        author_name: str = "System",
        author_email: str = "system@local",
    ) -> bool:
        """
        Stage and commit a single file.  Transactional: if the commit
        fails the file is rolled back (deleted if new, restored if updated).
        Serialized via a threading lock (REQ-1.7).
        """
        if not self.repo:
            logger.error("Git repository not initialized.")
            return False

        abs_path = Path(file_path).resolve()
        rel = self._rel(abs_path)
        actor = self._actor(author_name, author_email)

        with self._lock:
            # Capture previous content for rollback
            previous_content: bytes | None = None
            existed_before = abs_path.exists()
            if existed_before:
                previous_content = abs_path.read_bytes()

            try:
                self.repo.index.add([rel])
                self.repo.index.commit(message, author=actor, committer=actor)
                logger.info("Committed %s by %s <%s>", rel, author_name, author_email)
                return True
            except Exception as e:
                logger.error("Git commit failed for %s: %s — rolling back", rel, e)
                # Transactional rollback (REQ-1.6)
                try:
                    if existed_before and previous_content is not None:
                        abs_path.write_bytes(previous_content)
                    elif abs_path.exists():
                        abs_path.unlink()
                    # Reset the index
                    self.repo.head.reset(index=True, working_tree=True)
                except Exception as rb_err:
                    logger.error("Rollback also failed: %s", rb_err)
                return False

    def commit_multiple_files(
        self,
        file_paths: list[str],
        message: str,
        author_name: str = "System",
        author_email: str = "system@local",
    ) -> bool:
        """
        Stage and commit multiple files in a single transaction.
        If any part fails, roll back all modified files to their previous state.
        """
        if not self.repo:
            return False

        actor = self._actor(author_name, author_email)

        with self._lock:
            backups = {}
            for path_str in file_paths:
                p = Path(path_str).resolve()
                rel = self._rel(p)
                existed = p.exists()
                content = p.read_bytes() if existed else None
                backups[rel] = (p, existed, content)

            try:
                rels = [self._rel(Path(p).resolve()) for p in file_paths]
                self.repo.index.add(rels)
                self.repo.index.commit(message, author=actor, committer=actor)
                logger.info("Committed %d files by %s <%s>", len(file_paths), author_name, author_email)
                return True
            except Exception as e:
                logger.error("Git bulk commit failed: %s — rolling back", e)
                for rel, (p, existed, content) in backups.items():
                    try:
                        if existed and content is not None:
                            p.write_bytes(content)
                        elif p.exists():
                            p.unlink()
                    except Exception as rb_err:
                        logger.error("Failed to restore file %s: %s", rel, rb_err)
                try:
                    self.repo.head.reset(index=True, working_tree=True)
                except Exception as reset_err:
                    logger.error("Reset failed: %s", reset_err)
                return False

    def remove_and_commit_file(
        self,
        file_path: str,
        message: str,
        author_name: str = "System",
        author_email: str = "system@local",
    ) -> bool:
        """Remove a file from the working tree and commit the deletion."""
        if not self.repo:
            return False

        abs_path = Path(file_path).resolve()
        rel = self._rel(abs_path)
        actor = self._actor(author_name, author_email)

        with self._lock:
            try:
                self.repo.index.remove([rel], working_tree=True)
                self.repo.index.commit(message, author=actor, committer=actor)
                logger.info("Committed deletion of %s", rel)
                return True
            except Exception as e:
                logger.error("Error during file removal and commit: %s", e)
                return False

    # ── history & rollback ───────────────────────────────────────

    def get_file_history(self, rel_path: str, max_count: int = 50) -> list[dict]:
        """
        Return the commit history for a specific file.
        Each entry contains: commit_sha, author_name, author_email, date, message.
        """
        if not self.repo:
            return []

        try:
            commits = list(self.repo.iter_commits(paths=rel_path, max_count=max_count))
            return [
                {
                    "commit_sha": c.hexsha,
                    "author_name": c.author.name,
                    "author_email": c.author.email,
                    "date": c.committed_datetime.isoformat(),
                    "message": c.message.strip(),
                }
                for c in commits
            ]
        except Exception as e:
            logger.error("Failed to get history for %s: %s", rel_path, e)
            return []

    def restore_file(
        self,
        rel_path: str,
        commit_sha: str,
        author_name: str = "System",
        author_email: str = "system@local",
    ) -> bool:
        """
        Restore a file to its state at a specific commit.
        Creates a new commit recording the restoration.
        """
        if not self.repo:
            return False

        actor = self._actor(author_name, author_email)

        with self._lock:
            try:
                # Checkout the file content from the target commit
                self.repo.git.checkout(commit_sha, "--", rel_path)
                self.repo.index.add([rel_path])
                self.repo.index.commit(
                    f"Restore {rel_path} to version {commit_sha[:8]}",
                    author=actor,
                    committer=actor,
                )
                logger.info("Restored %s to commit %s", rel_path, commit_sha[:8])
                return True
            except Exception as e:
                logger.error("Failed to restore %s to %s: %s", rel_path, commit_sha, e)
                return False
