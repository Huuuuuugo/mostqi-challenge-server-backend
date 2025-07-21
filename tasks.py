import os
import json
from datetime import datetime


def delete_expired_data():
    from main import VALIDATION_DATA_DIR

    # check the expiration time on each validation data file
    for file in os.listdir(VALIDATION_DATA_DIR):
        file_path = os.path.join(VALIDATION_DATA_DIR, file)

        # read file data
        with open(file_path, "r", encoding="utf8") as f:
            data = json.loads(f.read())

        # delete file if expired
        if datetime.fromisoformat(data["expires"]) < datetime.now():
            os.remove(file_path)
