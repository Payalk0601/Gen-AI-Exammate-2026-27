"""Day 1 - KachraCheck interactive menu (loops until the user exits)."""
import random

TIPS = [
    "Rinse plastic bottles before binning so they stay recyclable.",
    "Never mix batteries with dry waste; they leak toxic metals.",
    "Flatten cardboard boxes to save space in the dry bin.",
    "Compost vegetable peels at home to cut wet waste by half.",
    "Wrap broken glass in newspaper before disposing of it.",
]

BIN_GUIDE = [
    ("Green", "Wet waste: food scraps, peels, tea leaves, flowers"),
    ("Blue", "Dry waste: paper, plastic, metal, glass, cardboard"),
    ("Red", "Hazardous and e-waste: batteries, bulbs, chargers"),
    ("Black", "Sanitary and reject: diapers, pads, masks"),
]

MENU = """
--- KachraCheck Menu ---
1. About the project
2. Bin colour guide
3. Tip of the moment
4. Exit
"""


def about():
    print("KachraCheck helps households segregate waste correctly by telling them")
    print("which bin an item belongs in, along with a short disposal tip.")


def bin_guide():
    for colour, meaning in BIN_GUIDE:
        print(f"[{colour}] {meaning}")


def tip():
    print("Tip:", random.choice(TIPS))


def main():
    actions = {"1": about, "2": bin_guide, "3": tip}
    while True:
        print(MENU)
        choice = input("Choose 1-4: ").strip()
        if choice == "4":
            print("Thank you for keeping it clean. Bye!")
            break
        action = actions.get(choice)
        if action:
            action()
        else:
            print("Invalid choice, please enter a number from 1 to 4.")


if __name__ == "__main__":
    main()
