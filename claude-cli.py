#!/usr/bin/env python3
"""
Simple Claude CLI wrapper for easy terminal access
Usage: claude "Your question here"
"""

import sys
import os
import anthropic

def main():
    # Check if API key is set
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY environment variable not set")
        print("Please ensure the API key is configured")
        sys.exit(1)

    # Get user input
    if len(sys.argv) < 2:
        print("Usage: claude 'Your question here'")
        print("Example: claude 'How do I implement binary search?'")
        sys.exit(1)

    user_input = ' '.join(sys.argv[1:])

    try:
        # Initialize Anthropic client
        client = anthropic.Anthropic(api_key=api_key)

        # Create message
        print(f"🤖 Claude: ", end="", flush=True)

        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": user_input}
            ]
        )

        # Print response
        print(message.content[0].text)

    except anthropic.APIError as e:
        print(f"❌ API Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
