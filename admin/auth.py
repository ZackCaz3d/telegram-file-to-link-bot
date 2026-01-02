from fastapi import Request
from fastapi.responses import RedirectResponse

def admin_required(request: Request):
    if not request.session.get("admin_id"):
        return RedirectResponse(
            url="/admin/login",
            status_code=303,
        )
