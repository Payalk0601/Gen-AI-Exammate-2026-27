"""Day 1 - KachraCheck menu (while loop). Option 3 is one if/elif rule check from the domain:
is a premises a 'bulk waste generator' under the SWM Rules 2026 definition?
It qualifies if it meets at least ONE of: building area >= 20,000 sq m,
water use >= 40,000 litres/day, or >= 100 kg solid waste/day."""

MENU = """
=== KachraCheck ===
1. About KachraCheck
2. Sample questions
3. Rule check: am I a bulk waste generator?
0. Exit
"""

SAMPLES = [
    "Who must register on the centralised portal?",
    "By when must a facility operator file the annual return?",
    "What bin colours must urban local bodies use?",
    "How does the 2026 segregation rule differ from 2016?",
]


def ask_number(prompt):
    """Return a float, or None if the user typed something that is not a number."""
    try:
        return float(input(prompt))
    except ValueError:
        return None


def bulk_generator_check():
    area = ask_number("Building area (sq m): ")
    water = ask_number("Water use (litres/day): ")
    waste = ask_number("Solid waste generated (kg/day): ")
    if None in (area, water, waste):
        print("Please enter numbers only.")
        return
    if area >= 20000:
        print("Bulk waste generator: building area is 20,000 sq m or more.")
    elif water >= 40000:
        print("Bulk waste generator: water use is 40,000 litres/day or more.")
    elif waste >= 100:
        print("Bulk waste generator: waste is 100 kg/day or more.")
    else:
        print("Not a bulk waste generator. Ordinary generator duties (Rule 5) apply.")
    # Note: Rule 6 duties (portal registration, annual return by 30 June) apply to bulk generators.


while True:
    print(MENU)
    choice = input("Choose 0-3: ").strip()
    if choice == "1":
        print("KachraCheck turns the SWM Rules 2026 into a searchable, stakeholder-wise duty list.")
    elif choice == "2":
        for n, q in enumerate(SAMPLES, start=1):
            print(f"  {n}. {q}")
    elif choice == "3":
        bulk_generator_check()
    elif choice == "0":
        print("Goodbye!")
        break
    else:
        print("Invalid choice. Enter 0, 1, 2 or 3.")
