with open(r"c:\Data\DS\Python\Spaceclaim_verv\alestest\manufacturing_pipeline\analysis\classification.py") as f:
    lines = f.readlines()
    print(f"Total lines: {len(lines)}")
    print(f"Last 5 lines:")
    for i, line in enumerate(lines[-5:], start=len(lines)-4):
        print(f"{i}: {line.rstrip()}")
