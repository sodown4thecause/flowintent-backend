"""Authentication service for the Natural Language Workflow Platform."""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from src.config import settings
from src.models.user import User
from src.services.database import DatabaseService, get_db


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class AuthService:
    """Service for user authentication and authorization."""
    
    def __init__(self, db: DatabaseService):
        """Initialize the auth service."""
        self.db = db
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Generate a password hash."""
        return pwd_context.hash(password)
    
    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user by email and password."""
        query = """
            SELECT id, email, name, preferences, created_at, subscription_tier, password_hash
            FROM users
            WHERE email = $1
        """
        
        user_data = await self.db.fetchrow(query, email)
        
        if not user_data:
            return None
        
        if not self.verify_password(password, user_data["password_hash"]):
            return None
        
        # Create User object (excluding password_hash)
        user_dict = dict(user_data)
        user_dict.pop("password_hash")
        
        return User(**user_dict)
    
    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
        
        to_encode.update({"exp": expire})
        
        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    
    async def get_current_user(self, token: str = Depends(oauth2_scheme)) -> User:
        """Get the current user from a JWT token."""
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        try:
            # Decode JWT token
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            user_id: str = payload.get("sub")
            
            if user_id is None:
                raise credentials_exception
        except jwt.PyJWTError:
            raise credentials_exception
        
        # Get user from database
        query = """
            SELECT id, email, name, preferences, created_at, subscription_tier
            FROM users
            WHERE id = $1
        """
        
        user_data = await self.db.fetchrow(query, user_id)
        
        if user_data is None:
            raise credentials_exception
        
        return User(**dict(user_data))
    
    async def register_user(self, email: str, password: str, name: str) -> User:
        """Register a new user."""
        # Check if user already exists
        query = "SELECT id FROM users WHERE email = $1"
        existing_user = await self.db.fetchval(query, email)
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Hash password
        password_hash = self.get_password_hash(password)
        
        # Insert user into database
        query = """
            INSERT INTO users (email, name, password_hash)
            VALUES ($1, $2, $3)
            RETURNING id, email, name, preferences, created_at, subscription_tier
        """
        
        user_data = await self.db.fetchrow(query, email, name, password_hash)
        
        return User(**dict(user_data))


# Dependency
async def get_auth_service(db: DatabaseService = Depends(get_db)) -> AuthService:
    """Get auth service instance."""
    return AuthService(db)


# Current user dependency
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service)
) -> User:
    """Get the current authenticated user."""
    return await auth_service.get_current_user(token)


# Optional current user dependency
async def get_optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service)
) -> Optional[User]:
    """Get the current user if authenticated, or None."""
    if not token:
        return None
    
    try:
        return await auth_service.get_current_user(token)
    except HTTPException:
        return None