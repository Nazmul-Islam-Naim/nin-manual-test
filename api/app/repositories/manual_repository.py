from sqlalchemy.orm import Session

from app.models import Manual


class ManualRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, manual: Manual) -> Manual:
        self.db.add(manual)
        self.db.commit()
        return manual

    def get(self, manual_id: str) -> Manual | None:
        return self.db.get(Manual, manual_id)
