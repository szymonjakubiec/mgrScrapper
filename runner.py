import subprocess
import os

PARAMS_FILE = "user_params.txt"
DEFAULT_DB_TABLE_NAME = 'final_test'
DEFAULT_START_DATE = '2018-01-01'
DEFAULT_END_DATE = '2019-01-01'
DEFAULT_MIN_STARS = '100'



def read_params():
    params = {}
    if not os.path.exists(PARAMS_FILE):
        return params

    with open(PARAMS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Pomijanie pustych linii i komentarzy
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                # Oczyszczanie ze zbędnych spacji i cudzysłowów
                params[key.strip()] = value.strip().strip("'\"")
    return params


def main():
    params = read_params()

    cmd = ["python", "download_proj_repos.py"]

    if "DB_TABLE_NAME" in params:
        print("DB_TABLE_NAME = ", params["DB_TABLE_NAME"])
        cmd.extend(["--db_table_name", params["DB_TABLE_NAME"]])
    else:
        print(f"[WARNING]: No DB_TABLE_NAME, setting default value: {DEFAULT_DB_TABLE_NAME}")
        cmd.extend(["--db_table_name", DEFAULT_DB_TABLE_NAME])
    if "START_DATE" in params:
        print("START_DATE = ", params["START_DATE"])
        cmd.extend(["--start_date", params["START_DATE"]])
    else:
        print(f"[WARNING]: No START_DATE, setting default value: {DEFAULT_START_DATE}")
        cmd.extend(["--start_date", DEFAULT_START_DATE])
    if "END_DATE" in params:
        print("END_DATE = ", params["END_DATE"])
        cmd.extend(["--end_date", params["END_DATE"]])
    else:
        print(f"[WARNING]: No END_DATE, setting default value: {DEFAULT_END_DATE}")
        cmd.extend(["--end_date", DEFAULT_END_DATE])
    if "MIN_STARS" in params:
        print("MIN_STARS = ", params["MIN_STARS"])
        cmd.extend(["--min_stars", params["MIN_STARS"]])
    else:
        print(f"[WARNING]: No MIN_STARS, setting default value: {DEFAULT_MIN_STARS}")
        cmd.extend(["--min_stars", DEFAULT_MIN_STARS])

    # Uruchomienie skryptu main.py
    subprocess.run(cmd)


if __name__ == "__main__":
    main()