import os
import tempfile
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    bot_token: str
    allowed_user_ids: set[int] = field(default_factory=set)
    max_file_mb: int = 50
    download_dir: str = "/tmp/downloads"

    @classmethod
    def load(cls) -> "Config":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("BOT_TOKEN environment variable is required")

        allowed_raw = os.getenv("ALLOWED_USER_IDS", "").strip()
        allowed = set()
        if allowed_raw:
            for item in allowed_raw.split(","):
                val = item.strip()
                if val.isdigit():
                    allowed.add(int(val))

        try:
            max_mb = int(os.getenv("MAX_FILE_MB", "50"))
        except ValueError:
            max_mb = 50

        download_dir = os.getenv("DOWNLOAD_DIR", "/tmp/downloads")
        os.makedirs(download_dir, exist_ok=True)

        return cls(
            bot_token=token,
            allowed_user_ids=allowed,
            max_file_mb=max_mb,
            download_dir=download_dir,
        )


config = Config.load()