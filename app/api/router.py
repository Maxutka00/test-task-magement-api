from fastapi import APIRouter

from app.api.v1 import auth, comments, invitations, roles, tasks, teams, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(teams.router)
api_router.include_router(roles.router)
api_router.include_router(invitations.router)
api_router.include_router(tasks.router)
api_router.include_router(comments.router)
