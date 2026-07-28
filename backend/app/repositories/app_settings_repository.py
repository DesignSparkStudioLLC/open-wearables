from typing import Any

from app.database import DbSession
from app.models import AppSetting


class AppSettingRepository:
    """Reads/writes the singleton app_settings row (id=1)."""

    def get(self, db: DbSession) -> AppSetting:
        return db.query(AppSetting).filter(AppSetting.id == 1).one()

    def update(self, db: DbSession, fields: dict[str, Any]) -> AppSetting:
        """Set the given columns on the singleton row and commit."""
        row = self.get(db)
        for key, value in fields.items():
            setattr(row, key, value)
        db.commit()
        db.refresh(row)
        return row
