import os
import shutil

project_dir = self.base_dir          # same as $PROJECT_DIR
repo_name = self.repo_path          # same as $REPO_NAME

src = os.path.join(project_dir, "dist", "output")
dst = os.path.join(repo_name, "output")

# Ensure destination folder exists (like mkdir -p)
os.makedirs(dst, exist_ok=True)

# Copy contents of output → repo/output (keep old files, overwrite if same)
for item in os.listdir(src):
    s = os.path.join(src, item)
    d = os.path.join(dst, item)

    if os.path.isdir(s):
        shutil.copytree(s, d, dirs_exist_ok=True)
    else:
        shutil.copy2(s, d)
