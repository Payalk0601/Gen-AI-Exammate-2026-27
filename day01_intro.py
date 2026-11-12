"""Day 1 - KachraCheck intro: prints the project card using variables and f-strings,
then asks for the user's name and question with input()."""

product = "KachraCheck"
tagline = "Know your duties under India's Solid Waste Management Rules, 2026"
user_group = "households, bulk generators, municipal officers, facility operators, students"
problem = "The 2026 Rules replace the 2016 Rules and spread duties over 15+ stakeholders."
data_source = "SWM Rules 2026, CPCB (swmp.cpcb.gov.in)"
version = "0.1 (Day 1)"

width = 66
print("=" * width)
print(f"{product:^{width}}")
print(f"{tagline:^{width}}")
print("=" * width)
print(f"Product     : command-line duty checker  [v{version}]")
print(f"For         : {user_group}")
print(f"Problem     : {problem}")
print(f"Data source : {data_source}")
print("-" * width)

name = input("Your name: ").strip().title() or "Friend"
question = input(f"{name}, which waste rule do you want to understand? ").strip()

print()
if question:
    print(f"Noted, {name}. Your question: \"{question}\"")
    print(f"({len(question.split())} words. Searching the rules dataset comes in later days.)")
else:
    print(f"No question entered, {name}. Try: 'Who must file an annual return?'")
