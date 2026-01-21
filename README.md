# Choir Telegram Bot - Complete Technical Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
4. [Data Layer](#data-layer)
5. [Features & Commands](#features--commands)
6. [Conversation Handlers](#conversation-handlers)
7. [Utilities](#utilities)
8. [Configuration & Deployment](#configuration--deployment)
9. [Technical Stack](#technical-stack)
10. [Data Flow](#data-flow)
11. [Key Algorithms](#key-algorithms)
12. [Error Handling](#error-handling)

---

## Overview

The Choir Telegram Bot is a comprehensive Python-based Telegram bot designed to manage choir song databases, organist rosters, and provide various music-related services. It integrates with Google Drive for data storage, includes AI-powered natural language processing, and supports multimedia downloads (YouTube, Spotify).

**Primary Purpose:**
- Manage and query a database of choir songs (Hymns, Lyrics, Conventions)
- Track when songs were last sung
- Provide sheet music notations
- Manage organist roster assignments
- Download and process audio files
- Bible verse lookup and games
- User preference management

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Telegram Bot API                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    bot.py (Main Entry)                      │
│  - Application setup                                        │
│  - Handler registration                                     │
│  - Event loop management                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼────┐  ┌──────▼──────┐  ┌───▼─────────┐
│ Handlers   │  │Conversations│  │ Preferences │
│ Module     │  │  Module     │  │   Module    │
│            │  │             │  │             │
│- Commands  │  │- Multi-step │  │- Settings   │
│- Callbacks │  │  workflows  │  │- User prefs │
└────┬───────┘  └──────┬──────┘  └──────┬──────┘
     │                 │                 │
     └─────────────────┼─────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼────┐  ┌──────▼──────┐  ┌───▼─────────┐
│ Data Layer │  │  Utilities  │  │ AI Assistant│
│            │  │             │  │             │
│- Datasets  │  │- Search     │  │- Gemini API │
│- Drive I/O │  │- Notation   │  │- Groq (FB)  │
│- User DB   │  │- Enhanced   │  │- NL Parser  │
│- Features  │  │  Search     │  │             │
└────┬───────┘  └──────┬──────┘  └──────┬──────┘
     │                 │                 │
     └─────────────────┼─────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              Google Drive Storage Layer                      │
│  - Song Databases (Excel)                                    │
│  - User Database                                             │
│  - Organist Roster                                           │
│  - Sheet Music Folders                                       │
│  - Log Documents                                             │
└──────────────────────────────────────────────────────────────┘
```

### Module Structure

```
Telegram_Bot/
├── bot.py                      # Main bot entry point
├── run_bot.py                  # Bot process management
├── config.py                   # Configuration management
├── logging_utils.py            # Logging setup
├── downloader.py               # Audio downloader (YouTube/Spotify)
│
├── telegram_handlers/          # Telegram bot handlers
│   ├── handlers.py             # Command handlers
│   ├── conversations.py        # Conversation workflows
│   ├── preferences.py          # User settings
│   └── utils.py                # Handler utilities
│
├── data/                       # Data layer
│   ├── datasets.py             # Dataset loading/processing
│   ├── drive.py                # Google Drive API
│   ├── udb.py                  # User database management
│   ├── vocabulary.py           # Song vocabulary/validation
│   ├── feature_control.py      # Feature enable/disable
│   ├── organist_roster.py      # Organist management
│   ├── auth.py                 # Authentication utilities
│   └── sheet_upload.py         # Sheet music upload
│
└── utils/                      # Utility modules
    ├── search.py               # Song search algorithms
    ├── notation.py             # Music notation handling
    ├── enhanced_search.py      # Advanced search with notation
    ├── ai_assistant.py         # AI natural language processing
    └── lockfile.py             # Process locking
```

---

## Core Components

### 1. bot.py - Main Application

**Purpose:** Central bot initialization and handler registration

**Key Responsibilities:**
- Initialize Telegram Application with bot token
- Load all datasets from Google Drive
- Build vocabulary from song databases
- Setup search indexing
- Register all conversation handlers
- Initialize AI assistant
- Load organist roster data
- Auto-update Sunday songs on startup
- Manage event loop and shutdown

**Key Functions:**
```python
def run_bot():
    """
    Main bot execution function
    - Acquires lock file to prevent multiple instances
    - Initializes theme components
    - Initializes AI assistant
    - Loads organist roster
    - Auto-updates Sunday songs
    - Starts polling loop
    - Handles graceful shutdown
    """
```

**Handler Registration Order:**
1. Basic commands (start, help, refresh)
2. Admin commands (user management, feature control)
3. Conversation handlers (search, download, upload, etc.)
4. Callback handlers (inline buttons)
5. AI message handler (catches unhandled text - MUST BE LAST)

### 2. run_bot.py - Process Management

**Purpose:** Bot lifecycle management for Streamlit deployment

**Key Functions:**
```python
def start_bot_in_background():
    """
    - Stops all existing bot instances
    - Removes stop signal and lock files
    - Starts bot as subprocess
    - Updates session state
    """

def stop_bot_in_background():
    """
    - Creates stop signal file
    - Terminates bot subprocess
    - Cleans up processes
    """
```

### 3. config.py - Configuration Management

**Purpose:** Centralized configuration and secrets management

**Configuration Class Structure:**
```python
class Config:
    # Bot Authentication
    TOKEN: str                    # Telegram bot token
    ADMIN_ID: int                 # Admin user ID
    AUTHORIZED_USERS: List[int]   # Authorized user IDs
    
    # Google Drive File IDs
    HLCFILE_ID: str               # Hymn/Lyric/Convention index
    TFILE_ID: str                 # Tune database
    FILE_ID: str                  # Main song database
    H_SHEET_MUSIC: str            # Hymn sheet music folder
    BFILE_ID: str                 # Bot log document
    UFILE_ID: str                 # User log document
    YFILE_ID: str                 # YouTube download log
    COMFILE_ID: str               # Comment/feedback log
    GAME_SCORE: str               # Bible game scores
    U_DATABASE: str               # User database
    ORGANIST_ROSTER_SHEET_ID: str # Organist roster
    DISABLED_DB: str              # Feature control database
    
    # Service Account
    service_account_data: dict    # Google API credentials
    
    # Settings
    LOG_UPLOAD_INTERVAL: int      # Log upload frequency (seconds)
```

**Configuration Loading:**
- Primary: Streamlit secrets (st.secrets)
- Fallback: Environment variables (os.environ)

---

## Data Layer

### 1. datasets.py - Dataset Management

**Purpose:** Load, clean, and preprocess song databases from Google Drive

**Global Datasets:**
```python
dfH   # Hymn List DataFrame
dfL   # Lyric List DataFrame
dfC   # Convention List DataFrame
yr23  # 2023 sung songs
yr24  # 2024 sung songs
yr25  # 2025 sung songs
df    # Combined historical data
dfTH  # Hymn Tune database
dfTD  # Doxology Tune database
```

**Key Functions:**

```python
def load_datasets():
    """
    Downloads Excel files from Google Drive
    Populates all global DataFrames
    Returns: tuple of all DataFrames
    """

def yrDataPreprocessing():
    """
    Preprocesses year DataFrames:
    - Drops NaN values
    - Promotes first row to column headers
    - Converts Date column to datetime.date
    - Fills missing tune/page numbers
    """

def dfcleaning():
    """
    Cleans main DataFrame:
    - Drops NaN values
    - Validates and converts dates
    - Resets index
    """

def standardize_song_columns():
    """
    Standardizes all song columns in df:
    - Removes whitespace
    - Formats song codes consistently
    """

def get_all_data():
    """
    Returns all global datasets
    """

def reload_all_datasets():
    """
    Reloads all data from Google Drive
    Used by /refresh command
    """
```

**Search Functions:**
```python
def Tunenofinder(no: str) -> str:
    """
    Finds tune name for a given hymn number
    Args: hymn number (e.g., "27")
    Returns: tune name or "Unknown"
    """

def Tune_finder_of_known_songs(song_code: str, song_type: str) -> str:
    """
    Finds tune for Hymns, Lyrics, Conventions
    Args: song_code (e.g., "H-27"), song_type
    Returns: tune name
    """

def Datefinder(song_code: str) -> Optional[date]:
    """
    Finds most recent date song was sung
    Args: song_code (e.g., "H-27")
    Returns: date or None
    """

def IndexFinder(song_code: str):
    """
    Finds index/title for a song
    Args: song_code
    Returns: DataFrame row or error message
    """
```

**TF-IDF Search:**
```python
# Uses scikit-learn TfidfVectorizer for fuzzy matching
# Applied to song titles and indices
# Returns similarity-ranked results
```

### 2. drive.py - Google Drive API

**Purpose:** Interface with Google Drive and Docs APIs

**Key Functions:**

```python
def get_drive_service():
    """
    Creates authenticated Google Drive service
    Uses service account credentials
    Returns: googleapiclient.discovery.Resource
    """

def get_docs_service():
    """
    Creates authenticated Google Docs service
    Returns: googleapiclient.discovery.Resource
    """

def upload_log_to_google_doc(doc_id: str, log_file: str):
    """
    Uploads log file contents to Google Docs
    Args:
        doc_id: Google Docs file ID
        log_file: Path to log file
    """

def append_download_to_google_doc(doc_id: str, user_info: dict, url: str, platform: str):
    """
    Appends download record to Google Doc
    Args:
        doc_id: Document ID
        user_info: User details
        url: Downloaded URL
        platform: "YouTube" or "Spotify"
    """

def save_game_score(doc_id: str, user_info: dict, difficulty: str, score: int):
    """
    Saves Bible game score to Google Doc
    """

def get_leaderboard(doc_id: str, difficulty: str) -> List[dict]:
    """
    Retrieves leaderboard for a difficulty
    Returns: List of {name, score, date}
    """
```

### 3. udb.py - User Database Management

**Purpose:** Manage user data persistence in Google Drive

**User Database Schema:**
```python
user_db = pd.DataFrame({
    'user_id': int,              # Telegram user ID (primary key)
    'username': str,             # @username
    'name': str,                 # Display name
    'last_seen': datetime,       # Last interaction
    'is_authorized': bool,       # Authorization status
    'is_admin': bool,            # Admin privileges
    'status': str,               # active/blocked/etc
    'notes': str,                # Admin notes
    
    # Preferences
    'bible_language': str,       # malayalam/english
    'game_language': str,        # malayalam/english
    'search_results_limit': int, # Default: 5
    'download_preference': str,  # single/ask
    'download_quality': str,     # high/medium/low/ask
    'theme_preference': str,     # UI theme
    'show_tunes_in_date': bool   # Show tunes in /date
})
```

**Key Functions:**

```python
def load_user_database():
    """
    Downloads user database from Google Drive
    Ensures proper schema
    Returns: DataFrame
    """

def save_user_database():
    """
    Uploads user database to Google Drive
    Converts DataFrame to Excel
    Returns: bool (success)
    """

def track_user_fast(user):
    """
    Quick user tracking without blocking
    Adds new user or updates last_seen
    Returns: (is_new_user, success)
    """

def track_user_interaction(user, command: str):
    """
    Full user tracking with command logging
    Updates last_seen and interaction count
    """

def user_exists(user_id: int) -> bool:
    """Check if user exists in database"""

def get_user_by_id(user_id: int) -> Optional[dict]:
    """Get user record by ID"""

def update_user_preference(user_id: int, pref_name: str, value):
    """Update specific user preference"""

def get_user_bible_language(user_id: int) -> str:
    """Get user's preferred Bible language"""

def get_user_download_preference(user_id: int) -> str:
    """Get user's download preference"""
```

**Optimization:**
- In-memory caching with `pending_saves` flag
- Batch saves to reduce API calls
- Fast tracking for high-frequency operations

### 4. vocabulary.py - Song Vocabulary

**Purpose:** Validate and standardize song identifiers

**Key Functions:**

```python
def ChoirVocabulary(df, dfH, dfL, dfC):
    """
    Builds vocabulary sets from song databases
    Returns: (all_vocab, hymn_vocab, lyric_vocab, convention_vocab)
    """

def isVocabulary(song_code: str, category: str = None) -> bool:
    """
    Checks if song code exists in vocabulary
    Args:
        song_code: e.g., "H-27"
        category: "hymn", "lyric", or "convention"
    Returns: bool
    """

def standardize_hlc_value(value: str) -> str:
    """
    Standardizes song code format
    Examples:
        "h 27" -> "H-27"
        "H27" -> "H-27"
        "hymn 27" -> "H-27"
    """
```

### 5. feature_control.py - Feature Management

**Purpose:** Dynamic feature enable/disable for maintenance

**FeatureController Class:**

```python
class FeatureController:
    def load_features() -> pd.DataFrame:
        """Load feature states from Google Drive"""
    
    def is_feature_enabled(feature_name: str) -> bool:
        """Check if feature is enabled"""
    
    def disable_feature(feature_name: str) -> bool:
        """Disable a feature"""
    
    def enable_feature(feature_name: str) -> bool:
        """Enable a feature"""
    
    def get_all_features() -> List[dict]:
        """Get all features with status"""
    
    def restrict_feature_access(feature_name: str, user_ids: List[int]):
        """Restrict feature to specific users"""
```

**Default Features:**
- download: Audio downloads
- search: Song search
- date: Date-based queries
- bible: Bible lookup
- games: Bible games
- organist: Organist roster
- upload: Sheet music upload
- ai_assistant: Natural language processing

### 6. organist_roster.py - Organist Management

**Purpose:** Manage organist assignments and Sunday song updates

**Key Functions:**

```python
def load_organist_roster_data():
    """
    Loads from 'Order of Songs' sheet
    Returns: DataFrame with columns:
        - 'Song/ Responses'
        - 'Name of The Organist'
    """

def get_organist_roster_data():
    """
    Returns cached roster or loads if needed
    Uses global _organist_roster_cache
    """

def update_songs_for_sunday():
    """
    Finds next Sunday date
    Retrieves songs for that date from year sheets
    Updates organist roster with song assignments
    Returns: (success, message, date_used)
    """

def assign_song_to_organist(song_code: str, organist_name: str):
    """
    Assigns specific song to organist
    Updates Google Sheet
    """

def get_unused_songs(category: str, duration: str):
    """
    Finds songs not sung in specified duration
    Args:
        category: "Hymn", "Lyric", "Convention"
        duration: "6months", "1year", "2years"
    Returns: List of song codes
    """
```

---

## Features & Commands

### Basic Commands

#### /start
- **Handler:** `start()`
- **Function:** Welcome message, user tracking, authorization check
- **Flow:**
  1. Track user with `track_user_fast()`
  2. If new user, save to database and notify admin
  3. Check authorization status
  4. Send welcome message with bot overview

#### /help
- **Handler:** `help_command()`
- **Function:** Display all available commands
- **Splits into multiple messages to avoid Telegram's 4096 character limit**

#### /refresh
- **Handler:** `refresh_command()`
- **Function:** Reload all data from Google Drive
- **Actions:**
  1. Reload datasets
  2. Rebuild vocabulary
  3. Rebuild search index
  4. Clear theme cache
  5. Reload organist roster
  6. Send confirmation

### Song Query Commands

#### /check
- **Type:** ConversationHandler
- **States:** ENTER_SONG
- **Function:** Check if song exists in database
- **Flow:**
  1. User sends `/check`
  2. Bot asks for song code
  3. User enters code (e.g., "H-27")
  4. Bot validates with `isVocabulary()`
  5. Returns existence status

#### /last
- **Type:** ConversationHandler
- **States:** ENTER_LAST_SONG
- **Function:** Find when song was last sung
- **Flow:**
  1. User sends `/last`
  2. Bot asks for song code
  3. User enters code
  4. Bot finds date with `Datefinder()`
  5. Shows last sung date
  6. Offers "Show all dates" button
  7. If clicked, displays all dates song was sung

#### /date
- **Type:** ConversationHandler
- **States:** ASK_DATE
- **Function:** Find songs sung on specific date
- **Flow:**
  1. User sends `/date`
  2. Bot asks for date (DD/MM/YYYY format)
  3. User enters date
  4. Bot searches year DataFrames
  5. Returns list of songs sung on that date
  6. Optionally includes tune names based on user preference

#### Direct Song Code
- **Handler:** `handle_song_code()`
- **Pattern:** `^[HhLlCc\s-]*\d+$`
- **Function:** Direct song information retrieval
- **Flow:**
  1. User sends "H-27" (or similar)
  2. Bot detects pattern
  3. Retrieves song info from IndexFinder()
  4. Finds last sung date
  5. Finds tune name
  6. Displays comprehensive info

### Search Commands

#### /search
- **Type:** ConversationHandler
- **States:** SEARCH_METHOD, INDEX_CATEGORY, INDEX_TEXT, NUMBER_CATEGORY, NUMBER_INPUT
- **Function:** Interactive song search
- **Methods:**
  1. **By Index:** Search by song title/first line
     - Choose category (Hymn/Lyric/Convention)
     - Enter search text
     - Bot uses TF-IDF similarity matching
     - Returns top N matches (configurable)
     - For hymns, includes "Find Notation" buttons
  
  2. **By Number:** Direct lookup by song number
     - Choose category
     - Enter number
     - Bot retrieves song details

**Enhanced Search Features:**
- Fuzzy matching with TF-IDF
- Notation link generation for hymns
- Interactive notation confirmation
- Page number correction system

#### /tune
- **Type:** ConversationHandler
- **States:** CHOOSE_METHOD, GET_INPUT
- **Function:** Find tune information
- **Methods:**
  1. **By Hymn Number:**
     - Enter hymn number
     - Returns tune name
     - Offers notation link if available
  
  2. **By Page Number:**
     - Enter page number from hymnal
     - Returns hymns on that page
     - Shows tune information

### Music Notation

#### /notation
- **Type:** ConversationHandler
- **States:** NOTATION_TYPE
- **Function:** Get sheet music notation
- **Flow:**
  1. User sends `/notation`
  2. Choose method:
     - **By Song Code:** Direct lookup (H-27)
     - **By Page Number:** Get sheet for page
  3. Bot finds notation in Google Drive folder
  4. Sends image or download link

**Notation Finding Algorithm:**
```
1. Check dfTH for confirmed page number
2. If not found, check "probable result" column
3. If not found, check dfH "Page no" column
4. Present notation image for confirmation
5. If confirmed, save to dfTH for future queries
6. If rejected, try next option
7. If all options exhausted, ask user for page number
```

### Theme/Vocabulary Commands

#### /theme
- **Type:** ConversationHandler
- **States:** THEME_TYPE, THEME_SELECTION, YEAR_FILTER, TYPO_CONFIRM
- **Function:** Find songs by theme or doctrine
- **Flow:**
  1. Choose theme type:
     - Hymn Themes
     - Doxology Themes
  2. Enter theme keyword
  3. Bot uses:
     - Sentence-BERT embeddings for semantic similarity
     - RapidFuzz for fuzzy string matching
  4. If multiple matches, shows confirmation
  5. Filter by year (optional)
  6. Display matching songs

**Theme Matching:**
- Uses `sentence-transformers/all-MiniLM-L6-v2` model
- Cosine similarity threshold: 0.7
- Fuzzy matching threshold: 50
- Caches embeddings for performance

#### /vocabulary
- **Type:** ConversationHandler
- **States:** CATEGORY_SELECTION
- **Function:** Browse song vocabulary
- **Categories:**
  - All Songs
  - Hymns Only
  - Lyrics Only
  - Conventions Only

### Bible Commands

#### /bible
- **Type:** ConversationHandler
- **States:** BIBLE_INPUT, BIBLE_CONFIRM
- **Function:** Lookup Bible verses
- **Supported Languages:**
  - English
  - Malayalam
- **Input Formats:**
  - "John 3:16"
  - "Genesis 1:1"
  - "Romans 3:23-25" (verse range)
- **Flow:**
  1. User sends `/bible`
  2. User enters reference
  3. Bot uses fuzzy matching for book names
  4. Fetches from WordProject.org
  5. Extracts and cleans text
  6. Sends formatted verse(s)

**Bible Text Processing:**
- HTML parsing with BeautifulSoup
- Language-specific cleaning (Malayalam vs English)
- Verse number extraction
- Formatting for Telegram

#### /games
- **Type:** ConversationHandler
- **States:** BIBLE_GAME_LANGUAGE, BIBLE_GAME_DIFFICULTY, BIBLE_GAME_QUESTION
- **Function:** Bible verse memorization game
- **Difficulties:**
  - Easy: Common verses (John 3:16, etc.)
  - Medium: Important verses
  - Hard: Obscure verses from minor prophets
- **Flow:**
  1. Choose language (English/Malayalam)
  2. Choose difficulty
  3. Bot presents verse text
  4. User chooses from 4 reference options
  5. Bot tracks score
  6. Continue playing or view leaderboard
  7. Scores saved to Google Drive

### Download Commands

#### /download
- **Type:** ConversationHandler
- **States:** ENTER_URL, PLAYLIST_CHOICE, SELECT_QUALITY
- **Supported Platforms:**
  - YouTube (videos, playlists)
  - Spotify (songs, albums, playlists)
- **Quality Options:**
  - High (320kbps)
  - Medium (192kbps)
  - Low (128kbps)
- **Flow:**
  1. User sends `/download`
  2. User enters URL
  3. Bot detects platform
  4. If playlist, asks single/all
  5. If user preference not set, asks quality
  6. Background download task starts
  7. Bot sends progress updates
  8. Sends audio file(s) on completion
  9. Logs download to Google Doc

**Download Implementation:**
- **AudioDownloader class** (downloader.py)
- YouTube: yt-dlp
- Spotify: spotdl
- FFmpeg for audio processing
- Automatic fallback mechanisms
- Cookie support for YouTube bot detection bypass
- Streamlit Cloud compatibility
- Temporary file cleanup

### Organist Commands

#### /organist
- **Type:** ConversationHandler
- **States:** ORGANIST_SELECTION
- **Function:** View/manage organist roster
- **Flow:**
  1. User sends `/organist`
  2. Bot displays unique organists
  3. User selects organist
  4. Bot shows songs assigned to that organist

#### /updatesunday
- **Handler:** `update_sunday_songs()`
- **Admin Only:** Yes
- **Function:** Auto-update organist roster with next Sunday's songs
- **Algorithm:**
  1. Calculate next Sunday date
  2. Search year sheets for that date
  3. Extract song list
  4. Update 'Order of Songs' sheet
  5. Return confirmation with date and songs

#### /updatedate
- **Type:** ConversationHandler
- **Admin Only:** Yes
- **Function:** Update roster for specific date

#### /assignsongs
- **Type:** ConversationHandler
- **States:** ASSIGN_SONG_SELECT, ASSIGN_ORGANIST_SELECT
- **Admin Only:** Yes
- **Function:** Manually assign songs to organists
- **Flow:**
  1. User sends `/assignsongs`
  2. Select song(s)
  3. Select organist
  4. Confirm assignment
  5. Update Google Sheet

#### /unused
- **Type:** ConversationHandler
- **States:** UNUSED_DURATION_SELECT, UNUSED_CATEGORY_SELECT
- **Function:** Find songs not sung in a while
- **Durations:**
  - 6 months
  - 1 year
  - 2 years
- **Categories:**
  - Hymns
  - Lyrics
  - Conventions

### Upload Commands

#### /upload
- **Type:** ConversationHandler
- **States:** UPLOAD_FILE, UPLOAD_FILENAME, UPLOAD_DESCRIPTION
- **Function:** Upload sheet music to Google Drive
- **Supported Types:**
  - PDF documents
  - Images
- **Flow:**
  1. User sends `/upload`
  2. User uploads file
  3. Bot asks for filename
  4. Bot asks for description
  5. Bot uploads to designated Google Drive folder
  6. Logs upload with metadata

#### /listuploads
- **Handler:** `list_uploads_command()`
- **Function:** List all uploaded sheet music files
- **Displays:**
  - Filename
  - Uploader
  - Upload date
  - Description
  - Download link

### User Settings

#### /setting
- **Type:** ConversationHandler
- **States:** SETTING_MENU, BIBLE_LANGUAGE_CHOICE, etc.
- **Function:** Manage user preferences
- **Settings:**
  1. **Bible Language:** English/Malayalam
  2. **Game Language:** English/Malayalam
  3. **Search Results Limit:** 1-10
  4. **Download Preference:** Single track/Ask each time
  5. **Download Quality:** High/Medium/Low/Ask
  6. **Tune Display in /date:** Show/Hide
  7. **Upload Preference:** (future use)

### Admin Commands

#### User Management

**/users**
- List all users in database
- Show user stats
- Display authorization status

**/view_authorized_users**
- List currently authorized users
- Show user IDs and names

**/add_authorized_user <user_id>**
- Add user to authorized list
- Updates secrets configuration
- Requires manual restart

**/remove_authorized_user <user_id>**
- Remove user from authorized list
- Updates secrets
- Requires restart

**/admin_save_db**
- Manually save user database to Google Drive

#### Feature Control

**/disable <feature_name>**
- Disable specific feature
- Example: `/disable download`
- Feature becomes unavailable to all users

**/ <feature_name>**
- Re-enable disabled feature

**/ feature_status**
- Show status of all features
- Display enabled/disabled state
- Show access restrictions

**/ restrict_access <feature> <user_ids>**
- Restrict feature to specific users
- Example: `/restrict_access upload 12345,67890`

**/ unrestrict_access <feature>**
- Remove access restrictions

**/ debug_features**
- Show detailed feature configuration
- For troubleshooting

**/ add_missing_features**
- Add any new features to database

**/ restore_all_features**
- Reset all features to default enabled state

#### AI Model Management

**/ model**
- Check current AI model status
- Display active provider (Gemini/Groq)
- Show configuration

**/ switchmodel <provider>**
- Switch between AI providers
- Options: gemini, groq, both

**/ testmodel <message>**
- Test AI model with sample input
- Returns parsed intent

#### Communication

**/ reply**
- **Type:** ConversationHandler
- **States:** REPLY_SELECT_USER, REPLY_ENTER_MESSAGE
- **Function:** Send message to specific user
- **Flow:**
  1. Admin sends `/reply`
  2. Bot lists recent users
  3. Admin enters user number
  4. Admin enters message
  5. Bot sends message to user

**/ comment**
- **Type:** ConversationHandler (user-facing)
- **States:** COMMENT
- **Function:** Users send feedback to admin
- **Flow:**
  1. User sends `/comment`
  2. User enters feedback
  3. Bot forwards to admin
  4. Admin can reply using inline button

### AI Natural Language Handler

**Handler:** `ai_message_handler()`
**Priority:** LAST (catches all unhandled text messages)
**Function:** Parse natural language queries using AI

**How It Works:**
1. User sends plain text message (not a command)
2. Bot checks if message should use AI (`should_use_ai()`)
3. Sends to `parse_user_intent()` (Gemini or Groq)
4. AI returns:
   - command: Suggested bot command
   - parameters: Extracted parameters
   - confidence: 0-1 score
5. If confidence > 0.7, execute command
6. Otherwise, respond conversationally

**Examples:**
- "What songs did we sing on Christmas?" → `/date 25/12/2024`
- "Find H-44" → `/search` + song lookup
- "Who is the organist?" → `/organist`
- "Show me some hymns about love" → `/theme` + "love"

**AI Providers:**
- **Primary:** Google Gemini 2.5 Flash (free tier)
- **Fallback:** Groq with Llama 3.3 70B (free tier)

**Prompt Engineering:**
- System prompt defines bot capabilities
- Structured JSON response format
- Command and parameter extraction
- Confidence scoring

---

## Conversation Handlers

### ConversationHandler Pattern

All multi-step interactions use Telegram's `ConversationHandler`:

```python
ConversationHandler(
    entry_points=[CommandHandler("command", start_func)],
    states={
        STATE_1: [MessageHandler(filters.TEXT, handler_1)],
        STATE_2: [MessageHandler(filters.TEXT, handler_2)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)
```

**State Management:**
- States stored in `context.user_data`
- Each handler returns next state or `ConversationHandler.END`
- `/cancel` command exits any conversation

### Common Conversation Patterns

**1. Simple Query:**
```
/command → Ask Input → Process → Result → END
```

**2. Multi-Choice:**
```
/command → Show Options → User Selects → Process → Result → END
```

**3. Conditional Flow:**
```
/command → Choice A/B
    ├→ A: Process A → Result → END
    └→ B: Process B → More Input → Result → END
```

**4. Loop:**
```
/command → Input → Result → "Continue?" → Yes/No
    ├→ Yes: Back to Input
    └→ No: END
```

---

## Utilities

### 1. search.py - Search Algorithms

**Purpose:** Advanced song search with TF-IDF

**Implementation:**
```python
# Global search indices
search_indices = {
    'hymn': None,
    'lyric': None,
    'convention': None
}

def setup_search(dfH, dfL, dfC):
    """
    Builds TF-IDF vectorizers for each category
    Indexes: Index (title) and First Lines
    Stores in global search_indices
    """

def find_best_match(query: str, category: str, top_n: int):
    """
    Performs TF-IDF similarity search
    Args:
        query: Search text
        category: "hymn", "lyric", "convention"
        top_n: Number of results
    Returns: (matches_df, column_label)
    
    Algorithm:
    1. Transform query using stored vectorizer
    2. Compute cosine similarity
    3. Sort by similarity score
    4. Return top N matches
    """

def search_index(no: str, option: str):
    """
    Direct lookup by song number
    Args:
        no: Song number
        option: Category
    Returns: DataFrame row or error
    """
```

### 2. notation.py - Music Notation Handling

**Purpose:** Find and retrieve sheet music notation

**Key Functions:**

```python
def getNotation(page_no: str):
    """
    Generates Google Drive image link for notation page
    Args: page_no (can be comma-separated list)
    Returns: List of image URLs
    """

def Music_notation_link(hymn_no, dfH, dfTH, Tune_finder):
    """
    Main notation link generator
    Algorithm:
    1. Find tune name for hymn
    2. Call find_tune_page_number()
    3. Generate notation links
    Returns: List of URLs or None
    """

def find_tune_page_number(tune_name, hymn_no, dfH, dfTH):
    """
    Multi-source page number finder
    Priority order:
    1. dfTH exact match in "page no" column
    2. dfTH "propabible result" column
    3. dfH "Page no" column
    Returns: page_no or None
    """

def save_confirmed_page_result(tune_name, hymn_no, page_no, source):
    """
    Saves user-confirmed page number to dfTH
    Uploads updated dfTH to Google Drive
    Creates learning system for future queries
    """
```

**Notation Discovery Process:**
```
User searches for H-27
    ↓
Get tune name: "Hursley"
    ↓
Check dfTH for "Hursley" + page number
    ↓ (not found)
Check dfTH "probable result" for "Hursley"
    ↓ (found: "page 10")
Retrieve page 10 image from Google Drive
    ↓
Send image to user with "Is this correct?" buttons
    ↓
User confirms "Yes"
    ↓
Save to dfTH "page no" column
    ↓
Upload updated dfTH to Google Drive
    ↓
Future queries for H-27 will use saved page number
```

### 3. enhanced_search.py - Advanced Search UI

**Purpose:** Enhanced search results with interactive notation

**Key Functions:**

```python
async def show_search_results_with_notation(update, context, search_results, category):
    """
    Displays search results
    For hymns: Adds "Find Notation" buttons
    For others: Standard display
    """

async def show_hymn_results_with_notation(update, context, matches, prefix):
    """
    Special display for hymn search results
    Each result includes:
    - Song code (H-27)
    - Index/Title
    - First Line
    - Last sung date
    - Tune name
    - [Find Notation] button (if tune known)
    """

async def handle_find_notation_callback(update, context):
    """
    Handles "Find Notation" button clicks
    Initiates notation finding process
    """

async def start_notation_finding_process(query, context, hymn_no, tune_name):
    """
    Starts notation discovery
    Tracks attempts in context.user_data
    """

async def show_notation_page_for_confirmation(query, context, hymn_no, tune_name, page_no):
    """
    Sends notation image with confirmation buttons:
    - ✅ Correct
    - ❌ Try Another
    - 📝 Provide Page Number
    """

async def handle_notation_confirmation(update, context):
    """
    Processes notation confirmation
    If correct: Save to database
    If wrong: Try next option
    """

async def handle_provide_page_number(update, context):
    """
    Allows user to manually enter correct page number
    Saves to database for future use
    """
```

### 4. ai_assistant.py - AI Integration

**Purpose:** Natural language understanding with Gemini/Groq

**Architecture:**
```python
# Global state
_gemini_model = None          # (client, model_name) tuple
_groq_client = None           # Groq client
_preferred_provider = "gemini" # Active provider
```

**Functions:**

```python
def initialize_gemini():
    """
    Initializes Gemini API
    Model: gemini-2.5-flash (free tier)
    Does not test connection (saves quota)
    Returns: bool (success)
    """

def initialize_groq():
    """
    Initializes Groq API as fallback
    Model: llama-3.3-70b-versatile
    Tests connection
    Returns: bool (success)
    """

def parse_user_intent(user_message: str) -> dict:
    """
    Main NLP function
    
    Args: user_message (natural language)
    
    Returns:
    {
        'command': str,        # Bot command to execute
        'parameters': dict,    # Extracted parameters
        'response_text': str,  # Conversational response
        'confidence': float    # 0-1 score
    }
    
    Process:
    1. Construct prompt with bot capabilities
    2. Send to preferred AI provider
    3. Parse JSON response
    4. Fallback to other provider if failed
    5. Return structured intent
    """

def should_use_ai(message_text: str) -> bool:
    """
    Determines if message should use AI
    
    Returns False for:
    - Commands (/command)
    - Song codes (H-27, L-5)
    - Very short messages (< 3 chars)
    
    Returns True for:
    - Natural language queries
    - Questions
    - Long messages
    """
```

**Prompt Template:**
```
You are a helpful assistant for a choir management bot.

Available commands:
- /date: Find songs by date
- /search: Search songs
- /organist: View organist roster
- /bible: Look up Bible verses
- /download: Download audio
- /last: When song was last sung
- /check: Check if song exists
- /theme: Find songs by theme

Parse this message and extract:
{
  "command": "command_name",
  "parameters": {...},
  "confidence": 0.0-1.0
}

Message: "{user_message}"
```

### 5. lockfile.py - Process Locking

**Purpose:** Prevent multiple bot instances

**Functions:**

```python
LOCK_FILE = "/tmp/telegram_bot.lock"
STOP_SIGNAL_FILE = "/tmp/telegram_bot_stop_signal"

def acquire_lock():
    """
    Creates lock file with PID
    Returns: bool (success)
    Prevents multiple bot instances
    """

def release_lock():
    """
    Removes lock file
    Called on bot shutdown
    """

def check_stop_signal():
    """
    Checks for stop signal file
    Used by Streamlit interface to stop bot
    """
```

---

## Configuration & Deployment

### Environment Setup

**Required Secrets (secrets.toml or Streamlit Cloud):**

```toml
# Bot Authentication
TOKEN = "your-telegram-bot-token"
ADMIN_ID = "your-telegram-user-id"
AUTHORIZED_USERS = "user_id_1,user_id_2,user_id_3"

# Google Drive File IDs
HLCFILE_ID = "google-drive-file-id"
TFILE_ID = "tune-database-id"
FILE_ID = "main-database-id"
H_SHEET_MUSIC = "hymn-folder-id"
BFILE_ID = "bot-log-doc-id"
UFILE_ID = "user-log-doc-id"
YFILE_ID = "youtube-log-doc-id"
COMFILE_ID = "comment-log-doc-id"
GAME_SCORE = "game-score-doc-id"
U_DATABASE = "user-database-id"
ORGANIST_ROSTER_SHEET_ID = "roster-sheet-id"
DISABLED_DB = "feature-control-id"

# Google Service Account (split into lines)
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-key-id"
client_email = "your-service-account@project.iam.gserviceaccount.com"
# ... (private_key split into l1-l28)

# AI API Keys
GEMINI_API_KEY = "your-gemini-api-key"
GROQ_API_KEY = "your-groq-api-key"  # Optional fallback

# Settings
LOG_UPLOAD_INTERVAL = "3600"  # seconds
```

### Deployment Options

**1. Local Development:**
```bash
# Install dependencies
pip install -r requirements.txt

# Run bot directly
python bot.py

# Or with Streamlit interface
streamlit run streamlit_app.py
```

**2. Linux Server:**
```bash
# Setup virtual environment
python3 -m venv venv_linux
source venv_linux/bin/activate
pip install -r requirements.txt

# Run as background process
nohup python bot.py > bot.log 2>&1 &
```

**3. Streamlit Cloud:**
```bash
# Configure secrets in dashboard
# Deploy from GitHub repository
# Auto-restart on push
```

**4. Docker (Future):**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

### Logging

**Log Files:**
- `bot_log.txt`: Bot operations and errors
- `user_log.txt`: User interactions
- `downloader_log.txt`: Download operations
- `bot_operations.json`: Operational metadata

**Google Drive Logging:**
- Logs automatically uploaded to Google Docs at configured interval
- Separate logs for bot, users, downloads, comments, games

**Log Rotation:**
- File mode: 'w' (overwrite on restart)
- Old logs preserved in Google Drive

---

## Technical Stack

### Core Technologies

**Language:** Python 3.12+

**Framework:** python-telegram-bot 20.7

**Key Libraries:**

1. **Telegram:**
   - python-telegram-bot: Bot framework
   - nest_asyncio: Async support

2. **Google APIs:**
   - google-api-python-client: Drive/Docs API
   - google-auth: Authentication
   - google-genai: Gemini AI

3. **Data Processing:**
   - pandas: DataFrame operations
   - openpyxl: Excel file handling
   - scikit-learn: TF-IDF vectorization

4. **AI/ML:**
   - sentence-transformers: Semantic embeddings
   - rapidfuzz: Fuzzy string matching
   - groq: Alternative AI provider

5. **Audio:**
   - yt-dlp: YouTube download
   - spotdl: Spotify download
   - mutagen: Audio metadata

6. **Web:**
   - requests: HTTP requests
   - beautifulsoup4: HTML parsing
   - streamlit: Web interface

### Data Storage

**Google Drive Structure:**
```
Choir Drive/
├── Databases/
│   ├── HLC Index.xlsx          # Song indices
│   ├── Tune Database.xlsx      # Tune information
│   ├── Main Database.xlsx      # Historical data
│   ├── User Database.xlsx      # User data
│   ├── Organist Roster.xlsx    # Organist assignments
│   └── Feature Control.xlsx    # Feature states
│
├── Sheet Music/
│   ├── Hymn Notation/          # Images folder
│   ├── Lyric Notation/         # PDFs folder
│   └── Uploaded/               # User uploads
│
└── Logs/
    ├── Bot Log.txt
    ├── User Log.txt
    ├── Download Log.txt
    ├── Comment Log.txt
    └── Game Scores.txt
```

### Performance Optimizations

**1. Caching:**
- User database in-memory cache
- Organist roster cache
- Theme embeddings cache
- Search index cache
- TF-IDF vectorizers cache

**2. Lazy Loading:**
- Theme components initialized on startup
- AI models initialized on first use
- Search indices built on first query

**3. Batch Operations:**
- User database batch saves
- Multiple dataset loads in parallel
- Bulk notation retrievals

**4. Async Operations:**
- Download tasks run in background
- Non-blocking user tracking
- Admin notifications don't block commands

---

## Data Flow

### User Message Flow

```
User sends message
    ↓
Telegram API receives
    ↓
python-telegram-bot processes
    ↓
Router (bot.py) checks handlers in order:
    1. Commands (/start, /help, etc.)
    2. ConversationHandlers (active conversations)
    3. CallbackQueryHandlers (button clicks)
    4. Regex patterns (song codes)
    5. AI message handler (natural language)
    ↓
Handler processes:
    - Validates authorization
    - Checks feature enabled
    - Retrieves data from Google Drive
    - Processes with algorithms
    - Generates response
    ↓
Response sent to user
    ↓
Log interaction (user_db, logs)
```

### Data Synchronization Flow

```
Bot Startup
    ↓
Load datasets from Google Drive
    ↓
Preprocess and clean data
    ↓
Build vocabularies
    ↓
Build search indices
    ↓
Cache in memory
    ↓
Ready to serve requests
    ↓
On /refresh command:
    - Reload all data
    - Rebuild indices
    - Clear caches
```

### Download Flow

```
User: /download <URL>
    ↓
Bot detects platform (YouTube/Spotify)
    ↓
If playlist, ask single/all
    ↓
Get quality preference from user DB
    ↓
Create AudioDownloader instance
    ↓
Start background_download_task()
    ↓
Send "Downloading..." message
    ↓
Download process:
    - yt-dlp or spotdl
    - FFmpeg processing
    - Metadata extraction
    - Thumbnail processing
    ↓
Progress updates every 10%
    ↓
On completion:
    - Send audio file to user
    - Log to Google Doc
    - Clean up temp files
    ↓
On error:
    - Send error message
    - Log error
    - Clean up
```

---

## Key Algorithms

### 1. Song Search Algorithm (TF-IDF)

```python
# Preprocessing
1. Combine "Index" and "First Lines" columns
2. Apply lowercase and strip whitespace
3. Create TF-IDF vocabulary

# Indexing
1. Fit TfidfVectorizer on combined text
2. Transform all documents to vectors
3. Store vectorizer and vectors

# Querying
1. Transform query using same vectorizer
2. Compute cosine_similarity(query_vector, all_vectors)
3. Sort by similarity score (descending)
4. Return top N results with scores > threshold
```

**Advantages:**
- Handles typos and variations
- Language-agnostic (works with Malayalam)
- Fast lookups (pre-computed vectors)
- Relevance-ranked results

### 2. Theme Matching Algorithm

```python
# Initialization (on bot startup)
1. Load SentenceTransformer model: 'all-MiniLM-L6-v2'
2. Extract all themes from dfTH/dfTD
3. Generate embeddings for all themes
4. Cache embeddings in memory

# Query Processing
1. User inputs theme keyword
2. Generate embedding for user input
3. Compute cosine similarity with all theme embeddings
4. Filter results with similarity > 0.7
5. If no results, fallback to RapidFuzz string matching
6. If multiple matches, show confirmation options
7. Once confirmed, filter songs by theme
```

**Hybrid Approach:**
- **Semantic:** Handles synonyms ("joy" matches "happiness")
- **Fuzzy:** Handles typos ("redemsion" matches "redemption")

### 3. Notation Discovery Algorithm

```python
# Multi-source lookup with learning
1. Get hymn number and tune name
2. Check dfTH["page no"] for exact match
   - If found: Return immediately (confirmed data)
3. Check dfTH["propabible result"] for probable match
   - If found: Return for confirmation
4. Check dfH["Page no"] for page number
   - If found: Return for confirmation
5. If all fail: Ask user to provide page number
6. Present notation image to user
7. If user confirms correct:
   - Save to dfTH["page no"]
   - Upload updated dfTH to Google Drive
8. If user rejects:
   - Try next source
   - Cycle through sources
   - Eventually ask for manual input
```

**Machine Learning Aspect:**
- Bot learns from user confirmations
- Future queries use learned data
- Continuously improving accuracy
- Crowdsourced page number database

### 4. AI Intent Parsing

```python
# Prompt Construction
1. Define available commands and parameters
2. Provide examples of intents
3. Specify JSON response format
4. Include user message

# API Call
1. Send to Gemini API (or Groq fallback)
2. Parse JSON response
3. Extract: command, parameters, confidence

# Execution
1. If confidence > 0.7:
   - Execute extracted command with parameters
2. If confidence < 0.7:
   - Respond conversationally
   - Don't execute command

# Error Handling
1. If JSON parse fails: Try regex extraction
2. If API fails: Fallback to secondary provider
3. If both fail: Respond with error
```

### 5. Date Finder Algorithm

```python
# Last Sung Date
def Datefinder(song_code):
    1. Parse song_code to determine category (H/L/C)
    2. Search in df (combined historical data)
    3. Filter rows where song_code appears
    4. Get maximum date (most recent)
    5. Return date or None

# All Dates
def get_all_dates(song_code):
    1. Same as Datefinder
    2. Instead of max, return all dates
    3. Sort in descending order (newest first)
    4. Return list of dates
```

### 6. Sunday Song Update Algorithm

```python
def update_songs_for_sunday():
    1. Calculate next Sunday:
       today = datetime.today()
       days_ahead = 6 - today.weekday()  # Sunday is 6
       next_sunday = today + timedelta(days_ahead)
    
    2. Search year DataFrames (yr23, yr24, yr25):
       - Filter by next_sunday date
       - Extract song list from that row
    
    3. Parse song codes from columns
    
    4. Load organist roster from Google Sheet
    
    5. Update 'Song/ Responses' column with new songs
    
    6. Upload updated roster to Google Drive
    
    7. Return confirmation with date and songs
```

---

## Error Handling

### Error Handling Strategy

**1. Graceful Degradation:**
- If AI fails, fall back to manual commands
- If one data source fails, try alternatives
- If feature disabled, inform user politely

**2. User-Friendly Messages:**
```python
try:
    # Operation
except Exception as e:
    await update.message.reply_text(
        "Sorry, something went wrong. Please try again."
    )
    logger.error(f"Error: {e}")
```

**3. Logging:**
- All errors logged with context
- Uploaded to Google Drive for analysis
- Admin notifications for critical errors

**4. Retry Mechanisms:**
- Google Drive API: Exponential backoff
- Download operations: Multiple attempts
- AI API: Provider fallback

### Common Error Scenarios

**1. Authorization:**
```python
if user_id not in authorized_users:
    await update.message.reply_text(
        "🚫 You are not authorized to use this bot."
    )
    await notify_admin(user_info)
    return
```

**2. Feature Disabled:**
```python
if not is_feature_enabled("download"):
    await update.message.reply_text(
        "⚠️ Download feature is currently disabled."
    )
    return
```

**3. Data Not Found:**
```python
result = Datefinder(song_code)
if result is None:
    await update.message.reply_text(
        "No records found for this song."
    )
else:
    await update.message.reply_text(f"Last sung: {result}")
```

**4. API Failures:**
```python
try:
    # Gemini API call
except Exception as gemini_error:
    logger.warning(f"Gemini failed: {gemini_error}")
    try:
        # Groq API call (fallback)
    except Exception as groq_error:
        logger.error(f"Both AI providers failed")
        # Use rule-based fallback
```

**5. Invalid Input:**
```python
if not re.match(r'^[HLC]-\d+$', song_code):
    await update.message.reply_text(
        "Please enter a valid song code (e.g., H-27)"
    )
    return
```

---

## Additional Notes for C++ Conversion

### Key Considerations

**1. Async/Await:**
- Python uses `asyncio` extensively
- C++: Consider using Boost.Asio or C++20 coroutines
- All handler functions are async

**2. Telegram Bot API:**
- Python: python-telegram-bot library
- C++: Consider `tgbot-cpp` or direct REST API calls
- Need webhook or long-polling implementation

**3. Data Processing:**
- Python pandas → C++: Consider using dataframes library or custom structures
- Excel reading: Use `libxlsx` or similar
- CSV might be easier than Excel for C++

**4. Google APIs:**
- Python: google-api-python-client
- C++: Use Google's C++ client libraries or REST API
- OAuth2 authentication needed

**5. AI Integration:**
- Python: google-genai, groq libraries
- C++: Use REST API directly with libcurl
- JSON parsing: Use nlohmann/json or rapidjson

**6. String Processing:**
- Malayalam text handling (Unicode)
- Regular expressions (std::regex)
- String similarity (Levenshtein distance)

**7. Concurrency:**
- Python: asyncio, threads
- C++: std::thread, std::async, or thread pools
- Need careful synchronization for shared data

**8. Dependencies:**
- C++ equivalents needed for:
  - HTTP requests: libcurl or cpr
  - JSON: nlohmann/json
  - Date/time: std::chrono or date library
  - Image processing: OpenCV or similar

**9. Database:**
- Current: Google Drive + Excel
- C++ Alternative: SQLite or PostgreSQL might be more suitable
- ORM: Consider SQLiteCpp or SOCI

**10. Configuration:**
- Python: streamlit.secrets, os.environ
- C++: Config file parser (INI, JSON, YAML)
- Environment variables: std::getenv

### Recommended C++ Architecture

```cpp
// Modular structure
TelegramBot/
├── src/
│   ├── main.cpp                    # Entry point
│   ├── bot/
│   │   ├── Application.cpp         # Bot application
│   │   ├── Handler.cpp             # Base handler class
│   │   └── CommandHandler.cpp      # Command implementations
│   ├── data/
│   │   ├── DriveService.cpp        # Google Drive API
│   │   ├── Database.cpp            # Data management
│   │   └── UserDatabase.cpp        # User management
│   ├── utils/
│   │   ├── Search.cpp              # Search algorithms
│   │   ├── AIAssistant.cpp         # AI integration
│   │   └── Logger.cpp              # Logging
│   └── models/
│       ├── Song.hpp                # Song data structure
│       ├── User.hpp                # User data structure
│       └── Config.hpp              # Configuration
├── include/                        # Header files
├── tests/                          # Unit tests
└── CMakeLists.txt                  # Build configuration
```

### Data Structures

```cpp
struct Song {
    std::string code;         // "H-27"
    std::string category;     // "hymn", "lyric", "convention"
    std::string index;        // Song title
    std::string firstLine;    // First line of lyrics
    std::string tune;         // Tune name
    std::optional<int> pageNo;// Sheet music page
    std::optional<std::chrono::system_clock::time_point> lastSung;
};

struct User {
    int64_t id;              // Telegram user ID
    std::string username;    // @username
    std::string name;        // Display name
    bool isAuthorized;
    bool isAdmin;
    std::chrono::system_clock::time_point lastSeen;
    
    // Preferences
    std::string bibleLanguage;
    std::string gameLanguage;
    int searchLimit;
    // ... other preferences
};

struct Config {
    std::string botToken;
    int64_t adminId;
    std::vector<int64_t> authorizedUsers;
    
    // Google Drive IDs
    std::map<std::string, std::string> fileIds;
    
    // API Keys
    std::string geminiApiKey;
    std::string groqApiKey;
    
    // Settings
    int logUploadInterval;
};
```

### Threading Model

```cpp
// Main thread: Telegram bot polling
// Worker threads:
//   - Database sync
//   - Download tasks
//   - AI processing
//   - Log uploads

class ThreadPool {
    std::vector<std::thread> workers;
    std::queue<std::function<void()>> tasks;
    std::mutex queueMutex;
    std::condition_variable condition;
    bool stop;
    
public:
    void enqueue(std::function<void()> task);
    void wait();
};
```

---

## Conclusion

This Telegram bot is a comprehensive, multi-functional system that combines:
- Database management
- Natural language processing
- Multimedia handling
- User preference management
- Admin controls
- Third-party API integrations

The architecture is modular, maintainable, and scalable. The AI integration provides modern natural language interaction while maintaining backward compatibility with traditional commands.

For C++ conversion, focus on:
1. Solid data structures
2. Efficient threading model
3. Robust error handling
4. Memory management
5. Library selection for Telegram, HTTP, JSON, and Google APIs

The core algorithms (TF-IDF search, theme matching, notation discovery) are language-agnostic and can be implemented in C++ with appropriate libraries.

---

## Contact & Support

- Admin: See `ADMIN_ID` in configuration
- Bot: `@YourBotName` on Telegram
- Documentation: See `/docs` folder for feature-specific guides

---

**End of Technical Documentation**
