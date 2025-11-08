import json, os

# character/jobs_library.py
class JobLibrary:
    jobs = {}
    _ini = False

    @staticmethod
    def init(json_file="jobs.json"):
        if JobLibrary._ini:
            return
        JobLibrary._ini = True
        base_dir = os.path.dirname(__file__)
        candidates = [
            os.path.join(base_dir, json_file),      # jobs.json
            os.path.join(base_dir, "jobs.json"),    # 後備
        ]
        for p in candidates:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    JobLibrary.jobs = json.load(f)
                return
        raise FileNotFoundError(f"Jobs json not found in: {candidates}")

    @staticmethod
    def get(name):
        return JobLibrary.jobs.get(name)
