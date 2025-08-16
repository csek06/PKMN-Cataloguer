import os
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.models import User
from app.logging import get_logger

logger = get_logger("auth")


class AuthService:
    """Authentication service for user management."""
    
    def __init__(self):
        self.secret_key = settings.secret_key
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 60 * 24 * 7  # 7 days
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    def create_access_token(self, username: str) -> str:
        """Create a JWT access token."""
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        to_encode = {"sub": username, "exp": expire}
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[str]:
        """Verify a JWT token and return the username."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            username: str = payload.get("sub")
            if username is None:
                return None
            return username
        except JWTError:
            return None
    
    def get_user_by_username(self, username: str, session: Session) -> Optional[User]:
        """Get a user by username (case-insensitive lookup)."""
        # Use case-insensitive comparison for username lookup
        statement = select(User).where(User.username.ilike(username))
        return session.exec(statement).first()
    
    def create_user(self, username: str, password: str, session: Session) -> User:
        """Create a new user."""
        # Check if user already exists (case-insensitive)
        existing_user = self.get_user_by_username(username, session)
        if existing_user:
            raise ValueError(f"User with username '{username}' already exists")
        
        password_hash = self.hash_password(password)
        user = User(
            username=username,  # Store username as provided (preserve original case)
            password_hash=password_hash,
            is_setup_complete=True
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        
        logger.info("user_created", username=username)
        return user
    
    def authenticate_user(self, username: str, password: str, session: Session) -> Optional[User]:
        """Authenticate a user with username and password (case-insensitive username)."""
        # Find user with case-insensitive username lookup
        user = self.get_user_by_username(username, session)
        if not user:
            logger.warning("authentication_failed_user_not_found", attempted_username=username)
            return None
        
        # Password verification is still case-sensitive (as it should be)
        if not self.verify_password(password, user.password_hash):
            logger.warning("authentication_failed_invalid_password", username=user.username)
            return None
        
        logger.info("user_authenticated", username=user.username, attempted_username=username)
        return user
    
    def change_password(self, username: str, old_password: str, new_password: str, session: Session) -> bool:
        """Change a user's password (case-insensitive username lookup)."""
        user = self.get_user_by_username(username, session)
        if not user:
            logger.warning("password_change_failed_user_not_found", attempted_username=username)
            return False
        
        if not self.verify_password(old_password, user.password_hash):
            logger.warning("password_change_failed_invalid_old_password", username=user.username)
            return False
        
        user.password_hash = self.hash_password(new_password)
        user.updated_at = datetime.utcnow()
        session.add(user)
        session.commit()
        
        logger.info("password_changed", username=user.username)
        return True
    
    def is_setup_required(self, session: Session) -> bool:
        """Check if initial setup is required (no users exist)."""
        statement = select(User)
        user = session.exec(statement).first()
        return user is None
    
    def check_admin_reset_password(self, username: str, password: str) -> bool:
        """Check if admin reset password is being used."""
        admin_reset_password = os.getenv("ADMIN_RESET_PASSWORD")
        if not admin_reset_password:
            return False
        
        # Allow login with any username if admin reset password is provided
        return password == admin_reset_password
    
    def force_password_change(self, username: str, new_password: str, session: Session) -> bool:
        """Force change password (used with admin reset, case-insensitive username lookup)."""
        user = self.get_user_by_username(username, session)
        if not user:
            # If user doesn't exist, create them
            try:
                self.create_user(username, new_password, session)
                return True
            except ValueError:
                # User already exists (race condition), try to find them again
                user = self.get_user_by_username(username, session)
                if not user:
                    return False
        
        user.password_hash = self.hash_password(new_password)
        user.updated_at = datetime.utcnow()
        session.add(user)
        session.commit()
        
        logger.info("password_force_changed", username=user.username)
        return True


# Global auth service instance
auth_service = AuthService()
