import os
from mcp_settings import PATH_PARENT

if PATH_PARENT:
    print(f"Parnet path: {PATH_PARENT}")
else:
    cur = os.path.dirname(os.path.abspath(__file__))
    cwd = os.getcwd()

    print(cur)
    print(cwd)

    print(f"No parent path manually set. Automatically set to: {cur}")
