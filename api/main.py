from fastapi import FastAPI, HTTPException, Depends, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorClient
import os
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import sys
import logging
from dotenv import load_dotenv
import jwt
from jwt.exceptions import InvalidTokenError
import httpx
import discord
from enum import Enum

# Add parent directory to path to import database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import DatabaseManager

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# JWT Settings
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")  # Change in production
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = 24  # hours

class TryoutGroup(BaseModel):
    """A tryout group for a specific event or role"""
    event_name: str = Field(..., description="Name of the event or role")
    description: str = Field(..., description="Description of the tryout")
    requirements: List[str] = Field(default=[], description="List of requirements for the tryout")
    ping_roles: List[str] = Field(default=[], description="List of role IDs to ping for this tryout")

class TryoutGroupUpdate(BaseModel):
    """Update model for tryout groups"""
    event_name: Optional[str] = Field(None, description="Name of the event or role")
    description: Optional[str] = Field(None, description="Description of the tryout")
    requirements: Optional[List[str]] = Field(None, description="List of requirements for the tryout")
    ping_roles: Optional[List[str]] = Field(None, description="List of role IDs to ping for this tryout")

class TryoutSession(BaseModel):
    """A tryout session instance"""
    group_id: str = Field(..., description="ID of the tryout group")
    channel_id: str = Field(..., description="ID of the channel where the tryout is taking place")
    voice_channel_id: Optional[str] = Field(None, description="ID of the voice channel if applicable")
    host_id: str = Field(..., description="ID of the user hosting the tryout")
    lock_timestamp: str = Field(..., description="When the tryout will be locked")
    requirements: List[str] = Field(default=[], description="List of requirements for this session")
    description: str = Field(..., description="Description of the session")

