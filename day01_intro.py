"""Day 1 - KachraCheck intro: banner, greeting and a one-line pitch."""

PROJECT = "KachraCheck"
TAGLINE = "Know your waste. Pick the right bin."
BINS = {"Green": "Wet waste", "Blue": "Dry waste", "Red": "Hazardous / e-waste", "Black": "Sanitary / reject"}


def banner():
    line = "=" * 44
    print(line)
    print(f"{PROJECT:^44}")
    print(f"{TAGLINE:^44}")
    print(line)


def greet():
    name = input("Your name: ").strip().title() or "Friend"
    print(f"\nNamaste, {name}! Welcome to {PROJECT}.")
    return name


def show_bins():
    print("\nQuick bin guide:")
    for colour, kind in BINS.items():
        print(f"  {colour:<6}-> {kind}")


if __name__ == "__main__":
    banner()
    greet()
    show_bins()
