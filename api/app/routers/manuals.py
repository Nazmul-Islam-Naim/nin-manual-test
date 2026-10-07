from fastapi import APIRouter, Depends, Request
from starlette.datastructures import UploadFile

from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.repositories.manual_repository import ManualRepository
from app.schemas import ManualCreated, ManualOut
from app.services.manual_service import ManualService

router = APIRouter(prefix="/manuals", tags=["manuals"])


def get_service(db=Depends(get_db)) -> ManualService:
    return ManualService(ManualRepository(db), get_settings())


def _invalid(msg: str) -> AppError:
    return AppError(422, "invalid_request", msg)


# ponytail: async handler with sync DB calls blocks the loop briefly; fine for this scale.
@router.post("", status_code=201, response_model=ManualCreated)
async def create_manual(request: Request, svc: ManualService = Depends(get_service)):
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype == "multipart/form-data":
        try:
            form = await request.form()
        except Exception:
            raise _invalid("Malformed multipart body.")
        f = form.get("file")
        if isinstance(f, UploadFile) and f.filename:  # file wins over text
            # read limit+1 so oversized uploads are detected without loading everything
            data = await f.read(svc.settings.max_upload_bytes + 1)
            return ManualCreated.from_model(svc.create_from_file(f.filename, data))
        text = form.get("text")
        if isinstance(text, str):
            return ManualCreated.from_model(svc.create_from_text(text))
        raise _invalid("Provide either 'text' or a 'file'.")
    if ctype == "application/json":
        try:
            body = await request.json()
        except Exception:
            raise _invalid("Body is not valid JSON.")
        if not isinstance(body, dict) or not isinstance(body.get("text"), str):
            raise _invalid("Provide either 'text' or a 'file'.")
        return ManualCreated.from_model(svc.create_from_text(body["text"]))
    raise _invalid("Content-Type must be application/json or multipart/form-data.")


@router.get("/{manual_id}", response_model=ManualOut)
def get_manual(manual_id: str, svc: ManualService = Depends(get_service)):
    return ManualOut.from_model(svc.get(manual_id))
