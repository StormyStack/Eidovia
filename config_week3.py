import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# API Configuration
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8001"))

# ============================================================
# CONTEXTUAL BANDIT CONFIGURATION
# ============================================================

# State Space (8 dimensions)
STATE_FEATURES = [
    "accuracy",           # Recent accuracy (0-1)
    "response_time",      # Time taken per question (ms)
    "difficulty_level",   # User's current difficulty (0=easy, 1=medium, 2=hard)
    "topic_match",        # How well current topic matches user preference (0-1)
    "engagement",         # User engagement level (0-1, based on consecutive correct)
    "question_count",     # Questions answered so far (normalized 0-1)
    "error_rate",         # Recent error rate (0-1)
    "time_spent",         # Time spent in session (minutes, normalized)
]
STATE_DIMENSION = len(STATE_FEATURES)

# Action Space (8 actions)
ACTIONS = {
    0: {"name": "difficulty_easy", "difficulty": 0, "description": "Show easy questions"},
    1: {"name": "difficulty_medium", "difficulty": 1, "description": "Show medium questions"},
    2: {"name": "difficulty_hard", "difficulty": 2, "description": "Show hard questions"},
    3: {"name": "topic_structure", "topic": "DNA Structure", "description": "Focus on DNA structure"},
    4: {"name": "topic_replication", "topic": "DNA Replication", "description": "Focus on replication"},
    5: {"name": "topic_transcription", "topic": "Transcription", "description": "Focus on transcription"},
    6: {"name": "topic_translation", "topic": "Translation", "description": "Focus on translation"},
    7: {"name": "topic_mutations", "topic": "Mutations", "description": "Focus on mutations"},
}
NUM_ACTIONS = len(ACTIONS)

# Thompson Sampling Hyperparameters
THOMPSON_ALPHA = 1.0  # Prior strength (Bayesian)
THOMPSON_BETA = 1.0   # Prior strength
THOMPSON_LAMBDA = 0.01  # Regularization (encourages exploration)

# State aggregation
STATE_UPDATE_INTERVAL = 5  # Update state every N interactions
REWARD_WINDOW = 10  # Recent N questions for accuracy calculation

# Mock User Simulator
MOCK_USERS = [
    {
        "user_id": "user_001",
        "name": "Alice (Fast Learner)",
        "difficulty_preference": 1,  # Prefers medium
        "topic_preference": "DNA Structure",
        "learning_rate": 0.15,  # Improves 15% per session
        "engagement": 0.9,
    },
    {
        "user_id": "user_002",
        "name": "Bob (Struggling)",
        "difficulty_preference": 0,  # Prefers easy
        "topic_preference": "DNA Replication",
        "learning_rate": 0.05,  # Improves 5% per session
        "engagement": 0.6,
    },
    {
        "user_id": "user_003",
        "name": "Charlie (Ambitious)",
        "difficulty_preference": 2,  # Prefers hard
        "topic_preference": "Transcription",
        "learning_rate": 0.10,
        "engagement": 0.8,
    },
    {
        "user_id": "user_004",
        "name": "Diana (Balanced)",
        "difficulty_preference": 1,
        "topic_preference": "Mutations",
        "learning_rate": 0.12,
        "engagement": 0.75,
    },
    {
        "user_id": "user_005",
        "name": "Eve (Topic-Focused)",
        "difficulty_preference": 2,
        "topic_preference": "Translation",
        "learning_rate": 0.08,
        "engagement": 0.7,
    },
]

# Simulation parameters
QUESTIONS_PER_SESSION = 10
NUM_SIMULATION_SESSIONS = 5  # 5 sessions per user
TOTAL_SIMULATED_USERS = len(MOCK_USERS)

# Metrics tracking
METRICS_FILE = DATA_DIR / "metrics.json"
