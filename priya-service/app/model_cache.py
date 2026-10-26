from pathlib import Path

from .config import settings


def local_huggingface_snapshot(repo_id: str, required_files: tuple[str, ...] = ('config.json',)) -> Path | None:
    """Resolve a complete local Hugging Face snapshot without network access."""
    repo_dir = settings.hf_cache_dir / f'models--{repo_id.replace("/", "--")}'
    snapshots = repo_dir / 'snapshots'
    ref = repo_dir / 'refs' / 'main'
    candidates: list[Path] = []
    if ref.is_file():
        revision = ref.read_text(encoding='utf-8').strip()
        if revision:
            candidates.append(snapshots / revision)
    if snapshots.is_dir():
        candidates.extend(sorted((p for p in snapshots.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True))
    return next((candidate for candidate in candidates if all((candidate / name).is_file() for name in required_files)), None)
