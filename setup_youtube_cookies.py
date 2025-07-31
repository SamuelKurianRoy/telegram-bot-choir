#!/usr/bin/env python3
"""
YouTube Cookie Setup Helper
This script helps set up browser cookies for bypassing YouTube bot detection.
"""

import os
import sys
import platform
from pathlib import Path

def main():
    print("🍪 YouTube Cookie Setup Helper")
    print("=" * 40)
    print()
    
    print("This script helps you set up browser cookies to bypass YouTube's bot detection.")
    print("Cookies are the most effective way to avoid download blocks.")
    print()
    
    # Check for existing cookie files
    cookie_locations = [
        Path.cwd() / "youtube_cookies.txt",
        Path.cwd() / "cookies.txt",
        Path("temp") / "youtube_cookies.txt",
    ]
    
    existing_cookies = [path for path in cookie_locations if path.exists()]
    
    if existing_cookies:
        print("✅ Found existing cookie files:")
        for cookie_file in existing_cookies:
            size = cookie_file.stat().st_size
            print(f"   📄 {cookie_file} ({size} bytes)")
        print()
        print("The bot should automatically use these cookies.")
        return
    
    print("❌ No cookie files found.")
    print()
    
    # Provide setup instructions
    print("🔧 Setup Options:")
    print()
    
    print("**Option 1: Automatic Browser Cookie Extraction (Recommended)**")
    print("The bot can automatically extract cookies from your browser.")
    print("Supported browsers: Brave, Chrome, Firefox, Edge")
    print("• Just use the bot normally - it will try to extract cookies automatically")
    print("• Brave browser works best (less tracking, better privacy)")
    print()
    
    print("**Option 2: Manual Cookie File Setup**")
    print("1. Install a browser extension like 'Get cookies.txt LOCALLY'")
    print("2. Visit YouTube and log in (if you want)")
    print("3. Export cookies to a file named 'youtube_cookies.txt'")
    print("4. Place the file in one of these locations:")
    for location in cookie_locations:
        print(f"   • {location}")
    print()
    
    print("**Option 3: Use Brave Browser (Easiest)**")
    print("1. Download and install Brave browser")
    print("2. Visit YouTube.com in Brave")
    print("3. The bot will automatically use Brave's cookies")
    print()
    
    # Check browser availability
    print("🌐 Browser Detection:")
    browsers = detect_browsers()
    for browser, available in browsers.items():
        status = "✅ Available" if available else "❌ Not found"
        print(f"   {browser.title()}: {status}")
    
    if browsers.get('brave'):
        print("\n🎉 Brave browser detected! The bot should work well with automatic cookie extraction.")
    elif any(browsers.values()):
        print(f"\n✅ Found browsers: {', '.join([b for b, a in browsers.items() if a])}")
        print("The bot will try to extract cookies automatically.")
    else:
        print("\n⚠️  No browsers detected. Consider installing Brave browser for best results.")
    
    print()
    print("💡 Tips:")
    print("• Brave browser has the best success rate")
    print("• You don't need to be logged into YouTube")
    print("• The bot tries multiple strategies automatically")
    print("• If one method fails, it tries others")
    print()
    print("🚀 Ready to test! Try downloading a YouTube video with the bot.")

def detect_browsers():
    """Detect available browsers on the system"""
    browsers = {
        'brave': False,
        'chrome': False,
        'firefox': False,
        'edge': False
    }
    
    system = platform.system().lower()
    home = Path.home()
    
    try:
        if system == "windows":
            paths = {
                'brave': home / "AppData/Local/BraveSoftware/Brave-Browser/Application/brave.exe",
                'chrome': home / "AppData/Local/Google/Chrome/Application/chrome.exe",
                'firefox': home / "AppData/Local/Mozilla Firefox/firefox.exe",
                'edge': home / "AppData/Local/Microsoft/Edge/Application/msedge.exe",
            }
        elif system == "darwin":  # macOS
            paths = {
                'brave': Path("/Applications/Brave Browser.app"),
                'chrome': Path("/Applications/Google Chrome.app"),
                'firefox': Path("/Applications/Firefox.app"),
                'edge': Path("/Applications/Microsoft Edge.app"),
            }
        else:  # Linux
            paths = {
                'brave': Path("/usr/bin/brave-browser"),
                'chrome': Path("/usr/bin/google-chrome"),
                'firefox': Path("/usr/bin/firefox"),
                'edge': Path("/usr/bin/microsoft-edge"),
            }
        
        for browser, path in paths.items():
            if path.exists():
                browsers[browser] = True
                
        # Also check cookie databases
        if system == "windows":
            cookie_paths = {
                'brave': home / "AppData/Local/BraveSoftware/Brave-Browser/User Data/Default/Cookies",
                'chrome': home / "AppData/Local/Google/Chrome/User Data/Default/Cookies",
                'edge': home / "AppData/Local/Microsoft/Edge/User Data/Default/Cookies",
            }
        elif system == "darwin":  # macOS
            cookie_paths = {
                'brave': home / "Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies",
                'chrome': home / "Library/Application Support/Google/Chrome/Default/Cookies",
                'edge': home / "Library/Application Support/Microsoft Edge/Default/Cookies",
            }
        else:  # Linux
            cookie_paths = {
                'brave': home / ".config/BraveSoftware/Brave-Browser/Default/Cookies",
                'chrome': home / ".config/google-chrome/Default/Cookies",
                'edge': home / ".config/microsoft-edge/Default/Cookies",
            }
        
        for browser, path in cookie_paths.items():
            if path.exists():
                browsers[browser] = True
                
    except Exception as e:
        print(f"Error detecting browsers: {e}")
    
    return browsers

if __name__ == "__main__":
    main()
