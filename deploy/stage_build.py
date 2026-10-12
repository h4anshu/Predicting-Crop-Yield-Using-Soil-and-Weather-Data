"""
Copy exactly the files the API needs into a clean folder, check it starts, and print what would ship.

    python deploy/stage_build.py [destination]        default: D:/agripredict-build (or $STAGE_DIR)

Then, from that folder:   docker build -t agripredict-api .      or      gcloud run deploy ... --source .

Why a manifest and not .dockerignore / .gcloudignore:
  * a local check of what a deploy contains, before pushing (the GitHub-triggered build uses the same files, all
    tracked in git: `serving/` holds the models and the small views of the dataset);
  * on this machine the checkout sits in OneDrive, where many files are cloud placeholders that Docker's build
    context refuses to read ("invalid file request"). Copying with shutil reads them, which also hydrates them;
  * the list below is the one place that says what is deployed.
Everything else (the master table, raw data, notebooks, the frontend, the retired state-level model) stays out of the image.
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = ["Dockerfile", "requirements.txt", "api.py", "forecasting.py", "district_forecast.py"]
MANIFEST = CODE + sorted(os.path.relpath(os.path.join(dp, f), ROOT).replace(os.sep, "/")
                         for dp, _, fs in os.walk(os.path.join(ROOT, "serving")) for f in fs)    # all of serving/


def stage(dest):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    total = 0
    for rel in MANIFEST:
        src = os.path.join(ROOT, rel)
        if not os.path.isfile(src):
            sys.exit("missing from the repository: %s (build it first, see ENGINEERING_NOTES section 16.3)" % rel)
        out = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copyfile(src, out)
        n = os.path.getsize(out)
        if n != os.path.getsize(src) or n == 0:
            sys.exit("copy of %s is empty or truncated" % rel)
        total += n
    print("staged %d files, %.1f MB, into %s" % (len(MANIFEST), total / 1e6, dest))
    return total


def smoke(dest):
    """The API must import from the staged folder alone, with nothing else from the repository on the path."""
    code = "import sys; sys.path.insert(0, '.'); import api; print('import ok:', len(api.STATES), 'states,', len(api.CROP_LIST), 'crops')"
    r = subprocess.run([sys.executable, "-I", "-c", code], cwd=dest, capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip()[-600:])
    if r.returncode:
        sys.exit("the staged API does not import: a file is missing from MANIFEST")


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("STAGE_DIR", "D:/agripredict-build")
    stage(dest)
    smoke(dest)
