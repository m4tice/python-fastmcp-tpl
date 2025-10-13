"""
Utilities
Meant for implementing users own functions
@author: GUU8HC
"""

from datetime import datetime

def get_precise_time():
    """
    Get the precise time up to microsecond precision
    """
    return datetime.now()
