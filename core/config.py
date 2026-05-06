import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Model configuration
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_MAX_TOKENS = 4096
GROQ_TEMPERATURE = 0.1        # Low temperature — consistent, factual output
GROQ_COVER_LETTER_TEMPERATURE = 0.4  # Higher — more natural prose for long-form writing

# Agent configuration
MAX_RETRIES = 3
MAX_SEARCH_RESULTS = 5
MATCH_SCORE_THRESHOLD = 0.6  # Below this = weak match warning

# Resume integrity rules
ALLOW_REWORDING = True        # Can reword existing content
ALLOW_REORDERING = True       # Can reorder bullet points
ALLOW_ADDING_SKILLS = False   # Cannot add skills not in original
ALLOW_ADDING_EXPERIENCE = False  # Cannot add experience not in original

# Output configuration
OUTPUT_DIR = "outputs"
SAMPLE_DATA_DIR = "sample_data"

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "agent.log"

def validate_env():
    required = {
        "GROQ_API_KEY": GROQ_API_KEY,
        "TAVILY_API_KEY": TAVILY_API_KEY,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {missing}\n"
            f"Check your .env file."
        )
    print("Environment validated. All required keys present.")

if __name__ == "__main__":
    validate_env()