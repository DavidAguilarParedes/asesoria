from functools import partial

from asesoria.config import Settings
from asesoria.domain.models import SourceDoc
from asesoria.infrastructure import downloader


def load_sources(settings: Settings) -> list[SourceDoc]:
    return downloader.read_sources(settings.data_dir / "sources.yaml")


def make_fetcher(settings: Settings, force: bool = False):
    return partial(downloader.download, user_agent=settings.sec_user_agent, force=force)
