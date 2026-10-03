from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from database.db import scalar
from services.core import broadcast, esc
from web.app import render
from web.deps import actor, form_with_csrf, require

router = APIRouter()


@router.get("/broadcast")
async def page(request: Request, user=Depends(require())):
    return render(request, "broadcast.html", users=await scalar("SELECT COUNT(*) FROM users"), result=None, text="")


@router.post("/broadcast")
async def send(request: Request):
    form, user = await form_with_csrf(request)
    text = str(form.get("text", "")).strip()
    users = await scalar("SELECT COUNT(*) FROM users")
    if not 3 <= len(text) <= 3500:
        return RedirectResponse("/broadcast?err=bad_input", status_code=303)
    if not form.get("confirm"):
        return render(request, "broadcast.html", users=users, result=None, text=text, preview=True)
    sent, failed = await broadcast(request.app.state.bot, esc(text), actor(user, request))
    return render(request, "broadcast.html", users=users, result={"sent": sent, "failed": failed}, text="")
