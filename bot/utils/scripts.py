import json


def get_claim_time(session_name: str) -> int:
    try:
        with open('nextClaims.json', 'r') as file:
            times = json.load(file)

        return times.get(session_name, {}).get('claimTime', 0)
    except FileNotFoundError:
        return 0


def set_claim_time(session_name: str, time: int) -> None:
    try:
        with open('nextClaims.json', 'r') as file:
            times = json.load(file)
    except FileNotFoundError:
        times = {}

    times[session_name] = {'claimTime': time}

    with open('nextClaims.json', 'w') as file:
        json.dump(times, file, indent=4, ensure_ascii=False)