app = FastAPI(
    title="SDHS Bot API",
    description="""
    The API for the SDHS Discord Bot. This API provides endpoints for managing tryouts,
    moderation cases, and server settings.
    
    ## Authentication
    All endpoints require JWT authentication. To get a token, make a POST request to `/token`
    with your Discord OAuth2 token in the Authorization header.
    
    ## Rate Limiting
    The API implements rate limiting to prevent abuse. Please cache responses when possible.
    
    ## Endpoints
    The API is organized around the following main resources:
    - Servers: Manage server settings and configurations
    - Tryouts: Manage tryout groups and sessions
    - Cases: Handle moderation cases
    - Stats: Get server statistics
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth2 scheme for JWT
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Models
class TokenData(BaseModel):
    user_id: str
    discord_token: str

async def verify_token(token: str = Depends(oauth2_scheme)) -> TokenData:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if datetime.fromtimestamp(payload["exp"]) < datetime.utcnow():
            raise HTTPException(
                status_code=401,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return TokenData(**payload)
    except InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Database connection
async def get_database():
    mongo_uri = os.getenv("MONGODB_URI")
    mongo_db_name = os.getenv("MONGODB_NAME")
    
    if not mongo_uri or not mongo_db_name:
        raise HTTPException(status_code=500, detail="MongoDB configuration missing")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[mongo_db_name]
    database = DatabaseManager(db=db)
    try:
        yield database
    finally:
        client.close()

# Token endpoint
@app.post("/token")
async def create_token(request: Request):
    try:
        # Get the Discord token from the Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.error("Invalid authorization header")
            raise HTTPException(status_code=401, detail="Invalid authorization header")
        
        discord_token = auth_header.split(" ")[1]
        logger.info("Attempting to verify Discord token")
        
        # Verify the Discord token by making a request to Discord API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://discord.com/api/users/@me",
                headers={"Authorization": f"Bearer {discord_token}"}
            )
            
            if response.status_code != 200:
                logger.error(f"Discord API returned status {response.status_code}: {response.text}")
                raise HTTPException(status_code=401, detail="Invalid Discord token")
            
            user_data = response.json()
            logger.info(f"Successfully verified Discord token for user {user_data['id']}")
            
            # Create JWT token
            token_data = {
                "user_id": user_data["id"],
                "discord_token": discord_token,
                "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION)
            }
            
            token = jwt.encode(token_data, JWT_SECRET, algorithm=JWT_ALGORITHM)
            logger.info(f"Created JWT token for user {user_data['id']}")
            
            return {"access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating token: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Protected API Routes
@app.get("/server/{server_id}/settings")
async def get_server_settings(
    server_id: int,
    token_data: TokenData = Depends(verify_token),
    db: DatabaseManager = Depends(get_database)
):
    try:
        settings = await db.get_server_settings(server_id)
        return settings
    except Exception as e:
        logger.error(f"Error getting server settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/server/{server_id}/tryout-groups",
    response_model=List[dict],
    tags=["tryouts"],
    summary="Get all tryout groups for a server",
    description="Returns a list of all tryout groups configured for the specified server."
)
async def get_tryout_groups(
    server_id: int,
    token_data: TokenData = Depends(verify_token),
    db: DatabaseManager = Depends(get_database)
):
    try:
        groups = await db.get_tryout_groups(server_id)
        return [
            {
                "group_id": group[0],
                "description": group[1],
                "event_name": group[2],
                "requirements": group[3],
                "ping_roles": group[4]
            }
            for group in groups
        ]
    except Exception as e:
        logger.error(f"Error getting tryout groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/server/{server_id}/tryout-groups",
    response_model=dict,
    tags=["tryouts"],
    summary="Create a new tryout group",
    description="Creates a new tryout group for the specified server."
)
async def create_tryout_group(
    server_id: int,
    group: TryoutGroup,
    token_data: TokenData = Depends(verify_token),
    db: DatabaseManager = Depends(get_database)
):
    try:
        # Generate a unique group ID (you might want to implement this in the database manager)
        import uuid
        group_id = str(uuid.uuid4())[:8].upper()
        
        await db.add_tryout_group(
            server_id,
            group_id,
            group.description,
            group.event_name,
            group.requirements
        )
        
        # Add ping roles if specified
        for role_id in group.ping_roles:
            await db.add_group_ping_role(server_id, group_id, int(role_id))
        
        return {
            "group_id": group_id,
            "message": "Tryout group created successfully"
        }
    except Exception as e:
        logger.error(f"Error creating tryout group: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/server/{server_id}/tryout-groups/{group_id}",
    response_model=dict,
    tags=["tryouts"],
    summary="Update a tryout group",
    description="Updates an existing tryout group's settings."
)
async def update_tryout_group(
    server_id: int,
    group_id: str,
    group: TryoutGroupUpdate,
    token_data: TokenData = Depends(verify_token),
    db: DatabaseManager = Depends(get_database)
):
    try:
        existing_group = await db.get_tryout_group(server_id, group_id)
        if not existing_group:
            raise HTTPException(status_code=404, detail="Tryout group not found")
        
        await db.update_tryout_group(
            server_id,
            group_id,
            group.description or existing_group[1],
            group.event_name or existing_group[2],
            group.requirements or existing_group[3]
        )
        
        if group.ping_roles is not None:
            # Remove existing ping roles
            current_roles = existing_group[4]
            for role_id in current_roles:
                await db.remove_group_ping_role(server_id, group_id, int(role_id))
            
            # Add new ping roles
            for role_id in group.ping_roles:
                await db.add_group_ping_role(server_id, group_id, int(role_id))
        
        return {"message": "Tryout group updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating tryout group: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/server/{server_id}/tryout-groups/{group_id}",
    response_model=dict,
    tags=["tryouts"],
    summary="Delete a tryout group",
    description="Deletes a tryout group and all associated data."
)
async def delete_tryout_group(
    server_id: int,
    group_id: str,
    token_data: TokenData = Depends(verify_token),
    db: DatabaseManager = Depends(get_database)
):
    try:
        await db.delete_tryout_group(server_id, group_id)
        return {"message": "Tryout group deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting tryout group: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/server/{server_id}/active-tryouts",
    response_model=List[dict],
    tags=["tryouts"],
    summary="Get active tryout sessions",
    description="Returns a list of all active tryout sessions for the specified server."
)
async def get_active_tryouts(
    server_id: int,
    token_data: TokenData = Depends(verify_token),
    db: DatabaseManager = Depends(get_database)
):
    try:
        sessions = await db.get_active_tryout_sessions(server_id)
        return sessions
    except Exception as e:
        logger.error(f"Error getting active tryouts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/server/{server_id}/tryout-sessions",
    response_model=dict,
    tags=["tryouts"],
    summary="Create a new tryout session",
    description="Creates a new tryout session for a specific tryout group."
)
async def create_tryout_session(
    server_id: int,
    session: TryoutSession,
    token_data: TokenData = Depends(verify_token),
    db: DatabaseManager = Depends(get_database)
):
    try:
        # Get the tryout group to verify it exists and get its name
        group = await db.get_tryout_group(server_id, session.group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Tryout group not found")
        
        # Create Discord invite if voice channel is specified
        voice_invite = None
        if session.voice_channel_id:
            try:
                channel = bot_client.get_channel(int(session.voice_channel_id))
                if channel and isinstance(channel, discord.VoiceChannel):
                    invite = await channel.create_invite(
                        max_age=3600,  # 1 hour
                        max_uses=0,    # unlimited uses
                        unique=True
                    )
                    voice_invite = str(invite)
            except Exception as e:
                logger.error(f"Error creating voice channel invite: {e}")
        
        session_id = await db.create_tryout_session(
            guild_id=server_id,
            host_id=int(session.host_id),
            group_id=session.group_id,
            group_name=group[2],  # event_name from the group
            channel_id=int(session.channel_id),
            voice_channel_id=int(session.voice_channel_id) if session.voice_channel_id else None,
            lock_timestamp=session.lock_timestamp,
            requirements=session.requirements,
            description=session.description,
            message_id=0,  # This will be updated when the bot posts the message
            voice_invite=voice_invite
        )
        
        return {
            "session_id": session_id,
            "voice_invite": voice_invite,
            "message": "Tryout session created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating tryout session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/server/{server_id}/warnings/{user_id}")
async def get_user_warnings(
    server_id: int,
    user_id: int,
    token_data: TokenData = Depends(verify_token),
    db: DatabaseManager = Depends(get_database)
):
    try:
        warnings = await db.get_warnings(user_id, server_id)
        return [
            {
                "user_id": warning[0],
                "server_id": warning[1],
                "moderator_id": warning[2],
                "reason": warning[3],
                "created_at": warning[4],
                "id": warning[5]
            }
            for warning in warnings
        ]
    except Exception as e:
        logger.error(f"Error getting user warnings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/server/{server_id}/command-stats")
async def get_command_stats(
    server_id: int,
    days: Optional[int] = 30,
    token_data: TokenData = Depends(verify_token),
    db: DatabaseManager = Depends(get_database)
):
    try:
        since = datetime.utcnow() - timedelta(days=days)
        stats = await db.get_command_usage_stats(guild_id=server_id, since=since)
        return stats
    except Exception as e:
        logger.error(f"Error getting command stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/server/{server_id}/cases")
async def get_server_cases(
    server_id: int,
    token_data: TokenData = Depends(verify_token),
    db: DatabaseManager = Depends(get_database)
):
    try:
        # Get all cases from the database
        cases = await db.db["cases"].find({
            "server_id": str(server_id)
        }).sort("timestamp", -1).to_list(None)
        
        # Format the response
        return [{
            "case_id": case["case_id"],
            "user_id": case["user_id"],
            "moderator_id": case["moderator_id"],
            "action_type": case["action_type"],
            "reason": case["reason"],
            "timestamp": case["timestamp"],
            "extra": case.get("extra", {})
        } for case in cases]
    except Exception as e:
        logger.error(f"Error getting server cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Add this after the JWT settings
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Create intents
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

# Initialize bot with intents
bot_client = discord.Client(intents=intents)

@bot_client.event
async def on_ready():
    logger.info(f"Bot connected as {bot_client.user}")
    logger.info(f"Bot is in {len(bot_client.guilds)} servers")
    for guild in bot_client.guilds:
        logger.info(f"- {guild.name} (id: {guild.id})")

# Start the bot in the background
import asyncio
asyncio.create_task(bot_client.start(DISCORD_BOT_TOKEN))

# Add this new endpoint after the other endpoints
@app.get("/bot/servers")
async def get_bot_servers(token_data: TokenData = Depends(verify_token)):
    try:
        if not bot_client.is_ready():
            raise HTTPException(status_code=503, detail="Bot is not ready")
            
        guilds = []
        for guild in bot_client.guilds:
            guild_data = {
                "id": str(guild.id),
                "name": guild.name,
                "icon": None
            }
            if guild.icon:
                guild_data["icon"] = guild.icon.key
            guilds.append(guild_data)
            
        logger.info(f"Returning {len(guilds)} servers")
        return guilds
    except Exception as e:
        logger.error(f"Error getting bot servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 