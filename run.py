"""Start Audiobook Generator: python run.py

Works straight from this folder without installing the package.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from audiobook_generator.app import main  # noqa: E402

if __name__ == "__main__":
    main()
