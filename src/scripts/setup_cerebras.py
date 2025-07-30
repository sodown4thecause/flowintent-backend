"""Script to set up Cerebras API key."""

import os
from pathlib import Path


def setup_cerebras_key():
    """Add Cerebras API key to .env file."""
    env_path = Path(".env")
    cerebras_key = "csk-xthxntm32x8kd5hdvfp4h3xk2vcnwtf2k2c9r8mtc8w2vvf2"
    
    # Read existing .env content
    env_content = ""
    if env_path.exists():
        with open(env_path, "r") as f:
            env_content = f.read()
    
    # Check if Cerebras key already exists
    if "CEREBRAS_API_KEY=" in env_content:
        # Update existing key
        lines = env_content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("CEREBRAS_API_KEY="):
                lines[i] = f"CEREBRAS_API_KEY={cerebras_key}"
                break
        env_content = "\n".join(lines)
    else:
        # Add new key
        if not env_content.endswith("\n") and env_content:
            env_content += "\n"
        env_content += f"CEREBRAS_API_KEY={cerebras_key}\n"
    
    # Write back to .env
    with open(env_path, "w") as f:
        f.write(env_content)
    
    print(f"✅ Cerebras API key added to {env_path}")
    print("🚀 You can now use Cerebras models in your agents!")


if __name__ == "__main__":
    setup_cerebras_key()