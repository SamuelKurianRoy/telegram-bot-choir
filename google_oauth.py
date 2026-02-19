"""
Google OAuth Integration for Streamlit App
Provides "Sign in with Google" functionality
"""

import streamlit as st
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import google.auth.transport.requests
import requests
import json
import os
import time
from pathlib import Path

# OAuth 2.0 configuration
SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile']

def get_google_oauth_config():
    """Load Google OAuth credentials from Streamlit secrets"""
    try:
        config = {
            'client_id': st.secrets.get("GOOGLE_OAUTH_CLIENT_ID"),
            'client_secret': st.secrets.get("GOOGLE_OAUTH_CLIENT_SECRET"),
            'redirect_uri': st.secrets.get("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8501"),
            'auth_uri': "https://accounts.google.com/o/oauth2/auth",
            'token_uri': "https://oauth2.googleapis.com/token",
        }
        
        return config
    except Exception as e:
        st.error(f"Google OAuth configuration error: {e}")
        return None

def create_oauth_flow():
    """Create OAuth flow for Google Sign In"""
    config = get_google_oauth_config()
    
    if not config or not config['client_id']:
        return None
    
    # Create client config
    client_config = {
        "web": {
            "client_id": config['client_id'],
            "client_secret": config['client_secret'],
            "auth_uri": config['auth_uri'],
            "token_uri": config['token_uri'],
            "redirect_uris": [config['redirect_uri']]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=config['redirect_uri']
    )
    
    # Disable HTTPS requirement ONLY for local development
    if 'localhost' in config['redirect_uri'] or '127.0.0.1' in config['redirect_uri']:
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    
    return flow

def get_google_signin_url():
    """Generate Google Sign In authorization URL"""
    try:
        flow = create_oauth_flow()
        
        if not flow:
            st.error("❌ Failed to create OAuth flow")
            return None
        
        config = get_google_oauth_config()
        
        authorization_url, state = flow.authorization_url(
            access_type='online',
            include_granted_scopes='true',
            prompt='select_account'
        )
        
        # Store state in session for verification
        st.session_state['oauth_state'] = state
        
        return authorization_url
    except Exception as e:
        st.error(f"❌ Error generating sign-in URL: {str(e)}")
        return None

def verify_google_oauth_callback(auth_code):
    """
    Verify OAuth callback and get user information
    
    Args:
        auth_code: Authorization code from Google
        
    Returns:
        dict: User information or None if verification fails
    """
    try:
        flow = create_oauth_flow()
        
        if not flow:
            st.error("❌ Failed to create OAuth flow in callback")
            return None
        
        # Exchange authorization code for credentials
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials
        
        # Get user info from Google
        user_info = get_google_user_info(credentials)
        
        return user_info
    
    except Exception as e:
        st.error(f"❌ OAuth verification error: {str(e)}")
        return None

def get_google_user_info(credentials):
    """
    Get user information from Google using credentials
    
    Args:
        credentials: OAuth credentials
        
    Returns:
        dict: User profile information
    """
    try:
        # Call Google's userinfo endpoint
        session = requests.Session()
        headers = {'Authorization': f'Bearer {credentials.token}'}
        response = session.get('https://www.googleapis.com/oauth2/v2/userinfo', headers=headers)
        
        if response.status_code == 200:
            user_info = response.json()
            return {
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'picture': user_info.get('picture'),
                'verified_email': user_info.get('verified_email'),
                'google_id': user_info.get('id')
            }
        else:
            return None
    
    except Exception as e:
        st.error(f"Error getting user info: {e}")
        return None

def is_authorized_google_user(email):
    """
    Check if a Google email is authorized to access the app
    
    Args:
        email: Google email address
        
    Returns:
        bool: True if authorized, False otherwise
    """
    try:
        # Get list of authorized Google emails from secrets
        authorized_emails = st.secrets.get("AUTHORIZED_GOOGLE_EMAILS", "").split(',')
        authorized_emails = [e.strip().lower() for e in authorized_emails if e.strip()]
        
        # Allow specific domains
        authorized_domains = st.secrets.get("AUTHORIZED_GOOGLE_DOMAINS", "").split(',')
        authorized_domains = [d.strip().lower() for d in authorized_domains if d.strip()]
        
        # If no authorization is configured, allow all (open access)
        if not authorized_emails and not authorized_domains:
            return True
        
        email_lower = email.lower()
        
        # Check if email is in authorized list
        if email_lower in authorized_emails:
            return True
        
        # Check if email domain is authorized
        email_domain = email_lower.split('@')[-1]
        if email_domain in authorized_domains:
            return True
        
        return False
    
    except Exception as e:
        return False

def render_google_signin_button():
    """Render Google Sign In button"""
    config = get_google_oauth_config()
    
    if not config or not config.get('client_id'):
        st.info("💡 Google Sign In is not configured. Add GOOGLE_OAUTH_CLIENT_ID to secrets to enable it.")
        return False
    
    # Get authorization URL
    auth_url = get_google_signin_url()
    
    if auth_url:
        # Try using Streamlit's native link_button (most reliable)
        if hasattr(st, 'link_button'):
            # Add custom styling to make it look like Google button
            st.markdown("""
            <style>
            /* Style the Streamlit link button to look like Google Sign-In with glass effect */
            div[data-testid="stButton"] > button {
                background-color: rgba(255, 255, 255, 0.4) !important;
                border: 1px solid rgba(255, 255, 255, 0.5) !important;
                border-radius: 4px !important;
                padding: 12px 24px !important;
                color: #000000 !important;
                font-size: 14px !important;
                font-weight: 500 !important;
                box-shadow: 0 1px 2px 0 rgba(60,64,67,0.3) !important;
                width: 100% !important;
            }
            div[data-testid="stButton"] > button:hover {
                background-color: rgba(255, 255, 255, 0.5) !important;
                box-shadow: 0 1px 3px 0 rgba(60,64,67,0.3) !important;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # Display Google icon separately
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.markdown("""
                <div style="text-align: center; margin-bottom: 10px;">
                    <svg width="20" height="20" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                    </svg>
                </div>
                """, unsafe_allow_html=True)
                st.link_button("Sign in with Google", auth_url, use_container_width=True)
        else:
            # Fallback: Use simple markdown link with Google icon
            st.markdown(f"""
            <div style="text-align: center; margin: 20px 0;">
                <a href="{auth_url}" style="
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    background-color: rgba(255, 255, 255, 0.4);
                    border: 1px solid rgba(255, 255, 255, 0.5);
                    border-radius: 4px;
                    padding: 12px 24px;
                    text-decoration: none;
                    color: #000000;
                    font-size: 14px;
                    font-weight: 500;
                    box-shadow: 0 1px 2px 0 rgba(60,64,67,0.3);
                    transition: all 0.2s ease;
                " onmouseover="this.style.backgroundColor='rgba(255, 255, 255, 0.5)'; this.style.boxShadow='0 1px 3px 0 rgba(60,64,67,0.3)';" 
                   onmouseout="this.style.backgroundColor='rgba(255, 255, 255, 0.4)'; this.style.boxShadow='0 1px 2px 0 rgba(60,64,67,0.3)';">
                    <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" style="margin-right: 12px;">
                        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                    </svg>
                    Sign in with Google
                </a>
            </div>
            """, unsafe_allow_html=True)
        
        return True
    
    return False

def handle_oauth_callback():
    """Handle OAuth callback from Google"""
    # Check if we have an authorization code in the URL
    query_params = st.query_params
    
    if 'error' in query_params:
        error_code = query_params['error']
        error_desc = query_params.get('error_description', '')
        
        # Show simple error message
        st.error("❌ Sign-in Failed")
        st.warning("Unable to complete Google sign-in. Please try again or contact the administrator.")
        
        st.query_params.clear()
        return False
    
    if 'code' in query_params:
        auth_code = query_params['code']
        state = query_params.get('state')
        
        # Verify state matches (if available)
        # Note: Streamlit loses session state on redirect, so state might be None
        stored_state = st.session_state.get('oauth_state')
        
        if stored_state and state != stored_state:
            st.error("❌ Invalid OAuth state. Please try signing in again.")
            st.query_params.clear()
            return False
        
        # Exchange code for user info
        with st.spinner("🔄 Verifying your Google account..."):
            user_info = verify_google_oauth_callback(auth_code)
        
        if user_info:
            # Check if user is authorized
            if is_authorized_google_user(user_info['email']):
                # Set session state
                st.session_state['password_correct'] = True
                st.session_state['current_user'] = user_info['name']
                st.session_state['user_email'] = user_info['email']
                st.session_state['user_picture'] = user_info.get('picture')
                st.session_state['login_time'] = time.time()
                st.session_state['auth_method'] = 'google'
                
                # Clear query params
                st.query_params.clear()
                
                st.success(f"✅ Welcome, {user_info['name']}!")
                st.balloons()
                st.rerun()
                return True
            else:
                st.error(f"❌ Access Denied")
                st.warning(f"Your email address ({user_info['email']}) is not authorized to access this application.")
                st.info("💡 Please contact the administrator to request access.")
                
                # Clear query params
                st.query_params.clear()
                return False
        else:
            st.error("❌ Failed to verify Google account. Please try again.")
            # Clear query params
            st.query_params.clear()
            return False
    
    return False
