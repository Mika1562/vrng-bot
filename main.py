import staypresent


if __name__ == "__main__":
    staypresent.run(
        "l6.py",
        restart_on_crash=True,
        max_restarts=5,
        restart_delay=2.0,
    )
